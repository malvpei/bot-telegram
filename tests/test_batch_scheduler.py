import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder

from app.bot import (
    BATCH_JOB_NAME_PREFIX,
    _queue_missed_scheduled_batch,
    _replace_scheduled_batch_jobs,
    _scheduled_batch_slot,
    _scheduled_target_in_active_window,
)
from app.config import get_settings
from app.state import BATCH_SCHEDULE_SCHEMA_VERSION, StateStore


def test_saved_daily_schedule_is_registered_with_madrid_timezone(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "_test_tmp" / f"batch-scheduler-{uuid4().hex}"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BATCH_TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("BATCH_PREPARATION_LEAD_MINUTES", "120")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        StateStore(settings.state_dir).write_batch_schedule(
            enabled=True,
            chat_id=100,
            user_id=10,
            count=6,
            times=["08:00", "17:00"],
            timezone_name="Europe/Madrid",
        )
        application = ApplicationBuilder().token("123:ABC").build()

        _replace_scheduled_batch_jobs(application)

        jobs = application.job_queue.jobs(rf"^{BATCH_JOB_NAME_PREFIX}")
        assert [job.name for job in jobs] == [
            f"{BATCH_JOB_NAME_PREFIX}08:00",
            f"{BATCH_JOB_NAME_PREFIX}17:00",
        ]
        assert all(job.data["count"] == 6 for job in jobs)
        assert [job.data["preparation_time"] for job in jobs] == [
            "06:00",
            "15:00",
        ]
        trigger_texts = [str(job.job.trigger) for job in jobs]
        assert "hour='6', minute='0'" in trigger_texts[0]
        assert "hour='15', minute='0'" in trigger_texts[1]
        assert all(
            str(job.job.trigger.timezone) == "Europe/Madrid"
            for job in jobs
        )

        _replace_scheduled_batch_jobs(application)
        assert len(application.job_queue.jobs(rf"^{BATCH_JOB_NAME_PREFIX}")) == 2
    finally:
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)


def test_legacy_08_18_schedule_is_migrated_once_to_08_17(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "_test_tmp" / f"batch-scheduler-{uuid4().hex}"
    state_dir = data_dir / "state"
    state_dir.mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BATCH_TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("BATCH_PREPARATION_LEAD_MINUTES", "120")
    get_settings.cache_clear()
    try:
        (state_dir / "batch_schedule.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "chat_id": 100,
                    "user_id": 10,
                    "count": 6,
                    "times": ["08:00", "18:00"],
                    "timezone": "Europe/Madrid",
                }
            ),
            encoding="utf-8",
        )
        application = ApplicationBuilder().token("123:ABC").build()

        _replace_scheduled_batch_jobs(application)

        schedule = StateStore(state_dir).read_batch_schedule()
        assert schedule["times"] == ["08:00", "17:00"]
        assert schedule["schema_version"] == BATCH_SCHEDULE_SCHEMA_VERSION
        assert [
            job.name
            for job in application.job_queue.jobs(rf"^{BATCH_JOB_NAME_PREFIX}")
        ] == [
            f"{BATCH_JOB_NAME_PREFIX}08:00",
            f"{BATCH_JOB_NAME_PREFIX}17:00",
        ]

        migrated_at = schedule["updated_at"]
        _replace_scheduled_batch_jobs(application)
        assert StateStore(state_dir).read_batch_schedule()["updated_at"] == migrated_at
    finally:
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)


def test_startup_inside_preparation_window_queues_the_missed_batch(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "_test_tmp" / f"batch-scheduler-{uuid4().hex}"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BATCH_TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("BATCH_PREPARATION_LEAD_MINUTES", "120")
    get_settings.cache_clear()
    created = []
    try:
        settings = get_settings()
        StateStore(settings.state_dir).write_batch_schedule(
            enabled=True,
            chat_id=100,
            user_id=10,
            count=6,
            times=["08:00", "17:00"],
            timezone_name="Europe/Madrid",
        )
        application = ApplicationBuilder().token("123:ABC").build()

        def capture_task(self, coroutine, **kwargs):
            created.append((coroutine, kwargs))
            coroutine.close()
            return None

        monkeypatch.setattr(type(application), "create_task", capture_task)
        queued = _queue_missed_scheduled_batch(
            application,
            now=datetime(2026, 7, 10, 6, 30, tzinfo=ZoneInfo("Europe/Madrid")),
        )

        assert queued is True
        assert len(created) == 1
        assert created[0][1]["name"] == "scheduled-catchup-20260710-0800"
    finally:
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)


def test_startup_does_not_repeat_an_already_handled_schedule_slot(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "_test_tmp" / f"batch-scheduler-{uuid4().hex}"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BATCH_TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("BATCH_PREPARATION_LEAD_MINUTES", "120")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        store = StateStore(settings.state_dir)
        store.write_batch_schedule(
            enabled=True,
            chat_id=100,
            user_id=10,
            count=6,
            times=["08:00", "17:00"],
            timezone_name="Europe/Madrid",
        )
        timezone = ZoneInfo("Europe/Madrid")
        target = _scheduled_target_in_active_window(
            "08:00",
            timezone,
            lead_minutes=120,
            now=datetime(2026, 7, 10, 6, 30, tzinfo=timezone),
        )
        assert target is not None
        slot = _scheduled_batch_slot(target, 100)
        assert store.claim_scheduled_batch_slot(slot, "scheduled-batch")
        store.finish_scheduled_batch_slot(
            slot,
            batch_id="scheduled-batch",
            status="completed",
        )
        # A later manual batch must not erase the persistent scheduled slot.
        store.write_last_batch_run({"status": "completed", "source": "manual"})
        application = ApplicationBuilder().token("123:ABC").build()
        monkeypatch.setattr(
            type(application),
            "create_task",
            lambda self, coroutine, **kwargs: (_ for _ in ()).throw(
                AssertionError("handled slot must not be queued again")
            ),
        )

        assert (
            _queue_missed_scheduled_batch(
                application,
                now=datetime(2026, 7, 10, 6, 30, tzinfo=timezone),
            )
            is False
        )
    finally:
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)


def test_startup_queues_every_missed_slot_when_windows_overlap(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "_test_tmp" / f"batch-scheduler-{uuid4().hex}"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BATCH_TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("BATCH_PREPARATION_LEAD_MINUTES", "120")
    get_settings.cache_clear()
    created = []
    try:
        settings = get_settings()
        StateStore(settings.state_dir).write_batch_schedule(
            enabled=True,
            chat_id=100,
            user_id=10,
            count=6,
            times=["08:00", "09:00"],
            timezone_name="Europe/Madrid",
        )
        application = ApplicationBuilder().token("123:ABC").build()

        def capture_task(self, coroutine, **kwargs):
            created.append(kwargs["name"])
            coroutine.close()
            return None

        monkeypatch.setattr(type(application), "create_task", capture_task)

        assert _queue_missed_scheduled_batch(
            application,
            now=datetime(2026, 7, 10, 7, 30, tzinfo=ZoneInfo("Europe/Madrid")),
        )
        assert created == [
            "scheduled-catchup-20260710-0800",
            "scheduled-catchup-20260710-0900",
        ]
    finally:
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)
