from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class VideoType(str, Enum):
    TYPE_1 = "1"
    TYPE_2 = "2"
    TYPE_3 = "3"


class Language(str, Enum):
    ES = "es"
    EN = "en"


class SlideRole(str, Enum):
    HOOK = "hook"
    OCTOBER = "october"
    NOVEMBER = "november"
    DECEMBER = "december"
    JANUARY = "january"
    FEBRUARY = "february"
    MARCH = "march"
    TIP1 = "tip1"
    TIP2 = "tip2"
    TIP3 = "tip3"
    TIP4 = "tip4"
    TOOL_STORE = "tool_store"
    TOOL_PRODUCT_SEARCH = "tool_product_search"
    TOOL_SCRIPTS = "tool_scripts"
    TOOL_PAYMENTS = "tool_payments"
    TOOL_EDITING = "tool_editing"
    TOOL_MARKETING = "tool_marketing"


TYPE_1_ROLES: tuple[SlideRole, ...] = (
    SlideRole.HOOK,
    SlideRole.OCTOBER,
    SlideRole.NOVEMBER,
    SlideRole.DECEMBER,
    SlideRole.JANUARY,
    SlideRole.FEBRUARY,
    SlideRole.MARCH,
)

TYPE_2_ROLES: tuple[SlideRole, ...] = (
    SlideRole.HOOK,
    SlideRole.TIP1,
    SlideRole.TIP2,
    SlideRole.TIP3,
    SlideRole.TIP4,
)

TYPE_3_ROLES: tuple[SlideRole, ...] = (
    SlideRole.HOOK,
    SlideRole.TOOL_STORE,
    SlideRole.TOOL_PRODUCT_SEARCH,
    SlideRole.TOOL_SCRIPTS,
    SlideRole.TOOL_PAYMENTS,
    SlideRole.TOOL_EDITING,
    SlideRole.TOOL_MARKETING,
)

FIXED_ROLE_BY_TYPE: dict[VideoType, SlideRole] = {
    VideoType.TYPE_1: SlideRole.FEBRUARY,
    VideoType.TYPE_2: SlideRole.TIP3,
}


@dataclass
class VideoRequest:
    chat_id: int
    user_id: int
    video_type: VideoType
    language: Language
    account_inputs: list[str]


@dataclass
class ImageMetrics:
    brightness: float
    daylight: float
    sharpness: float
    faces: int
    aspect_ratio: float
    is_landscape: bool
    outdoor_score: float
    casual_score: float
    luxury_score: float
    quality_score: float
    has_visual_luxury: bool = False
    sky_ratio: float = 0.0
    face_area_ratio: float = 0.0
    face_center_score: float = 0.0
    portrait_focus_score: float = 0.0
    affluent_lifestyle_score: float = 0.0
    laptop_score: float = 0.0
    hands_score: float = 0.0


@dataclass
class MediaCandidate:
    source_account: str
    source_id: str
    local_path: Path
    permalink: str
    caption: str
    width: int
    height: int
    created_at: str
    metrics: ImageMetrics | None = None


@dataclass
class SlidePlan:
    index: int
    role: SlideRole
    text: str
    media: MediaCandidate
    fixed_asset: bool = False


@dataclass
class ScriptPackage:
    slides_by_role: dict[SlideRole, str]
    ordered_slides: list[str]
    signature: str
    plain_text: str


@dataclass
class VideoPlan:
    chosen_account: str
    video_type: VideoType
    language: Language
    slides: list[SlidePlan]
    used_media_ids: list[str] = field(default_factory=list)
    fallback_accounts: list[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    video_path: Path
    script_path: Path
    preview_text: str
    chosen_account: str
    video_type: VideoType
    language: Language
    fallback_accounts: list[str]
    slides: list[SlidePlan] = field(default_factory=list)
