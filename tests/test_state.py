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


def test_media_memory_is_exact_not_near_duplicate(state_dir):
    store = StateStore(state_dir)
    store.reserve_media(["ahash:0000000000000000"], job_id="job-1")

    assert not store.is_media_used("ahash:0000000000000001")
    assert not store.is_media_used("ahash:ffffffffffffffff")


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


def test_recent_chosen_accounts_returns_newest_unique_accounts(state_dir):
    store = StateStore(state_dir)
    for job_id, account, video_type in [
        ("job-1", "alpha", VideoType.TYPE_1),
        ("job-2", "beta", VideoType.TYPE_2),
        ("job-3", "alpha", VideoType.TYPE_1),
        ("job-4", "gamma", VideoType.TYPE_1),
    ]:
        store.log_job(
            store.build_job_record(
                job_id=job_id,
                chosen_account=account,
                requested_accounts=[account],
                fallback_accounts=[],
                video_type=video_type,
                language=Language.ES,
                video_path=None,
                script_path=f"{job_id}.txt",
            )
        )

    assert store.recent_chosen_accounts(limit=3) == ["gamma", "alpha", "beta"]
    assert store.recent_chosen_accounts(limit=2, video_type=VideoType.TYPE_1) == [
        "gamma",
        "alpha",
    ]


def test_persistence_marker_is_stable(state_dir):
    store = StateStore(state_dir)

    first = store.ensure_persistence_marker()
    second = StateStore(state_dir).ensure_persistence_marker()

    assert first["created_now"] is True
    assert second["created_now"] is False
    assert second["install_id"] == first["install_id"]


def test_memory_snapshot_reports_usage_and_account_diversity(state_dir):
    store = StateStore(state_dir)
    store.ensure_persistence_marker()
    store.reserve_media(["media-1", "media-2"], job_id="job-1")
    for job_id, account in [("job-1", "alpha"), ("job-2", "beta"), ("job-3", "alpha")]:
        store.log_job(
            store.build_job_record(
                job_id=job_id,
                chosen_account=account,
                requested_accounts=[account],
                fallback_accounts=[],
                video_type=VideoType.TYPE_1,
                language=Language.ES,
                video_path=None,
                script_path=f"{job_id}.txt",
            )
        )

    snapshot = store.memory_snapshot(recent_limit=5)

    assert snapshot["used_media_count"] == 2
    assert snapshot["jobs_count"] == 3
    assert snapshot["unique_chosen_accounts"] == 2
    assert snapshot["recent_accounts"] == ["alpha", "beta"]
    assert snapshot["top_accounts"][:2] == [("alpha", 2), ("beta", 1)]


def test_claim_or_check_owner_allows_only_first_telegram_user(state_dir):
    store = StateStore(state_dir)

    assert store.claim_or_check_owner(
        user_id=10,
        chat_id=100,
        username="owner",
    )
    assert store.claim_or_check_owner(
        user_id=10,
        chat_id=200,
        username="owner-second-device",
    )
    assert not store.claim_or_check_owner(
        user_id=11,
        chat_id=300,
        username="other",
    )
    assert store.get_owner_user_id() == 10
