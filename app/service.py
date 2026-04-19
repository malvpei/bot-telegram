from __future__ import annotations

import logging
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from PIL import Image

from app.config import get_settings
from app.instagram import InstagramCollector, InstagramCollectorError, extract_usernames
from app.models import GenerationResult, VideoPlan, VideoRequest
from app.render import VideoRenderer
from app.selector import ImageSelector
from app.state import StateStore
from app.texts import ScriptGenerator


LOGGER = logging.getLogger(__name__)


def _cover_resize(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    scale = max(target_width / image.width, target_height / image.height)
    new_width = max(1, int(round(image.width * scale)))
    new_height = max(1, int(round(image.height * scale)))
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    offset_x = (resized.width - target_width) // 2
    offset_y = (resized.height - target_height) // 2
    return resized.crop(
        (offset_x, offset_y, offset_x + target_width, offset_y + target_height)
    )


class VideoCreationService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._ensure_directories()
        self.state = StateStore(
            self.settings.state_dir,
            history_max_per_bucket=self.settings.history_max_per_bucket,
        )
        self.collector = InstagramCollector(self.settings)
        self.selector = ImageSelector(self.settings, self.state)
        self.script_generator = ScriptGenerator(self.state)
        self.renderer = VideoRenderer(self.settings)
        # instaloader holds session/cookies that aren't safe to share across
        # concurrent threads, so we serialize the whole pipeline. Telegram
        # video generation is a single-tenant workflow anyway.
        self._job_lock = Lock()

    def preflight(self) -> list[str]:
        # Returns a list of human-readable warnings; empty list means OK.
        warnings: list[str] = []
        if not self.settings.fixed_image_path.exists():
            warnings.append(
                "Falta la imagen fija obligatoria: "
                f"{self.settings.fixed_image_path}"
            )
        if not self.settings.fonts_dir.exists():
            LOGGER.info(
                "No fonts directory at %s; will fall back to system fonts.",
                self.settings.fonts_dir,
            )
        return warnings

    def create_video(self, request: VideoRequest) -> GenerationResult:
        with self._job_lock:
            return self._create_video_locked(request)

    def _create_video_locked(self, request: VideoRequest) -> GenerationResult:
        usernames = extract_usernames(
            request.account_inputs, len(request.account_inputs) or 1
        )
        if not usernames:
            raise ValueError("No se detectaron cuentas de Instagram válidas.")

        plan, tried = self._pick_account_with_plan(usernames, request)
        LOGGER.info(
            "Picked @%s after trying %d account(s) of %d available",
            plan.chosen_account,
            len(tried),
            len(usernames),
        )

        # Reserve image IDs atomically before generating the script + render so
        # parallel processes cannot collide on the same images.
        job_id = self._build_job_id()
        already_used = self.state.reserve_media(plan.used_media_ids, job_id)
        if already_used:
            raise RuntimeError(
                "Otro job acaba de reservar estas imágenes. Reintenta en unos segundos: "
                + ", ".join(already_used)
            )

        try:
            script_package = self.script_generator.generate(
                request.video_type, request.language
            )

            # Bind text to slides by role so order changes never desync them.
            for slide in plan.slides:
                slide.text = script_package.slides_by_role[slide.role]

            job_dir = self.settings.outputs_dir / job_id
            video_path, script_path = self.renderer.render(plan, job_dir)
            self._normalize_slide_images(plan, job_dir)

            self.state.set_last_signature(
                request.video_type, request.language, script_package.signature
            )
            self.state.remember_signature(
                request.video_type,
                request.language,
                script_package.signature,
            )
            self.state.log_job(
                self.state.build_job_record(
                    job_id=job_id,
                    chosen_account=plan.chosen_account,
                    requested_accounts=usernames,
                    fallback_accounts=plan.fallback_accounts,
                    video_type=request.video_type,
                    language=request.language,
                    video_path=str(video_path),
                    script_path=str(script_path),
                )
            )
        except Exception:
            # If anything blew up after reservation, release the IDs so they
            # remain available for future runs.
            self.state.release_media(plan.used_media_ids)
            raise

        self._cleanup_old_outputs()

        return GenerationResult(
            video_path=video_path,
            script_path=script_path,
            preview_text=script_package.plain_text,
            chosen_account=plan.chosen_account,
            video_type=request.video_type,
            language=request.language,
            fallback_accounts=plan.fallback_accounts,
            slides=list(plan.slides),
        )

    def _pick_account_with_plan(
        self, usernames: list[str], request: VideoRequest
    ):
        # Pick one account at random. On collector failure OR not-enough-images
        # after selector filtering, try the next account. Stop at the first
        # success — we only need one viable plan.
        shuffled = list(usernames)
        random.shuffle(shuffled)
        max_attempts = min(self.settings.account_pick_attempts, len(shuffled))
        tried: list[str] = []
        errors: list[str] = []
        for username in shuffled[:max_attempts]:
            tried.append(username)
            try:
                candidates = self.collector.collect_one(username)
            except InstagramCollectorError as error:
                LOGGER.warning("@%s descartada (fetch): %s", username, error)
                errors.append(f"@{username}: {error}")
                continue
            try:
                plan = self.selector.create_plan(
                    {username: candidates}, request.video_type, request.language
                )
            except ValueError as error:
                LOGGER.warning("@%s descartada (plan): %s", username, error)
                errors.append(f"@{username}: {error}")
                continue
            return plan, tried
        raise InstagramCollectorError(
            "Ninguna de las cuentas probadas dio imágenes utilizables.\n"
            + "\n".join(errors)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_directories(self) -> None:
        for directory in (
            self.settings.data_dir,
            self.settings.downloads_dir,
            self.settings.outputs_dir,
            self.settings.state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _normalize_slide_images(self, plan: VideoPlan, job_dir: Path) -> None:
        # Telegram-bound images must share the vertical TikTok carousel format
        # (1080x1920 by default). We center-crop each slide to cover the canvas
        # so the aspect ratio is identical for every image we send.
        target_width = self.settings.width
        target_height = self.settings.height
        slides_dir = job_dir / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        for slide in plan.slides:
            source_path = slide.media.local_path
            if not source_path.exists():
                continue
            out_path = slides_dir / f"slide_{slide.index:02d}.jpg"
            try:
                with Image.open(source_path) as image:
                    normalized = _cover_resize(
                        image.convert("RGB"), target_width, target_height
                    )
                    normalized.save(out_path, format="JPEG", quality=92)
            except OSError as error:
                LOGGER.warning(
                    "No pude normalizar %s: %s", source_path, error
                )
                continue
            slide.media.local_path = out_path
            slide.media.width = target_width
            slide.media.height = target_height

    def _build_job_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{timestamp}-{uuid4().hex[:8]}"

    def _cleanup_old_outputs(self) -> None:
        retention_days = self.settings.output_retention_days
        if retention_days <= 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        outputs_dir = self.settings.outputs_dir
        if not outputs_dir.exists():
            return
        for child in outputs_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
