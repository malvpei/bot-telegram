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
from uuid import uuid4

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
        self._recent_text_choices_path = self.state_dir / "recent_text_choices.json"
        self._recent_social_choices_path = self.state_dir / "recent_social_choices.json"
        self._script_history_path = self.state_dir / "script_history.json"
        self._jobs_log_path = self.state_dir / "jobs_log.json"
        self._owner_path = self.state_dir / "telegram_owner.json"
        self._persistence_marker_path = self.state_dir / "persistence_marker.json"
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
        return self._media_id_is_used(media_id, used)

    def filter_unused(self, media_ids: list[str]) -> list[str]:
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
        return [
            media_id
            for media_id in media_ids
            if not self._media_id_is_used(media_id, used)
        ]

    def any_media_used(self, media_ids: list[str]) -> bool:
        if not media_ids:
            return False
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
        return any(self._media_id_is_used(media_id, used) for media_id in media_ids)

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
            already = [
                mid
                for mid in media_ids
                if self._media_id_is_used(mid, used)
            ]
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

    def get_last_text_choice(
        self,
        video_type: VideoType,
        language: Language,
    ) -> str | None:
        with self._exclusive():
            recent = self._read_json(self._recent_text_choices_path, {})
        value = recent.get(self._bucket_key(video_type, language))
        return value if isinstance(value, str) else None

    def set_last_text_choice(
        self,
        video_type: VideoType,
        language: Language,
        choice_key: str,
    ) -> None:
        with self._exclusive():
            recent = self._read_json(self._recent_text_choices_path, {})
            recent[self._bucket_key(video_type, language)] = choice_key
            self._write_json(self._recent_text_choices_path, recent)

    def get_last_social_choice(
        self,
        video_type: VideoType,
        language: Language,
    ) -> str | None:
        with self._exclusive():
            recent = self._read_json(self._recent_social_choices_path, {})
        value = recent.get(self._bucket_key(video_type, language))
        return value if isinstance(value, str) else None

    def set_last_social_choice(
        self,
        video_type: VideoType,
        language: Language,
        choice_key: str,
    ) -> None:
        with self._exclusive():
            recent = self._read_json(self._recent_social_choices_path, {})
            recent[self._bucket_key(video_type, language)] = choice_key
            self._write_json(self._recent_social_choices_path, recent)

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

    def ensure_persistence_marker(self) -> dict[str, Any]:
        with self._exclusive():
            marker = self._read_json(self._persistence_marker_path, {})
            created_now = False
            if not isinstance(marker, dict) or not marker.get("install_id"):
                created_now = True
                marker = {
                    "install_id": uuid4().hex,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "state_dir": str(self.state_dir),
                }
                self._write_json(self._persistence_marker_path, marker)
            snapshot = dict(marker)
            snapshot["created_now"] = created_now
            return snapshot

    def memory_snapshot(self, *, recent_limit: int = 20) -> dict[str, Any]:
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
            jobs = self._read_json(self._jobs_log_path, [])
            marker = self._read_json(self._persistence_marker_path, {})

        if not isinstance(used, dict):
            used = {}
        if not isinstance(jobs, list):
            jobs = []
        if not isinstance(marker, dict):
            marker = {}

        account_counts: dict[str, int] = {}
        recent_accounts: list[str] = []
        recent_seen: set[str] = set()
        for job in jobs:
            account = str(job.get("chosen_account") or "").strip().lower()
            if account:
                account_counts[account] = account_counts.get(account, 0) + 1
        for job in reversed(jobs):
            account = str(job.get("chosen_account") or "").strip().lower()
            if not account or account in recent_seen:
                continue
            recent_seen.add(account)
            recent_accounts.append(account)
            if len(recent_accounts) >= recent_limit:
                break

        return {
            "state_dir": str(self.state_dir),
            "used_media_count": len(used),
            "jobs_count": len(jobs),
            "unique_chosen_accounts": len(account_counts),
            "recent_accounts": recent_accounts,
            "top_accounts": sorted(
                account_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:recent_limit],
            "marker": marker,
        }

    def recent_chosen_accounts(
        self,
        *,
        limit: int,
        video_type: VideoType | None = None,
    ) -> list[str]:
        if limit <= 0:
            return []
        with self._exclusive():
            jobs = self._read_json(self._jobs_log_path, [])
        recent: list[str] = []
        seen: set[str] = set()
        expected_type = video_type.value if video_type is not None else None
        for job in reversed(jobs):
            if expected_type and job.get("video_type") != expected_type:
                continue
            account = str(job.get("chosen_account") or "").strip().lower()
            if not account or account in seen:
                continue
            seen.add(account)
            recent.append(account)
            if len(recent) >= limit:
                break
        return recent

    def claim_or_check_owner(
        self,
        *,
        user_id: int,
        chat_id: int | None,
        username: str,
    ) -> bool:
        with self._exclusive():
            owner = self._read_json(self._owner_path, {})
            owner_id = owner.get("user_id")
            if owner_id is None:
                self._write_json(
                    self._owner_path,
                    {
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "username": username,
                        "claimed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                return True
            return int(owner_id) == user_id

    def get_owner_user_id(self) -> int | None:
        with self._exclusive():
            owner = self._read_json(self._owner_path, {})
        owner_id = owner.get("user_id")
        if owner_id is None:
            return None
        try:
            return int(owner_id)
        except (TypeError, ValueError):
            return None

    def build_job_record(
        self,
        *,
        job_id: str,
        chosen_account: str,
        requested_accounts: list[str],
        fallback_accounts: list[str],
        video_type: VideoType,
        language: Language,
        video_path: str | None,
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

    @staticmethod
    def _media_id_is_used(media_id: str, used: dict[str, Any]) -> bool:
        if media_id in used:
            return True
        return False
