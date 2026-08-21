from __future__ import annotations

import logging
import math
import random
import re
import hashlib
import time
from dataclasses import asdict, dataclass, replace
from typing import Callable

import cv2
import imageio.v3 as iio
import numpy as np
from PIL import Image, UnidentifiedImageError

try:
    import pillow_heif
except ImportError:  # pragma: no cover - optional dependency in prod only
    pillow_heif = None
else:  # pragma: no cover - exercised indirectly when dependency exists
    pillow_heif.register_heif_opener()

from app.config import Settings
from app.models import (
    ImageMetrics,
    Language,
    MediaCandidate,
    SlidePlan,
    SlideRole,
    TYPE_1_ROLES,
    TYPE_2_ROLES,
    TYPE_3_ROLES,
    VideoGender,
    VideoPlan,
    VideoType,
)
from app.opencv_compat import build_cascade, build_people_detector
from app.parkez import PARKEZ_ROLES, parkez_fixed_image_name
from app.state import StateStore


LOGGER = logging.getLogger(__name__)


CASUAL_KEYWORDS = {
    "selfie", "gym", "beach", "travel", "sunset", "holiday", "vacation", "trip",
    "playa", "viaje", "verano", "mirror", "friends", "friend", "weekend",
}
LAPTOP_KEYWORDS = {
    "laptop", "macbook", "notebook", "computer", "pc", "desk", "keyboard",
    "screen", "monitor", "setup", "workstation", "office", "coworking",
    "portatil", "portátil", "ordenador", "teclado", "pantalla", "escritorio",
    "oficina", "trabajo", "workspace",
}
HANDS_KEYWORDS = {
    "hands", "hand", "typing", "writing", "desk", "keyboard", "coffee",
    "watch", "bracelet", "manos", "mano", "teclado", "escribiendo", "reloj",
    "pulsera", "mesa",
}
LANDSCAPE_KEYWORDS = {
    "view", "landscape", "sunset", "beach", "ocean", "sea", "mountain",
    "skyline", "vista", "paisaje", "playa", "atardecer", "horizon", "sky",
    "naturaleza", "nature",
}
LUXURY_KEYWORDS = {
    "dubai", "ferrari", "lamborghini", "rolex", "rich", "luxury", "yacht",
    "private jet", "mansion", "supercar", "rolls", "g wagon", "designer",
    "birkin", "bugatti", "richard mille", "patek", "maybach",
    # old money / quiet luxury / estilo de vida alto
    "old money", "quiet luxury", "tailored", "suit", "tuxedo", "blazer",
    "cashmere", "linen", "polo", "country club", "equestrian",
    "sailing", "regatta", "estate", "manor", "villa", "penthouse",
    "first class", "business class", "five star", "champagne", "gala",
    "art gallery", "museum", "opera", "boarding school", "ivy",
    "ralph lauren", "loro piana", "hermes", "hermès", "chanel", "dior",
    "gucci", "louis vuitton", "prada", "riviera", "monaco", "st tropez",
    "saint tropez", "hamptons", "aspen", "amalfi", "capri", "mayfair",
    "fifth avenue", "madison avenue", "cartier", "tiffany", "bulgari",
    "bvlgari", "aston martin", "bentley", "porsche", "audemars piguet",
    "vacheron", "fine dining", "michelin",
}
AFFLUENT_LIFESTYLE_KEYWORDS = {
    "old money", "quiet luxury", "private club", "country club", "estate",
    "villa", "penthouse", "mayfair", "monaco", "st tropez", "saint tropez",
    "hamptons", "aspen", "amalfi", "capri", "fine dining", "michelin",
    "boardroom", "founder", "entrepreneur", "ceo", "ecommerce", "dropshipping",
    "success", "wealth", "wealthy", "freedom", "scaling", "remote lifestyle",
    "luxury hotel", "five star", "business class", "first class", "tailored",
    "linen", "cashmere", "blazer", "loafers",
}
EXTREME_LUXURY_KEYWORDS = {
    "private jet", "bugatti", "lamborghini", "ferrari", "mclaren", "maybach",
    "rolls royce", "yacht", "richard mille",
}
HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")
TYPE_3_BACKGROUND_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
TYPE_2_TIP3_FIXED_IMAGE_NAME = "tip3_dropradar.jpg"

# Slots whose image can be swapped for a landscape without breaking the
# month-by-month narrative or the fixed slots. Hook stays put, fixed slot is
# untouchable, and December / February / March carry the monetary narrative.
TYPE_1_REPLACEABLE_FOR_LANDSCAPE: tuple[SlideRole, ...] = (
    SlideRole.OCTOBER,
    SlideRole.NOVEMBER,
    SlideRole.JANUARY,
)
TYPE_2_REPLACEABLE_FOR_LANDSCAPE: tuple[SlideRole, ...] = (
    SlideRole.TIP4,
    SlideRole.TIP1,
    SlideRole.TIP2,
)
TOP_PICK_SCORE_RATIO = 0.92
TOP_PICK_SCORE_WINDOW = 0.08
MIN_VISIBLE_FACE_AREA_RATIO = 0.006
MIN_VISIBLE_PERSON_FOCUS_SCORE = 0.22
MIN_VISIBLE_BODY_AREA_RATIO = 0.035
MIN_VISIBLE_BODY_FOCUS_SCORE = 0.18
TYPE_1_PORTRAIT_FALLBACK_MIN_QUALITY = 0.16
TYPE_1_PORTRAIT_FALLBACK_MIN_DAYLIGHT = 0.12
TYPE_1_HOOK_FALLBACK_MIN_QUALITY = 0.45
TYPE_1_HOOK_FALLBACK_MIN_DAYLIGHT = 0.20
TYPE_1_PORTRAIT_MAX_ASPECT_RATIO = 0.92
IMAGE_ANALYSIS_CACHE_VERSION = 2
IMAGE_ANALYSIS_CACHE_MAX_ITEMS = 5000


def _word_in_text(word: str, lowered: str) -> bool:
    pattern = r"\b" + re.escape(word) + r"\b"
    return re.search(pattern, lowered) is not None


@dataclass
class CandidateScore:
    media: MediaCandidate
    score: float


class ImageSelector:
    def __init__(self, settings: Settings, state: StateStore) -> None:
        self.settings = settings
        self.state = state
        self._face_detector = build_cascade("haarcascade_frontalface_default.xml")
        self._people_detector = build_people_detector()
        self._fixed_media_cache: MediaCandidate | None = None
        self._type_2_tip3_fixed_media_cache: MediaCandidate | None = None
        self._parkez_fixed_media_cache: dict[VideoGender, MediaCandidate] = {}
        self._type_3_backgrounds_cache: tuple[MediaCandidate, ...] | None = None
        self._used_media_snapshot: dict[str, object] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        video_type: VideoType,
        language: Language,
        *,
        gender: VideoGender = VideoGender.MALE,
    ) -> VideoPlan:
        previous_snapshot = self._used_media_snapshot
        snapshot = self.state.read_used_media()
        self._used_media_snapshot = snapshot
        try:
            # Skip exact source IDs before decoding images. Perceptual
            # fingerprint conflicts are checked again after analysis.
            available_catalog = {
                account: [
                    media
                    for media in items
                    if not self.state.any_media_used_in_snapshot(
                        [media.source_id],
                        snapshot,
                    )
                ]
                for account, items in catalog.items()
            }
            for items in available_catalog.values():
                self._prepare_candidates(items)

            if video_type == VideoType.TYPE_1:
                return self._create_type_1_plan(available_catalog, language)
            if video_type == VideoType.TYPE_2:
                return self._create_type_2_plan(available_catalog, language)
            if video_type == VideoType.TYPE_3:
                return self._create_type_3_plan(available_catalog, language)
            if video_type == VideoType.PARKEZ:
                return self._create_parkez_plan(
                    available_catalog,
                    language,
                    gender,
                )
            raise ValueError(
                f"El tipo {video_type.value} no usa selector de Instagram."
            )
        finally:
            self._used_media_snapshot = previous_snapshot

    def pick_extra_image(
        self,
        media_items: list[MediaCandidate],
        video_type: VideoType,
        *,
        allow_plan_compatible_fallback: bool = False,
    ) -> MediaCandidate:
        previous_snapshot = self._used_media_snapshot
        self._used_media_snapshot = self.state.read_used_media()
        try:
            return self._pick_extra_image_from_candidates(
                media_items,
                video_type,
                allow_plan_compatible_fallback=allow_plan_compatible_fallback,
            )
        finally:
            self._used_media_snapshot = previous_snapshot

    def _pick_extra_image_from_candidates(
        self,
        media_items: list[MediaCandidate],
        video_type: VideoType,
        *,
        allow_plan_compatible_fallback: bool = False,
    ) -> MediaCandidate:
        self._prepare_candidates(media_items)
        available = [
            candidate
            for candidate in media_items
            if not self._is_candidate_used(candidate)
            and candidate.metrics is not None
            and not self._is_extreme_luxury(candidate)
        ]
        best = self._pick_best(
            available,
            exclude_ids=set(),
            score_fn=lambda media: self._score_extra_image(media, video_type),
        )
        if best is None and allow_plan_compatible_fallback:
            best = self._pick_best(
                available,
                exclude_ids=set(),
                score_fn=lambda media: self._score_plan_compatible_extra_image(
                    media,
                    video_type,
                ),
            )
        if best is None:
            raise ValueError(
                "No encontré otra imagen válida de esa cuenta sin repetir."
            )
        return best.media

    def reservation_keys_for(self, media_items) -> list[str]:
        return self._reservation_keys(media_items)

    def has_viable_type_1_candidate_set(
        self,
        media_items: list[MediaCandidate],
    ) -> bool:
        """Return whether unused, prepared candidates can fill a Type 1 plan.

        The media-pool service filters reservations and prepares metrics before
        calling this helper. Keeping the composition rule here prevents `/pool`
        from advertising six landscapes as a viable six-photo Type 1 account.
        """
        summary = self.type_1_candidate_summary(media_items)
        return self._type_1_summary_is_viable(summary)

    @staticmethod
    def _type_1_summary_is_viable(summary: dict[str, int]) -> bool:
        return (
            summary["total"] >= 6
            and summary["hooks"] >= 1
            and summary["people"] + min(1, summary["landscapes"]) >= 6
        )

    def type_1_candidate_summary(
        self,
        media_items: list[MediaCandidate],
    ) -> dict[str, int]:
        """Describe the exact Type 1 composition available in one account."""
        candidates = list(
            {
                media.source_id: media
                for media in media_items
                if media.metrics is not None
            }.values()
        )
        person_candidates = [
            media
            for media in candidates
            if self._is_type_1_person_visible_media(media)
            and any(
                self._score_type_1(media, role) > 0
                for role in TYPE_1_ROLES
                if role not in {SlideRole.HOOK, SlideRole.FEBRUARY}
            )
        ]
        hook_candidates = [
            media
            for media in person_candidates
            if self._score_type_1(media, SlideRole.HOOK) > 0
        ]
        landscape_exceptions = [
            media
            for media in candidates
            if not self._is_type_1_person_visible_media(media)
            and self._is_landscape_media(media)
            and any(
                self._score_type_1(media, role) > 0
                for role in TYPE_1_REPLACEABLE_FOR_LANDSCAPE
            )
        ]
        strict_people = sum(
            1 for media in person_candidates if self._has_person_signal(media)
        )
        return {
            "total": len(candidates),
            "people": len(person_candidates),
            "strict_people": strict_people,
            "fallback_portraits": len(person_candidates) - strict_people,
            "hooks": len(hook_candidates),
            "landscapes": len(landscape_exceptions),
        }

    # ------------------------------------------------------------------
    # Type 1
    # ------------------------------------------------------------------

    def _create_type_1_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        language: Language,
    ) -> VideoPlan:
        fixed_image = self._build_fixed_media()
        ranked: list[tuple[float, VideoPlan]] = []

        for account, raw_candidates in catalog.items():
            available = [
                candidate
                for candidate in raw_candidates
                if not self._is_candidate_used(candidate)
            ]
            LOGGER.info(
                "tipo1 @%s: %d/%d candidatos disponibles",
                account,
                len(available),
                len(raw_candidates),
            )
            if len(available) < 6:
                LOGGER.info("tipo1 @%s: descartada, < 6 disponibles", account)
                continue
            type_1_summary = self.type_1_candidate_summary(available)
            if not self._type_1_summary_is_viable(type_1_summary):
                LOGGER.info(
                    "tipo1 @%s: descartada, no hay una combinacion de portada, "
                    "personas y paisaje compatible "
                    "(total=%d, personas=%d, detectadas=%d, retratos_fallback=%d, "
                    "portadas=%d, paisajes=%d)",
                    account,
                    type_1_summary["total"],
                    type_1_summary["people"],
                    type_1_summary["strict_people"],
                    type_1_summary["fallback_portraits"],
                    type_1_summary["hooks"],
                    type_1_summary["landscapes"],
                )
                continue

            non_fixed_roles = [role for role in TYPE_1_ROLES if role != SlideRole.FEBRUARY]
            picked: dict[SlideRole, MediaCandidate] = {}
            role_scores: dict[SlideRole, float] = {}

            for role in non_fixed_roles:
                best = self._pick_best_with_post_preference(
                    available,
                    picked=picked,
                    score_fn=lambda media, current_role=role: self._score_type_1(
                        media, current_role
                    ),
                )
                if best is None:
                    break
                picked[role] = best.media
                role_scores[role] = best.score

            valid_pick = len(picked) == len(non_fixed_roles)
            if not valid_pick:
                LOGGER.info(
                    "tipo1 @%s: solo pude elegir %d/%d slides (pool=%d)",
                    account,
                    len(picked),
                    len(non_fixed_roles),
                    len(available),
                )

            if valid_pick:
                valid_pick = self._enforce_single_landscape(
                    account,
                    picked,
                    role_scores,
                    available,
                    score_fn=self._score_type_1,
                    label="tipo1",
                    landscape_fn=lambda media: (
                        self._is_landscape_media(media)
                        and not self._is_type_1_person_visible_media(media)
                    ),
                    strict=False,
                )

            if valid_pick:
                valid_pick = self._enforce_type_1_person_visibility(
                    account,
                    picked,
                    role_scores,
                    available,
                    replaceable_roles=TYPE_1_REPLACEABLE_FOR_LANDSCAPE,
                )

            if not valid_pick:
                constrained_pick = self._pick_constrained_type_1(available)
                if constrained_pick is None:
                    LOGGER.info(
                        "tipo1 @%s: la seleccion restringida tampoco encontro plan",
                        account,
                    )
                    continue
                picked, role_scores = constrained_pick
                LOGGER.info(
                    "tipo1 @%s: uso seleccion restringida para conservar "
                    "la combinacion valida",
                    account,
                )

            fallback_accounts: list[str] = []

            slides = self._build_slide_plans(
                TYPE_1_ROLES,
                picked=picked,
                fixed_role=SlideRole.FEBRUARY,
                fixed_media=fixed_image,
            )
            plan = VideoPlan(
                chosen_account=account,
                video_type=VideoType.TYPE_1,
                language=language,
                slides=slides,
                used_media_ids=self._reservation_keys(picked.values()),
                fallback_accounts=fallback_accounts,
            )
            ranked.append((self._plan_score(role_scores, VideoType.TYPE_1), plan))

        if not ranked:
            raise ValueError(
                "No pude formar un video tipo 1 con esta cuenta. Se necesitan 6 "
                "fotos nuevas de la misma cuenta: una portada vertical o cuadrada "
                "y otras 5 fotos con persona o formato retrato. Como máximo una "
                "puede ser un paisaje. Esto no significa que el pool completo esté vacío."
            )
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return ranked[0][1]

    def _pick_constrained_type_1(
        self,
        available: list[MediaCandidate],
    ) -> tuple[dict[SlideRole, MediaCandidate], dict[SlideRole, float]] | None:
        picked: dict[SlideRole, MediaCandidate] = {}
        role_scores: dict[SlideRole, float] = {}
        hook = self._pick_best_with_post_preference(
            available,
            picked=picked,
            score_fn=lambda media: self._score_type_1(media, SlideRole.HOOK),
        )
        if hook is None:
            return None
        picked[SlideRole.HOOK] = hook.media
        role_scores[SlideRole.HOOK] = hook.score

        person_pool = [
            media
            for media in available
            if self._is_type_1_person_visible_media(media)
        ]
        remaining_person_ids = {
            media.source_id
            for media in person_pool
            if media.source_id != hook.media.source_id
        }
        landscape_role: SlideRole | None = None
        if len(remaining_person_ids) < 5:
            landscape_role = TYPE_1_REPLACEABLE_FOR_LANDSCAPE[0]
            landscape = self._pick_best_with_post_preference(
                available,
                picked=picked,
                score_fn=lambda media, current_role=landscape_role: (
                    self._score_type_1(media, current_role)
                    if not self._is_type_1_person_visible_media(media)
                    and self._is_landscape_media(media)
                    else 0.0
                ),
            )
            if landscape is None:
                return None
            picked[landscape_role] = landscape.media
            role_scores[landscape_role] = landscape.score

        for role in TYPE_1_ROLES:
            if role in {SlideRole.HOOK, SlideRole.FEBRUARY, landscape_role}:
                continue
            best = self._pick_best_with_post_preference(
                person_pool,
                picked=picked,
                score_fn=lambda media, current_role=role: self._score_type_1(
                    media,
                    current_role,
                ),
            )
            if best is None:
                return None
            picked[role] = best.media
            role_scores[role] = best.score

        return picked, role_scores

    # ------------------------------------------------------------------
    # Type 2
    # ------------------------------------------------------------------

    def _create_type_2_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        language: Language,
    ) -> VideoPlan:
        fixed_image = self._build_type_2_tip3_fixed_media()
        ranked: list[tuple[float, VideoPlan]] = []

        for account, raw_candidates in catalog.items():
            available = [
                candidate
                for candidate in raw_candidates
                if not self._is_candidate_used(candidate)
            ]
            LOGGER.info(
                "tipo2 @%s: %d/%d candidatos disponibles",
                account,
                len(available),
                len(raw_candidates),
            )
            if len(available) < 4:
                LOGGER.info("tipo2 @%s: descartada, < 4 disponibles", account)
                continue

            non_fixed_roles = [role for role in TYPE_2_ROLES if role != SlideRole.TIP3]
            picked: dict[SlideRole, MediaCandidate] = {}
            role_scores: dict[SlideRole, float] = {}

            for role in non_fixed_roles:
                best = self._pick_best_with_post_preference(
                    available,
                    picked=picked,
                    score_fn=lambda media, current_role=role: self._score_type_2(
                        media, current_role
                    ),
                )
                if best is None:
                    break
                picked[role] = best.media
                role_scores[role] = best.score

            if len(picked) != len(non_fixed_roles):
                LOGGER.info(
                    "tipo2 @%s: solo pude elegir %d/%d slides (pool=%d)",
                    account,
                    len(picked),
                    len(non_fixed_roles),
                    len(available),
                )
                continue

            if not self._enforce_single_landscape(
                account,
                picked,
                role_scores,
                available,
                score_fn=self._score_type_2,
                label="tipo2",
            ):
                LOGGER.info(
                    "tipo2 @%s: descartada, demasiadas fotos de paisaje sin reemplazo con persona",
                    account,
                )
                continue

            if not self._enforce_type_2_user_visibility(
                account,
                picked,
                role_scores,
                available,
                replaceable_roles=TYPE_2_REPLACEABLE_FOR_LANDSCAPE,
            ):
                LOGGER.info(
                    "tipo2 @%s: descartada, no hay suficientes fotos con persona visible",
                    account,
                )
                continue

            slides = self._build_slide_plans(
                TYPE_2_ROLES,
                picked=picked,
                fixed_role=SlideRole.TIP3,
                fixed_media=fixed_image,
            )
            plan = VideoPlan(
                chosen_account=account,
                video_type=VideoType.TYPE_2,
                language=language,
                slides=slides,
                used_media_ids=self._reservation_keys(picked.values()),
                fallback_accounts=[],
            )
            ranked.append((self._plan_score(role_scores, VideoType.TYPE_2), plan))

        if not ranked:
            raise ValueError(
                "No encontré suficientes fotos válidas para un video tipo 2 sin reutilizar imágenes."
            )
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return ranked[0][1]

    # ------------------------------------------------------------------
    # Helpers — composition
    # ------------------------------------------------------------------

    def _create_parkez_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        language: Language,
        gender: VideoGender,
    ) -> VideoPlan:
        fixed_image = self._build_parkez_fixed_media(gender)
        photo_roles = PARKEZ_ROLES[:-1]
        ranked: list[tuple[float, VideoPlan]] = []

        for account, raw_candidates in catalog.items():
            available = [
                candidate
                for candidate in raw_candidates
                if not self._is_candidate_used(candidate)
                and self._is_type_2_user_visible_media(candidate)
            ]
            if len(available) < len(photo_roles):
                continue

            picked: dict[SlideRole, MediaCandidate] = {}
            role_scores: dict[SlideRole, float] = {}
            for role in photo_roles:
                best = self._pick_best_with_post_preference(
                    available,
                    picked=picked,
                    score_fn=lambda media, current_role=role: self._score_type_2(
                        media,
                        current_role,
                    ),
                )
                if best is None:
                    break
                picked[role] = best.media
                role_scores[role] = best.score

            if len(picked) != len(photo_roles):
                continue

            slides = self._build_slide_plans(
                PARKEZ_ROLES,
                picked=picked,
                fixed_role=SlideRole.PARKEZ_PROMO,
                fixed_media=fixed_image,
            )
            plan = VideoPlan(
                chosen_account=account,
                video_type=VideoType.PARKEZ,
                language=language,
                slides=slides,
                used_media_ids=self._reservation_keys(picked.values()),
                fallback_accounts=[],
            )
            ranked.append((self._plan_score(role_scores, VideoType.PARKEZ), plan))

        if not ranked:
            label = "mujer" if gender == VideoGender.FEMALE else "hombre"
            raise ValueError(
                "No encontré tres fotos nuevas con una persona visible para "
                f"crear el carrusel ParkEz de {label}."
            )
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return ranked[0][1]

    def _create_type_3_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        language: Language,
    ) -> VideoPlan:
        backgrounds = self._type_3_backgrounds()
        background_ids = [background.source_id for background in backgrounds]
        selected_background_id = self.state.get_next_type_3_background_id(background_ids)
        background_by_id = {
            background.source_id: background for background in backgrounds
        }
        background = background_by_id.get(selected_background_id or "")
        if background is None:
            background = backgrounds[0]
            selected_background_id = background.source_id
        ranked: list[tuple[float, VideoPlan]] = []

        for account, raw_candidates in catalog.items():
            available = [
                candidate
                for candidate in raw_candidates
                if not self._is_candidate_used(candidate)
            ]
            LOGGER.info(
                "tipo3 @%s: %d/%d candidatos disponibles",
                account,
                len(available),
                len(raw_candidates),
            )
            hook = self._pick_best(
                available,
                exclude_ids=set(),
                score_fn=self._score_type_3_hook,
            )
            if hook is None:
                LOGGER.info("tipo3 @%s: sin hook válido", account)
                continue

            slides: list[SlidePlan] = [
                SlidePlan(index=1, role=SlideRole.HOOK, text="", media=hook.media)
            ]
            for index, role in enumerate(TYPE_3_ROLES[1:], start=2):
                slide_background = replace(
                    background,
                    source_id=f"{background.source_id}:{index}",
                )
                slides.append(
                    SlidePlan(
                        index=index,
                        role=role,
                        text="",
                        media=slide_background,
                        fixed_asset=True,
                    )
                )

            plan = VideoPlan(
                chosen_account=account,
                video_type=VideoType.TYPE_3,
                language=language,
                slides=slides,
                used_media_ids=self._reservation_keys([hook.media]),
                fallback_accounts=[],
                type_3_background_id=selected_background_id,
                type_3_background_candidates=list(background_ids),
            )
            ranked.append((hook.score, plan))

        if not ranked:
            raise ValueError(
                "No encontré una foto válida para un video tipo 3 sin reutilizar imágenes."
            )
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return ranked[0][1]

    def _build_slide_plans(
        self,
        roles: tuple[SlideRole, ...],
        *,
        picked: dict[SlideRole, MediaCandidate],
        fixed_role: SlideRole,
        fixed_media: MediaCandidate,
    ) -> list[SlidePlan]:
        slides: list[SlidePlan] = []
        for index, role in enumerate(roles, start=1):
            if role == fixed_role:
                slides.append(
                    SlidePlan(
                        index=index,
                        role=role,
                        text="",
                        media=fixed_media,
                        fixed_asset=True,
                    )
                )
            else:
                slides.append(
                    SlidePlan(index=index, role=role, text="", media=picked[role])
                )
        return slides

    def _cap_landscapes_to_one(
        self,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        available: list[MediaCandidate],
        *,
        replaceable_roles: tuple[SlideRole, ...],
    ) -> None:
        # TYPE_2 solo puede mostrar UNA foto donde el usuario no sea el sujeto
        # principal — sea paisaje puro o el usuario como actor secundario
        # (sin cara detectada con tamaño suficiente). El resto de los slots
        # reemplazables debe ser retrato del creador. HOOK no se toca.
        landscape_roles = [
            role for role, media in picked.items()
            if self._is_landscape_dominant_media(media) and role in replaceable_roles
        ]
        if len(landscape_roles) <= 1:
            return
        landscape_roles.sort(key=lambda role: role_scores.get(role, 0.0), reverse=True)
        for role in landscape_roles[1:]:
            original = picked[role]
            exclude = self._exclude_ids_by_post(picked, available)
            replacement = self._pick_best(
                available,
                exclude_ids=exclude,
                score_fn=lambda media, current_role=role: (
                    0.0 if self._is_landscape_dominant_media(media)
                    else self._score_type_2(media, current_role)
                ),
            )
            if replacement is None:
                continue
            picked[role] = replacement.media
            role_scores[role] = replacement.score
            LOGGER.info(
                "tipo2 landscape cap: %s -> reemplazo %s por %s",
                role.value,
                original.source_id,
                replacement.media.source_id,
            )

    def _is_landscape_dominant_media(self, media: MediaCandidate) -> bool:
        return self._is_type_2_non_user_media(media)

    def _enforce_single_landscape(
        self,
        account: str,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        available: list[MediaCandidate],
        *,
        score_fn: Callable[[MediaCandidate, SlideRole], float],
        label: str,
        landscape_fn: Callable[[MediaCandidate], bool] | None = None,
        strict: bool = True,
    ) -> bool:
        if landscape_fn is None:
            landscape_fn = self._is_landscape_media
        landscape_roles = [
            role for role, media in picked.items()
            if landscape_fn(media)
        ]
        if len(landscape_roles) <= 1:
            return True

        landscape_roles.sort(key=lambda role: role_scores.get(role, 0.0), reverse=True)
        for role in landscape_roles[1:]:
            original = picked[role]
            replacement = self._pick_best_with_post_preference(
                available,
                picked=picked,
                score_fn=lambda media, current_role=role: (
                    0.0 if landscape_fn(media)
                    else score_fn(media, current_role)
                ),
            )
            if replacement is None:
                LOGGER.info(
                    "%s @%s: no pude reemplazar paisaje %s por foto no paisaje",
                    label,
                    account,
                    original.source_id,
                )
                if strict:
                    return False
                continue
            picked[role] = replacement.media
            role_scores[role] = replacement.score
            LOGGER.info(
                "%s landscape cap: %s -> reemplazo %s por %s",
                label,
                role.value,
                original.source_id,
                replacement.media.source_id,
            )
        return True

    def _enforce_type_1_person_visibility(
        self,
        account: str,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        available: list[MediaCandidate],
        *,
        replaceable_roles: tuple[SlideRole, ...],
    ) -> bool:
        self._move_type_1_landscape_exception_to_replaceable_role(
            picked,
            role_scores,
            replaceable_roles=replaceable_roles,
        )

        allowed_landscape_roles: list[SlideRole] = []
        roles_to_replace: list[SlideRole] = []

        for role, media in picked.items():
            if self._is_type_1_person_visible_media(media):
                continue
            if role in replaceable_roles and self._is_landscape_media(media):
                allowed_landscape_roles.append(role)
                continue
            roles_to_replace.append(role)

        allowed_landscape_roles.sort(
            key=lambda role: role_scores.get(role, 0.0),
            reverse=True,
        )
        roles_to_replace.extend(allowed_landscape_roles[1:])

        for role in roles_to_replace:
            original = picked[role]
            replacement = self._pick_best_with_post_preference(
                available,
                picked=picked,
                score_fn=lambda media, current_role=role: (
                    self._score_type_1(media, current_role)
                    if self._is_type_1_person_visible_media(media)
                    else 0.0
                ),
            )
            if replacement is None:
                LOGGER.info(
                    "tipo1 @%s: no pude reemplazar %s por una foto con persona",
                    account,
                    original.source_id,
                )
                continue
            picked[role] = replacement.media
            role_scores[role] = replacement.score
            LOGGER.info(
                "tipo1 person visibility: %s -> reemplazo %s por %s",
                role.value,
                original.source_id,
                replacement.media.source_id,
            )

        remaining_without_person = [
            role for role, media in picked.items()
            if not self._is_type_1_person_visible_media(media)
        ]
        allowed_remaining = [
            role
            for role in remaining_without_person
            if role in replaceable_roles and self._is_landscape_media(picked[role])
        ]
        if (
            len(remaining_without_person) != len(allowed_remaining)
            or len(allowed_remaining) > 1
        ):
            LOGGER.info(
                "tipo1 @%s: descartada, %d foto(s) sin persona detectada tras priorizar personas",
                account,
                len(remaining_without_person),
            )
            return False
        return True

    def _move_type_1_landscape_exception_to_replaceable_role(
        self,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        *,
        replaceable_roles: tuple[SlideRole, ...],
    ) -> None:
        for role, media in list(picked.items()):
            if role in replaceable_roles:
                continue
            if self._is_type_1_person_visible_media(media):
                continue
            if not self._is_landscape_media(media):
                continue

            donor_role = self._type_1_person_donor_role(
                picked,
                role_scores,
                replaceable_roles=replaceable_roles,
            )
            if donor_role is None:
                continue
            donor_media = picked[donor_role]
            picked[role], picked[donor_role] = donor_media, media
            role_scores[role], role_scores[donor_role] = (
                role_scores[donor_role],
                role_scores[role],
            )
            LOGGER.info(
                "tipo1 person visibility: muevo paisaje %s de %s a %s",
                media.source_id,
                role.value,
                donor_role.value,
            )

    def _type_1_person_donor_role(
        self,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        *,
        replaceable_roles: tuple[SlideRole, ...],
    ) -> SlideRole | None:
        donor_roles = [
            role
            for role in replaceable_roles
            if role in picked and self._is_type_1_person_visible_media(picked[role])
        ]
        if not donor_roles:
            return None
        return min(donor_roles, key=lambda role: role_scores.get(role, 0.0))

    def _enforce_type_2_user_visibility(
        self,
        account: str,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        available: list[MediaCandidate],
        *,
        replaceable_roles: tuple[SlideRole, ...],
    ) -> bool:
        allowed_landscape_roles: list[SlideRole] = []
        roles_to_replace: list[SlideRole] = []

        for role, media in picked.items():
            if self._is_type_2_user_visible_media(media):
                continue
            if role in replaceable_roles and self._is_landscape_media(media):
                allowed_landscape_roles.append(role)
                continue
            roles_to_replace.append(role)

        allowed_landscape_roles.sort(
            key=lambda role: role_scores.get(role, 0.0),
            reverse=True,
        )
        roles_to_replace.extend(allowed_landscape_roles[1:])

        for role in roles_to_replace:
            original = picked[role]
            replacement = self._pick_best_with_post_preference(
                available,
                picked=picked,
                score_fn=lambda media, current_role=role: (
                    0.0 if self._is_type_2_non_user_media(media)
                    else self._score_type_2(media, current_role)
                ),
            )
            if replacement is None:
                LOGGER.info(
                    "tipo2 @%s: no pude reemplazar %s sin usuario visible",
                    account,
                    original.source_id,
                )
                return False
            picked[role] = replacement.media
            role_scores[role] = replacement.score
            LOGGER.info(
                "tipo2 user visibility cap: %s -> reemplazo %s por %s",
                role.value,
                original.source_id,
                replacement.media.source_id,
            )

        remaining = [
            role for role, media in picked.items()
            if self._is_type_2_non_user_media(media)
        ]
        allowed_remaining = [
            role for role in remaining
            if role in replaceable_roles and self._is_landscape_media(picked[role])
        ]
        if len(remaining) != len(allowed_remaining) or len(allowed_remaining) > 1:
            LOGGER.info(
                "tipo2 @%s: descartada, %d fotos sin usuario visible",
                account,
                len(remaining),
            )
            return False
        return True

    def _is_type_2_non_user_media(self, media: MediaCandidate) -> bool:
        if not media.metrics:
            return True
        return not self._is_type_2_user_visible_media(media)

    def _is_type_2_user_visible_media(self, media: MediaCandidate) -> bool:
        return self._has_person_signal(media)

    def _is_person_visible_media(self, media: MediaCandidate) -> bool:
        return self._has_person_signal(media)

    def _is_hook_person_visible_media(self, media: MediaCandidate) -> bool:
        return self._has_person_signal(media)

    def _is_type_1_person_visible_media(self, media: MediaCandidate) -> bool:
        if self._has_person_signal(media):
            return True
        if media.metrics is None:
            return False
        return self._is_type_1_portrait_fallback(media.metrics)

    def _is_type_1_hook_media(self, media: MediaCandidate) -> bool:
        """Accept a detected person or a conservative detector-miss fallback.

        The semantic landscape flag also includes sky and caption keywords. A
        detected person in a vertical photo must therefore not be rejected just
        because the background contains a beach or a large patch of sky.
        """
        metrics = media.metrics
        if metrics is None or metrics.aspect_ratio > 1.05:
            return False
        if self._has_person_signal(media):
            return True
        return (
            self._is_type_1_portrait_fallback(metrics)
            and metrics.quality_score >= TYPE_1_HOOK_FALLBACK_MIN_QUALITY
            and metrics.daylight >= TYPE_1_HOOK_FALLBACK_MIN_DAYLIGHT
        )

    def _is_type_1_portrait_fallback(self, metrics: ImageMetrics) -> bool:
        return (
            not self._metrics_have_person_signal(metrics)
            and metrics.quality_score >= TYPE_1_PORTRAIT_FALLBACK_MIN_QUALITY
            and metrics.daylight >= TYPE_1_PORTRAIT_FALLBACK_MIN_DAYLIGHT
            and metrics.aspect_ratio <= TYPE_1_PORTRAIT_MAX_ASPECT_RATIO
            and not metrics.is_landscape
        )

    def _has_person_signal(self, media: MediaCandidate) -> bool:
        if not media.metrics:
            return False
        return self._metrics_have_person_signal(media.metrics)

    def _metrics_have_person_signal(self, metrics: ImageMetrics) -> bool:
        face_signal = (
            metrics.faces >= 1
            and (
                metrics.face_area_ratio >= MIN_VISIBLE_FACE_AREA_RATIO
                or metrics.portrait_focus_score >= MIN_VISIBLE_PERSON_FOCUS_SCORE
            )
        )
        body_signal = (
            metrics.body_area_ratio >= MIN_VISIBLE_BODY_AREA_RATIO
            and metrics.body_focus_score >= MIN_VISIBLE_BODY_FOCUS_SCORE
        )
        weak_face_signal = (
            metrics.faces == 0
            and metrics.face_area_ratio >= MIN_VISIBLE_FACE_AREA_RATIO
            and metrics.portrait_focus_score >= MIN_VISIBLE_PERSON_FOCUS_SCORE
        )
        return face_signal or body_signal or weak_face_signal

    def _inject_landscape(
        self,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        catalog: dict[str, list[MediaCandidate]],
        *,
        selected_account: str,
        replaceable_roles: tuple[SlideRole, ...],
        allow_luxury: bool,
    ) -> MediaCandidate | None:
        used_ids = set(self._reservation_keys(picked.values()))
        used_post_keys = {self._post_key(item) for item in picked.values()}
        replacement = self._find_landscape_replacement(
            catalog,
            used_ids=used_ids,
            used_post_keys=used_post_keys,
            allow_luxury=allow_luxury,
            prefer_account=selected_account,
        )
        if replacement is None:
            return None

        target_role = self._weakest_replaceable_role(role_scores, replaceable_roles)
        if target_role is None:
            return None

        picked[target_role] = replacement.media
        role_scores[target_role] = replacement.score
        return replacement.media

    def _weakest_replaceable_role(
        self,
        role_scores: dict[SlideRole, float],
        replaceable_roles: tuple[SlideRole, ...],
    ) -> SlideRole | None:
        candidates = [
            (role, role_scores[role])
            for role in replaceable_roles
            if role in role_scores
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry[1])
        return candidates[0][0]

    # ------------------------------------------------------------------
    # Helpers — image preparation and analysis
    # ------------------------------------------------------------------

    def _prepare_candidates(
        self,
        media_items: list[MediaCandidate],
        *,
        ensure_fingerprints: bool = True,
    ) -> None:
        needs_analysis = any(
            media.metrics is None
            or (ensure_fingerprints and not media.content_fingerprints)
            for media in media_items
        )
        if not needs_analysis:
            return
        cache_payload: dict[str, object] = {}
        cache_items: dict[str, object] = {}
        cache_changed = False
        if needs_analysis:
            cache_payload = self.state.read_image_analysis_cache()
            if cache_payload.get("version") == IMAGE_ANALYSIS_CACHE_VERSION:
                raw_items = cache_payload.get("items")
                if isinstance(raw_items, dict):
                    cache_items = dict(raw_items)
            else:
                cache_payload = {
                    "version": IMAGE_ANALYSIS_CACHE_VERSION,
                    "items": {},
                }

        for media in media_items:
            cache_key = self._image_analysis_cache_key(media)
            if media.metrics is None and cache_key:
                cached = cache_items.get(cache_key)
                if isinstance(cached, dict) and self._restore_cached_analysis(
                    media,
                    cached,
                    require_fingerprints=ensure_fingerprints,
                ):
                    continue
            if media.metrics is not None:
                if ensure_fingerprints and not media.content_fingerprints:
                    try:
                        media.content_fingerprints = self._fingerprint_images(media)
                        media.content_fingerprint = media.content_fingerprints[0]
                    except (UnidentifiedImageError, OSError, ValueError) as error:
                        LOGGER.warning(
                            "Skipping unreadable image %s: %s", media.local_path, error
                        )
                        media.metrics = None
            else:
                try:
                    media.metrics = self._analyze_image(media)
                    if not media.content_fingerprints:
                        media.content_fingerprints = self._fingerprint_images(media)
                        media.content_fingerprint = media.content_fingerprints[0]
                except (UnidentifiedImageError, OSError, ValueError) as error:
                    LOGGER.warning(
                        "Skipping unreadable image %s: %s", media.local_path, error
                    )
                    media.metrics = None
                    media.content_fingerprint = None
                    media.content_fingerprints = []

            if media.metrics is not None and cache_key:
                cache_items.pop(cache_key, None)
                cache_items[cache_key] = {
                    "metrics": asdict(media.metrics),
                    "content_fingerprint": media.content_fingerprint,
                    "content_fingerprints": list(media.content_fingerprints),
                    "width": media.width,
                    "height": media.height,
                    "cached_at": time.time(),
                }
                cache_changed = True

        if cache_changed:
            if len(cache_items) > IMAGE_ANALYSIS_CACHE_MAX_ITEMS:
                overflow = len(cache_items) - IMAGE_ANALYSIS_CACHE_MAX_ITEMS
                for stale_key in list(cache_items)[:overflow]:
                    cache_items.pop(stale_key, None)
            cache_payload["version"] = IMAGE_ANALYSIS_CACHE_VERSION
            cache_payload["items"] = cache_items
            self.state.write_image_analysis_cache(cache_payload)

    def _image_analysis_cache_key(self, media: MediaCandidate) -> str | None:
        try:
            stat = media.local_path.stat()
            resolved = media.local_path.resolve()
        except OSError:
            return None
        caption_hash = hashlib.sha256(
            (media.caption or "").encode("utf-8")
        ).hexdigest()[:20]
        return "|".join(
            (
                media.source_id,
                str(resolved),
                str(stat.st_size),
                str(stat.st_mtime_ns),
                caption_hash,
            )
        )

    def _restore_cached_analysis(
        self,
        media: MediaCandidate,
        cached: dict[str, object],
        *,
        require_fingerprints: bool,
    ) -> bool:
        metrics = cached.get("metrics")
        fingerprints = cached.get("content_fingerprints")
        if not isinstance(metrics, dict):
            return False
        if require_fingerprints and not isinstance(fingerprints, list):
            return False
        try:
            media.metrics = ImageMetrics(**metrics)
            media.width = int(cached.get("width") or media.width)
            media.height = int(cached.get("height") or media.height)
        except (TypeError, ValueError):
            media.metrics = None
            return False
        media.content_fingerprints = [
            str(value) for value in (fingerprints or []) if value
        ]
        media.content_fingerprint = (
            str(cached.get("content_fingerprint"))
            if cached.get("content_fingerprint")
            else (
                media.content_fingerprints[0]
                if media.content_fingerprints
                else None
            )
        )
        return not require_fingerprints or bool(media.content_fingerprints)

    def _analyze_image(self, media: MediaCandidate) -> ImageMetrics:
        rgb = self._open_image_rgb_array(media)
        if not media.content_fingerprints:
            media.content_fingerprints = self._fingerprints_from_image(
                Image.fromarray(rgb)
            )
            media.content_fingerprint = media.content_fingerprints[0]

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        brightness = float(np.mean(gray))
        daylight = self._normalize(brightness, low=85.0, high=190.0)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness_score = self._normalize(sharpness, low=60.0, high=900.0)
        face_boxes = self._detect_faces(gray)
        faces = int(len(face_boxes))
        face_area_ratio, face_center_score, portrait_focus_score = self._face_presence_features(
            face_boxes,
            gray.shape,
        )
        body_boxes = self._detect_people(rgb)
        body_area_ratio, body_focus_score = self._body_presence_features(
            body_boxes,
            gray.shape,
        )
        aspect_ratio = media.width / max(media.height, 1)

        sky_ratio = self._sky_ratio(rgb)
        landscape_by_caption = self._keyword_score(media.caption, LANDSCAPE_KEYWORDS) > 0.0
        is_landscape = (
            aspect_ratio > 1.05
            or sky_ratio > 0.18
            or landscape_by_caption
        )

        outdoor_score = max(
            0.0,
            min(
                1.0,
                0.55 * sky_ratio
                + 0.25 * self._keyword_score(media.caption, LANDSCAPE_KEYWORDS)
                + 0.20 * daylight,
            ),
        )
        casual_score = max(
            0.0,
            min(
                1.0,
                0.5 * self._keyword_score(media.caption, CASUAL_KEYWORDS)
                + 0.3 * min(faces, 2) / 2.0
                + 0.2 * min(body_focus_score, 1.0)
                + 0.2 * daylight,
            ),
        )
        keyword_luxury = self._keyword_score(media.caption, LUXURY_KEYWORDS)
        affluent_keywords = self._keyword_score(media.caption, AFFLUENT_LIFESTYLE_KEYWORDS)
        laptop_score = self._keyword_score(media.caption, LAPTOP_KEYWORDS)
        hands_score = self._keyword_score(media.caption, HANDS_KEYWORDS)
        visual_luxury = self._visual_luxury_score(rgb)
        luxury_score = max(
            0.0,
            min(
                1.0,
                0.6 * keyword_luxury
                + 0.4 * visual_luxury,
            ),
        )
        quality_score = max(
            0.0,
            min(
                1.0,
                0.55 * daylight + 0.45 * sharpness_score,
            ),
        )
        affluent_lifestyle_score = max(
            0.0,
            min(
                1.0,
                0.35 * luxury_score
                + 0.20 * affluent_keywords
                + 0.15 * visual_luxury
                + 0.15 * quality_score
                + 0.15 * daylight
                - 0.12 * casual_score,
            ),
        )
        return ImageMetrics(
            brightness=brightness,
            daylight=daylight,
            sharpness=sharpness,
            faces=faces,
            aspect_ratio=aspect_ratio,
            is_landscape=is_landscape,
            outdoor_score=outdoor_score,
            casual_score=casual_score,
            luxury_score=luxury_score,
            quality_score=quality_score,
            has_visual_luxury=visual_luxury > 0.45,
            sky_ratio=sky_ratio,
            face_area_ratio=face_area_ratio,
            face_center_score=face_center_score,
            portrait_focus_score=portrait_focus_score,
            affluent_lifestyle_score=affluent_lifestyle_score,
            laptop_score=laptop_score,
            hands_score=hands_score,
            body_area_ratio=body_area_ratio,
            body_focus_score=body_focus_score,
        )

    def _open_image_rgb_array(self, media: MediaCandidate) -> np.ndarray:
        try:
            with Image.open(media.local_path) as raw:
                image = raw.convert("RGB")
                media.width, media.height = image.size
                return np.asarray(image)
        except UnidentifiedImageError:
            if self._looks_like_heic(media.local_path):
                LOGGER.info("Intentando decodificar HEIC en %s", media.local_path)
            if pillow_heif is not None:
                with Image.open(media.local_path) as raw:
                    image = raw.convert("RGB")
                    media.width, media.height = image.size
                    return np.asarray(image)
            try:
                rgb = iio.imread(media.local_path)
            except Exception as error:  # noqa: BLE001
                raise UnidentifiedImageError(
                    f"No pude abrir {media.local_path.name}. Si es HEIC, instala pillow-heif."
                ) from error
            if rgb.ndim == 2:
                rgb = np.stack([rgb, rgb, rgb], axis=-1)
            if rgb.ndim == 3 and rgb.shape[2] == 4:
                rgb = rgb[..., :3]
            media.height, media.width = rgb.shape[:2]
            return rgb.astype(np.uint8)

    def _fingerprint_images(self, media: MediaCandidate) -> list[str]:
        with Image.open(media.local_path) as raw:
            image = raw.convert("RGB")
        return self._fingerprints_from_image(image)

    def _fingerprints_from_image(self, image: Image.Image) -> list[str]:
        digest = hashlib.sha256()
        digest.update(str(image.size).encode("ascii"))
        digest.update(image.tobytes())
        return [f"sha256:{digest.hexdigest()}", self._dhash(image)]

    def _dhash(self, image: Image.Image) -> str:
        small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(small.getdata())
        value = 0
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                value = (value << 1) | int(left > right)
        return f"dhash:{value:016x}"

    def _looks_like_heic(self, path) -> bool:
        try:
            header = path.read_bytes()[:32]
        except OSError:
            return False
        return any(brand in header for brand in HEIC_BRANDS)

    def _detect_faces(self, gray: np.ndarray) -> np.ndarray:
        if self._face_detector.empty():
            return np.empty((0, 4), dtype=np.int32)
        detected = self._face_detector.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(80, 80),
        )
        if len(detected) == 0:
            return np.empty((0, 4), dtype=np.int32)
        return np.asarray(detected)

    def _detect_people(self, rgb: np.ndarray) -> np.ndarray:
        height, width = rgb.shape[:2]
        scale = min(1.0, 900.0 / max(height, width, 1))
        if scale < 1.0:
            resized = cv2.resize(
                rgb,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            resized = rgb
        boxes, weights = self._people_detector.detectMultiScale(
            resized,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        if len(boxes) == 0:
            return np.empty((0, 4), dtype=np.int32)
        if len(weights) > 0:
            boxes = np.asarray(
                [
                    box
                    for box, weight in zip(boxes, weights)
                    if float(weight) >= 0.2
                ],
                dtype=np.float32,
            )
            if len(boxes) == 0:
                return np.empty((0, 4), dtype=np.int32)
        boxes = np.asarray(boxes, dtype=np.float32)
        if scale < 1.0:
            boxes[:, :4] = boxes[:, :4] / scale
        return boxes.astype(np.int32)

    def _face_presence_features(
        self,
        face_boxes: np.ndarray,
        image_shape: tuple[int, int],
    ) -> tuple[float, float, float]:
        if len(face_boxes) == 0:
            return 0.0, 0.0, 0.0

        height, width = image_shape
        image_area = max(float(height * width), 1.0)
        cx = width / 2.0
        cy = height / 2.0

        best_area_ratio = 0.0
        best_center_score = 0.0
        best_portrait_focus = 0.0
        max_distance = max(math.hypot(cx, cy), 1.0)

        for x, y, w, h in face_boxes:
            area_ratio = (w * h) / image_area
            face_center_x = x + (w / 2.0)
            face_center_y = y + (h / 2.0)
            distance = math.hypot(face_center_x - cx, face_center_y - cy)
            center_score = max(0.0, 1.0 - (distance / max_distance))
            size_score = self._normalize(area_ratio, low=0.015, high=0.18)
            portrait_focus = max(
                0.0,
                min(1.0, 0.70 * size_score + 0.30 * center_score),
            )
            if portrait_focus > best_portrait_focus:
                best_area_ratio = area_ratio
                best_center_score = center_score
                best_portrait_focus = portrait_focus

        return best_area_ratio, best_center_score, best_portrait_focus

    def _body_presence_features(
        self,
        body_boxes: np.ndarray,
        image_shape: tuple[int, int],
    ) -> tuple[float, float]:
        if len(body_boxes) == 0:
            return 0.0, 0.0

        height, width = image_shape
        image_area = max(float(height * width), 1.0)
        cx = width / 2.0
        cy = height / 2.0
        max_distance = max(math.hypot(cx, cy), 1.0)

        best_area_ratio = 0.0
        best_focus = 0.0
        for x, y, w, h in body_boxes:
            area_ratio = (w * h) / image_area
            body_center_x = x + (w / 2.0)
            body_center_y = y + (h / 2.0)
            distance = math.hypot(body_center_x - cx, body_center_y - cy)
            center_score = max(0.0, 1.0 - (distance / max_distance))
            size_score = self._normalize(area_ratio, low=0.035, high=0.35)
            focus = max(0.0, min(1.0, 0.70 * size_score + 0.30 * center_score))
            if focus > best_focus:
                best_area_ratio = area_ratio
                best_focus = focus
        return best_area_ratio, best_focus

    def _sky_ratio(self, rgb: np.ndarray) -> float:
        # Approximate "sky / open horizon" by counting blue-cyan pixels in the
        # upper third of the image. Heuristic — declared as such.
        height = rgb.shape[0]
        upper = rgb[: max(1, height // 3), :, :]
        hsv = cv2.cvtColor(upper, cv2.COLOR_RGB2HSV)
        h = hsv[..., 0]
        s = hsv[..., 1]
        v = hsv[..., 2]
        sky = (h >= 90) & (h <= 135) & (s >= 15) & (s <= 160) & (v >= 110)
        return float(sky.mean())

    def _visual_luxury_score(self, rgb: np.ndarray) -> float:
        # Rough proxy: high saturation gold / chrome reflections combined with
        # very dark surroundings (typical product / car shoots). Weak signal.
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        gold = ((h <= 35) | (h >= 160)) & (s >= 110) & (v >= 170)
        chrome = (s <= 35) & (v >= 210)
        ratio = float((gold | chrome).mean())
        return min(ratio * 4.5, 1.0)

    # ------------------------------------------------------------------
    # Helpers — picking
    # ------------------------------------------------------------------

    def _pick_best(
        self,
        pool: list[MediaCandidate],
        *,
        exclude_ids: set[str],
        score_fn: Callable[[MediaCandidate], float],
        accept_fn: Callable[[MediaCandidate], bool] | None = None,
    ) -> CandidateScore | None:
        scored: list[CandidateScore] = []
        for media in pool:
            if media.source_id in exclude_ids:
                continue
            if media.metrics is None:
                continue
            if accept_fn is not None and not accept_fn(media):
                continue
            score = score_fn(media)
            if score <= 0:
                continue
            scored.append(CandidateScore(media=media, score=score))
        if not scored:
            return None
        best_score = max(candidate.score for candidate in scored)
        cutoff = max(
            best_score * TOP_PICK_SCORE_RATIO,
            best_score - TOP_PICK_SCORE_WINDOW,
        )
        top_candidates = [
            candidate for candidate in scored
            if candidate.score >= cutoff
        ]
        return random.choice(top_candidates)

    def _pick_best_with_post_preference(
        self,
        pool: list[MediaCandidate],
        *,
        picked: dict[SlideRole, MediaCandidate],
        score_fn: Callable[[MediaCandidate], float],
        accept_fn: Callable[[MediaCandidate], bool] | None = None,
    ) -> CandidateScore | None:
        best = self._pick_best(
            pool,
            exclude_ids=self._exclude_ids_by_post(picked, pool),
            score_fn=score_fn,
            accept_fn=accept_fn,
        )
        if best is not None:
            return best
        if not picked:
            return None
        LOGGER.info(
            "No hay suficientes posts distintos; permito otra imagen del mismo carrusel"
        )
        return self._pick_best(
            pool,
            exclude_ids=self._exclude_exact_ids(picked),
            score_fn=score_fn,
            accept_fn=accept_fn,
        )

    def _find_landscape_replacement(
        self,
        catalog: dict[str, list[MediaCandidate]],
        *,
        used_ids: set[str],
        used_post_keys: set[str],
        allow_luxury: bool,
        prefer_account: str | None = None,
    ) -> CandidateScore | None:
        scored: list[CandidateScore] = []
        for account, candidates in catalog.items():
            for media in candidates:
                if media.source_id in used_ids:
                    continue
                if self._post_key(media) in used_post_keys:
                    continue
                if self._is_candidate_used(media):
                    continue
                if not media.metrics or not self._is_landscape_media(media):
                    continue
                if not allow_luxury and self._is_extreme_luxury(media):
                    continue
                metrics = media.metrics
                base = 0.55 * metrics.quality_score + 0.35 * metrics.outdoor_score + 0.10 * metrics.daylight
                if account == prefer_account:
                    base += 0.05
                scored.append(CandidateScore(media=media, score=base))
        if not scored:
            return None
        best_score = max(candidate.score for candidate in scored)
        cutoff = max(
            best_score * TOP_PICK_SCORE_RATIO,
            best_score - TOP_PICK_SCORE_WINDOW,
        )
        top_candidates = [
            candidate for candidate in scored
            if candidate.score >= cutoff
        ]
        return random.choice(top_candidates)

    def _plan_score(
        self,
        role_scores: dict[SlideRole, float],
        video_type: VideoType,
    ) -> float:
        total = sum(role_scores.values())
        hook_weight = 0.45 if video_type == VideoType.TYPE_1 else 0.35
        return total + hook_weight * role_scores.get(SlideRole.HOOK, 0.0)

    def _score_type_1(self, media: MediaCandidate, role: SlideRole) -> float:
        metrics = media.metrics
        if metrics is None:
            return 0.0
        face_score = self._single_person_score(metrics)
        person_or_composition = max(
            face_score,
            metrics.portrait_focus_score,
            metrics.body_focus_score,
        )
        score = (
            0.44 * metrics.quality_score
            + 0.18 * metrics.daylight
            + 0.14 * person_or_composition
            + 0.12 * metrics.outdoor_score
            + 0.08 * metrics.casual_score
            + 0.04 * metrics.hands_score
        )
        if role == SlideRole.HOOK:
            if not self._is_type_1_hook_media(media):
                return 0.0
            score += (
                0.12 * metrics.daylight
                + 0.18 * person_or_composition
            )
        elif role == SlideRole.MARCH:
            # March is the closing slide, slight bump for upbeat outdoor shots.
            score += 0.05 * metrics.outdoor_score
        if metrics.has_visual_luxury:
            score -= 0.04
        return score

    def _score_type_2(self, media: MediaCandidate, role: SlideRole) -> float:
        metrics = media.metrics
        if metrics is None:
            return 0.0
        has_visible_user = self._is_type_2_user_visible_media(media)
        if (
            not has_visible_user
            and not self._is_landscape_media(media)
        ):
            return 0.0
        face_score = self._single_person_score(metrics)
        person_or_composition = max(
            face_score,
            metrics.portrait_focus_score,
            metrics.body_focus_score,
        )
        score = (
            0.42 * metrics.quality_score
            + 0.18 * metrics.daylight
            + 0.16 * person_or_composition
            + 0.12 * metrics.outdoor_score
            + 0.08 * metrics.casual_score
            + 0.04 * metrics.hands_score
        )
        if has_visible_user:
            score += 0.24 + 0.12 * person_or_composition
        else:
            score -= 0.38
        if role == SlideRole.HOOK:
            if (
                not self._is_hook_person_visible_media(media)
                or self._is_landscape_media(media)
            ):
                return 0.0
            score += (
                0.18 * person_or_composition
                + 0.08 * metrics.daylight
            )
        elif role == SlideRole.TIP4:
            score += 0.10 * metrics.outdoor_score
        if metrics.has_visual_luxury:
            score -= 0.06
        return score

    def _score_type_3_hook(self, media: MediaCandidate) -> float:
        metrics = media.metrics
        if metrics is None:
            return 0.0
        if self._is_landscape_media(media):
            return 0.0

        type_2_hook_score = self._score_type_2(media, SlideRole.HOOK)
        fallback_portrait = (
            type_2_hook_score <= 0
            and metrics.quality_score >= 0.28
            and self._is_type_3_fallback_portrait_hook(metrics)
        )
        if type_2_hook_score <= 0 and not fallback_portrait:
            return 0.0

        person_or_hands = max(
            self._single_person_score(metrics),
            metrics.portrait_focus_score,
            metrics.body_focus_score,
            metrics.hands_score,
        )
        if fallback_portrait:
            person_or_hands = max(person_or_hands, 0.35)
        if person_or_hands <= 0:
            return 0.0

        score = (
            0.28 * metrics.quality_score
            + 0.24 * metrics.affluent_lifestyle_score
            + 0.18 * metrics.luxury_score
            + 0.14 * metrics.laptop_score
            + 0.12 * person_or_hands
            + 0.04 * metrics.daylight
            + 0.18 * min(type_2_hook_score, 1.0)
        )
        if metrics.laptop_score > 0 and person_or_hands > 0:
            score += 0.18
        if metrics.has_visual_luxury:
            score += 0.08
        return score

    def _is_type_3_fallback_portrait_hook(self, metrics: ImageMetrics) -> bool:
        portrait_shape = metrics.aspect_ratio <= 0.92
        affluent_square = (
            metrics.aspect_ratio <= 1.0
            and max(metrics.affluent_lifestyle_score, metrics.luxury_score) >= 0.55
        )
        return (
            metrics.faces == 0
            and metrics.quality_score >= 0.52
            and metrics.daylight >= 0.38
            and (portrait_shape or affluent_square)
            and not metrics.is_landscape
            and metrics.laptop_score < 0.75
            and metrics.hands_score < 0.75
        )

    def _score_extra_image(self, media: MediaCandidate, video_type: VideoType) -> float:
        if self._is_landscape_media(media) or not self._is_person_visible_media(media):
            return 0.0
        if video_type == VideoType.TYPE_1:
            return max(
                self._score_type_1(media, SlideRole.HOOK),
                self._score_type_1(media, SlideRole.OCTOBER),
                self._score_type_1(media, SlideRole.MARCH),
            )
        if video_type == VideoType.TYPE_2:
            return max(
                self._score_type_2(media, SlideRole.HOOK),
                self._score_type_2(media, SlideRole.TIP1),
                self._score_type_2(media, SlideRole.TIP4),
            )
        return self._score_type_3_hook(media)

    def _score_plan_compatible_extra_image(
        self,
        media: MediaCandidate,
        video_type: VideoType,
    ) -> float:
        if video_type == VideoType.TYPE_1:
            if not (
                self._is_type_1_person_visible_media(media)
                or self._is_landscape_media(media)
            ):
                return 0.0
            return max(
                self._score_type_1(media, SlideRole.HOOK),
                self._score_type_1(media, SlideRole.OCTOBER),
                self._score_type_1(media, SlideRole.MARCH),
            )
        if video_type == VideoType.TYPE_2:
            if not self._is_type_2_user_visible_media(media):
                return 0.0
            return max(
                self._score_type_2(media, SlideRole.HOOK),
                self._score_type_2(media, SlideRole.TIP1),
                self._score_type_2(media, SlideRole.TIP4),
            )
        return self._score_type_3_hook(media)

    def _post_key(self, media: MediaCandidate) -> str:
        # source_id is built as "<user>:<shortcode>:<node_index>". Two
        # images that share the first two segments come from the same post
        # (carousel / multi-variant), so they are effectively the same shot.
        parts = media.source_id.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
        return media.source_id

    def _exclude_ids_by_post(
        self,
        picked: dict[SlideRole, MediaCandidate],
        available: list[MediaCandidate],
    ) -> set[str]:
        # Expand the per-slide exclusion so we skip every sibling image
        # from any post already picked (blocks "same photo zoomed in").
        picked_post_keys = {self._post_key(m) for m in picked.values()}
        if not picked_post_keys:
            return set()
        return {
            candidate.source_id
            for candidate in available
            if self._post_key(candidate) in picked_post_keys
        }

    def _exclude_exact_ids(
        self,
        picked: dict[SlideRole, MediaCandidate],
    ) -> set[str]:
        return {media.source_id for media in picked.values()}

    def _is_extreme_luxury(self, media: MediaCandidate) -> bool:
        lowered = (media.caption or "").lower()
        return any(_word_in_text(keyword, lowered) or keyword in lowered for keyword in EXTREME_LUXURY_KEYWORDS)

    def _is_landscape_media(self, media: MediaCandidate) -> bool:
        if not media.metrics:
            return False
        metrics = media.metrics
        if metrics.is_landscape:
            return True
        if self._has_person_signal(media):
            return False

        lowered = (media.caption or "").lower()
        landscape_by_caption = any(
            _word_in_text(keyword, lowered) or keyword in lowered
            for keyword in LANDSCAPE_KEYWORDS
        )
        scenic_score = max(metrics.sky_ratio, metrics.outdoor_score)
        return scenic_score >= 0.62 or (
            landscape_by_caption and scenic_score >= 0.35
        )

    def _is_candidate_used(self, media: MediaCandidate) -> bool:
        keys = self._reservation_keys([media])
        if self._used_media_snapshot is not None:
            return self.state.any_media_used_in_snapshot(
                keys,
                self._used_media_snapshot,
            )
        return self.state.any_media_used(keys)

    def _reservation_keys(self, media_items) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for media in media_items:
            for key in (
                media.source_id,
                *media.content_fingerprints,
                media.content_fingerprint,
            ):
                if not key or key in seen:
                    continue
                seen.add(key)
                keys.append(key)
        return keys

    def _first_image_is_valid(self, media: MediaCandidate) -> bool:
        if media.metrics is None:
            return False
        if (
            media.metrics.quality_score >= 0.38
            and media.metrics.daylight >= 0.35
            and self._has_person_signal(media)
        ):
            return True
        return self._is_high_quality_portrait_without_detected_face(media.metrics)

    def _first_type_1_image_is_valid(self, media: MediaCandidate) -> bool:
        return (
            self._first_image_is_valid(media)
            and self._is_type_1_person_visible_media(media)
        )

    def _is_high_quality_portrait_without_detected_face(self, metrics: ImageMetrics) -> bool:
        return (
            metrics.faces == 0
            and metrics.quality_score >= 0.58
            and metrics.daylight >= 0.50
            and metrics.aspect_ratio <= 0.92
            and not metrics.is_landscape
        )

    def _single_person_score(self, metrics: ImageMetrics) -> float:
        if not self._metrics_have_person_signal(metrics):
            return 0.0
        if metrics.faces <= 0:
            return max(0.55, min(0.85, metrics.body_focus_score))
        if metrics.faces == 1:
            return 1.0
        if metrics.faces == 2:
            return 0.72
        return 0.45

    def _build_fixed_media(self) -> MediaCandidate:
        if self._fixed_media_cache is not None:
            return self._fixed_media_cache
        fixed_path = self.settings.fixed_image_path
        if not fixed_path.exists():
            raise FileNotFoundError(
                "No encuentro la imagen fija requerida en "
                f"{fixed_path}. "
                "Coloca tip3_dropradar.jpg en assets/fixed/ o ajusta FIXED_IMAGE_PATH."
            )
        fixed_id = fixed_path.stem
        with Image.open(fixed_path) as fixed_image:
            width, height = fixed_image.size
        candidate = MediaCandidate(
            source_account="fixed",
            source_id=f"fixed:{fixed_id}",
            local_path=fixed_path,
            permalink=f"fixed://{fixed_id}",
            caption=fixed_path.name,
            width=width,
            height=height,
            created_at="fixed",
        )
        candidate.metrics = self._analyze_image(candidate)
        self._fixed_media_cache = candidate
        return candidate

    def _build_type_2_tip3_fixed_media(self) -> MediaCandidate:
        if self._type_2_tip3_fixed_media_cache is not None:
            return self._type_2_tip3_fixed_media_cache

        fixed_path = self.settings.fixed_assets_dir / TYPE_2_TIP3_FIXED_IMAGE_NAME
        if not fixed_path.exists():
            raise FileNotFoundError(
                "No encuentro la imagen fija requerida para el consejo 3 "
                f"del tipo 2 en {fixed_path}. "
                f"Coloca {TYPE_2_TIP3_FIXED_IMAGE_NAME} en assets/fixed/."
            )
        with Image.open(fixed_path) as fixed_image:
            width, height = fixed_image.size
        candidate = MediaCandidate(
            source_account="fixed",
            source_id="fixed:tip3_dropradar",
            local_path=fixed_path,
            permalink="fixed://tip3_dropradar",
            caption=TYPE_2_TIP3_FIXED_IMAGE_NAME,
            width=width,
            height=height,
            created_at="fixed",
        )
        candidate.metrics = self._analyze_image(candidate)
        self._type_2_tip3_fixed_media_cache = candidate
        return candidate

    def _build_parkez_fixed_media(
        self,
        gender: VideoGender,
    ) -> MediaCandidate:
        cached = self._parkez_fixed_media_cache.get(gender)
        if cached is not None:
            return cached

        fixed_path = self.settings.fixed_assets_dir / parkez_fixed_image_name(gender)
        if not fixed_path.exists():
            raise FileNotFoundError(
                "Falta la imagen fija de ParkEz en "
                f"{fixed_path}."
            )
        with Image.open(fixed_path) as fixed_image:
            width, height = fixed_image.size
        candidate = MediaCandidate(
            source_account="fixed",
            source_id=f"fixed:parkez:{gender.value}",
            local_path=fixed_path,
            permalink=f"fixed://parkez/{gender.value}",
            caption=fixed_path.name,
            width=width,
            height=height,
            created_at="fixed",
        )
        self._parkez_fixed_media_cache[gender] = candidate
        return candidate

    def _type_3_backgrounds(self) -> tuple[MediaCandidate, ...]:
        if self._type_3_backgrounds_cache is not None:
            return self._type_3_backgrounds_cache
        backgrounds_dir = self.settings.root_dir / "tipo3" / "fondocolores"
        if not backgrounds_dir.exists():
            backgrounds_dir = self.settings.root_dir / "tipo3" / "colores"
        if not backgrounds_dir.exists():
            raise FileNotFoundError(
                "No encuentro la carpeta de fondos para tipo 3. "
                "Crea tipo3/fondocolores o tipo3/colores."
            )

        paths = [
            path
            for path in sorted(backgrounds_dir.iterdir(), key=lambda item: item.name.lower())
            if path.is_file() and path.suffix.lower() in TYPE_3_BACKGROUND_EXTENSIONS
        ]
        if not paths:
            raise FileNotFoundError(
                f"No encontré fondos válidos en {backgrounds_dir}."
            )

        backgrounds: list[MediaCandidate] = []
        for index, path in enumerate(paths):
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError):
                LOGGER.warning("Fondo tipo3 no legible, lo salto: %s", path)
                continue
            backgrounds.append(
                MediaCandidate(
                    source_account="tipo3_fondo",
                    source_id=f"tipo3_fondo:{index}",
                    local_path=path,
                    permalink=f"asset://{path.name}",
                    caption=path.stem,
                    width=width,
                    height=height,
                    created_at="fixed",
                )
            )

        if not backgrounds:
            raise FileNotFoundError(
                f"No pude abrir ningún fondo válido en {backgrounds_dir}."
            )
        self._type_3_backgrounds_cache = tuple(backgrounds)
        return self._type_3_backgrounds_cache

    def _keyword_score(self, text: str, keywords: set[str]) -> float:
        lowered = (text or "").lower()
        if not lowered:
            return 0.0
        matches = 0
        for keyword in keywords:
            if " " in keyword:
                if keyword in lowered:
                    matches += 1
            elif _word_in_text(keyword, lowered):
                matches += 1
        return min(matches / 2.0, 1.0)

    def _normalize(self, value: float, *, low: float, high: float) -> float:
        if math.isclose(high, low):
            return 0.0
        return max(0.0, min(1.0, (value - low) / (high - low)))
