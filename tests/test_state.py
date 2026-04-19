import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.models import Language, VideoType
from app.state import StateStore


@pytest.fixture()
def state_dir():
    workspace_tmp = Path(__file__).resolve().parents[1] / "data" / "_test_tmp"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    path = workspace_tmp / f"state-store-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_reserve_media_blocks_second_reservation(state_dir):
    store = StateStore(state_dir)
    conflict = store.reserve_media(["a", "b"], job_id="job-1")
    assert conflict == []

    # Second job tries to grab one of the same IDs.
    conflict = store.reserve_media(["b", "c"], job_id="job-2")
    assert conflict == ["b"]

    # The uncontested IDs from job-2 must NOT have been written yet.
    assert not store.is_media_used("c")


def test_release_media_frees_ids(state_dir):
    store = StateStore(state_dir)
    store.reserve_media(["x", "y"], job_id="job-1")
    assert store.is_media_used("x")
    store.release_media(["x", "y"])
    assert not store.is_media_used("x")
    assert not store.is_media_used("y")


def test_signature_history_is_bounded(state_dir):
    store = StateStore(state_dir, history_max_per_bucket=25)
    for index in range(50):
        store.remember_signature(VideoType.TYPE_1, Language.ES, f"sig-{index}")
    signatures = store.get_known_signatures(VideoType.TYPE_1, Language.ES)
    assert len(signatures) == 25
    # Should keep the most recent ones.
    assert "sig-49" in signatures
    assert "sig-0" not in signatures


def test_atomic_write_survives_partial_read(state_dir):
    store = StateStore(state_dir)
    store.mark_media_used(["id-1"], job_id="job-1")

    # Simulate a corrupted file: truncated JSON.
    used_path = state_dir / "used_media.json"
    used_path.write_text("{bad", encoding="utf-8")

    # Reading should fall back to the empty default rather than raising.
    assert store.is_media_used("id-1") is False
