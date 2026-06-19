from __future__ import annotations

import logging
import os
import random
import shutil
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from PIL import Image

from app.config import DEFAULT_ACCOUNT_PICK_ATTEMPTS, get_settings
from app.instagram import InstagramCollector, InstagramCollectorError, extract_usernames
from app.media_pool import MediaPoolService
from app.models import (
    GenerationResult,
    Language,
    MediaCandidate,
    SocialCopy,
    TemplateVideoResult,
    TYPE_4_ROLES,
    VideoPlan,
    VideoRequest,
    VideoType,
    SlidePlan,
    SlideRole,
)
from app.r2_storage import R2StorageClient
from app.render import VideoRenderer
from app.selector import ImageSelector, TYPE_2_TIP3_FIXED_IMAGE_NAME
from app.state import StateStore
from app.story_images import StoryCarouselImageGenerator
from app.texts import ScriptGenerator


LOGGER = logging.getLogger(__name__)
VIDEO_TEMPLATE_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
TEMPLATE_VIDEO_SOCIAL_COPIES: dict[Language, tuple[SocialCopy, ...]] = {
    Language.ES: (
        SocialCopy(
            title="Herramientas para empezar dropshipping sin complicarte",
            description=(
                "Si quieres lanzar una tienda online, no necesitas mil apps: necesitas "
                "un stack claro. Investiga productos, monta la tienda, prepara anuncios, "
                "cobra bien y edita contenido que se pueda publicar rapido."
            ),
            hashtags=[
                "#dropshipping",
                "#ecommerce",
                "#shopify",
                "#herramientas",
                "#dropradar",
                "#metaads",
                "#tiktokmarketing",
                "#capcut",
            ],
        ),
        SocialCopy(
            title="El stack basico para lanzar una tienda online",
            description=(
                "Estas herramientas cubren lo esencial: encontrar productos con demanda, "
                "crear la tienda, aceptar pagos, grabar contenido y testear anuncios. "
                "Menos ruido, mas ejecucion."
            ),
            hashtags=[
                "#tiendaonline",
                "#dropshippingespana",
                "#shopify",
                "#stripe",
                "#chatgpt",
                "#ecommerce",
                "#negocioonline",
            ],
        ),
        SocialCopy(
            title="Tu flujo de trabajo para vender online",
            description=(
                "Empieza por validar producto, escribe angulos de venta, prepara creativos "
                "cortos y mide resultados. Con las herramientas correctas, el proceso se "
                "vuelve mucho mas facil de repetir."
            ),
            hashtags=[
                "#dropshipping",
                "#marketingdigital",
                "#metaads",
                "#tiktokads",
                "#capcut",
                "#emprenderonline",
                "#ecommerce",
            ],
        ),
        SocialCopy(
            title="Herramientas que aceleran tu primer lanzamiento",
            description=(
                "No se trata de usar mas plataformas, sino de usar las correctas para cada "
                "parte del lanzamiento: producto, tienda, pagos, creatividad y trafico. "
                "Asi evitas improvisar cuando toca publicar."
            ),
            hashtags=[
                "#dropshippingtips",
                "#shopifyespana",
                "#dropradar",
                "#stripe",
                "#chatgpt",
                "#negociosonline",
                "#ventas",
            ],
        ),
        SocialCopy(
            title="La base para crear contenido y vender con dropshipping",
            description=(
                "Una buena idea necesita sistema: analiza productos, estructura la oferta, "
                "edita videos verticales y prueba anuncios con datos. Este stack te da una "
                "base sencilla para empezar."
            ),
            hashtags=[
                "#dropshipping",
                "#contenidovertical",
                "#capcut",
                "#tiktokmarketing",
                "#metaads",
                "#shopify",
                "#ecommercebusiness",
            ],
        ),
    ),
    Language.EN: (
        SocialCopy(
            title="Tools to start dropshipping without overcomplicating it",
            description=(
                "If you want to launch an online store, you do not need dozens of apps. "
                "You need a clear stack: research products, build the store, prepare ads, "
                "set up payments and edit content you can publish fast."
            ),
            hashtags=[
                "#dropshipping",
                "#ecommerce",
                "#shopify",
                "#businesstools",
                "#dropradar",
                "#metaads",
                "#tiktokmarketing",
                "#capcut",
            ],
        ),
        SocialCopy(
            title="The basic stack to launch your online store",
            description=(
                "These tools cover the essentials: finding products with demand, creating "
                "the store, accepting payments, producing content and testing ads. Less "
                "noise, more execution."
            ),
            hashtags=[
                "#onlinestore",
                "#dropshippingtips",
                "#shopify",
                "#stripe",
                "#chatgpt",
                "#ecommerce",
                "#onlinebusiness",
            ],
        ),
        SocialCopy(
            title="Your workflow for selling online",
            description=(
                "Start by validating the product, write strong selling angles, prepare "
                "short creatives and measure the results. With the right tools, the "
                "process becomes much easier to repeat."
            ),
            hashtags=[
                "#dropshipping",
                "#digitalmarketing",
                "#metaads",
                "#tiktokads",
                "#capcut",
                "#onlinebusiness",
                "#ecommerce",
            ],
        ),
        SocialCopy(
            title="Tools that speed up your first launch",
            description=(
                "It is not about using more platforms. It is about using the right ones "
                "for each step: product research, store, payments, creative production "
                "and traffic. That way you are not improvising when it is time to post."
            ),
            hashtags=[
                "#dropshippingtips",
                "#shopifystore",
                "#dropradar",
                "#stripe",
                "#chatgpt",
                "#onlinebusiness",
                "#sales",
            ],
        ),
        SocialCopy(
            title="The base for creating content and selling with dropshipping",
            description=(
                "A good idea needs a system: analyze products, structure the offer, edit "
                "vertical videos and test ads with data. This stack gives you a simple "
                "foundation to start."
            ),
            hashtags=[
                "#dropshipping",
                "#shortformcontent",
                "#capcut",
                "#tiktokmarketing",
                "#metaads",
                "#shopify",
                "#ecommercebusiness",
            ],
        ),
    ),
}


def _merge_preserving_order(existing: list[str], new_items: list[str]) -> list[str]:
    merged = list(existing)
    seen = set(existing)
    for item in new_items:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _prepare_template_video_social_copy(social_copy: SocialCopy) -> SocialCopy:
    return SocialCopy(
        title="",
        description=social_copy.description,
        hashtags=list(social_copy.hashtags[:5]),
    )


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
        self.pool = MediaPoolService(
            self.settings,
            self.state,
            self.collector,
            self.selector,
        )
        self.script_generator = ScriptGenerator(self.state)
        self.renderer = VideoRenderer(self.settings)
        self.r2_storage = R2StorageClient(self.settings)
        self.story_image_generator = StoryCarouselImageGenerator(self.settings)
        # instaloader holds session/cookies that aren't safe to share across
        # concurrent threads, so we serialize the whole pipeline. Telegram
        # video generation is a single-tenant workflow anyway.
        self._job_lock = Lock()

    def preflight(self) -> list[str]:
        # Returns a list of human-readable warnings; empty list means OK.
        warnings: list[str] = []
        marker = self.state.ensure_persistence_marker()
        memory = self.state.memory_snapshot(recent_limit=8)
        LOGGER.info(
            "State memory at %s: %d used media keys, %d jobs, %d unique chosen accounts, marker=%s",
            memory["state_dir"],
            memory["used_media_count"],
            memory["jobs_count"],
            memory["unique_chosen_accounts"],
            marker.get("install_id", "-"),
        )
        LOGGER.info(
            "Instagram collection settings: max_posts_per_account=%d, account_cache_ttl_hours=%d",
            self.settings.max_posts_per_account,
            self.settings.account_cache_ttl_hours,
        )
        if marker.get("created_now"):
            warnings.append(
                "Se ha creado un marker nuevo de memoria persistente en "
                f"{self.settings.state_dir}. Si este aviso aparece despues de cada "
                "redeploy, Coolify no esta preservando /app/data."
            )
        persistence = self.persistence_status()
        if persistence["warning"]:
            warnings.append(str(persistence["warning"]))
        if not self.settings.fixed_image_path.exists():
            warnings.append(
                "Falta la imagen fija obligatoria: "
                f"{self.settings.fixed_image_path}"
            )
        type_2_tip3_fixed_path = (
            self.settings.fixed_assets_dir / TYPE_2_TIP3_FIXED_IMAGE_NAME
        )
        if not type_2_tip3_fixed_path.exists():
            warnings.append(
                "Falta la imagen fija obligatoria para el consejo 3 del tipo 2: "
                f"{type_2_tip3_fixed_path}"
            )
        if not self.settings.fonts_dir.exists():
            LOGGER.info(
                "No fonts directory at %s; will fall back to system fonts.",
                self.settings.fonts_dir,
            )
        if self.settings.image_provider == "fal" and not self.settings.fal_key:
            warnings.append(
                "Falta FAL_KEY; el carrusel IA tipo 4 no podra generar imagenes con fal.ai."
            )
        if self.settings.image_provider == "openai" and not self.settings.openai_api_key:
            warnings.append(
                "Falta OPENAI_API_KEY; el carrusel IA tipo 4 no podra generar imagenes con OpenAI."
            )
        return warnings

    def create_video(self, request: VideoRequest) -> GenerationResult:
        with self._job_lock:
            return self._create_video_locked(request)

    def create_extra_image(self, request: VideoRequest) -> MediaCandidate:
        with self._job_lock:
            return self._create_extra_image_locked(request)

    def exclude_account(self, account: str) -> int:
        with self._job_lock:
            return self.pool.exclude_account(account)

    def sync_accounts(self, account_inputs: list[str]) -> dict[str, object]:
        with self._job_lock:
            usernames = extract_usernames(account_inputs, len(account_inputs) or 1)
            if not usernames:
                raise ValueError("No se detectaron cuentas de Instagram válidas.")

            downloaded: dict[str, int] = {}
            errors: dict[str, str] = {}
            for username in usernames:
                try:
                    downloaded[username] = len(self.collector.collect_one(username))
                except Exception as error:  # noqa: BLE001
                    LOGGER.warning("@%s no se pudo sincronizar: %s", username, error)
                    errors[username] = str(error)
            return {
                "requested": len(usernames),
                "downloaded": downloaded,
                "errors": errors,
            }

    def refill_pool(self, account_inputs: list[str]) -> dict[str, object]:
        with self._job_lock:
            usernames = extract_usernames(account_inputs, len(account_inputs) or 1)
            usernames = self._without_excluded_accounts(usernames)
            if not usernames:
                raise ValueError("No se detectaron cuentas de Instagram válidas.")
            return self.pool.refill(usernames)

    def pool_status(self) -> dict[str, object]:
        return self.pool.stock_counts()

    def account_audit(self, account_inputs: list[str]) -> dict[str, object]:
        usernames = extract_usernames(account_inputs, len(account_inputs) or 1)
        if not usernames:
            raise ValueError("No se detectaron cuentas de Instagram validas.")
        return self.pool.account_audit(usernames)

    def create_template_video(
        self,
        source: str | None = None,
        language: Language = Language.ES,
    ) -> TemplateVideoResult:
        with self._job_lock:
            template_language = self._template_video_language(language)
            job_id = self._build_job_id()
            job_dir = self.settings.outputs_dir / job_id
            if getattr(self, "r2_storage", None) is not None and self.r2_storage.is_configured:
                source_video, queue_restarted = self._download_template_video_from_r2(
                    source,
                    job_dir,
                )
            else:
                source_dir = self._resolve_template_video_dir(source)
                source_video, queue_restarted = self._pick_template_video(source_dir)
            output_path = self.renderer.render_template_video(
                source_video,
                job_dir,
                template_language,
            )
            self._cleanup_old_outputs()
            return TemplateVideoResult(
                video_path=output_path,
                social_copy=_prepare_template_video_social_copy(
                    random.choice(TEMPLATE_VIDEO_SOCIAL_COPIES[template_language])
                ),
                queue_restarted=queue_restarted,
            )

    def persistence_status(self) -> dict[str, object]:
        data_dir = self.settings.data_dir
        state_dir = self.settings.state_dir
        in_container = _running_in_container()
        expected_data_dir = Path("/app/data")
        is_expected_path = data_dir == expected_data_dir
        is_mount = False
        mount_check = "not_checked"
        warning = ""

        if in_container:
            try:
                is_mount = data_dir.exists() and data_dir.is_mount()
                mount_check = "ok"
            except OSError as error:
                mount_check = f"error: {error}"

            if not is_expected_path:
                warning = (
                    f"DATA_DIR={data_dir} pero en Coolify debe ser /app/data "
                    "para coincidir con el Persistent Storage."
                )
            elif not is_mount:
                warning = (
                    "No detecto /app/data como mount del contenedor. En Coolify "
                    "crea un Persistent Storage en la app con Mount path /app/data."
                )

        return {
            "data_dir": str(data_dir),
            "state_dir": str(state_dir),
            "in_container": in_container,
            "expected_data_dir": str(expected_data_dir),
            "is_expected_path": is_expected_path,
            "is_mount": is_mount,
            "mount_check": mount_check,
            "warning": warning,
        }

    def _create_video_locked(self, request: VideoRequest) -> GenerationResult:
        if request.video_type == VideoType.TYPE_4:
            return self._create_story_carousel_locked(request)

        usernames = extract_usernames(
            request.account_inputs, len(request.account_inputs) or 1
        )
        usernames = self._without_excluded_accounts(usernames)
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
        self._assert_single_source_account(plan)

        try:
            script_package = self.script_generator.generate(
                request.video_type,
                request.language,
                gender=request.gender,
                lowercase_text=request.lowercase_text,
            )

            # Bind text to slides by role so order changes never desync them.
            for slide in plan.slides:
                slide.text = script_package.slides_by_role[slide.role]

            job_dir = self.settings.outputs_dir / job_id
            video_path, script_path = self._render_outputs(
                plan,
                job_dir,
                embed_slide_text=not request.separate_slide_text,
            )

            self.state.set_last_signature(
                request.video_type, request.language, script_package.signature
            )
            if script_package.choice_key:
                self.state.set_last_text_choice(
                    request.video_type,
                    request.language,
                    script_package.choice_key,
                )
            if script_package.social_choice_key:
                self.state.set_last_social_choice(
                    request.video_type,
                    request.language,
                    script_package.social_choice_key,
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
                    gender=request.gender.value,
                )
            )
            if plan.type_3_background_id and plan.type_3_background_candidates:
                self.state.remember_type_3_background_choice(
                    plan.type_3_background_id,
                    plan.type_3_background_candidates,
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
            pool_remaining=(
                int(
                    self.pool.stock_counts(usernames)["by_type"].get(
                        request.video_type.value,
                        0,
                    )
                )
                if hasattr(self, "pool")
                else 0
            ),
            pool_low_stock=(
                self.pool.is_low_stock(request.video_type, usernames)
                if hasattr(self, "pool")
                else False
            ),
            separate_slide_text=request.separate_slide_text,
        )

    def _create_story_carousel_locked(self, request: VideoRequest) -> GenerationResult:
        job_id = self._build_job_id()
        job_dir = self.settings.outputs_dir / job_id
        reference_image_path = request.reference_image_path
        reference_source = "foto de referencia"
        if reference_image_path is None:
            reference_image_path, reference_source, queue_restarted = (
                self._download_story_reference_from_r2(job_dir)
            )
            if queue_restarted:
                LOGGER.info("R2 story reference image queue restarted for type 4")
        if not reference_image_path.exists():
            raise FileNotFoundError(
                f"No encuentro la foto de referencia: {reference_image_path}"
            )

        script_package = self.script_generator.generate(
            VideoType.TYPE_4,
            Language.ES,
            gender=request.gender,
            lowercase_text=False,
        )
        generated_media = self.story_image_generator.generate_slides(
            reference_image_path,
            job_dir,
        )
        if len(generated_media) != len(TYPE_4_ROLES) - 1:
            raise RuntimeError(
                "El generador IA no devolvio las 6 imagenes esperadas para el tipo 4."
            )

        reference_media = self._copy_story_reference_image(reference_image_path, job_dir)
        media_by_role = {
            role: media
            for role, media in zip(TYPE_4_ROLES[:-1], generated_media, strict=True)
        }
        media_by_role[SlideRole.STORY_ORIGINAL_REFERENCE] = reference_media

        slides = [
            SlidePlan(
                index=index,
                role=role,
                text=script_package.slides_by_role[role],
                media=media_by_role[role],
                fixed_asset=role == SlideRole.STORY_ORIGINAL_REFERENCE,
            )
            for index, role in enumerate(TYPE_4_ROLES, start=1)
        ]
        plan = VideoPlan(
            chosen_account=reference_source,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            slides=slides,
            used_media_ids=[],
            fallback_accounts=[],
        )
        video_path, script_path = self._render_outputs(plan, job_dir)

        self.state.log_job(
            self.state.build_job_record(
                job_id=job_id,
                chosen_account=plan.chosen_account,
                requested_accounts=[reference_source],
                fallback_accounts=[],
                video_type=VideoType.TYPE_4,
                language=Language.ES,
                video_path=str(video_path) if video_path is not None else None,
                script_path=str(script_path),
                gender=request.gender.value,
            )
        )
        self._cleanup_old_outputs()
        return GenerationResult(
            video_path=video_path,
            script_path=script_path,
            preview_text=script_package.plain_text,
            social_copy=script_package.social_copy,
            chosen_account=plan.chosen_account,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            fallback_accounts=[],
            slides=list(plan.slides),
            pool_remaining=0,
            pool_low_stock=False,
            separate_slide_text=False,
        )

    def _download_story_reference_from_r2(
        self,
        job_dir: Path,
    ) -> tuple[Path, str, bool]:
        if getattr(self, "r2_storage", None) is None or not self.r2_storage.is_configured:
            raise ValueError(
                "El tipo 4 necesita una imagen en R2. Configura R2 y sube imagenes "
                f"al prefijo {self.settings.r2_image_prefix!r}."
            )
        prefix = self.settings.r2_image_prefix
        images = self.r2_storage.list_images(prefix)
        effective_prefix = prefix
        if not images and prefix:
            LOGGER.warning(
                "R2 story reference prefix %r has no compatible images; trying whole bucket",
                prefix,
            )
            images = self.r2_storage.list_images("")
            effective_prefix = ""
        if not images:
            visible_keys = self._list_r2_keys_for_error(prefix)
            if not visible_keys and prefix:
                visible_keys = self._list_r2_keys_for_error("")
            if visible_keys:
                visible_line = " Objetos vistos: " + ", ".join(visible_keys[:8])
            elif prefix:
                visible_line = (
                    " No vi ningun objeto bajo ese prefijo ni imagenes compatibles "
                    "en el bucket."
                )
            else:
                visible_line = " No vi ningun objeto en el bucket."
            raise ValueError(
                "No encontre imagenes compatibles en R2"
                + (f" bajo el prefijo {prefix!r}." if prefix else ".")
                + visible_line
            )
        ordered_images = sorted(images, key=lambda item: item.key)
        selected_key, queue_restarted = self.state.get_next_story_reference_image_id(
            f"r2:{effective_prefix}" if effective_prefix else "r2:*",
            [image.key for image in ordered_images],
        )
        selected = next(
            (image for image in ordered_images if image.key == selected_key),
            ordered_images[0],
        )
        suffix = Path(selected.key).suffix.lower() or ".jpg"
        local_input = job_dir / "story_reference_input" / f"source{suffix}"
        return (
            self.r2_storage.download(selected.key, local_input),
            f"r2:{selected.key}",
            queue_restarted,
        )

    def _list_r2_keys_for_error(self, prefix: str) -> list[str]:
        try:
            client = self.r2_storage._boto_client()
            paginator = client.get_paginator("list_objects_v2")
            keys: list[str] = []
            for page in paginator.paginate(
                Bucket=self.settings.r2_bucket,
                Prefix=prefix.strip().lstrip("/"),
            ):
                for item in page.get("Contents", []):
                    key = str(item.get("Key") or "")
                    if key and not key.endswith("/"):
                        keys.append(key)
                    if len(keys) >= 8:
                        return keys
            return keys
        except Exception as error:  # noqa: BLE001
            return [f"no pude listar objetos para diagnostico: {error}"]

    def _create_extra_image_locked(self, request: VideoRequest) -> MediaCandidate:
        usernames = extract_usernames(
            request.account_inputs, len(request.account_inputs) or 1
        )
        usernames = self._without_excluded_accounts(usernames)
        if not usernames:
            raise ValueError("No se detectó la cuenta de Instagram para repetir.")
        account = usernames[0]

        conflicts: list[str] = []
        media: MediaCandidate | None = None
        media_ids: list[str] = []
        job_id = self._build_job_id()
        for attempt in range(1, 4):
            media = self._pick_extra_image_candidate(account, request.video_type)
            media_ids = self.selector.reservation_keys_for([media])
            already_used = self.state.reserve_media(media_ids, job_id)
            if not already_used:
                break
            conflicts.extend(already_used)
            LOGGER.warning(
                "Extra image reservation conflict on attempt %d for @%s: %s",
                attempt,
                account,
                ", ".join(already_used),
            )
            media = None
        if media is None:
            raise RuntimeError(
                "Otro job acaba de reservar la imagen extra. Reintenté pero "
                "sigue chocando: "
                + ", ".join(dict.fromkeys(conflicts))
            )

        try:
            job_dir = self.settings.outputs_dir / job_id
            normalized = self._normalize_extra_image(media, job_dir)
            self.state.log_job(
                self.state.build_job_record(
                    job_id=job_id,
                    chosen_account=account,
                    requested_accounts=[account],
                    fallback_accounts=[],
                    video_type=request.video_type,
                    language=request.language,
                    video_path=None,
                    script_path=str(normalized.local_path),
                    gender=request.gender.value,
                )
            )
        except Exception:
            self.state.release_media(media_ids)
            raise

        self._cleanup_old_outputs()
        return normalized

    def _pick_extra_image_candidate(
        self,
        account: str,
        video_type: VideoType,
    ) -> MediaCandidate:
        if hasattr(self, "pool"):
            try:
                return self.pool.pick_extra_image(account, video_type)
            except ValueError as pool_error:
                LOGGER.info(
                    "No valid extra image for @%s in pool, checking account directly: %s",
                    account,
                    pool_error,
                )

        try:
            candidates = self.collector.collect_one(account, use_cache=False)
        except TypeError:
            candidates = self.collector.collect_one(account)
        return self.selector.pick_extra_image(
            candidates,
            video_type,
            allow_plan_compatible_fallback=True,
        )

    def _render_outputs(
        self,
        plan: VideoPlan,
        job_dir: Path,
        *,
        embed_slide_text: bool = True,
    ) -> tuple[Path | None, Path]:
        LOGGER.info(
            "Preparing slide images for type %s job %s",
            plan.video_type.value,
            job_dir.name,
        )
        script_path = self.renderer.write_script(plan, job_dir)
        self._normalize_slide_images(
            plan,
            job_dir,
            embed_slide_text=embed_slide_text,
        )
        return None, script_path

    def _assert_single_source_account(self, plan: VideoPlan) -> None:
        source_accounts = {
            slide.media.source_account
            for slide in plan.slides
            if not slide.fixed_asset
            and slide.media.source_account != "fixed"
        }
        if len(source_accounts) > 1:
            raise RuntimeError(
                "El plan mezcla fotos de varias cuentas: "
                + ", ".join(f"@{account}" for account in sorted(source_accounts))
            )

    def _pick_and_reserve_plan(
        self,
        usernames: list[str],
        request: VideoRequest,
        job_id: str,
    ) -> tuple[VideoPlan, list[str]]:
        conflicts: list[str] = []
        all_tried: list[str] = []
        for attempt in range(1, 4):
            collected_for_pool: dict[str, list[MediaCandidate]] = {}
            plan, tried, plan_source = self._pick_plan_prefer_pool(
                usernames,
                request,
                collected_for_pool=collected_for_pool,
            )
            all_tried = _merge_preserving_order(all_tried, tried)
            already_used = self.state.reserve_media(plan.used_media_ids, job_id)
            if not already_used:
                if hasattr(self, "pool"):
                    self.pool.note_account_used(plan.chosen_account, request.video_type)
                if plan_source == "dynamic":
                    self._warm_pool_from_dynamic_candidates(collected_for_pool, plan)
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

    def _pick_plan_prefer_pool(
        self,
        usernames: list[str],
        request: VideoRequest,
        *,
        collected_for_pool: dict[str, list[MediaCandidate]],
    ) -> tuple[VideoPlan, list[str], str]:
        if hasattr(self, "pool"):
            try:
                plan, tried = self.pool.select_plan(
                    usernames,
                    request.video_type,
                    request.language,
                    skip_accounts=request.skip_accounts,
                )
                return plan, tried, "pool"
            except ValueError as error:
                LOGGER.info(
                    "Pool has no viable plan for type %s; falling back to dynamic fetch: %s",
                    request.video_type.value,
                    error,
                )

        plan, tried = self._pick_account_with_plan(
            usernames,
            request,
            collected_by_account=collected_for_pool,
        )
        return plan, tried, "dynamic"

    def _pick_account_with_plan(
        self,
        usernames: list[str],
        request: VideoRequest,
        *,
        collected_by_account: dict[str, list[MediaCandidate]] | None = None,
    ) -> tuple[VideoPlan, list[str]]:
        # Shuffle all accounts and try them one by one. The account choice is
        # intentionally pure random; if a picked account cannot produce the
        # requested video, the next random account gets a chance.
        skipped = {
            account.strip().lstrip("@").lower()
            for account in request.skip_accounts
            if account.strip().lstrip("@")
        }
        ordered = [
            username
            for username in self._ordered_accounts_for_pick(
                usernames, request.video_type
            )
            if username.lower() not in skipped
        ]
        if not ordered:
            raise InstagramCollectorError(
                "No quedan cuentas disponibles despues de aplicar los descartes."
            )
        max_attempts = self._max_account_attempts(len(ordered))
        tried: list[str] = []
        errors: list[str] = []
        last_plan_error: str | None = None
        for username in ordered[:max_attempts]:
            tried.append(username)
            try:
                candidates = self.collector.collect_one(username)
            except InstagramCollectorError as error:
                LOGGER.warning("@%s descartada (fetch): %s", username, error)
                errors.append(f"@{username}: {error}")
                continue
            if collected_by_account is not None:
                collected_by_account[username] = candidates

            try:
                plan = self.selector.create_plan(
                    {username: candidates}, request.video_type, request.language
                )
                LOGGER.info(
                    "Selected random viable account @%s after %d attempt(s)",
                    plan.chosen_account,
                    len(tried),
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

    def _warm_pool_from_dynamic_candidates(
        self,
        collected_by_account: dict[str, list[MediaCandidate]],
        plan: VideoPlan,
    ) -> None:
        if not hasattr(self, "pool") or not hasattr(self.pool, "add_candidates"):
            return
        candidates = collected_by_account.get(plan.chosen_account, [])
        if not candidates:
            return
        try:
            added = self.pool.add_candidates(candidates)
        except Exception as error:  # noqa: BLE001
            LOGGER.info(
                "No pude calentar el pool con @%s tras fallback dinamico: %s",
                plan.chosen_account,
                error,
            )
            return
        if added:
            LOGGER.info(
                "Dynamic fallback warmed pool with %d extra item(s) from @%s",
                added,
                plan.chosen_account,
            )

    def _ordered_accounts_for_pick(
        self,
        usernames: list[str],
        video_type: VideoType,
    ) -> list[str]:
        shuffled = list(usernames)
        random.shuffle(shuffled)
        sample = ", ".join(f"@{username}" for username in shuffled[:12])
        LOGGER.info(
            "Account picker: pure random order over %d account(s); first candidates: %s",
            len(shuffled),
            sample,
        )
        return shuffled

    def _without_excluded_accounts(self, usernames: list[str]) -> list[str]:
        excluded = self.state.read_excluded_accounts()
        return [username for username in usernames if username.lower() not in excluded]

    def _max_account_attempts(self, available_count: int) -> int:
        configured = self.settings.account_pick_attempts
        limit = configured if configured > 0 else DEFAULT_ACCOUNT_PICK_ATTEMPTS
        max_attempts = min(available_count, max(1, limit))
        if max_attempts < available_count:
            LOGGER.info(
                "Account picker will try %d/%d account(s). Set ACCOUNT_PICK_ATTEMPTS "
                "higher if you want a wider search.",
                max_attempts,
                available_count,
            )
        return max_attempts

    @staticmethod
    def _template_video_language(language: Language) -> Language:
        try:
            parsed = Language(language)
        except (TypeError, ValueError):
            return Language.ES
        return parsed if parsed in TEMPLATE_VIDEO_SOCIAL_COPIES else Language.ES

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_directories(self) -> None:
        for directory in (
            self.settings.data_dir,
            self.settings.downloads_dir,
            self.settings.outputs_dir,
            self.settings.state_dir,
            self.settings.template_videos_dir,
            self.settings.r2_downloads_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _download_template_video_from_r2(
        self,
        prefix: str | None,
        job_dir: Path,
    ) -> tuple[Path, bool]:
        r2_prefix = (
            prefix.strip().lstrip("/")
            if prefix and prefix.strip()
            else self.settings.r2_input_prefix
        )
        videos = self.r2_storage.list_videos(r2_prefix)
        if not videos:
            scope = f" bajo el prefijo {r2_prefix!r}" if r2_prefix else ""
            raise ValueError(f"No encontré videos en R2{scope}.")
        ordered_videos = sorted(videos, key=lambda item: item.key)
        selected_key, queue_restarted = self.state.get_next_template_video_id(
            f"r2:{r2_prefix}",
            [video.key for video in ordered_videos],
        )
        selected = next(
            (video for video in ordered_videos if video.key == selected_key),
            ordered_videos[0],
        )
        suffix = Path(selected.key).suffix.lower() or ".mp4"
        local_input = job_dir / "input" / f"source{suffix}"
        return self.r2_storage.download(selected.key, local_input), queue_restarted

    def _resolve_template_video_dir(self, folder: str | None) -> Path:
        if folder is None or not folder.strip():
            return self.settings.template_videos_dir
        path = Path(folder.strip().strip('"'))
        if path.is_absolute():
            return path
        return self.settings.root_dir / path

    def _pick_template_video(self, source_dir: Path) -> tuple[Path, bool]:
        if not source_dir.exists():
            raise ValueError(
                "No encuentro la carpeta de videos plantilla: "
                f"{source_dir}. Pon MP4 ahi o define TEMPLATE_VIDEOS_DIR."
            )
        if not source_dir.is_dir():
            raise ValueError(f"La ruta no es una carpeta: {source_dir}")
        candidates = [
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_TEMPLATE_EXTENSIONS
        ]
        if not candidates:
            raise ValueError(
                "No encontré videos .mp4/.mov/.m4v/.webm en "
                f"{source_dir}."
            )
        ordered_candidates = sorted(candidates)
        selected_id, queue_restarted = self.state.get_next_template_video_id(
            f"local:{source_dir.resolve()}",
            [str(path.resolve()) for path in ordered_candidates],
        )
        selected_path = Path(selected_id) if selected_id else ordered_candidates[0]
        if selected_path not in ordered_candidates:
            selected_path = ordered_candidates[0]
        return selected_path, queue_restarted

    def _normalize_slide_images(
        self,
        plan: VideoPlan,
        job_dir: Path,
        *,
        embed_slide_text: bool = True,
    ) -> None:
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
            if (
                plan.video_type == VideoType.TYPE_4
                and slide.role == SlideRole.STORY_ORIGINAL_REFERENCE
            ):
                out_path = self._copy_original_story_slide(source_path, slides_dir, slide.index)
                with Image.open(out_path) as image:
                    width, height = image.size
                slide.media = replace(
                    slide.media,
                    local_path=out_path,
                    width=width,
                    height=height,
                )
                continue
            out_path = slides_dir / f"slide_{slide.index:02d}.jpg"
            try:
                render_slide = (
                    slide
                    if embed_slide_text
                    else replace(slide, text="")
                )
                normalized = self.renderer.render_slide_still(
                    render_slide, plan.video_type
                ).convert("RGB")
                normalized.save(out_path, format="JPEG", quality=95, subsampling=0)
            except OSError as error:
                LOGGER.warning(
                    "No pude normalizar %s: %s", source_path, error
                )
                continue
            slide.media = replace(
                slide.media,
                local_path=out_path,
                width=target_width,
                height=target_height,
            )

    def _copy_story_reference_image(
        self,
        reference_image_path: Path,
        job_dir: Path,
    ) -> MediaCandidate:
        reference_dir = job_dir / "story_reference"
        reference_dir.mkdir(parents=True, exist_ok=True)
        suffix = reference_image_path.suffix.lower() or ".jpg"
        output_path = reference_dir / f"original_reference{suffix}"
        shutil.copy2(reference_image_path, output_path)
        with Image.open(output_path) as image:
            width, height = image.size
        return MediaCandidate(
            source_account="story_reference",
            source_id=f"story_reference:{output_path.name}",
            local_path=output_path,
            permalink=f"file://{output_path.name}",
            caption="original reference image",
            width=width,
            height=height,
            created_at="reference",
        )

    def _copy_original_story_slide(
        self,
        source_path: Path,
        slides_dir: Path,
        slide_index: int,
    ) -> Path:
        suffix = source_path.suffix.lower() or ".jpg"
        out_path = slides_dir / f"slide_{slide_index:02d}_original{suffix}"
        shutil.copy2(source_path, out_path)
        return out_path

    def _normalize_extra_image(
        self,
        media: MediaCandidate,
        job_dir: Path,
    ) -> MediaCandidate:
        target_width = self.settings.width
        target_height = self.settings.height
        extra_dir = job_dir / "extra"
        extra_dir.mkdir(parents=True, exist_ok=True)
        out_path = extra_dir / "extra_01.jpg"
        with Image.open(media.local_path) as image:
            normalized = _cover_resize(
                image.convert("RGB"), target_width, target_height
            )
        normalized.save(out_path, format="JPEG", quality=95, subsampling=0)
        media.local_path = out_path
        media.width = target_width
        media.height = target_height
        return media

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


def _running_in_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    lowered = cgroup.lower()
    return any(token in lowered for token in ("docker", "kubepods", "containerd"))
