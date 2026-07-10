import shutil
from pathlib import Path
from uuid import uuid4

from telegram.ext import ApplicationBuilder

from app.bot import BATCH_JOB_NAME_PREFIX, _replace_scheduled_batch_jobs
from app.config import get_settings
from app.state import StateStore


def test_saved_daily_schedule_is_registered_with_madrid_timezone(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "_test_tmp" / f"batch-scheduler-{uuid4().hex}"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("BATCH_TIMEZONE", "Europe/Madrid")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        StateStore(settings.state_dir).write_batch_schedule(
            enabled=True,
            chat_id=100,
            user_id=10,
            count=6,
            times=["08:00", "18:00"],
            timezone_name="Europe/Madrid",
        )
        application = ApplicationBuilder().token("123:ABC").build()

        _replace_scheduled_batch_jobs(application)

        jobs = application.job_queue.jobs(rf"^{BATCH_JOB_NAME_PREFIX}")
        assert [job.name for job in jobs] == [
            f"{BATCH_JOB_NAME_PREFIX}08:00",
            f"{BATCH_JOB_NAME_PREFIX}18:00",
        ]
        assert all(job.data["count"] == 6 for job in jobs)
        assert all(
            str(job.job.trigger.timezone) == "Europe/Madrid"
            for job in jobs
        )
    finally:
        get_settings.cache_clear()
        shutil.rmtree(data_dir, ignore_errors=True)
