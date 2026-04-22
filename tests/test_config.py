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
        assert settings.instagram_session_path == persistent_dir / "state" / "instagram_session"
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
