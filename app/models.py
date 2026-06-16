from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class VideoType(str, Enum):
    TYPE_1 = "1"
    TYPE_2 = "2"
    TYPE_3 = "3"
    TYPE_4 = "4"


class VideoGender(str, Enum):
    MALE = "male"
    FEMALE = "female"


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
    STORY_MCDONALD = "story_mcdonald"
    STORY_BUILDING_STORE = "story_building_store"
    STORY_FIRST_FAILURE = "story_first_failure"
    STORY_DEEP_FAILURE = "story_deep_failure"
    STORY_DROPRADAR = "story_dropradar"
    STORY_SUCCESS_COMIC = "story_success_comic"
    STORY_ORIGINAL_REFERENCE = "story_original_reference"


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

TYPE_4_ROLES: tuple[SlideRole, ...] = (
    SlideRole.STORY_MCDONALD,
    SlideRole.STORY_BUILDING_STORE,
    SlideRole.STORY_FIRST_FAILURE,
    SlideRole.STORY_DEEP_FAILURE,
    SlideRole.STORY_DROPRADAR,
    SlideRole.STORY_SUCCESS_COMIC,
    SlideRole.STORY_ORIGINAL_REFERENCE,
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
    gender: VideoGender = VideoGender.MALE
    skip_accounts: list[str] = field(default_factory=list)
    lowercase_text: bool = False
    reference_image_path: Path | None = None


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
    body_area_ratio: float = 0.0
    body_focus_score: float = 0.0


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
    content_fingerprint: str | None = None
    content_fingerprints: list[str] = field(default_factory=list)


@dataclass
class SlidePlan:
    index: int
    role: SlideRole
    text: str
    media: MediaCandidate
    fixed_asset: bool = False


@dataclass
class SocialCopy:
    title: str
    description: str
    hashtags: list[str]

    @property
    def hashtag_line(self) -> str:
        return " ".join(self.hashtags)

    @property
    def messages(self) -> list[str]:
        return [
            message
            for message in [self.title, self.description, self.hashtag_line]
            if message.strip()
        ]


@dataclass
class TemplateVideoResult:
    video_path: Path
    social_copy: SocialCopy
    queue_restarted: bool = False


@dataclass
class ScriptPackage:
    slides_by_role: dict[SlideRole, str]
    ordered_slides: list[str]
    signature: str
    plain_text: str
    social_copy: SocialCopy
    choice_key: str | None = None
    social_choice_key: str | None = None


@dataclass
class VideoPlan:
    chosen_account: str
    video_type: VideoType
    language: Language
    slides: list[SlidePlan]
    used_media_ids: list[str] = field(default_factory=list)
    fallback_accounts: list[str] = field(default_factory=list)
    type_3_background_id: str | None = None
    type_3_background_candidates: list[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    video_path: Path | None
    script_path: Path
    preview_text: str
    social_copy: SocialCopy
    chosen_account: str
    video_type: VideoType
    language: Language
    fallback_accounts: list[str]
    slides: list[SlidePlan] = field(default_factory=list)
    pool_remaining: int = 0
    pool_low_stock: bool = False
