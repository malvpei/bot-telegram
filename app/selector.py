from __future__ import annotations

import logging
import math
import random
import re
import hashlib
from dataclasses import dataclass, replace
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
    VideoPlan,
    VideoType,
)
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
        self._face_detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        video_type: VideoType,
        language: Language,
    ) -> VideoPlan:
        # Pre-compute metrics once per candidate before any per-account loop.
        for items in catalog.values():
            self._prepare_candidates(items)

        if video_type == VideoType.TYPE_1:
            return self._create_type_1_plan(catalog, language)
        if video_type == VideoType.TYPE_2:
            return self._create_type_2_plan(catalog, language)
        return self._create_type_3_plan(catalog, language)

    def pick_extra_image(
        self,
        media_items: list[MediaCandidate],
        video_type: VideoType,
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
        if best is None:
            raise ValueError(
                "No encontré otra imagen válida de esa cuenta sin repetir."
            )
        return best.media

    def reservation_keys_for(self, media_items) -> list[str]:
        return self._reservation_keys(media_items)

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
                and not self._is_extreme_luxury(candidate)
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

            non_fixed_roles = [role for role in TYPE_1_ROLES if role != SlideRole.FEBRUARY]
            picked: dict[SlideRole, MediaCandidate] = {}
            role_scores: dict[SlideRole, float] = {}

            for role in non_fixed_roles:
                exclude = self._exclude_ids_by_post(picked, available)
                best = self._pick_best(
                    available,
                    exclude_ids=exclude,
                    score_fn=lambda media, current_role=role: self._score_type_1(
                        media, current_role
                    ),
                )
                if best is None:
                    break
                picked[role] = best.media
                role_scores[role] = best.score

            if len(picked) != len(non_fixed_roles):
                LOGGER.info(
                    "tipo1 @%s: solo pude elegir %d/%d slides (pool=%d)",
                    account,
                    len(picked),
                    len(non_fixed_roles),
                    len(available),
                )
                continue

            if not self._first_image_is_valid(picked[SlideRole.HOOK]):
                LOGGER.info("tipo1 @%s: hook no pasa el umbral de calidad", account)
                continue

            fallback_accounts: list[str] = []
            if not any(self._is_landscape_media(media) for media in picked.values()):
                replaced = self._inject_landscape(
                    picked,
                    role_scores,
                    catalog,
                    selected_account=account,
                    replaceable_roles=TYPE_1_REPLACEABLE_FOR_LANDSCAPE,
                    allow_luxury=False,
                )
                if replaced and replaced.source_account != account:
                    fallback_accounts.append(replaced.source_account)
                elif not replaced:
                    LOGGER.info(
                        "tipo1 @%s: sin paisaje disponible, sigo con las picks actuales",
                        account,
                    )

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
                "No encontré suficientes fotos válidas para un video tipo 1 sin reutilizar imágenes."
            )
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return ranked[0][1]

    # ------------------------------------------------------------------
    # Type 2
    # ------------------------------------------------------------------

    def _create_type_2_plan(
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
                exclude = self._exclude_ids_by_post(picked, available)
                best = self._pick_best(
                    available,
                    exclude_ids=exclude,
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

            hook_media = picked[SlideRole.HOOK]
            if not self._is_type_2_user_visible_media(hook_media):
                LOGGER.info("tipo2 @%s: hook sin usuario visible", account)
                continue

            if not self._enforce_type_2_user_visibility(
                account,
                picked, role_scores, available,
                replaceable_roles=TYPE_2_REPLACEABLE_FOR_LANDSCAPE,
            ):
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

    def _create_type_3_plan(
        self,
        catalog: dict[str, list[MediaCandidate]],
        language: Language,
    ) -> VideoPlan:
        backgrounds = self._type_3_backgrounds()
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
            background_index = sum(ord(char) for char in account) % len(backgrounds)
            background = backgrounds[background_index]
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

    def _enforce_type_2_user_visibility(
        self,
        account: str,
        picked: dict[SlideRole, MediaCandidate],
        role_scores: dict[SlideRole, float],
        available: list[MediaCandidate],
        *,
        replaceable_roles: tuple[SlideRole, ...],
    ) -> bool:
        non_user_roles = [
            role for role, media in picked.items()
            if self._is_type_2_non_user_media(media) and role in replaceable_roles
        ]
        if len(non_user_roles) <= 1:
            return True

        non_user_roles.sort(key=lambda role: role_scores.get(role, 0.0), reverse=True)
        for role in non_user_roles[1:]:
            original = picked[role]
            exclude = self._exclude_ids_by_post(picked, available)
            replacement = self._pick_best(
                available,
                exclude_ids=exclude,
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
            if self._is_type_2_non_user_media(media) and role in replaceable_roles
        ]
        if len(remaining) > 1:
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
        if not media.metrics:
            return False
        metrics = media.metrics
        if metrics.faces >= 1:
            return True
        return metrics.face_area_ratio > 0 and metrics.portrait_focus_score >= 0.22

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

    def _prepare_candidates(self, media_items: list[MediaCandidate]) -> None:
        for media in media_items:
            if media.metrics is not None:
                if not media.content_fingerprints:
                    try:
                        media.content_fingerprints = self._fingerprint_images(media)
                        media.content_fingerprint = media.content_fingerprints[0]
                    except (UnidentifiedImageError, OSError, ValueError) as error:
                        LOGGER.warning(
                            "Skipping unreadable image %s: %s", media.local_path, error
                        )
                        media.metrics = None
                continue
            try:
                media.metrics = self._analyze_image(media)
                media.content_fingerprints = self._fingerprint_images(media)
                media.content_fingerprint = media.content_fingerprints[0]
            except (UnidentifiedImageError, OSError, ValueError) as error:
                LOGGER.warning(
                    "Skipping unreadable image %s: %s", media.local_path, error
                )
                media.metrics = None
                media.content_fingerprint = None
                media.content_fingerprints = []

    def _analyze_image(self, media: MediaCandidate) -> ImageMetrics:
        rgb = self._open_image_rgb_array(media)

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
        digest = hashlib.sha256()
        digest.update(str(image.size).encode("ascii"))
        digest.update(image.tobytes())
        return [f"sha256:{digest.hexdigest()}"]

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
    ) -> CandidateScore | None:
        scored: list[CandidateScore] = []
        for media in pool:
            if media.source_id in exclude_ids:
                continue
            if media.metrics is None:
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
        if self._is_extreme_luxury(media):
            return -1.0

        # TYPE_1 es historia personal, la cara del creador es lo que engancha.
        # Cuantas más caras visibles, mejor; hook sin cara se penaliza duro.
        face_score = min(metrics.faces, 3) / 3.0
        portrait_score = metrics.portrait_focus_score
        score = (
            0.24 * metrics.quality_score
            + 0.10 * metrics.casual_score
            + 0.08 * metrics.outdoor_score
            + 0.24 * face_score
            + 0.22 * portrait_score
            - 0.18 * metrics.luxury_score
        )
        if metrics.has_visual_luxury:
            score -= 0.15
        if role == SlideRole.HOOK:
            if metrics.faces < 1:
                score -= 0.55
            score += (
                0.10 * metrics.daylight
                + 0.18 * face_score
                + 0.30 * portrait_score
            )
            if metrics.is_landscape:
                score -= 0.28
        elif role == SlideRole.MARCH:
            # March is the closing slide, slight bump for upbeat outdoor shots.
            score += 0.05 * metrics.outdoor_score
        elif metrics.is_landscape:
            score += 0.05
        return score

    def _score_type_2(self, media: MediaCandidate, role: SlideRole) -> float:
        metrics = media.metrics
        if metrics is None:
            return 0.0
        # TYPE_2 tiene que vender "me ha ido bien": lifestyle alto, old money
        # y una sensación de éxito del usuario, no solo objetos bonitos.
        face_score = min(metrics.faces, 2) / 2.0
        landscape_penalty = 0.22 if self._is_landscape_dominant_media(media) else 0.0
        score = (
            0.22 * metrics.quality_score
            + 0.32 * metrics.affluent_lifestyle_score
            + 0.16 * metrics.luxury_score
            + 0.08 * metrics.daylight
            + 0.10 * metrics.outdoor_score
            + 0.12 * metrics.portrait_focus_score
            + 0.06 * face_score
            - 0.18 * metrics.casual_score
            - landscape_penalty
        )
        if metrics.has_visual_luxury:
            score += 0.10
        if role == SlideRole.HOOK:
            if metrics.faces < 1:
                return -1.0
            score += (
                0.20 * face_score
                + 0.26 * metrics.portrait_focus_score
                + 0.08 * metrics.daylight
            )
            if self._is_landscape_dominant_media(media):
                # Hook debe ser retrato con cara, el paisaje va en un tip.
                score -= 0.35
        elif role == SlideRole.TIP4:
            score += 0.10 * metrics.outdoor_score
            if self._is_landscape_dominant_media(media):
                score += 0.08
        elif self._is_landscape_dominant_media(media):
            score -= 0.08
        return score

    def _score_type_3_hook(self, media: MediaCandidate) -> float:
        metrics = media.metrics
        if metrics is None:
            return 0.0
        if metrics.quality_score < 0.28:
            return 0.0

        person_or_hands = max(
            min(metrics.faces, 2) / 2.0,
            metrics.portrait_focus_score,
            metrics.hands_score,
        )
        if person_or_hands <= 0 and metrics.laptop_score <= 0:
            person_or_hands = 0.12 if not metrics.is_landscape else 0.0

        score = (
            0.28 * metrics.quality_score
            + 0.24 * metrics.affluent_lifestyle_score
            + 0.18 * metrics.luxury_score
            + 0.14 * metrics.laptop_score
            + 0.12 * person_or_hands
            + 0.04 * metrics.daylight
        )
        if metrics.laptop_score > 0 and person_or_hands > 0:
            score += 0.18
        if metrics.has_visual_luxury:
            score += 0.08
        if metrics.is_landscape and metrics.faces < 1 and metrics.laptop_score <= 0:
            score -= 0.18
        return score

    def _score_extra_image(self, media: MediaCandidate, video_type: VideoType) -> float:
        if video_type == VideoType.TYPE_1:
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

    def _is_extreme_luxury(self, media: MediaCandidate) -> bool:
        lowered = (media.caption or "").lower()
        return any(_word_in_text(keyword, lowered) or keyword in lowered for keyword in EXTREME_LUXURY_KEYWORDS)

    def _is_landscape_media(self, media: MediaCandidate) -> bool:
        return bool(media.metrics and media.metrics.is_landscape)

    def _is_candidate_used(self, media: MediaCandidate) -> bool:
        return self.state.any_media_used(self._reservation_keys([media]))

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
        return (
            media.metrics.quality_score >= 0.38
            and media.metrics.daylight >= 0.35
            and (
                media.metrics.faces >= 1
                or media.metrics.portrait_focus_score >= 0.18
            )
        )

    def _build_fixed_media(self) -> MediaCandidate:
        if not self.settings.fixed_image_path.exists():
            raise FileNotFoundError(
                "No encuentro la imagen fija requerida en "
                f"{self.settings.fixed_image_path}. "
                "Coloca imagen6.png en assets/fixed/ o ajusta FIXED_IMAGE_PATH."
            )
        with Image.open(self.settings.fixed_image_path) as fixed_image:
            width, height = fixed_image.size
        candidate = MediaCandidate(
            source_account="fixed",
            source_id="fixed:imagen6",
            local_path=self.settings.fixed_image_path,
            permalink="fixed://imagen6",
            caption="imagen6.png",
            width=width,
            height=height,
            created_at="fixed",
        )
        candidate.metrics = self._analyze_image(candidate)
        return candidate

    def _type_3_backgrounds(self) -> list[MediaCandidate]:
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
            candidate = MediaCandidate(
                source_account="tipo3_fondo",
                source_id=f"tipo3_fondo:{index}",
                local_path=path,
                permalink=f"asset://{path.name}",
                caption=path.stem,
                width=self.settings.width,
                height=self.settings.height,
                created_at="fixed",
            )
            try:
                candidate.metrics = self._analyze_image(candidate)
            except (UnidentifiedImageError, OSError, ValueError):
                LOGGER.warning("Fondo tipo3 no legible, lo salto: %s", path)
                continue
            backgrounds.append(candidate)

        if not backgrounds:
            raise FileNotFoundError(
                f"No pude abrir ningún fondo válido en {backgrounds_dir}."
            )
        return backgrounds

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
