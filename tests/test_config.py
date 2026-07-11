from pathlib import Path
import shutil
from uuid import uuid4

from app.config import get_settings


def test_data_dir_env_moves_persistent_paths(monkeypatch):
    workspace_tmp = Path(__file__).resolve().parents[1] / "data" / "_test_tmp"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    persistent_dir = workspace_tmp / f"persistent-data-{uuid4().hex}"
    try:
        monkeypatch.setenv("DATA_DIR", str(persistent_dir))
        get_settings.cache_clear()
        settings = get_settings()

        assert settings.data_dir == persistent_dir
        assert settings.downloads_dir == persistent_dir / "downloads"
        assert settings.outputs_dir == persistent_dir / "outputs"
        assert settings.state_dir == persistent_dir / "state"
        assert settings.template_videos_dir == persistent_dir / "template_videos"
        assert settings.r2_downloads_dir == persistent_dir / "r2_downloads"
        assert (
            settings.instagram_session_path
            == persistent_dir / "state" / "instagram_session"
        )
        assert (
            settings.women_accounts_file
            == Path(__file__).resolve().parents[1] / "accounts_women.txt"
        )
    finally:
        get_settings.cache_clear()
        shutil.rmtree(persistent_dir, ignore_errors=True)


def test_relative_data_dir_env_is_resolved_from_project_root(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "persistent")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.data_dir == Path(__file__).resolve().parents[1] / "persistent"
    finally:
        get_settings.cache_clear()


def test_default_type_1_fixed_image_reuses_dropradar_tip3(monkeypatch):
    monkeypatch.delenv("FIXED_IMAGE_PATH", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert (
            settings.fixed_image_path
            == Path(__file__).resolve().parents[1] / "assets" / "fixed" / "tip3_dropradar.jpg"
        )
    finally:
        get_settings.cache_clear()


def test_women_accounts_file_env_is_resolved_from_project_root(monkeypatch):
    monkeypatch.setenv("WOMEN_ACCOUNTS_FILE", "data/women.txt")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert (
            settings.women_accounts_file
            == Path(__file__).resolve().parents[1] / "data" / "women.txt"
        )
    finally:
        get_settings.cache_clear()


def test_template_videos_dir_env_is_resolved_from_project_root(monkeypatch):
    monkeypatch.setenv("TEMPLATE_VIDEOS_DIR", "data/video-inputs")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert (
            settings.template_videos_dir
            == Path(__file__).resolve().parents[1] / "data" / "video-inputs"
        )
    finally:
        get_settings.cache_clear()


def test_upload_site_defaults_are_enabled_for_image_uploads(monkeypatch):
    for key in (
        "UPLOAD_SITE_ENABLED",
        "UPLOAD_SITE_HOST",
        "UPLOAD_SITE_PORT",
        "UPLOAD_SITE_USERNAME",
        "UPLOAD_SITE_PASSWORD",
        "UPLOAD_SITE_MAX_IMAGE_MB",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.upload_site_enabled is True
        assert settings.upload_site_host == "0.0.0.0"
        assert settings.upload_site_port == 8000
        assert settings.upload_site_username == "admin"
        assert settings.upload_site_password == "pon_una_password"
        assert settings.upload_site_max_image_mb == 20
        assert settings.r2_image_prefix == "videos/imagenes"
    finally:
        get_settings.cache_clear()


def test_fal_image_provider_defaults_are_loaded(monkeypatch):
    for key in (
        "IMAGE_PROVIDER",
        "FAL_KEY",
        "FAL_MODEL",
        "FAL_IMAGE_ASPECT_RATIO",
        "FAL_IMAGE_SIZE",
        "FAL_IMAGE_QUALITY",
        "FAL_OUTPUT_FORMAT",
        "FAL_SAFETY_TOLERANCE",
        "FAL_GUIDANCE_SCALE",
        "FAL_POLL_INTERVAL_SECONDS",
        "FAL_REQUEST_TIMEOUT_SECONDS",
    ):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.image_provider == "fal"
        assert settings.fal_key == ""
        assert settings.fal_model == "openai/gpt-image-2/edit"
        assert settings.fal_image_aspect_ratio == "9:16"
        assert settings.fal_image_size == "864x1536"
        assert settings.fal_image_quality == "medium"
        assert settings.fal_output_format == "png"
        assert settings.fal_safety_tolerance == "2"
        assert settings.fal_guidance_scale == 3.5
        assert settings.fal_poll_interval_seconds == 2.0
        assert settings.fal_request_timeout_seconds == 240.0
    finally:
        get_settings.cache_clear()


def test_fal_image_provider_env_is_loaded(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "fal")
    monkeypatch.setenv("FAL_KEY", "fal-secret")
    monkeypatch.setenv("FAL_MODEL", "fal-ai/flux-pro/kontext")
    monkeypatch.setenv("FAL_IMAGE_ASPECT_RATIO", "9:16")
    monkeypatch.setenv("FAL_IMAGE_SIZE", "768x1360")
    monkeypatch.setenv("FAL_IMAGE_QUALITY", "low")
    monkeypatch.setenv("FAL_OUTPUT_FORMAT", "jpeg")
    monkeypatch.setenv("FAL_SAFETY_TOLERANCE", "3")
    monkeypatch.setenv("FAL_GUIDANCE_SCALE", "4.25")
    monkeypatch.setenv("FAL_POLL_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("FAL_REQUEST_TIMEOUT_SECONDS", "90")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.image_provider == "fal"
        assert settings.fal_key == "fal-secret"
        assert settings.fal_model == "fal-ai/flux-pro/kontext"
        assert settings.fal_image_aspect_ratio == "9:16"
        assert settings.fal_image_size == "768x1360"
        assert settings.fal_image_quality == "low"
        assert settings.fal_output_format == "jpeg"
        assert settings.fal_safety_tolerance == "3"
        assert settings.fal_guidance_scale == 4.25
        assert settings.fal_poll_interval_seconds == 0.5
        assert settings.fal_request_timeout_seconds == 90.0
    finally:
        get_settings.cache_clear()


def test_r2_settings_are_loaded_from_env(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_INPUT_PREFIX", "/inputs/videos")
    monkeypatch.setenv("R2_IMAGE_PREFIX", "/inputs/images")
    monkeypatch.setenv("UPLOAD_SITE_ENABLED", "true")
    monkeypatch.setenv("UPLOAD_SITE_PORT", "9001")
    monkeypatch.setenv("UPLOAD_SITE_PASSWORD", "secret")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.r2_account_id == "acct"
        assert settings.r2_access_key_id == "key"
        assert settings.r2_secret_access_key == "secret"
        assert settings.r2_bucket == "bucket"
        assert settings.r2_input_prefix == "inputs/videos"
        assert settings.r2_image_prefix == "inputs/images"
        assert settings.upload_site_enabled is True
        assert settings.upload_site_port == 9001
        assert settings.upload_site_password == "secret"
    finally:
        get_settings.cache_clear()


def test_pool_refill_fresh_account_limit_env(monkeypatch):
    monkeypatch.setenv("POOL_REFILL_MAX_FRESH_ACCOUNTS", "3")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.pool_refill_max_fresh_accounts == 3
    finally:
        get_settings.cache_clear()


def test_pool_refill_account_limit_env(monkeypatch):
    monkeypatch.setenv("POOL_REFILL_MAX_ACCOUNTS", "5")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.pool_refill_max_accounts == 5
    finally:
        get_settings.cache_clear()


def test_dynamic_pick_max_posts_env(monkeypatch):
    monkeypatch.setenv("DYNAMIC_PICK_MAX_POSTS_PER_ACCOUNT", "12")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.dynamic_pick_max_posts_per_account == 12
    finally:
        get_settings.cache_clear()


def test_batch_timezone_defaults_to_madrid(monkeypatch):
    monkeypatch.delenv("BATCH_TIMEZONE", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().batch_timezone == "Europe/Madrid"
    finally:
        get_settings.cache_clear()


def test_batch_timezone_can_be_configured(monkeypatch):
    monkeypatch.setenv("BATCH_TIMEZONE", "America/New_York")
    get_settings.cache_clear()
    try:
        assert get_settings().batch_timezone == "America/New_York"
    finally:
        get_settings.cache_clear()


def test_fast_ffmpeg_and_story_worker_defaults(monkeypatch):
    monkeypatch.delenv("FFMPEG_PRESET", raising=False)
    monkeypatch.delenv("STORY_IMAGE_WORKERS", raising=False)
    monkeypatch.delenv("OPENAI_IMAGE_SIZE", raising=False)
    monkeypatch.delenv("OPENAI_IMAGE_QUALITY", raising=False)
    monkeypatch.delenv("STORY_REVIEW_ENABLED", raising=False)
    monkeypatch.delenv("STORY_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("STORY_REVIEW_FAL_MODEL", raising=False)
    monkeypatch.delenv("STORY_REVIEW_MIN_SCORE", raising=False)
    monkeypatch.delenv("STORY_IMAGE_MAX_ATTEMPTS", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.ffmpeg_preset == "veryfast"
        assert settings.story_image_workers == 2
        assert settings.openai_image_size == "864x1536"
        assert settings.openai_image_quality == "medium"
        assert settings.story_review_enabled is True
        assert settings.story_review_model == "gpt-5.4-nano"
        assert settings.story_review_fal_model == "google/gemini-2.5-flash"
        assert settings.story_review_min_score == 8
        assert settings.story_image_max_attempts == 2
    finally:
        get_settings.cache_clear()


def test_story_quality_settings_are_clamped(monkeypatch):
    monkeypatch.setenv("STORY_REVIEW_ENABLED", "false")
    monkeypatch.setenv("STORY_REVIEW_MODEL", "vision-reviewer")
    monkeypatch.setenv("STORY_REVIEW_FAL_MODEL", "provider/vision-reviewer")
    monkeypatch.setenv("STORY_REVIEW_MIN_SCORE", "99")
    monkeypatch.setenv("STORY_IMAGE_MAX_ATTEMPTS", "20")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.story_review_enabled is False
        assert settings.story_review_model == "vision-reviewer"
        assert settings.story_review_fal_model == "provider/vision-reviewer"
        assert settings.story_review_min_score == 10
        assert settings.story_image_max_attempts == 4
    finally:
        get_settings.cache_clear()


def test_invalid_ffmpeg_preset_falls_back_to_safe_default(monkeypatch):
    monkeypatch.setenv("FFMPEG_PRESET", "not-a-preset")
    get_settings.cache_clear()
    try:
        assert get_settings().ffmpeg_preset == "veryfast"
    finally:
        get_settings.cache_clear()
