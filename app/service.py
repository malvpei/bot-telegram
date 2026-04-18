from __future__ import annotations

import logging
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.config import get_settings
from app.instagram import InstagramCollector, InstagramCollectorError, extract_usernames
from app.models import GenerationResult, VideoRequest
from app.render import VideoRenderer
from app.selector import ImageSelector
from app.state import StateStore
from app.texts import ScriptGenerator


LOGGER = logging.getLogger(__name__)


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

        catalog, tried = self._collect_random_account(usernames)
        plan = self.selector.create_plan(catalog, request.video_type, request.language)
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
        )

    def _collect_random_account(
        self, usernames: list[str]
    ) -> tuple[dict[str, list], list[str]]:
        # Pick one account at random. On rate limit / missing / private,
        # try the next one. Stop at the first success — we only need one.
        shuffled = list(usernames)
        random.shuffle(shuffled)
        max_attempts = min(self.settings.account_pick_attempts, len(shuffled))
        tried: list[str] = []
        errors: list[str] = []
        for username in shuffled[:max_attempts]:
            tried.append(username)
            try:
                candidates = self.collector.collect_one(username)
                return {username: candidates}, tried
            except InstagramCollectorError as error:
                LOGGER.warning("@%s descartada: %s", username, error)
                errors.append(f"@{username}: {error}")
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
