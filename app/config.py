from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_ACCOUNT_PICK_ATTEMPTS = 24
DEFAULT_POOL_REFILL_MAX_FRESH_ACCOUNTS = 8
DEFAULT_R2_IMAGE_PREFIX = "videos/imagenes"
DEFAULT_UPLOAD_SITE_ENABLED = True
DEFAULT_UPLOAD_SITE_HOST = "0.0.0.0"
DEFAULT_UPLOAD_SITE_PORT = 8000
DEFAULT_UPLOAD_SITE_USERNAME = "admin"
DEFAULT_UPLOAD_SITE_PASSWORD = "pon_una_password"
DEFAULT_UPLOAD_SITE_MAX_IMAGE_MB = 20
DEFAULT_IMAGE_PROVIDER = "fal"
DEFAULT_FAL_MODEL = "fal-ai/flux-pro/kontext"
DEFAULT_FAL_IMAGE_ASPECT_RATIO = "9:16"
DEFAULT_FAL_OUTPUT_FORMAT = "png"
DEFAULT_FAL_SAFETY_TOLERANCE = "2"
DEFAULT_FAL_GUIDANCE_SCALE = 3.5
DEFAULT_FAL_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_FAL_REQUEST_TIMEOUT_SECONDS = 240.0
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
DEFAULT_OPENAI_IMAGE_SIZE = "1024x1536"
DEFAULT_OPENAI_IMAGE_QUALITY = "high"
DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS = 180.0


def _split_chat_ids(raw_value: str) -> set[int]:
    chat_ids: set[int] = set()
    for piece in raw_value.split(","):
        value = piece.strip()
        if not value:
            continue
        try:
            chat_ids.add(int(value))
        except ValueError:
            continue
    return chat_ids


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(key: str, default: Path, root_dir: Path) -> Path:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    path = Path(raw)
    if path.is_absolute():
        return path
    return root_dir / path


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    app_dir: Path
    data_dir: Path
    downloads_dir: Path
    outputs_dir: Path
    state_dir: Path
    template_videos_dir: Path
    r2_downloads_dir: Path
    fixed_assets_dir: Path
    fonts_dir: Path
    telegram_bot_token: str
    allowed_chat_ids: set[int]
    instagram_username: str | None
    instagram_password: str | None
    instagram_session_path: Path
    fixed_image_path: Path
    accounts_file: Path
    women_accounts_file: Path
    max_posts_per_account: int
    width: int
    height: int
    fps: int
    slide_seconds: float
    transition_seconds: float
    max_urls_per_job: int
    max_video_size_mb: int
    history_max_per_bucket: int
    download_retries: int
    download_backoff_seconds: float
    output_retention_days: int
    account_cache_ttl_hours: int
    account_pick_attempts: int
    pool_target_images: int
    pool_low_stock_threshold: int
    pool_refill_max_fresh_accounts: int
    account_cooldown_days: int
    ig_sessionid: str
    ig_ds_user_id: str
    ig_csrftoken: str
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    r2_endpoint_url: str
    r2_input_prefix: str
    r2_image_prefix: str
    upload_site_enabled: bool
    upload_site_host: str
    upload_site_port: int
    upload_site_username: str
    upload_site_password: str
    upload_site_max_image_mb: int
    image_provider: str
    fal_key: str
    fal_model: str
    fal_image_aspect_ratio: str
    fal_output_format: str
    fal_safety_tolerance: str
    fal_guidance_scale: float
    fal_poll_interval_seconds: float
    fal_request_timeout_seconds: float
    openai_api_key: str
    openai_image_model: str
    openai_image_size: str
    openai_image_quality: str
    openai_request_timeout_seconds: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")

    data_dir = _env_path("DATA_DIR", root_dir / "data", root_dir)
    downloads_dir = data_dir / "downloads"
    outputs_dir = data_dir / "outputs"
    state_dir = data_dir / "state"
    template_videos_dir = _env_path(
        "TEMPLATE_VIDEOS_DIR",
        data_dir / "template_videos",
        root_dir,
    )
    r2_downloads_dir = data_dir / "r2_downloads"
    fixed_assets_dir = root_dir / "assets" / "fixed"
    fonts_dir = root_dir / "assets" / "fonts"

    fixed_image_path = _env_path(
        "FIXED_IMAGE_PATH",
        fixed_assets_dir / "tip3_dropradar.jpg",
        root_dir,
    )

    instagram_session_path = _env_path(
        "INSTAGRAM_SESSION_PATH",
        state_dir / "instagram_session",
        root_dir,
    )

    accounts_file = _env_path("ACCOUNTS_FILE", root_dir / "accounts.txt", root_dir)
    women_accounts_file = _env_path(
        "WOMEN_ACCOUNTS_FILE",
        root_dir / "accounts_women.txt",
        root_dir,
    )

    return Settings(
        root_dir=root_dir,
        app_dir=root_dir / "app",
        data_dir=data_dir,
        downloads_dir=downloads_dir,
        outputs_dir=outputs_dir,
        state_dir=state_dir,
        template_videos_dir=template_videos_dir,
        r2_downloads_dir=r2_downloads_dir,
        fixed_assets_dir=fixed_assets_dir,
        fonts_dir=fonts_dir,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        allowed_chat_ids=_split_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")),
        instagram_username=os.getenv("INSTAGRAM_USERNAME", "").strip() or None,
        instagram_password=os.getenv("INSTAGRAM_PASSWORD", "").strip() or None,
        instagram_session_path=instagram_session_path,
        fixed_image_path=fixed_image_path,
        accounts_file=accounts_file,
        women_accounts_file=women_accounts_file,
        max_posts_per_account=_env_int("MAX_POSTS_PER_ACCOUNT", 100),
        width=_env_int("VIDEO_WIDTH", 1080),
        height=_env_int("VIDEO_HEIGHT", 1920),
        fps=_env_int("VIDEO_FPS", 30),
        slide_seconds=_env_float("SLIDE_SECONDS", 3.8),
        transition_seconds=_env_float("TRANSITION_SECONDS", 0.35),
        max_urls_per_job=_env_int("MAX_URLS_PER_JOB", 8),
        max_video_size_mb=_env_int("MAX_VIDEO_SIZE_MB", 48),
        history_max_per_bucket=_env_int("HISTORY_MAX_PER_BUCKET", 200),
        download_retries=_env_int("DOWNLOAD_RETRIES", 3),
        download_backoff_seconds=_env_float("DOWNLOAD_BACKOFF_SECONDS", 1.5),
        output_retention_days=_env_int("OUTPUT_RETENTION_DAYS", 7),
        account_cache_ttl_hours=_env_int("ACCOUNT_CACHE_TTL_HOURS", 0),
        account_pick_attempts=_env_int("ACCOUNT_PICK_ATTEMPTS", DEFAULT_ACCOUNT_PICK_ATTEMPTS),
        pool_target_images=_env_int("POOL_TARGET_IMAGES", 100),
        pool_low_stock_threshold=_env_int("POOL_LOW_STOCK_THRESHOLD", 12),
        pool_refill_max_fresh_accounts=_env_int(
            "POOL_REFILL_MAX_FRESH_ACCOUNTS",
            DEFAULT_POOL_REFILL_MAX_FRESH_ACCOUNTS,
        ),
        account_cooldown_days=_env_int("ACCOUNT_COOLDOWN_DAYS", 30),
        ig_sessionid=os.getenv("IG_SESSIONID", "").strip(),
        ig_ds_user_id=os.getenv("IG_DS_USER_ID", "").strip(),
        ig_csrftoken=os.getenv("IG_CSRFTOKEN", "").strip(),
        r2_account_id=os.getenv("R2_ACCOUNT_ID", "").strip(),
        r2_access_key_id=os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        r2_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        r2_bucket=os.getenv("R2_BUCKET", "").strip(),
        r2_endpoint_url=os.getenv("R2_ENDPOINT_URL", "").strip(),
        r2_input_prefix=os.getenv("R2_INPUT_PREFIX", "").strip().lstrip("/"),
        r2_image_prefix=os.getenv("R2_IMAGE_PREFIX", DEFAULT_R2_IMAGE_PREFIX)
        .strip()
        .lstrip("/"),
        upload_site_enabled=_env_bool(
            "UPLOAD_SITE_ENABLED",
            DEFAULT_UPLOAD_SITE_ENABLED,
        ),
        upload_site_host=os.getenv(
            "UPLOAD_SITE_HOST",
            DEFAULT_UPLOAD_SITE_HOST,
        ).strip()
        or DEFAULT_UPLOAD_SITE_HOST,
        upload_site_port=_env_int("UPLOAD_SITE_PORT", DEFAULT_UPLOAD_SITE_PORT),
        upload_site_username=os.getenv(
            "UPLOAD_SITE_USERNAME",
            DEFAULT_UPLOAD_SITE_USERNAME,
        ).strip()
        or DEFAULT_UPLOAD_SITE_USERNAME,
        upload_site_password=os.getenv(
            "UPLOAD_SITE_PASSWORD",
            DEFAULT_UPLOAD_SITE_PASSWORD,
        ).strip()
        or DEFAULT_UPLOAD_SITE_PASSWORD,
        upload_site_max_image_mb=_env_int(
            "UPLOAD_SITE_MAX_IMAGE_MB",
            DEFAULT_UPLOAD_SITE_MAX_IMAGE_MB,
        ),
        image_provider=os.getenv("IMAGE_PROVIDER", DEFAULT_IMAGE_PROVIDER).strip().lower()
        or DEFAULT_IMAGE_PROVIDER,
        fal_key=os.getenv("FAL_KEY", "").strip(),
        fal_model=os.getenv("FAL_MODEL", DEFAULT_FAL_MODEL).strip()
        or DEFAULT_FAL_MODEL,
        fal_image_aspect_ratio=os.getenv(
            "FAL_IMAGE_ASPECT_RATIO",
            DEFAULT_FAL_IMAGE_ASPECT_RATIO,
        ).strip()
        or DEFAULT_FAL_IMAGE_ASPECT_RATIO,
        fal_output_format=os.getenv("FAL_OUTPUT_FORMAT", DEFAULT_FAL_OUTPUT_FORMAT)
        .strip()
        .lower()
        or DEFAULT_FAL_OUTPUT_FORMAT,
        fal_safety_tolerance=os.getenv(
            "FAL_SAFETY_TOLERANCE",
            DEFAULT_FAL_SAFETY_TOLERANCE,
        ).strip()
        or DEFAULT_FAL_SAFETY_TOLERANCE,
        fal_guidance_scale=_env_float("FAL_GUIDANCE_SCALE", DEFAULT_FAL_GUIDANCE_SCALE),
        fal_poll_interval_seconds=_env_float(
            "FAL_POLL_INTERVAL_SECONDS",
            DEFAULT_FAL_POLL_INTERVAL_SECONDS,
        ),
        fal_request_timeout_seconds=_env_float(
            "FAL_REQUEST_TIMEOUT_SECONDS",
            DEFAULT_FAL_REQUEST_TIMEOUT_SECONDS,
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_image_model=os.getenv(
            "OPENAI_IMAGE_MODEL",
            DEFAULT_OPENAI_IMAGE_MODEL,
        ).strip()
        or DEFAULT_OPENAI_IMAGE_MODEL,
        openai_image_size=os.getenv("OPENAI_IMAGE_SIZE", DEFAULT_OPENAI_IMAGE_SIZE).strip()
        or DEFAULT_OPENAI_IMAGE_SIZE,
        openai_image_quality=os.getenv(
            "OPENAI_IMAGE_QUALITY",
            DEFAULT_OPENAI_IMAGE_QUALITY,
        ).strip()
        or DEFAULT_OPENAI_IMAGE_QUALITY,
        openai_request_timeout_seconds=_env_float(
            "OPENAI_REQUEST_TIMEOUT_SECONDS",
            DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS,
        ),
    )
