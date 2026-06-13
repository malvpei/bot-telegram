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


def test_r2_settings_are_loaded_from_env(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_INPUT_PREFIX", "/inputs/videos")
    get_settings.cache_clear()
    try:
        settings = get_settings()

        assert settings.r2_account_id == "acct"
        assert settings.r2_access_key_id == "key"
        assert settings.r2_secret_access_key == "secret"
        assert settings.r2_bucket == "bucket"
        assert settings.r2_input_prefix == "inputs/videos"
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
