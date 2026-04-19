from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterator

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    _HAS_FILELOCK = True
except ImportError:  # pragma: no cover - fallback when filelock not installed
    FileLock = None  # type: ignore[assignment]
    FileLockTimeout = Exception  # type: ignore[assignment]
    _HAS_FILELOCK = False

from app.models import Language, VideoType


_LOCK_TIMEOUT_SECONDS = 30.0
_ATOMIC_REPLACE_RETRIES = 5
_ATOMIC_REPLACE_BACKOFF_SECONDS = 0.05


class StateStore:
    def __init__(self, state_dir: Path, history_max_per_bucket: int = 200) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._used_media_path = self.state_dir / "used_media.json"
        self._recent_scripts_path = self.state_dir / "recent_scripts.json"
        self._script_history_path = self.state_dir / "script_history.json"
        self._jobs_log_path = self.state_dir / "jobs_log.json"
        self._lock_path = self.state_dir / ".state.lock"
        self._thread_lock = Lock()
        self._history_max = max(20, history_max_per_bucket)

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        # Combine in-process lock with cross-process file lock so concurrent
        # bot instances cannot interleave reads and writes on the JSON files.
        with self._thread_lock:
            if _HAS_FILELOCK:
                lock = FileLock(str(self._lock_path), timeout=_LOCK_TIMEOUT_SECONDS)
                try:
                    with lock:
                        yield
                except FileLockTimeout as error:
                    raise RuntimeError(
                        "No pude adquirir el lock del estado en %.0f segundos."
                        % _LOCK_TIMEOUT_SECONDS
                    ) from error
            else:
                yield

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace so a crash mid-write cannot corrupt the file.
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            for attempt in range(1, _ATOMIC_REPLACE_RETRIES + 1):
                try:
                    os.replace(tmp_name, path)
                    break
                except PermissionError:
                    if attempt == _ATOMIC_REPLACE_RETRIES:
                        raise
                    time.sleep(_ATOMIC_REPLACE_BACKOFF_SECONDS * attempt)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def is_media_used(self, media_id: str) -> bool:
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
        return media_id in used

    def filter_unused(self, media_ids: list[str]) -> list[str]:
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
        return [media_id for media_id in media_ids if media_id not in used]

    def mark_media_used(self, media_ids: list[str], job_id: str) -> None:
        if not media_ids:
            return
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
            timestamp = datetime.now(timezone.utc).isoformat()
            for media_id in media_ids:
                used[media_id] = {"job_id": job_id, "used_at": timestamp}
            self._write_json(self._used_media_path, used)

    def reserve_media(self, media_ids: list[str], job_id: str) -> list[str]:
        # Atomically check-and-mark; returns the IDs that were already in use,
        # so the caller can react instead of silently producing duplicates.
        if not media_ids:
            return []
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
            already = [mid for mid in media_ids if mid in used]
            if already:
                return already
            timestamp = datetime.now(timezone.utc).isoformat()
            for media_id in media_ids:
                used[media_id] = {"job_id": job_id, "used_at": timestamp}
            self._write_json(self._used_media_path, used)
        return []

    def release_media(self, media_ids: list[str]) -> None:
        if not media_ids:
            return
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
            mutated = False
            for media_id in media_ids:
                if media_id in used:
                    used.pop(media_id, None)
                    mutated = True
            if mutated:
                self._write_json(self._used_media_path, used)

    def get_last_signature(self, video_type: VideoType, language: Language) -> str | None:
        with self._exclusive():
            recent = self._read_json(self._recent_scripts_path, {})
        return recent.get(self._bucket_key(video_type, language))

    def set_last_signature(
        self,
        video_type: VideoType,
        language: Language,
        signature: str,
    ) -> None:
        with self._exclusive():
            recent = self._read_json(self._recent_scripts_path, {})
            recent[self._bucket_key(video_type, language)] = signature
            self._write_json(self._recent_scripts_path, recent)

    def get_known_signatures(self, video_type: VideoType, language: Language) -> set[str]:
        with self._exclusive():
            history = self._read_json(self._script_history_path, {})
        values = history.get(self._bucket_key(video_type, language), [])
        return set(values)

    def remember_signature(
        self,
        video_type: VideoType,
        language: Language,
        signature: str,
    ) -> None:
        with self._exclusive():
            history = self._read_json(self._script_history_path, {})
            key = self._bucket_key(video_type, language)
            signatures = list(history.get(key, []))
            if signature in signatures:
                signatures.remove(signature)
            signatures.append(signature)
            # Keep history bounded so the dedup loop doesn't degenerate over time.
            if len(signatures) > self._history_max:
                signatures = signatures[-self._history_max :]
            history[key] = signatures
            self._write_json(self._script_history_path, history)

    def log_job(self, payload: dict[str, Any]) -> None:
        with self._exclusive():
            jobs = self._read_json(self._jobs_log_path, [])
            jobs.append(payload)
            self._write_json(self._jobs_log_path, jobs)

    def build_job_record(
        self,
        *,
        job_id: str,
        chosen_account: str,
        requested_accounts: list[str],
        fallback_accounts: list[str],
        video_type: VideoType,
        language: Language,
        video_path: str,
        script_path: str,
    ) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "chosen_account": chosen_account,
            "requested_accounts": requested_accounts,
            "fallback_accounts": fallback_accounts,
            "video_type": video_type.value,
            "language": language.value,
            "video_path": video_path,
            "script_path": script_path,
        }

    @staticmethod
    def _bucket_key(video_type: VideoType, language: Language) -> str:
        return f"{video_type.value}:{language.value}"
