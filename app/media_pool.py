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
COMPATIBLE_SOURCE_TYPES_BY_REQUESTED = {
    VideoType.TYPE_1: (VideoType.TYPE_1, VideoType.TYPE_2, VideoType.TYPE_3),
    VideoType.TYPE_2: (VideoType.TYPE_2, VideoType.TYPE_3),
    VideoType.TYPE_3: (VideoType.TYPE_3,),
}
MIN_POOL_ITEMS_BY_TYPE = {
    VideoType.TYPE_1: 6,
    VideoType.TYPE_2: 4,
    VideoType.TYPE_3: 1,
}


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
        excluded_accounts = self.state.read_excluded_accounts()
        usernames = [
            username
            for username in usernames
            if username.lower() not in excluded_accounts
        ]
        target = max(1, self.settings.pool_target_images)
        pool = self._normalise_pool(self.state.read_media_pool())
        used_media = self.state.read_used_media()
        before = self._stock_counts(pool, used_media=used_media, usernames=usernames)
        pruned = self._prune_unavailable_items(pool, used_media=used_media)
        cooldowns = self.state.read_account_cooldowns()
        now = datetime.now(timezone.utc)

        added_by_account: dict[str, int] = {}
        valid_by_account: dict[str, int] = {}
        errors: dict[str, str] = {}
        skipped_cooldown: list[str] = []
        refreshed_during_cooldown: list[str] = []
        scraped: list[str] = []
        fresh_limit = max(
            0,
            int(getattr(self.settings, "pool_refill_max_fresh_accounts", 0)),
        )
        fresh_limit_reached = False
        fresh_attempts = 0

        for username in usernames:
            if self._pool_ready(pool, usernames, target, used_media=used_media):
                break
            cooldown_until = self._cooldown_until(cooldowns, username)

            cached_candidates = self._cached_candidates(username)
            if cached_candidates:
                added, valid = self._add_candidates_to_pool(
                    pool,
                    cached_candidates,
                    used_media=used_media,
                    usernames=usernames,
                    target=target,
                )
                if added:
                    added_by_account[username] = (
                        added_by_account.get(username, 0) + added
                    )
                    valid_by_account[username] = (
                        valid_by_account.get(username, 0) + valid
                    )
                if self._pool_ready(pool, usernames, target, used_media=used_media):
                    continue

            if cooldown_until is not None and cooldown_until > now:
                LOGGER.info(
                    "@%s en cooldown; uso cache local y salto red en este refill",
                    username,
                )
                skipped_cooldown.append(username)
                continue

            if fresh_limit and fresh_attempts >= fresh_limit:
                LOGGER.info(
                    "Pool refill fresh-account limit reached (%d); stopping this run",
                    fresh_limit,
                )
                fresh_limit_reached = True
                break

            fresh_attempts += 1
            try:
                candidates = self.collector.collect_one(username, use_cache=False)
            except Exception as error:  # noqa: BLE001
                LOGGER.warning("@%s no se pudo rellenar en pool: %s", username, error)
                errors[username] = str(error)
                continue

            scraped.append(username)
            added, valid = self._add_candidates_to_pool(
                pool,
                candidates,
                used_media=used_media,
                usernames=usernames,
                target=target,
            )
            added_by_account[username] = added_by_account.get(username, 0) + added
            valid_by_account[username] = (
                valid_by_account.get(username, 0) + valid
            )

            scraped_at = now.isoformat()
            cooldown_until_text = (
                now + timedelta(days=max(1, self.settings.account_cooldown_days))
            ).isoformat()
            self.state.set_account_cooldown(
                username,
                cooldown_until=cooldown_until_text,
                scraped_at=scraped_at,
                added_count=added,
                valid_count=valid,
                total_count=len(candidates),
            )
            cooldowns[username] = {"cooldown_until": cooldown_until_text}

        pool["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state.write_media_pool(pool)
        after = self._stock_counts(pool, used_media=used_media, usernames=usernames)
        viable_accounts_after = self._viable_accounts_by_type(
            pool,
            usernames,
            used_media=used_media,
        )
        viable_after = {
            video_type: bool(accounts)
            for video_type, accounts in viable_accounts_after.items()
        }
        ready_by_type = {
            video_type.value: (
                int(after["by_type"].get(video_type.value, 0)) >= target
                and bool(viable_accounts_after.get(video_type.value))
            )
            for video_type in ALL_VIDEO_TYPES
        }
        return {
            "target": target,
            "before": before,
            "after": after,
            "viable_after": viable_after,
            "ready_by_type": ready_by_type,
            "viable_accounts_after": viable_accounts_after,
            "ready": self._pool_ready(
                pool,
                usernames,
                target,
                used_media=used_media,
            ),
            "added": sum(added_by_account.values()),
            "pruned": pruned,
            "added_by_account": added_by_account,
            "valid_by_account": valid_by_account,
            "valid_by_type_by_account": self._valid_by_type_by_account(
                pool,
                added_by_account,
                used_media=used_media,
            ),
            "fresh_limit": fresh_limit,
            "fresh_limit_reached": fresh_limit_reached,
            "fresh_attempts": fresh_attempts,
            "scraped": scraped,
            "skipped_cooldown": skipped_cooldown,
            "refreshed_during_cooldown": refreshed_during_cooldown,
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
        used_media = self.state.read_used_media()
        candidates_by_account = self._available_candidates_by_account(
            pool,
            video_type=video_type,
            usernames=usernames,
            skip_accounts=skip_accounts or [],
            used_media=used_media,
        )
        ordered_accounts = self._ordered_accounts_for_plan(
            candidates_by_account,
            pool=pool,
            video_type=video_type,
        )
        tried: list[str] = []
        last_error: str | None = None
        for account in ordered_accounts:
            tried.append(account)
            try:
                plan = self.selector.create_plan(
                    {account: candidates_by_account[account]},
                    video_type,
                    language,
                )
            except ValueError as error:
                last_error = str(error)
                LOGGER.info("Pool account @%s no viable: %s", account, error)
                continue
            return plan, tried

        detail = f"\nUltimo motivo: {last_error}" if last_error else ""
        raise ValueError(
            "No hay una cuenta del pool que pueda generar este tipo de video. "
            f"Probe todas las cuentas locales disponibles ({len(tried)}/{len(ordered_accounts)}). "
            "Se puede usar busqueda dinamica fuera del pool para encontrar mas fotos."
            + detail
        )

    def add_candidates(self, candidates: list[MediaCandidate]) -> int:
        if not candidates:
            return 0
        pool = self._normalise_pool(self.state.read_media_pool())
        used_media = self.state.read_used_media()
        added, _ = self._add_candidates_to_pool(
            pool,
            candidates,
            used_media=used_media,
        )
        if added:
            pool["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.state.write_media_pool(pool)
        return added

    def note_account_used(self, account: str, video_type: VideoType) -> None:
        pool = self._normalise_pool(self.state.read_media_pool())
        pool["cursor_by_type"][video_type.value] = account
        pool["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state.write_media_pool(pool)

    def exclude_account(self, account: str) -> int:
        normalized = account.strip().lstrip("@").lower()
        if not normalized:
            return 0
        self.state.exclude_account(normalized)
        pool = self._normalise_pool(self.state.read_media_pool())
        before = len(pool["items"])
        pool["items"] = [
            item
            for item in pool["items"]
            if str(item.get("source_account") or "").strip().lstrip("@").lower()
            != normalized
        ]
        removed = before - len(pool["items"])
        if removed:
            pool["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.state.write_media_pool(pool)
        return removed

    def pick_extra_image(
        self,
        account: str,
        video_type: VideoType,
    ) -> MediaCandidate:
        pool = self._normalise_pool(self.state.read_media_pool())
        used_media = self.state.read_used_media()
        candidates_by_account = self._available_candidates_by_account(
            pool,
            video_type=video_type,
            usernames=[account],
            skip_accounts=[],
            used_media=used_media,
        )
        candidates = candidates_by_account.get(account, [])
        if not candidates:
            raise ValueError(
                f"No quedan fotos disponibles de @{account} en el pool."
            )
        return self.selector.pick_extra_image(
            candidates,
            video_type,
            allow_plan_compatible_fallback=True,
        )

    def stock_counts(self, usernames: list[str] | None = None) -> dict[str, Any]:
        used_media = self.state.read_used_media()
        return self._stock_counts(
            self._normalise_pool(self.state.read_media_pool()),
            used_media=used_media,
            usernames=usernames,
        )

    def is_low_stock(
        self,
        video_type: VideoType | None = None,
        usernames: list[str] | None = None,
    ) -> bool:
        counts = self.stock_counts(usernames)
        threshold = max(1, self.settings.pool_low_stock_threshold)
        if video_type is None:
            return int(counts["total"]) <= threshold
        return int(counts["by_type"].get(video_type.value, 0)) <= threshold

    def _valid_pool_candidates(
        self,
        candidates: list[MediaCandidate],
        *,
        used_media: dict[str, Any],
    ) -> list[tuple[MediaCandidate, list[str]]]:
        self.selector._prepare_candidates(candidates)
        valid: list[tuple[MediaCandidate, list[str]]] = []
        for candidate in candidates:
            if candidate.metrics is None:
                continue
            keys = self.selector.reservation_keys_for([candidate])
            if self._keys_used(keys, used_media):
                continue
            eligible_types = self._eligible_types(candidate)
            if not eligible_types:
                continue
            valid.append((candidate, eligible_types))
        return valid

    def _eligible_types(self, candidate: MediaCandidate) -> list[str]:
        return [
            video_type.value
            for video_type in ALL_VIDEO_TYPES
            if self._candidate_counts_for_type(candidate, video_type)
        ]

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

    def _add_candidates_to_pool(
        self,
        pool: dict[str, Any],
        candidates: list[MediaCandidate],
        *,
        used_media: dict[str, Any],
        usernames: list[str] | None = None,
        target: int | None = None,
    ) -> tuple[int, int]:
        items = pool["items"]
        seen_keys: set[str] = set()
        for item in items:
            seen_keys.update(self._item_keys(item))

        added = 0
        valid = 0
        check_readiness = usernames is not None and target is not None
        ready = (
            self._pool_ready(pool, usernames or [], target or 0, used_media=used_media)
            if check_readiness
            else False
        )
        for candidate in candidates:
            if ready:
                break

            known_keys = self._candidate_known_keys(candidate)
            if known_keys and (
                self._keys_used(list(known_keys), used_media)
                or self._keys_conflict(seen_keys, known_keys)
            ):
                continue

            self.selector._prepare_candidates([candidate])
            if candidate.metrics is None:
                continue
            keys = self.selector.reservation_keys_for([candidate])
            if not keys:
                continue
            incoming = set(keys)
            if self._keys_used(keys, used_media) or self._keys_conflict(
                seen_keys, incoming
            ):
                continue
            eligible_types = self._eligible_types(candidate)
            if not eligible_types:
                continue
            items.append(self._candidate_to_item(candidate, eligible_types))
            seen_keys.update(incoming)
            valid += 1
            added += 1
            if check_readiness:
                ready = self._pool_ready(
                    pool,
                    usernames or [],
                    target or 0,
                    used_media=used_media,
                )
        return added, valid

    def _available_candidates_by_account(
        self,
        pool: dict[str, Any],
        *,
        video_type: VideoType,
        usernames: list[str],
        skip_accounts: list[str],
        include_landscape_exceptions: bool = True,
        used_media: dict[str, Any] | None = None,
    ) -> dict[str, list[MediaCandidate]]:
        if used_media is None:
            used_media = self.state.read_used_media()
        allowed = {username.lower() for username in usernames}
        skipped = {account.lower() for account in skip_accounts}
        excluded = self.state.read_excluded_accounts()
        by_account: dict[str, list[MediaCandidate]] = {}
        for item in pool["items"]:
            account = str(item.get("source_account") or "").lower()
            if account in excluded:
                continue
            if allowed and account not in allowed:
                continue
            if account in skipped:
                continue
            if not Path(str(item.get("local_path") or "")).exists():
                continue
            if self._item_used(item, used_media):
                continue
            if not self._item_allowed_for_type(item, video_type):
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

    def _ordered_accounts_for_plan(
        self,
        candidates_by_account: dict[str, list[MediaCandidate]],
        *,
        pool: dict[str, Any],
        video_type: VideoType,
    ) -> list[str]:
        rotated = self._ordered_accounts(
            list(candidates_by_account),
            pool=pool,
            video_type=video_type,
        )
        rotated_index = {account: index for index, account in enumerate(rotated)}
        minimum = MIN_POOL_ITEMS_BY_TYPE[video_type]

        return sorted(
            rotated,
            key=lambda account: (
                self._usable_count_for_type(
                    candidates_by_account[account],
                    video_type,
                ) < minimum,
                -self._usable_count_for_type(
                    candidates_by_account[account],
                    video_type,
                ),
                rotated_index[account],
            ),
        )

    def _pool_ready(
        self,
        pool: dict[str, Any],
        usernames: list[str],
        target: int,
        *,
        used_media: dict[str, Any] | None = None,
    ) -> bool:
        if used_media is None:
            used_media = self.state.read_used_media()
        counts = self._stock_counts(pool, used_media=used_media, usernames=usernames)
        if any(
            int(counts["by_type"].get(video_type.value, 0)) < target
            for video_type in ALL_VIDEO_TYPES
        ):
            return False
        viable = counts["viable_accounts_by_type"]
        return all(bool(viable.get(video_type.value)) for video_type in ALL_VIDEO_TYPES)

    def _prune_unavailable_items(
        self,
        pool: dict[str, Any],
        *,
        used_media: dict[str, Any],
    ) -> int:
        excluded = self.state.read_excluded_accounts()
        kept: list[dict[str, Any]] = []
        for item in pool["items"]:
            account = str(item.get("source_account") or "").strip().lstrip("@").lower()
            path = Path(str(item.get("local_path") or ""))
            if account in excluded or not path.exists() or self._item_used(item, used_media):
                continue
            candidate = self._item_to_candidate(item)
            if candidate.metrics is not None and not self._eligible_types(candidate):
                continue
            kept.append(item)
        removed = len(pool["items"]) - len(kept)
        if removed:
            LOGGER.info("Pool cleanup: retiro %d fotos usadas o ya no aptas", removed)
            pool["items"] = kept
        return removed

    def _viable_accounts_by_type(
        self,
        pool: dict[str, Any],
        usernames: list[str],
        *,
        used_media: dict[str, Any] | None = None,
    ) -> dict[str, list[str]]:
        if used_media is None:
            used_media = self.state.read_used_media()
        result: dict[str, list[str]] = {}
        for video_type in ALL_VIDEO_TYPES:
            candidates_by_account = self._available_candidates_by_account(
                pool,
                video_type=video_type,
                usernames=usernames,
                skip_accounts=[],
                used_media=used_media,
            )
            result[video_type.value] = []
            for account, candidates in candidates_by_account.items():
                usable_count = self._usable_count_for_type(candidates, video_type)
                if usable_count < MIN_POOL_ITEMS_BY_TYPE[video_type]:
                    continue
                result[video_type.value].append(account)
        return result

    def _stock_counts(
        self,
        pool: dict[str, Any],
        *,
        used_media: dict[str, Any] | None = None,
        usernames: list[str] | None = None,
    ) -> dict[str, Any]:
        if used_media is None:
            used_media = self.state.read_used_media()
        excluded = self.state.read_excluded_accounts()
        allowed = {username.lower() for username in usernames or []}
        raw_total_seen: set[str] = set()
        raw_by_account: dict[str, int] = {}
        for item in pool["items"]:
            account = str(item.get("source_account") or "").lower()
            if account in excluded:
                continue
            if allowed and account not in allowed:
                continue
            keys = list(self._item_keys(item))
            if not keys or self._keys_used(keys, used_media):
                continue
            if not Path(str(item.get("local_path") or "")).exists():
                continue
            source_id = str(item.get("source_id") or "")
            if source_id:
                raw_total_seen.add(source_id)
            if account:
                raw_by_account[account] = raw_by_account.get(account, 0) + 1

        by_type = {video_type.value: 0 for video_type in ALL_VIDEO_TYPES}
        by_type_by_account: dict[str, dict[str, int]] = {}
        usable_ids_by_account: dict[str, set[str]] = {}
        viable_accounts_by_type: dict[str, list[str]] = {}

        for video_type in ALL_VIDEO_TYPES:
            video_key = video_type.value
            viable_accounts_by_type[video_key] = []
            candidates_by_account = self._available_candidates_by_account(
                pool,
                video_type=video_type,
                usernames=usernames or [],
                skip_accounts=[],
                used_media=used_media,
            )
            for account, candidates in candidates_by_account.items():
                usable = [
                    candidate
                    for candidate in candidates
                    if self._candidate_counts_for_type(candidate, video_type)
                ]
                if len(usable) < MIN_POOL_ITEMS_BY_TYPE[video_type]:
                    continue
                by_type[video_key] += len(usable)
                by_type_by_account.setdefault(account, {})[video_key] = len(usable)
                viable_accounts_by_type[video_key].append(account)
                usable_ids = usable_ids_by_account.setdefault(account, set())
                usable_ids.update(candidate.source_id for candidate in usable)

        by_account = {
            account: len(source_ids)
            for account, source_ids in usable_ids_by_account.items()
        }
        return {
            "total": sum(len(source_ids) for source_ids in usable_ids_by_account.values()),
            "raw_total": len(raw_total_seen),
            "by_type": by_type,
            "by_account": dict(sorted(by_account.items())),
            "raw_by_account": dict(sorted(raw_by_account.items())),
            "by_type_by_account": {
                account: {
                    video_type.value: counts.get(video_type.value, 0)
                    for video_type in ALL_VIDEO_TYPES
                }
                for account, counts in sorted(by_type_by_account.items())
            },
            "viable_accounts_by_type": viable_accounts_by_type,
        }

    def _valid_by_type_by_account(
        self,
        pool: dict[str, Any],
        touched_accounts: dict[str, int],
        *,
        used_media: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, int]]:
        touched = {account.lower() for account in touched_accounts}
        by_account = self._stock_counts(
            pool,
            used_media=used_media,
        ).get("by_type_by_account", {})
        return {
            account: {
                video_type.value: int(
                    by_account.get(account.lower(), {}).get(video_type.value, 0)
                )
                for video_type in ALL_VIDEO_TYPES
            }
            for account in touched_accounts
            if account.lower() in touched
        }

    def _usable_count_for_type(
        self,
        candidates: list[MediaCandidate],
        video_type: VideoType,
    ) -> int:
        return sum(
            1
            for candidate in candidates
            if self._candidate_counts_for_type(candidate, video_type)
        )

    def _candidate_counts_for_type(
        self,
        candidate: MediaCandidate,
        video_type: VideoType,
    ) -> bool:
        if video_type == VideoType.TYPE_2:
            return self.selector._is_type_2_user_visible_media(candidate)
        return any(
            self._candidate_matches_type_rules(candidate, source_type)
            for source_type in COMPATIBLE_SOURCE_TYPES_BY_REQUESTED[video_type]
        )

    def _candidate_matches_type_rules(
        self,
        candidate: MediaCandidate,
        video_type: VideoType,
    ) -> bool:
        if candidate.metrics is None:
            return False
        if video_type == VideoType.TYPE_1:
            return (
                self.selector._is_type_1_person_visible_media(candidate)
                or self.selector._is_landscape_media(candidate)
            )
        if video_type == VideoType.TYPE_2:
            return (
                self.selector._is_type_2_user_visible_media(candidate)
                or self.selector._is_landscape_media(candidate)
            )
        scorer = getattr(self.selector, "_score_type_3_hook", None)
        if scorer is None:
            return True
        return scorer(candidate) > 0

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
            "eligible_types": self._compatible_eligible_types(eligible_types),
            "added_at": datetime.now(timezone.utc).isoformat(),
        }

    def _item_allowed_for_type(
        self,
        item: dict[str, Any],
        video_type: VideoType,
    ) -> bool:
        raw_types = item.get("eligible_types")
        if not isinstance(raw_types, list) or not raw_types:
            return True
        eligible = {str(value) for value in raw_types}
        return any(
            source_type.value in eligible
            for source_type in COMPATIBLE_SOURCE_TYPES_BY_REQUESTED[video_type]
        )

    def _compatible_eligible_types(self, eligible_types: list[str]) -> list[str]:
        eligible = set(eligible_types)
        requested_types = [
            video_type.value
            for video_type in ALL_VIDEO_TYPES
            if any(
                source_type.value in eligible
                for source_type in COMPATIBLE_SOURCE_TYPES_BY_REQUESTED[video_type]
            )
        ]
        return requested_types

    def _candidate_allowed_for_type(
        self,
        candidate: MediaCandidate,
        video_type: VideoType,
        *,
        include_landscape_exceptions: bool,
    ) -> bool:
        if video_type == VideoType.TYPE_2:
            return self.selector._is_type_2_user_visible_media(candidate)
        if not include_landscape_exceptions:
            return not self.selector._is_landscape_media(candidate)
        return True

    def _item_to_candidate(self, item: dict[str, Any]) -> MediaCandidate:
        metrics = item.get("metrics")
        metric_values = (
            metrics
            if isinstance(metrics, dict)
            and self._has_current_metric_fields(metrics)
            else None
        )
        candidate = MediaCandidate(
            source_account=str(item["source_account"]),
            source_id=str(item["source_id"]),
            local_path=Path(str(item["local_path"])),
            permalink=str(item.get("permalink", "")),
            caption=str(item.get("caption", "")),
            width=int(item.get("width", 0)),
            height=int(item.get("height", 0)),
            created_at=str(item.get("created_at", "")),
            metrics=ImageMetrics(**metric_values) if metric_values else None,
            content_fingerprint=item.get("content_fingerprint"),
            content_fingerprints=list(item.get("content_fingerprints") or []),
        )
        return candidate

    def _has_current_metric_fields(self, metrics: dict[str, Any]) -> bool:
        return all(
            field in metrics
            for field in (
                "sky_ratio",
                "face_area_ratio",
                "portrait_focus_score",
                "body_area_ratio",
                "body_focus_score",
            )
        )

    def _item_keys(self, item: dict[str, Any]) -> set[str]:
        keys = {str(item.get("source_id") or "")}
        keys.update(str(key) for key in item.get("content_fingerprints") or [] if key)
        if item.get("content_fingerprint"):
            keys.add(str(item["content_fingerprint"]))
        keys.discard("")
        return keys

    def _candidate_known_keys(self, candidate: MediaCandidate) -> set[str]:
        keys = {candidate.source_id}
        keys.update(candidate.content_fingerprints)
        if candidate.content_fingerprint:
            keys.add(candidate.content_fingerprint)
        keys.discard("")
        return keys

    def _item_used(self, item: dict[str, Any], used_media: dict[str, Any]) -> bool:
        return self._keys_used(list(self._item_keys(item)), used_media)

    def _keys_used(self, keys: list[str], used_media: dict[str, Any]) -> bool:
        return self.state.any_media_used_in_snapshot(keys, used_media)

    def _cached_candidates(self, username: str) -> list[MediaCandidate]:
        loader = getattr(self.collector, "_load_cached_account", None)
        if not callable(loader):
            return []
        try:
            cached = loader(username)
        except Exception as error:  # noqa: BLE001
            LOGGER.info("@%s no se pudo leer desde cache para pool: %s", username, error)
            return []
        return list(cached or [])

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
