from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.instagram import InstagramCollector
from app.models import ImageMetrics, Language, MediaCandidate, VideoPlan, VideoType
from app.selector import ImageSelector
from app.state import StateStore


LOGGER = logging.getLogger(__name__)
POOL_VERSION = 1
ALL_VIDEO_TYPES = (VideoType.TYPE_1, VideoType.TYPE_2, VideoType.TYPE_3)
GLOBAL_POOL_ACCOUNT = "pool_global"


class MediaPoolService:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        collector: InstagramCollector,
        selector: ImageSelector,
    ) -> None:
        self.settings = settings
        self.state = state
        self.collector = collector
        self.selector = selector

    def refill(self, usernames: list[str]) -> dict[str, Any]:
        target = max(1, self.settings.pool_target_images)
        pool = self._normalise_pool(self.state.read_media_pool())
        before = self._stock_counts(pool)
        cooldowns = self.state.read_account_cooldowns()
        now = datetime.now(timezone.utc)

        added_by_account: dict[str, int] = {}
        valid_by_account: dict[str, int] = {}
        errors: dict[str, str] = {}
        skipped_cooldown: list[str] = []
        scraped: list[str] = []

        for username in usernames:
            if self._pool_ready(pool, usernames, target):
                break
            cooldown_until = self._cooldown_until(cooldowns, username)
            if cooldown_until is not None and cooldown_until > now:
                skipped_cooldown.append(username)
                continue
            try:
                candidates = self.collector.collect_one(username, use_cache=False)
            except Exception as error:  # noqa: BLE001
                LOGGER.warning("@%s no se pudo rellenar en pool: %s", username, error)
                errors[username] = str(error)
                continue

            scraped.append(username)
            valid_candidates = self._valid_pool_candidates(candidates)
            added = self._merge_candidates_into_pool(pool, valid_candidates)
            added_by_account[username] = added
            valid_by_account[username] = len(valid_candidates)

            scraped_at = now.isoformat()
            cooldown_until_text = (
                now + timedelta(days=max(1, self.settings.account_cooldown_days))
            ).isoformat()
            self.state.set_account_cooldown(
                username,
                cooldown_until=cooldown_until_text,
                scraped_at=scraped_at,
                added_count=added,
                valid_count=len(valid_candidates),
                total_count=len(candidates),
            )
            cooldowns[username] = {"cooldown_until": cooldown_until_text}

        pool["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state.write_media_pool(pool)
        after = self._stock_counts(pool)
        viable_accounts_after = self._viable_accounts_by_type(pool, usernames)
        viable_after = {
            video_type: bool(accounts)
            for video_type, accounts in viable_accounts_after.items()
        }
        return {
            "target": target,
            "before": before,
            "after": after,
            "viable_after": viable_after,
            "viable_accounts_after": viable_accounts_after,
            "ready": self._pool_ready(pool, usernames, target),
            "added": sum(added_by_account.values()),
            "added_by_account": added_by_account,
            "valid_by_account": valid_by_account,
            "valid_by_type_by_account": self._valid_by_type_by_account(pool, added_by_account),
            "scraped": scraped,
            "skipped_cooldown": skipped_cooldown,
            "errors": errors,
        }

    def select_plan(
        self,
        usernames: list[str],
        video_type: VideoType,
        language: Language,
        *,
        skip_accounts: list[str] | None = None,
    ) -> tuple[VideoPlan, list[str]]:
        pool = self._normalise_pool(self.state.read_media_pool())
        candidates_by_account = self._available_candidates_by_account(
            pool,
            video_type=video_type,
            usernames=usernames,
            skip_accounts=skip_accounts or [],
        )
        ordered_accounts = self._ordered_accounts(
            list(candidates_by_account),
            pool=pool,
            video_type=video_type,
        )
        candidates = [
            candidate
            for account in ordered_accounts
            for candidate in candidates_by_account[account]
        ]
        if not candidates:
            raise ValueError(
                "No hay fotos disponibles en el pool global. "
                "Ejecuta /download_pool para rellenarlo."
            )

        try:
            plan = self.selector.create_plan(
                {GLOBAL_POOL_ACCOUNT: candidates},
                video_type,
                language,
            )
        except ValueError as error:
            LOGGER.info("Pool global no viable: %s", error)
            detail = f"\n{error}"
            raise ValueError(
                "No hay fotos suficientes en el pool global para este tipo de video. "
                "Ejecuta /download_pool para rellenarlo."
                + detail
            ) from error

        plan.chosen_account = self._primary_account_for_plan(plan, candidates)
        return plan, ordered_accounts

    def note_account_used(self, account: str, video_type: VideoType) -> None:
        pool = self._normalise_pool(self.state.read_media_pool())
        pool["cursor_by_type"][video_type.value] = account
        pool["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state.write_media_pool(pool)

    def pick_extra_image(
        self,
        account: str,
        video_type: VideoType,
    ) -> MediaCandidate:
        pool = self._normalise_pool(self.state.read_media_pool())
        candidates_by_account = self._available_candidates_by_account(
            pool,
            video_type=video_type,
            usernames=[account],
            skip_accounts=[],
            include_landscape_exceptions=False,
        )
        candidates = candidates_by_account.get(account, [])
        if not candidates:
            raise ValueError(
                f"No quedan fotos disponibles de @{account} en el pool."
            )
        return self.selector.pick_extra_image(candidates, video_type)

    def stock_counts(self) -> dict[str, Any]:
        return self._stock_counts(self._normalise_pool(self.state.read_media_pool()))

    def is_low_stock(self, video_type: VideoType | None = None) -> bool:
        counts = self.stock_counts()
        threshold = max(1, self.settings.pool_low_stock_threshold)
        if video_type is None:
            return int(counts["total"]) <= threshold
        return int(counts["by_type"].get(video_type.value, 0)) <= threshold

    def _valid_pool_candidates(
        self,
        candidates: list[MediaCandidate],
    ) -> list[tuple[MediaCandidate, list[str]]]:
        self.selector._prepare_candidates(candidates)
        valid: list[tuple[MediaCandidate, list[str]]] = []
        for candidate in candidates:
            if candidate.metrics is None:
                continue
            keys = self.selector.reservation_keys_for([candidate])
            if self.state.any_media_used(keys):
                continue
            eligible_types = self._eligible_types(candidate)
            if not eligible_types:
                continue
            valid.append((candidate, eligible_types))
        return valid

    def _eligible_types(self, candidate: MediaCandidate) -> list[str]:
        return [video_type.value for video_type in ALL_VIDEO_TYPES]

    def _merge_candidates_into_pool(
        self,
        pool: dict[str, Any],
        candidates: list[tuple[MediaCandidate, list[str]]],
    ) -> int:
        items = pool["items"]
        seen_keys: set[str] = set()
        for item in items:
            seen_keys.update(self._item_keys(item))

        added = 0
        for candidate, eligible_types in candidates:
            keys = self.selector.reservation_keys_for([candidate])
            if self._keys_conflict(seen_keys, set(keys)):
                continue
            payload = self._candidate_to_item(candidate, eligible_types)
            items.append(payload)
            seen_keys.update(keys)
            added += 1
        return added

    def _available_candidates_by_account(
        self,
        pool: dict[str, Any],
        *,
        video_type: VideoType,
        usernames: list[str],
        skip_accounts: list[str],
        include_landscape_exceptions: bool = True,
    ) -> dict[str, list[MediaCandidate]]:
        allowed = {username.lower() for username in usernames}
        skipped = {account.lower() for account in skip_accounts}
        by_account: dict[str, list[MediaCandidate]] = {}
        for item in pool["items"]:
            account = str(item.get("source_account") or "").lower()
            if allowed and account not in allowed:
                continue
            if account in skipped:
                continue
            if not Path(str(item.get("local_path") or "")).exists():
                continue
            if self.state.any_media_used(list(self._item_keys(item))):
                continue
            candidate = self._item_to_candidate(item)
            if not self._candidate_allowed_for_type(
                candidate,
                video_type,
                include_landscape_exceptions=include_landscape_exceptions,
            ):
                continue
            by_account.setdefault(account, []).append(candidate)
        return by_account

    def _ordered_accounts(
        self,
        accounts: list[str],
        *,
        pool: dict[str, Any],
        video_type: VideoType,
    ) -> list[str]:
        if not accounts:
            return []
        last_account = str(pool.get("cursor_by_type", {}).get(video_type.value) or "")
        if last_account not in accounts:
            return accounts
        index = accounts.index(last_account)
        return accounts[index + 1 :] + accounts[: index + 1]

    def _pool_ready(
        self,
        pool: dict[str, Any],
        usernames: list[str],
        target: int,
    ) -> bool:
        counts = self._stock_counts(pool)
        if int(counts["total"]) < target:
            return False
        viable = self._viable_accounts_by_type(pool, usernames)
        return all(bool(viable.get(video_type.value)) for video_type in ALL_VIDEO_TYPES)

    def _viable_accounts_by_type(
        self,
        pool: dict[str, Any],
        usernames: list[str],
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for video_type in ALL_VIDEO_TYPES:
            candidates_by_account = self._available_candidates_by_account(
                pool,
                video_type=video_type,
                usernames=usernames,
                skip_accounts=[],
            )
            result[video_type.value] = []
            candidates = [
                candidate
                for account_candidates in candidates_by_account.values()
                for candidate in account_candidates
            ]
            try:
                self.selector.create_plan(
                    {GLOBAL_POOL_ACCOUNT: candidates},
                    video_type,
                    Language.ES,
                )
            except Exception:  # noqa: BLE001
                continue
            result[video_type.value].append(GLOBAL_POOL_ACCOUNT)
        return result

    def _stock_counts(self, pool: dict[str, Any]) -> dict[str, Any]:
        by_type = {video_type.value: 0 for video_type in ALL_VIDEO_TYPES}
        by_account: dict[str, int] = {}
        total_seen: set[str] = set()
        for item in pool["items"]:
            keys = list(self._item_keys(item))
            if not keys or self.state.any_media_used(keys):
                continue
            if not Path(str(item.get("local_path") or "")).exists():
                continue
            source_id = str(item.get("source_id") or "")
            if source_id:
                total_seen.add(source_id)
            account = str(item.get("source_account") or "").lower()
            if account:
                by_account[account] = by_account.get(account, 0) + 1
            for video_type in ALL_VIDEO_TYPES:
                by_type[video_type.value] += 1
        return {
            "total": len(total_seen),
            "by_type": by_type,
            "by_account": dict(sorted(by_account.items())),
        }

    def _valid_by_type_by_account(
        self,
        pool: dict[str, Any],
        touched_accounts: dict[str, int],
    ) -> dict[str, dict[str, int]]:
        touched = {account.lower() for account in touched_accounts}
        result: dict[str, dict[str, int]] = {
            account: {video_type.value: 0 for video_type in ALL_VIDEO_TYPES}
            for account in touched_accounts
        }
        for item in pool["items"]:
            account = str(item.get("source_account") or "").lower()
            if account not in touched:
                continue
            result.setdefault(
                account,
                {video_type.value: 0 for video_type in ALL_VIDEO_TYPES},
            )
            for video_type in ALL_VIDEO_TYPES:
                result[account][video_type.value] += 1
        return result

    def _candidate_to_item(
        self,
        candidate: MediaCandidate,
        eligible_types: list[str],
    ) -> dict[str, Any]:
        return {
            "source_account": candidate.source_account,
            "source_id": candidate.source_id,
            "local_path": str(candidate.local_path),
            "permalink": candidate.permalink,
            "caption": candidate.caption,
            "width": candidate.width,
            "height": candidate.height,
            "created_at": candidate.created_at,
            "metrics": asdict(candidate.metrics) if candidate.metrics else None,
            "content_fingerprint": candidate.content_fingerprint,
            "content_fingerprints": list(candidate.content_fingerprints),
            "eligible_types": [video_type.value for video_type in ALL_VIDEO_TYPES],
            "added_at": datetime.now(timezone.utc).isoformat(),
        }

    def _candidate_allowed_for_type(
        self,
        candidate: MediaCandidate,
        video_type: VideoType,
        *,
        include_landscape_exceptions: bool,
    ) -> bool:
        return True

    def _primary_account_for_plan(
        self,
        plan: VideoPlan,
        candidates: list[MediaCandidate],
    ) -> str:
        counts: dict[str, int] = {}
        for slide in plan.slides:
            if slide.fixed_asset:
                continue
            account = slide.media.source_account.strip().lower()
            if account:
                counts[account] = counts.get(account, 0) + 1
        if not counts:
            selected = set(plan.used_media_ids)
            for candidate in candidates:
                keys = set(self.selector.reservation_keys_for([candidate]))
                if not selected.intersection(keys):
                    continue
                account = candidate.source_account.strip().lower()
                if account:
                    counts[account] = counts.get(account, 0) + 1
        if counts:
            return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        return candidates[0].source_account if candidates else plan.chosen_account

    def _item_to_candidate(self, item: dict[str, Any]) -> MediaCandidate:
        metrics = item.get("metrics")
        candidate = MediaCandidate(
            source_account=str(item["source_account"]),
            source_id=str(item["source_id"]),
            local_path=Path(str(item["local_path"])),
            permalink=str(item.get("permalink", "")),
            caption=str(item.get("caption", "")),
            width=int(item.get("width", 0)),
            height=int(item.get("height", 0)),
            created_at=str(item.get("created_at", "")),
            metrics=ImageMetrics(**metrics) if isinstance(metrics, dict) else None,
            content_fingerprint=item.get("content_fingerprint"),
            content_fingerprints=list(item.get("content_fingerprints") or []),
        )
        return candidate

    def _item_keys(self, item: dict[str, Any]) -> set[str]:
        keys = {str(item.get("source_id") or "")}
        keys.update(str(key) for key in item.get("content_fingerprints") or [] if key)
        if item.get("content_fingerprint"):
            keys.add(str(item["content_fingerprint"]))
        keys.discard("")
        return keys

    def _keys_conflict(self, existing: set[str], incoming: set[str]) -> bool:
        if existing.intersection(incoming):
            return True
        incoming_dhashes = [key for key in incoming if key.startswith("dhash:")]
        if not incoming_dhashes:
            return False
        existing_dhashes = [key for key in existing if key.startswith("dhash:")]
        for incoming_hash in incoming_dhashes:
            for existing_hash in existing_dhashes:
                if self._dhash_distance(incoming_hash, existing_hash) <= 6:
                    return True
        return False

    def _dhash_distance(self, first: str, second: str) -> int:
        try:
            first_value = int(first.split(":", maxsplit=1)[1], 16)
            second_value = int(second.split(":", maxsplit=1)[1], 16)
        except (IndexError, ValueError):
            return 65
        return (first_value ^ second_value).bit_count()

    def _normalise_pool(self, pool: dict[str, Any]) -> dict[str, Any]:
        if pool.get("version") != POOL_VERSION:
            pool["version"] = POOL_VERSION
        if not isinstance(pool.get("items"), list):
            pool["items"] = []
        if not isinstance(pool.get("cursor_by_type"), dict):
            pool["cursor_by_type"] = {}
        return pool

    def _cooldown_until(
        self, cooldowns: dict[str, Any], username: str
    ) -> datetime | None:
        raw = cooldowns.get(username.lower(), {})
        if not isinstance(raw, dict):
            return None
        value = raw.get("cooldown_until")
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
