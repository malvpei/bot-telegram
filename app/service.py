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
from app.models import GenerationResult, VideoPlan, VideoRequest, VideoType
from app.render import VideoRenderer
from app.selector import ImageSelector
from app.state import StateStore
from app.texts import ScriptGenerator


LOGGER = logging.getLogger(__name__)


def _merge_preserving_order(existing: list[str], new_items: list[str]) -> list[str]:
    merged = list(existing)
    seen = set(existing)
    for item in new_items:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


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
            raise ValueError("No se detectaron cuentas de Instagram vÃ¡lidas.")

        job_id = self._build_job_id()
        plan, tried = self._pick_and_reserve_plan(usernames, request, job_id)
        LOGGER.info(
            "Picked @%s after trying %d account(s) of %d available",
            plan.chosen_account,
            len(tried),
            len(usernames),
        )

        try:
            script_package = self.script_generator.generate(
                request.video_type, request.language
            )

            # Bind text to slides by role so order changes never desync them.
            for slide in plan.slides:
                slide.text = script_package.slides_by_role[slide.role]

            job_dir = self.settings.outputs_dir / job_id
            video_path, script_path = self._render_outputs(plan, job_dir)

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
                    video_path=str(video_path) if video_path is not None else None,
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
            social_copy=script_package.social_copy,
            chosen_account=plan.chosen_account,
            video_type=request.video_type,
            language=request.language,
            fallback_accounts=plan.fallback_accounts,
            slides=list(plan.slides),
        )

    def _render_outputs(self, plan: VideoPlan, job_dir: Path) -> tuple[Path | None, Path]:
        if plan.video_type == VideoType.TYPE_3:
            LOGGER.info("Rendering tipo3 still images for job %s", job_dir.name)
            script_path = self.renderer.write_script(plan, job_dir)
            self._normalize_slide_images(plan, job_dir)
            return None, script_path

        LOGGER.info(
            "Rendering video type %s for job %s", plan.video_type.value, job_dir.name
        )
        video_path, script_path = self.renderer.render(plan, job_dir)
        self._normalize_slide_images(plan, job_dir)
        return video_path, script_path

    def _pick_and_reserve_plan(
        self,
        usernames: list[str],
        request: VideoRequest,
        job_id: str,
    ) -> tuple[VideoPlan, list[str]]:
        conflicts: list[str] = []
        all_tried: list[str] = []
        for attempt in range(1, 4):
            plan, tried = self._pick_account_with_plan(usernames, request)
            all_tried = _merge_preserving_order(all_tried, tried)
            already_used = self.state.reserve_media(plan.used_media_ids, job_id)
            if not already_used:
                return plan, all_tried
            conflicts.extend(already_used)
            LOGGER.warning(
                "Plan reservation conflict on attempt %d for @%s: %s",
                attempt,
                plan.chosen_account,
                ", ".join(already_used),
            )
        raise RuntimeError(
            "Otro job acaba de reservar estas imagenes. He reintentado con otros "
            "planes pero siguen chocando: "
            + ", ".join(dict.fromkeys(conflicts))
        )

    def _pick_account_with_plan(
        self, usernames: list[str], request: VideoRequest
    ):
        # Try accounts progressively. Recently chosen accounts go last so a
        # big account file rotates instead of picking the same creator again.
        ordered = self._ordered_accounts_for_pick(usernames, request.video_type)
        max_attempts = self._max_account_attempts(len(ordered))
        tried: list[str] = []
        errors: list[str] = []
        catalog: dict[str, list] = {}
        last_plan_error: str | None = None
        for username in ordered[:max_attempts]:
            tried.append(username)
            try:
                catalog[username] = self.collector.collect_one(username)
            except InstagramCollectorError as error:
                LOGGER.warning("@%s descartada (fetch): %s", username, error)
                errors.append(f"@{username}: {error}")
                continue

            try:
                plan = self.selector.create_plan(
                    catalog, request.video_type, request.language
                )
                return plan, tried
            except ValueError as error:
                last_plan_error = str(error)
                LOGGER.info(
                    "No viable plan after %d/%d tested account(s): %s",
                    len(tried),
                    max_attempts,
                    error,
                )
                continue
        if last_plan_error:
            errors.append(last_plan_error)
        raise InstagramCollectorError(
            f"Ninguna de las {len(tried)} cuentas probadas dio imagenes utilizables "
            f"(de {len(usernames)} disponibles).\n"
            + "\n".join(errors)
        )

    def _ordered_accounts_for_pick(
        self,
        usernames: list[str],
        video_type: VideoType,
    ) -> list[str]:
        shuffled = list(usernames)
        random.shuffle(shuffled)
        recent = set(
            self.state.recent_chosen_accounts(
                limit=len(shuffled),
                video_type=video_type,
            )
        )
        fresh = [username for username in shuffled if username.lower() not in recent]
        repeated = [username for username in shuffled if username.lower() in recent]
        if fresh:
            LOGGER.info(
                "Account picker: %d fresh / %d recent accounts available",
                len(fresh),
                len(repeated),
            )
            return fresh + repeated
        return shuffled

    def _max_account_attempts(self, available_count: int) -> int:
        configured = self.settings.account_pick_attempts
        if configured > 0 and configured < available_count:
            LOGGER.info(
                "ACCOUNT_PICK_ATTEMPTS=%d is a soft target; picker can continue "
                "through %d accounts to avoid false exhaustion.",
                configured,
                available_count,
            )
        return available_count

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
                if plan.video_type == VideoType.TYPE_3:
                    normalized = self.renderer.render_slide_still(
                        slide, plan.video_type
                    ).convert("RGB")
                else:
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
