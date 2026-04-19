from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.models import (
    ImageMetrics,
    Language,
    MediaCandidate,
    SlidePlan,
    SlideRole,
    TYPE_1_ROLES,
    TYPE_2_ROLES,
    VideoPlan,
    VideoType,
)
from app.state import StateStore


LOGGER = logging.getLogger(__name__)


CASUAL_KEYWORDS = {
    "selfie", "gym", "beach", "travel", "sunset", "holiday", "vacation", "trip",
    "playa", "viaje", "verano", "mirror", "friends", "friend", "weekend",
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
}
EXTREME_LUXURY_KEYWORDS = {
    "private jet", "bugatti", "lamborghini", "ferrari", "mclaren", "maybach",
    "rolls royce", "yacht", "richard mille",
}

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
        return self._create_type_2_plan(catalog, language)

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
                if not self.state.is_media_used(candidate.source_id)
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
                used_media_ids=[media.source_id for media in picked.values()],
                fallback_accounts=fallback_accounts,
            )
            ranked.append((sum(role_scores.values()), plan))

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
                if not self.state.is_media_used(candidate.source_id)
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
            if not hook_media.metrics or hook_media.metrics.faces < 1:
                LOGGER.info("tipo2 @%s: hook sin cara detectada", account)
                continue

            fallback_accounts: list[str] = []
            if not any(self._is_landscape_media(media) for media in picked.values()):
                replaced = self._inject_landscape(
                    picked,
                    role_scores,
                    catalog,
                    selected_account=account,
                    replaceable_roles=TYPE_2_REPLACEABLE_FOR_LANDSCAPE,
                    allow_luxury=True,
                )
                if replaced and replaced.source_account != account:
                    fallback_accounts.append(replaced.source_account)
                elif not replaced:
                    LOGGER.info(
                        "tipo2 @%s: sin paisaje disponible, sigo con las picks actuales",
                        account,
                    )

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
                used_media_ids=[media.source_id for media in picked.values()],
                fallback_accounts=fallback_accounts,
            )
            ranked.append((sum(role_scores.values()), plan))

        if not ranked:
            raise ValueError(
                "No encontré suficientes fotos válidas para un video tipo 2 sin reutilizar imágenes."
            )
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return ranked[0][1]

    # ------------------------------------------------------------------
    # Helpers — composition
    # ------------------------------------------------------------------

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
        used_ids = {item.source_id for item in picked.values()}
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
                continue
            try:
                media.metrics = self._analyze_image(media)
            except (UnidentifiedImageError, OSError, ValueError) as error:
                LOGGER.warning(
                    "Skipping unreadable image %s: %s", media.local_path, error
                )
                media.metrics = None

    def _analyze_image(self, media: MediaCandidate) -> ImageMetrics:
        with Image.open(media.local_path) as raw:
            image = raw.convert("RGB")
            rgb = np.asarray(image)

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        brightness = float(np.mean(gray))
        daylight = self._normalize(brightness, low=85.0, high=190.0)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness_score = self._normalize(sharpness, low=60.0, high=900.0)
        faces = self._detect_faces(gray)
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
        )

    def _detect_faces(self, gray: np.ndarray) -> int:
        if self._face_detector.empty():
            return 0
        detected = self._face_detector.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(80, 80),
        )
        return int(len(detected))

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
        best: CandidateScore | None = None
        for media in pool:
            if media.source_id in exclude_ids:
                continue
            if media.metrics is None:
                continue
            score = score_fn(media)
            if score <= 0:
                continue
            if best is None or score > best.score:
                best = CandidateScore(media=media, score=score)
        return best

    def _find_landscape_replacement(
        self,
        catalog: dict[str, list[MediaCandidate]],
        *,
        used_ids: set[str],
        used_post_keys: set[str],
        allow_luxury: bool,
        prefer_account: str | None = None,
    ) -> CandidateScore | None:
        best: CandidateScore | None = None
        for account, candidates in catalog.items():
            for media in candidates:
                if media.source_id in used_ids:
                    continue
                if self._post_key(media) in used_post_keys:
                    continue
                if self.state.is_media_used(media.source_id):
                    continue
                if not media.metrics or not self._is_landscape_media(media):
                    continue
                if not allow_luxury and self._is_extreme_luxury(media):
                    continue
                metrics = media.metrics
                base = 0.55 * metrics.quality_score + 0.35 * metrics.outdoor_score + 0.10 * metrics.daylight
                if account == prefer_account:
                    base += 0.05
                if best is None or base > best.score:
                    best = CandidateScore(media=media, score=base)
        return best

    def _score_type_1(self, media: MediaCandidate, role: SlideRole) -> float:
        metrics = media.metrics
        if metrics is None:
            return 0.0
        if self._is_extreme_luxury(media):
            return -1.0

        score = (
            0.40 * metrics.quality_score
            + 0.18 * metrics.casual_score
            + 0.14 * metrics.outdoor_score
            + 0.14 * min(metrics.faces, 2) / 2.0
            - 0.18 * metrics.luxury_score
        )
        if metrics.has_visual_luxury:
            score -= 0.15
        if role == SlideRole.HOOK:
            score += 0.14 * metrics.daylight + 0.18 * min(metrics.faces, 2) / 2.0
            if metrics.is_landscape:
                score -= 0.10
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
        score = (
            0.30 * metrics.quality_score
            + 0.30 * metrics.luxury_score
            + 0.12 * metrics.outdoor_score
            + 0.10 * min(metrics.faces, 2) / 2.0
        )
        if metrics.has_visual_luxury:
            score += 0.10
        if role == SlideRole.HOOK:
            if metrics.faces < 1:
                return -1.0
            score += 0.22 * min(metrics.faces, 2) / 2.0 + 0.08 * metrics.daylight
        elif role == SlideRole.TIP4:
            score += 0.08 * metrics.outdoor_score
        elif metrics.is_landscape:
            score += 0.08
        return score

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

    def _first_image_is_valid(self, media: MediaCandidate) -> bool:
        if media.metrics is None:
            return False
        # Slightly relaxed thresholds so studio-lit but well-exposed shots pass,
        # while still ruling out under-exposed night shots.
        return media.metrics.quality_score >= 0.38 and media.metrics.daylight >= 0.40

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
