from __future__ import annotations

from app.bot import run_bot
from app.config import get_settings
from app.upload_site import start_upload_site_thread


if __name__ == "__main__":
    settings = get_settings()
    if settings.upload_site_enabled:
        start_upload_site_thread(settings)
    run_bot()
