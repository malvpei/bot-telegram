from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


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
    fixed_assets_dir: Path
    fonts_dir: Path
    telegram_bot_token: str
    allowed_chat_ids: set[int]
    instagram_username: str | None
    instagram_password: str | None
    instagram_session_path: Path
    fixed_image_path: Path
    accounts_file: Path
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
    ig_sessionid: str
    ig_ds_user_id: str
    ig_csrftoken: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")

    data_dir = _env_path("DATA_DIR", root_dir / "data", root_dir)
    downloads_dir = data_dir / "downloads"
    outputs_dir = data_dir / "outputs"
    state_dir = data_dir / "state"
    fixed_assets_dir = root_dir / "assets" / "fixed"
    fonts_dir = root_dir / "assets" / "fonts"

    fixed_image_path = _env_path(
        "FIXED_IMAGE_PATH",
        fixed_assets_dir / "imagen6.png",
        root_dir,
    )

    instagram_session_path = _env_path(
        "INSTAGRAM_SESSION_PATH",
        state_dir / "instagram_session",
        root_dir,
    )

    accounts_file = _env_path("ACCOUNTS_FILE", root_dir / "accounts.txt", root_dir)

    return Settings(
        root_dir=root_dir,
        app_dir=root_dir / "app",
        data_dir=data_dir,
        downloads_dir=downloads_dir,
        outputs_dir=outputs_dir,
        state_dir=state_dir,
        fixed_assets_dir=fixed_assets_dir,
        fonts_dir=fonts_dir,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        allowed_chat_ids=_split_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")),
        instagram_username=os.getenv("INSTAGRAM_USERNAME", "").strip() or None,
        instagram_password=os.getenv("INSTAGRAM_PASSWORD", "").strip() or None,
        instagram_session_path=instagram_session_path,
        fixed_image_path=fixed_image_path,
        accounts_file=accounts_file,
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
        account_cache_ttl_hours=_env_int("ACCOUNT_CACHE_TTL_HOURS", 72),
        account_pick_attempts=_env_int("ACCOUNT_PICK_ATTEMPTS", 0),
        ig_sessionid=os.getenv("IG_SESSIONID", "").strip(),
        ig_ds_user_id=os.getenv("IG_DS_USER_ID", "").strip(),
        ig_csrftoken=os.getenv("IG_CSRFTOKEN", "").strip(),
    )
