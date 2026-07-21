import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.batches import BATCH_ROTATION_CYCLE_LENGTH
from app.models import Language, VideoType
from app.state import BATCH_SCHEDULE_SCHEMA_VERSION, StateStore


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


def test_release_media_cannot_release_another_jobs_reservation(state_dir):
    store = StateStore(state_dir)
    store.reserve_media(["shared-photo"], job_id="user-1-job")

    store.release_media(["shared-photo"], job_id="user-2-job")
    assert store.is_media_used("shared-photo")

    store.release_media(["shared-photo"], job_id="user-1-job")
    assert not store.is_media_used("shared-photo")


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


def test_type_3_background_queue_rotates_globally(state_dir):
    store = StateStore(state_dir)
    background_ids = ["bg-1", "bg-2", "bg-3"]

    assert store.get_next_type_3_background_id(background_ids) == "bg-1"

    store.remember_type_3_background_choice("bg-1", background_ids)
    assert store.get_next_type_3_background_id(background_ids) == "bg-2"

    store.remember_type_3_background_choice("bg-2", background_ids)
    assert store.get_next_type_3_background_id(background_ids) == "bg-3"

    store.remember_type_3_background_choice("bg-3", background_ids)
    assert store.get_next_type_3_background_id(background_ids) == "bg-1"


def test_template_queue_does_not_replay_when_pool_changes_mid_cycle(state_dir):
    store = StateStore(state_dir)

    assert store.get_next_template_video_id("videos", ["a", "b", "c"])[0] == "a"
    # Removing the already-served first entry must not shift a cursor back to b/a.
    assert store.get_next_template_video_id("videos", ["b", "c", "d"])[0] == "b"
    assert store.get_next_template_video_id("videos", ["b", "c", "d"])[0] == "c"
    assert store.get_next_template_video_id("videos", ["b", "c", "d"])[0] == "d"
    selected, restarted = store.get_next_template_video_id(
        "videos",
        ["b", "c", "d"],
    )
    assert selected == "b"
    assert restarted is True


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


def test_owner_can_authorize_and_revoke_multiple_telegram_users(state_dir):
    store = StateStore(state_dir)
    store.claim_or_check_owner(user_id=10, chat_id=100, username="owner")

    store.authorize_telegram_user(user_id=11, added_by=10)
    store.authorize_telegram_user(user_id=12, added_by=10, username="second")

    assert store.is_telegram_user_authorized(10)
    assert store.is_telegram_user_authorized(11)
    assert store.is_telegram_user_authorized(12)
    assert [item["user_id"] for item in store.list_telegram_users()] == [10, 11, 12]
    assert not store.revoke_telegram_user(10)
    assert store.revoke_telegram_user(11)
    assert not store.is_telegram_user_authorized(11)
    assert [item["user_id"] for item in store.list_telegram_users()] == [10, 12]


def test_memory_snapshot_only_exposes_requesting_users_jobs(state_dir):
    store = StateStore(state_dir)
    store.claim_or_check_owner(user_id=10, chat_id=100, username="owner")
    store.authorize_telegram_user(user_id=11, added_by=10)
    store.reserve_media(["globally-used"], job_id="job-1")
    for job_id, account, user_id in [
        ("job-1", "alpha", 10),
        ("job-2", "secret-account", 11),
    ]:
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
                user_id=user_id,
                chat_id=user_id * 10,
            )
        )

    owner_snapshot = store.memory_snapshot(user_id=10)
    user_snapshot = store.memory_snapshot(user_id=11)

    assert owner_snapshot["jobs_count"] == 1
    assert owner_snapshot["recent_accounts"] == ["alpha"]
    assert user_snapshot["jobs_count"] == 1
    assert user_snapshot["recent_accounts"] == ["secret-account"]
    assert user_snapshot["global_jobs_count"] == 2
    assert user_snapshot["used_media_count"] == 1


def test_historical_r2_story_jobs_are_migrated_to_global_reservations(state_dir):
    store = StateStore(state_dir)
    store.log_job(
        store.build_job_record(
            job_id="old-story",
            chosen_account="r2:imagenes/already-used.jpg",
            requested_accounts=["r2:imagenes/already-used.jpg"],
            fallback_accounts=[],
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            video_path=None,
            script_path="old-story.txt",
            user_id=10,
        )
    )

    assert store.backfill_story_reference_reservations() == 1
    assert store.backfill_story_reference_reservations() == 0
    assert store.is_media_used("r2-story:imagenes/already-used.jpg")


def test_batch_schedule_and_rotation_survive_new_store_instance(state_dir):
    store = StateStore(state_dir)
    store.write_batch_schedule(
        enabled=True,
        chat_id=100,
        user_id=10,
        count=5,
        times=["08:00", "17:00"],
        timezone_name="Europe/Madrid",
    )
    assert store.get_batch_rotation_phase() == 0
    assert store.advance_batch_rotation() == 1

    restored = StateStore(state_dir)
    schedule = restored.read_batch_schedule()
    assert schedule["enabled"] is True
    assert schedule["chat_id"] == 100
    assert schedule["count"] == 5
    assert schedule["times"] == ["08:00", "17:00"]
    assert schedule["schema_version"] == BATCH_SCHEDULE_SCHEMA_VERSION
    assert restored.get_batch_rotation_phase() == 1


def test_batch_rotation_wraps_and_can_be_reset(state_dir):
    store = StateStore(state_dir)
    for _ in range(BATCH_ROTATION_CYCLE_LENGTH):
        store.advance_batch_rotation()
    assert store.get_batch_rotation_phase() == 0

    store.advance_batch_rotation()
    store.reset_batch_rotation()
    assert store.get_batch_rotation_phase(cycle_length=7) == 0


def test_disabling_batch_schedule_keeps_its_configuration(state_dir):
    store = StateStore(state_dir)
    store.write_batch_schedule(
        enabled=True,
        chat_id=100,
        user_id=10,
        count=4,
        times=["09:30"],
        timezone_name="Europe/Madrid",
    )

    disabled = store.disable_batch_schedule()

    assert disabled["enabled"] is False
    assert disabled["count"] == 4
    assert disabled["times"] == ["09:30"]


def test_scheduled_batch_slots_survive_manual_runs_and_restarts(state_dir):
    store = StateStore(state_dir)
    slot = "2026-07-12|08:00|Europe/Madrid|100"

    assert store.claim_scheduled_batch_slot(slot, "batch-a")
    assert store.finish_scheduled_batch_slot(
        slot,
        batch_id="batch-a",
        status="completed",
    )
    store.write_last_batch_run({"status": "completed", "source": "manual"})

    restored = StateStore(state_dir)
    assert restored.scheduled_batch_slot_is_terminal(slot)
    assert not restored.claim_scheduled_batch_slot(slot, "batch-b")


def test_interrupted_running_schedule_slot_can_be_reclaimed(state_dir):
    store = StateStore(state_dir)
    slot = "2026-07-12|17:00|Europe/Madrid|100"

    assert store.claim_scheduled_batch_slot(slot, "crashed-batch")
    assert not store.scheduled_batch_slot_is_terminal(slot)
    assert not store.claim_scheduled_batch_slot(slot, "duplicate-batch")
    assert store.claim_scheduled_batch_slot(
        slot,
        "recovery-batch",
        allow_reclaim_running=True,
    )
    assert not store.finish_scheduled_batch_slot(
        slot,
        batch_id="crashed-batch",
        status="completed",
    )
    assert store.finish_scheduled_batch_slot(
        slot,
        batch_id="recovery-batch",
        status="completed",
    )
