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
_PERCEPTUAL_HASH_DISTANCE = 6
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
        self._media_pool_path = self.state_dir / "media_pool.json"
        self._excluded_accounts_path = self.state_dir / "excluded_accounts.json"
        self._account_cooldowns_path = self.state_dir / "account_cooldowns.json"
        self._type_3_background_queue_path = self.state_dir / "type3_background_queue.json"
        self._template_video_queue_path = self.state_dir / "template_video_queue.json"
        self._story_reference_queue_path = self.state_dir / "story_reference_queue.json"
        self._batch_schedule_path = self.state_dir / "batch_schedule.json"
        self._batch_rotation_path = self.state_dir / "batch_rotation.json"
        self._last_batch_run_path = self.state_dir / "last_batch_run.json"
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
        return self.any_media_used_in_snapshot(media_ids, used)

    def read_used_media(self) -> dict[str, Any]:
        with self._exclusive():
            used = self._read_json(self._used_media_path, {})
        return used if isinstance(used, dict) else {}

    @classmethod
    def any_media_used_in_snapshot(
        cls,
        media_ids: list[str],
        used: dict[str, Any],
    ) -> bool:
        if not media_ids:
            return False
        return any(cls._media_id_is_used(media_id, used) for media_id in media_ids)

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

    def get_last_shared_text_choice(self, video_type: VideoType) -> str | None:
        with self._exclusive():
            recent = self._read_json(self._recent_text_choices_path, {})
        value = recent.get(self._shared_text_choice_key(video_type))
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
            recent[self._shared_text_choice_key(video_type)] = choice_key
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

    def get_next_type_3_background_id(self, background_ids: list[str]) -> str | None:
        if not background_ids:
            return None
        with self._exclusive():
            queue = self._read_json(self._type_3_background_queue_path, {})
            normalized = self._normalize_type_3_background_order(queue, background_ids)
            if queue.get("order") != normalized:
                self._write_json(
                    self._type_3_background_queue_path,
                    {"order": normalized},
                )
        return normalized[0] if normalized else None

    def remember_type_3_background_choice(
        self,
        background_id: str,
        background_ids: list[str],
    ) -> None:
        if not background_id or not background_ids:
            return
        with self._exclusive():
            queue = self._read_json(self._type_3_background_queue_path, {})
            normalized = self._normalize_type_3_background_order(queue, background_ids)
            if background_id not in normalized:
                return
            normalized.remove(background_id)
            normalized.append(background_id)
            self._write_json(
                self._type_3_background_queue_path,
                {"order": normalized},
            )

    def get_next_template_video_id(
        self,
        scope: str,
        video_ids: list[str],
    ) -> tuple[str | None, bool]:
        if not video_ids:
            return None, False
        scope_key = str(scope or "default").strip() or "default"
        with self._exclusive():
            payload = self._read_json(self._template_video_queue_path, {})
            if not isinstance(payload, dict):
                payload = {}
            scopes = payload.get("scopes")
            if not isinstance(scopes, dict):
                scopes = {}
            queue = scopes.get(scope_key)
            if not isinstance(queue, dict):
                queue = {}

            order = self._normalize_template_video_order(queue, video_ids)
            cursor = queue.get("cursor", 0)
            try:
                cursor = int(cursor)
            except (TypeError, ValueError):
                cursor = 0
            if cursor < 0:
                cursor = 0

            restarted = False
            if cursor >= len(order):
                cursor = 0
                restarted = True

            selected = order[cursor] if order else None
            scopes[scope_key] = {
                "order": order,
                "cursor": cursor + 1,
            }
            self._write_json(self._template_video_queue_path, {"scopes": scopes})
        return selected, restarted

    def get_next_story_reference_image_id(
        self,
        scope: str,
        image_ids: list[str],
    ) -> tuple[str | None, bool]:
        if not image_ids:
            return None, False
        scope_key = str(scope or "default").strip() or "default"
        with self._exclusive():
            payload = self._read_json(self._story_reference_queue_path, {})
            if not isinstance(payload, dict):
                payload = {}
            scopes = payload.get("scopes")
            if not isinstance(scopes, dict):
                scopes = {}
            queue = scopes.get(scope_key)
            if not isinstance(queue, dict):
                queue = {}

            order = self._normalize_template_video_order(queue, image_ids)
            cursor = queue.get("cursor", 0)
            try:
                cursor = int(cursor)
            except (TypeError, ValueError):
                cursor = 0
            if cursor < 0:
                cursor = 0

            restarted = False
            if cursor >= len(order):
                cursor = 0
                restarted = True

            selected = order[cursor] if order else None
            scopes[scope_key] = {
                "order": order,
                "cursor": cursor + 1,
            }
            self._write_json(self._story_reference_queue_path, {"scopes": scopes})
        return selected, restarted

    def read_media_pool(self) -> dict[str, Any]:
        with self._exclusive():
            pool = self._read_json(self._media_pool_path, {})
        if not isinstance(pool, dict):
            pool = {}
        items = pool.get("items")
        if not isinstance(items, list):
            pool["items"] = []
        cursors = pool.get("cursor_by_type")
        if not isinstance(cursors, dict):
            pool["cursor_by_type"] = {}
        return pool

    def write_media_pool(self, pool: dict[str, Any]) -> None:
        with self._exclusive():
            self._write_json(self._media_pool_path, pool)

    def read_batch_schedule(self) -> dict[str, Any]:
        with self._exclusive():
            payload = self._read_json(self._batch_schedule_path, {})
        if not isinstance(payload, dict):
            return {}
        return dict(payload)

    def write_batch_schedule(
        self,
        *,
        enabled: bool,
        chat_id: int,
        user_id: int,
        count: int,
        times: list[str],
        timezone_name: str,
    ) -> dict[str, Any]:
        payload = {
            "enabled": bool(enabled),
            "chat_id": int(chat_id),
            "user_id": int(user_id),
            "count": int(count),
            "times": list(times),
            "timezone": str(timezone_name),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._exclusive():
            self._write_json(self._batch_schedule_path, payload)
        return dict(payload)

    def disable_batch_schedule(self) -> dict[str, Any]:
        with self._exclusive():
            payload = self._read_json(self._batch_schedule_path, {})
            if not isinstance(payload, dict):
                payload = {}
            payload["enabled"] = False
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json(self._batch_schedule_path, payload)
        return dict(payload)

    def get_batch_rotation_phase(self, *, cycle_length: int = 7) -> int:
        normalized_length = max(1, int(cycle_length))
        with self._exclusive():
            payload = self._read_json(self._batch_rotation_path, {})
        if not isinstance(payload, dict):
            return 0
        try:
            phase = int(payload.get("phase", 0))
        except (TypeError, ValueError):
            phase = 0
        return max(0, phase) % normalized_length

    def advance_batch_rotation(self, *, cycle_length: int = 7) -> int:
        normalized_length = max(1, int(cycle_length))
        with self._exclusive():
            payload = self._read_json(self._batch_rotation_path, {})
            if not isinstance(payload, dict):
                payload = {}
            try:
                phase = int(payload.get("phase", 0))
            except (TypeError, ValueError):
                phase = 0
            next_phase = (max(0, phase) + 1) % normalized_length
            self._write_json(
                self._batch_rotation_path,
                {
                    "phase": next_phase,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return next_phase

    def reset_batch_rotation(self) -> None:
        with self._exclusive():
            self._write_json(
                self._batch_rotation_path,
                {
                    "phase": 0,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    def write_last_batch_run(self, payload: dict[str, Any]) -> None:
        data = dict(payload)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with self._exclusive():
            self._write_json(self._last_batch_run_path, data)

    def read_last_batch_run(self) -> dict[str, Any]:
        with self._exclusive():
            payload = self._read_json(self._last_batch_run_path, {})
        return dict(payload) if isinstance(payload, dict) else {}

    def read_excluded_accounts(self) -> set[str]:
        with self._exclusive():
            payload = self._read_json(self._excluded_accounts_path, [])
        if not isinstance(payload, list):
            return set()
        return {
            self._normalize_account_name(account)
            for account in payload
            if self._normalize_account_name(account)
        }

    def exclude_account(self, account: str) -> None:
        normalized = self._normalize_account_name(account)
        if not normalized:
            return
        with self._exclusive():
            payload = self._read_json(self._excluded_accounts_path, [])
            accounts = set(payload if isinstance(payload, list) else [])
            accounts.add(normalized)
            self._write_json(self._excluded_accounts_path, sorted(accounts))

    def read_account_cooldowns(self) -> dict[str, Any]:
        with self._exclusive():
            cooldowns = self._read_json(self._account_cooldowns_path, {})
        return cooldowns if isinstance(cooldowns, dict) else {}

    def set_account_cooldown(
        self,
        account: str,
        *,
        cooldown_until: str,
        scraped_at: str,
        added_count: int,
        valid_count: int,
        total_count: int,
    ) -> None:
        account_key = account.strip().lower()
        if not account_key:
            return
        with self._exclusive():
            cooldowns = self._read_json(self._account_cooldowns_path, {})
            if not isinstance(cooldowns, dict):
                cooldowns = {}
            cooldowns[account_key] = {
                "cooldown_until": cooldown_until,
                "scraped_at": scraped_at,
                "added_count": added_count,
                "valid_count": valid_count,
                "total_count": total_count,
            }
            self._write_json(self._account_cooldowns_path, cooldowns)

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
        gender: str | None = None,
    ) -> dict[str, Any]:
        record = {
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
        if gender:
            record["gender"] = gender
        return record

    @staticmethod
    def _bucket_key(video_type: VideoType, language: Language) -> str:
        return f"{video_type.value}:{language.value}"

    @staticmethod
    def _shared_text_choice_key(video_type: VideoType) -> str:
        return f"{video_type.value}:shared"

    @staticmethod
    def _normalize_account_name(account: Any) -> str:
        return str(account or "").strip().lstrip("@").lower()

    @staticmethod
    def _normalize_type_3_background_order(
        queue: Any,
        background_ids: list[str],
    ) -> list[str]:
        available: list[str] = []
        seen: set[str] = set()
        for background_id in background_ids:
            if not isinstance(background_id, str) or not background_id:
                continue
            if background_id in seen:
                continue
            seen.add(background_id)
            available.append(background_id)

        saved_order = queue.get("order", []) if isinstance(queue, dict) else []
        normalized: list[str] = []
        normalized_seen: set[str] = set()
        for background_id in saved_order:
            if background_id in seen and background_id not in normalized_seen:
                normalized.append(background_id)
                normalized_seen.add(background_id)
        for background_id in available:
            if background_id not in normalized_seen:
                normalized.append(background_id)
                normalized_seen.add(background_id)
        return normalized

    @staticmethod
    def _normalize_template_video_order(
        queue: Any,
        video_ids: list[str],
    ) -> list[str]:
        available: list[str] = []
        seen: set[str] = set()
        for video_id in video_ids:
            normalized_id = str(video_id or "").strip()
            if not normalized_id or normalized_id in seen:
                continue
            seen.add(normalized_id)
            available.append(normalized_id)

        saved_order = queue.get("order", []) if isinstance(queue, dict) else []
        normalized: list[str] = []
        normalized_seen: set[str] = set()
        for video_id in saved_order:
            normalized_id = str(video_id or "").strip()
            if normalized_id in seen and normalized_id not in normalized_seen:
                normalized.append(normalized_id)
                normalized_seen.add(normalized_id)
        for video_id in available:
            if video_id not in normalized_seen:
                normalized.append(video_id)
                normalized_seen.add(video_id)
        return normalized

    @staticmethod
    def _media_id_is_used(media_id: str, used: dict[str, Any]) -> bool:
        if media_id in used:
            return True
        if media_id.startswith("dhash:"):
            try:
                current = int(media_id.split(":", maxsplit=1)[1], 16)
            except (IndexError, ValueError):
                return False
            for used_id in used:
                if not isinstance(used_id, str) or not used_id.startswith("dhash:"):
                    continue
                try:
                    other = int(used_id.split(":", maxsplit=1)[1], 16)
                except (IndexError, ValueError):
                    continue
                if (current ^ other).bit_count() <= _PERCEPTUAL_HASH_DISTANCE:
                    return True
        return False
