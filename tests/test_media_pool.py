from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.config import get_settings
from app.media_pool import MediaPoolService
from app.models import ImageMetrics, Language, MediaCandidate, VideoPlan, VideoType
from app.selector import ImageSelector
from app.state import StateStore


class FakePlanSelector:
    def _prepare_candidates(self, media_items):
        return None

    def create_plan(self, catalog, video_type, language):
        account = next(iter(catalog))
        return VideoPlan(
            chosen_account=account,
            video_type=video_type,
            language=language,
            slides=[],
            used_media_ids=[catalog[account][0].source_id],
        )

    def reservation_keys_for(self, media_items):
        return [
            key
            for media in media_items
            for key in (media.source_id, media.content_fingerprint)
            if key
        ]

    def _is_type_1_person_visible_media(self, candidate):
        return True

    def _is_type_2_user_visible_media(self, candidate):
        return True

    def _is_landscape_media(self, candidate):
        return bool(candidate.metrics and candidate.metrics.is_landscape)

    def _score_type_3_hook(self, candidate):
        return 1.0


class RequiresSixSelector(FakePlanSelector):
    def create_plan(self, catalog, video_type, language):
        account = next(iter(catalog))
        candidates = catalog[account]
        if video_type == VideoType.TYPE_1 and len(candidates) < 6:
            raise ValueError("need six")
        picked = candidates[:6] if video_type == VideoType.TYPE_1 else candidates[:1]
        return VideoPlan(
            chosen_account=account,
            video_type=video_type,
            language=language,
            slides=[],
            used_media_ids=[candidate.source_id for candidate in picked],
        )


class OnlyGoodSelector(FakePlanSelector):
    def create_plan(self, catalog, video_type, language):
        account = next(iter(catalog))
        if account != "good":
            raise ValueError("not good")
        return super().create_plan(catalog, video_type, language)


class TypeCompatibilitySelector(FakePlanSelector):
    def _is_type_1_person_visible_media(self, candidate):
        return candidate.source_id.endswith(":TYPE1:0")

    def _is_type_2_user_visible_media(self, candidate):
        return candidate.source_id.endswith(":TYPE2:0")

    def _score_type_3_hook(self, candidate):
        return 1.0 if candidate.source_id.endswith(":TYPE3:0") else 0.0


class CachedOnlyCollector:
    def __init__(self, items):
        self.items = items
        self.collect_called = False

    def _load_cached_account(self, username: str):
        return self.items

    def collect_one(self, username: str, *, use_cache: bool = True):
        self.collect_called = True
        raise AssertionError("cooldown accounts should be filled from cache only")


class RefreshingCollector:
    def __init__(self, cached, fresh):
        self.cached = cached
        self.fresh = fresh
        self.seen: list[str] = []

    def _load_cached_account(self, username: str):
        return self.cached

    def collect_one(self, username: str, *, use_cache: bool = True):
        self.seen.append(f"{username}:{use_cache}")
        return self.fresh


class MappingCollector:
    def __init__(self, items_by_account):
        self.items_by_account = items_by_account

    def _load_cached_account(self, username: str):
        return self.items_by_account.get(username, [])


def test_pool_merge_blocks_near_dhash_duplicates():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        selector = ImageSelector(settings, state)
        service = MediaPoolService(settings, state, None, selector)  # type: ignore[arg-type]
        first = _candidate(root, "alpha:POST1:0", "dhash:0000000000000000")
        second = _candidate(root, "alpha:POST2:0", "dhash:0000000000000001")
        pool = {"version": 1, "items": [], "cursor_by_type": {}}

        added = service._merge_candidates_into_pool(
            pool,
            [
                (first, [VideoType.TYPE_3.value]),
                (second, [VideoType.TYPE_3.value]),
            ],
        )

        assert added == 1
        assert len(pool["items"]) == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_account_audit_marks_exhausted_and_not_viable_accounts():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        alpha = [
            _candidate(root, f"alpha:TYPE1:{index}", f"dhash:{index + 1:016x}")
            for index in range(6)
        ]
        beta = [_candidate(root, "beta:BAD:0", "dhash:eeeeeeeeeeeeeeee")]
        state.mark_media_used([candidate.source_id for candidate in alpha], "job-old")
        service = MediaPoolService(
            settings,
            state,
            MappingCollector({"alpha": alpha, "beta": beta}),
            TypeCompatibilitySelector(),  # type: ignore[arg-type]
        )

        audit = service.account_audit(["alpha", "beta", "gamma"])
        rows = {row["account"]: row for row in audit["accounts"]}

        assert rows["alpha"]["status"] == "exhausted"
        assert rows["alpha"]["available"] == 0
        assert rows["beta"]["status"] == "not_viable"
        assert rows["gamma"]["status"] == "missing_cache"
        assert audit["status_counts"] == {
            "exhausted": 1,
            "not_viable": 1,
            "missing_cache": 1,
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_uses_cached_candidates_during_cooldown():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=1,
        )
        state = StateStore(settings.state_dir)
        dhashes = ("1", "e", "3", "c", "5", "a")
        candidates = [
            _candidate(root, f"alpha:POST{index}:0", f"dhash:{digit * 16}")
            for index, digit in enumerate(dhashes)
        ]
        collector = CachedOnlyCollector(candidates)
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )
        state.set_account_cooldown(
            "alpha",
            cooldown_until="2999-01-01T00:00:00+00:00",
            scraped_at="2026-01-01T00:00:00+00:00",
            added_count=0,
            valid_count=0,
            total_count=0,
        )

        summary = service.refill(["alpha"])

        assert summary["added"] == 6
        assert summary["skipped_cooldown"] == []
        assert summary["scraped"] == []
        assert collector.collect_called is False
        assert state.read_media_pool()["items"][0]["source_id"] == "alpha:POST0:0"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_uses_cached_candidates_before_network_without_cooldown():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=1,
        )
        state = StateStore(settings.state_dir)
        dhashes = ("1", "e", "3", "c", "5", "a")
        candidates = [
            _candidate(root, f"alpha:POST{index}:0", f"dhash:{digit * 16}")
            for index, digit in enumerate(dhashes)
        ]
        collector = CachedOnlyCollector(candidates)
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        summary = service.refill(["alpha"])

        assert summary["added"] == 6
        assert summary["scraped"] == []
        assert collector.collect_called is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_skips_cooldown_account_when_cached_stock_is_already_in_pool():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=10,
        )
        state = StateStore(settings.state_dir)
        cached = _candidate(root, "alpha:CACHED:0", "dhash:1111111111111111")
        fresh = _candidate(root, "alpha:FRESH:0", "dhash:eeeeeeeeeeeeeeee")
        collector = RefreshingCollector([cached], [fresh])
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": [
                    service._candidate_to_item(
                        cached,
                        [VideoType.TYPE_1.value, VideoType.TYPE_2.value, VideoType.TYPE_3.value],
                    )
                ],
            }
        )
        state.set_account_cooldown(
            "alpha",
            cooldown_until="2999-01-01T00:00:00+00:00",
            scraped_at="2026-01-01T00:00:00+00:00",
            added_count=1,
            valid_count=1,
            total_count=1,
        )

        summary = service.refill(["alpha"])

        assert collector.seen == []
        assert summary["skipped_cooldown"] == ["alpha"]
        assert summary["refreshed_during_cooldown"] == []
        assert summary["added"] == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_uses_cached_stock_and_skips_fresh_fetch_during_cooldown():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=10,
        )
        state = StateStore(settings.state_dir)
        cached = _candidate(root, "alpha:CACHED:0", "dhash:1111111111111111")
        fresh = _candidate(root, "alpha:FRESH:0", "dhash:eeeeeeeeeeeeeeee")
        collector = RefreshingCollector([cached], [fresh])
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )
        state.set_account_cooldown(
            "alpha",
            cooldown_until="2999-01-01T00:00:00+00:00",
            scraped_at="2026-01-01T00:00:00+00:00",
            added_count=0,
            valid_count=0,
            total_count=0,
        )

        summary = service.refill(["alpha"])

        assert collector.seen == []
        assert summary["skipped_cooldown"] == ["alpha"]
        assert summary["refreshed_during_cooldown"] == []
        assert summary["added"] == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_combines_cached_and_fresh_stock_without_cooldown():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=10,
        )
        state = StateStore(settings.state_dir)
        cached = _candidate(root, "alpha:CACHED:0", "dhash:1111111111111111")
        fresh = _candidate(root, "alpha:FRESH:0", "dhash:eeeeeeeeeeeeeeee")
        collector = RefreshingCollector([cached], [fresh])
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        summary = service.refill(["alpha"])

        assert collector.seen == ["alpha:False"]
        assert summary["skipped_cooldown"] == []
        assert summary["added"] == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_stops_after_fresh_account_limit():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)

    class FreshCollector:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def _load_cached_account(self, username: str):
            return []

        def collect_one(self, username: str, *, use_cache: bool = True):
            self.seen.append(f"{username}:{use_cache}")
            return [
                _candidate(
                    root,
                    f"{username}:FRESH:0",
                    f"dhash:{format(len(self.seen), 'x') * 16}",
                )
            ]

    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=10,
            pool_refill_max_fresh_accounts=1,
        )
        state = StateStore(settings.state_dir)
        collector = FreshCollector()
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        summary = service.refill(["alpha", "beta", "gamma"])

        assert collector.seen == ["alpha:False"]
        assert summary["scraped"] == ["alpha"]
        assert summary["fresh_attempts"] == 1
        assert summary["fresh_limit"] == 1
        assert summary["fresh_limit_reached"] is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_stops_after_total_account_limit_even_for_cached_cooldown():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)

    class CachedMappingCollector:
        def __init__(self) -> None:
            self.loaded: list[str] = []
            self.collect_called = False

        def _load_cached_account(self, username: str):
            self.loaded.append(username)
            return [
                _candidate(
                    root,
                    f"{username}:CACHED:0",
                    f"dhash:{format(len(self.loaded), 'x') * 16}",
                )
            ]

        def collect_one(self, username: str, *, use_cache: bool = True):
            self.collect_called = True
            raise AssertionError("cooldown accounts should not hit the network")

    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=10,
            pool_refill_max_accounts=2,
            pool_refill_max_fresh_accounts=8,
        )
        state = StateStore(settings.state_dir)
        for account in ["alpha", "beta", "gamma"]:
            state.set_account_cooldown(
                account,
                cooldown_until="2999-01-01T00:00:00+00:00",
                scraped_at="2026-01-01T00:00:00+00:00",
                added_count=0,
                valid_count=0,
                total_count=0,
            )
        collector = CachedMappingCollector()
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        summary = service.refill(["alpha", "beta", "gamma"])

        assert collector.loaded == ["alpha", "beta"]
        assert collector.collect_called is False
        assert summary["accounts_checked"] == 2
        assert summary["account_limit"] == 2
        assert summary["account_limit_reached"] is True
        assert summary["skipped_cooldown"] == ["alpha", "beta"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_select_plan_can_skip_current_account():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        alpha_path = root / "alpha.jpg"
        beta_path = root / "beta.jpg"
        Image.new("RGB", (32, 32), (10, 20, 30)).save(alpha_path)
        Image.new("RGB", (32, 32), (30, 20, 10)).save(beta_path)
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": [
                    _pool_item("alpha", "alpha:POST1:0", alpha_path),
                    _pool_item("beta", "beta:POST1:0", beta_path),
                ],
            }
        )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        plan, tried = service.select_plan(
            ["alpha", "beta"],
            VideoType.TYPE_3,
            Language.ES,
            skip_accounts=["alpha"],
        )

        assert plan.chosen_account == "beta"
        assert tried == ["beta"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_can_add_candidates_without_full_refill():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        candidate = _candidate(root, "alpha:POST1:0", "dhash:1111111111111111")
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        added = service.add_candidates([candidate])
        pool = state.read_media_pool()

        assert added == 1
        assert pool["items"][0]["source_id"] == "alpha:POST1:0"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_ignores_stale_saved_metrics_for_reanalysis():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        selector = ImageSelector(settings, state)
        service = MediaPoolService(settings, state, None, selector)  # type: ignore[arg-type]
        image_path = root / "legacy.jpg"
        Image.new("RGB", (32, 32), (10, 20, 30)).save(image_path)
        item = _pool_item("alpha", "alpha:LEGACY:0", image_path)
        for stale_field in (
            "sky_ratio",
            "face_area_ratio",
            "portrait_focus_score",
            "body_area_ratio",
            "body_focus_score",
        ):
            item["metrics"].pop(stale_field)

        candidate = service._item_to_candidate(item)

        assert candidate.metrics is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_select_plan_never_mixes_accounts_for_one_video():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        image_paths = []
        for index in range(6):
            image_path = root / f"account{index}.jpg"
            Image.new("RGB", (32, 32), (10 + index, 20, 30)).save(image_path)
            image_paths.append(image_path)
        pool = {
            "version": 1,
            "cursor_by_type": {},
            "items": [
                _pool_item(
                    f"account{index}",
                    f"account{index}:POST1:0",
                    image_paths[index],
                )
                for index in range(6)
            ],
        }
        state.write_media_pool(pool)
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            RequiresSixSelector(),  # type: ignore[arg-type]
        )

        try:
            service.select_plan(
                [f"account{index}" for index in range(6)],
                VideoType.TYPE_1,
                Language.ES,
            )
        except ValueError as error:
            assert "No hay una cuenta del pool" in str(error)
        else:  # pragma: no cover - defensive assertion for readability
            raise AssertionError("pool picker must not mix accounts")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_select_plan_tries_all_local_accounts_without_attempt_limit():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            account_pick_attempts=1,
        )
        state = StateStore(settings.state_dir)
        items = []
        accounts = ["bad", "good"]
        for account in accounts:
            image_path = root / f"{account}.jpg"
            Image.new("RGB", (32, 32), (10, 20, 30)).save(image_path)
            items.append(_pool_item(account, f"{account}:POST1:0", image_path))
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": items,
            }
        )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            OnlyGoodSelector(),  # type: ignore[arg-type]
        )

        plan, tried = service.select_plan(accounts, VideoType.TYPE_3, Language.ES)

        assert plan.chosen_account == "good"
        assert tried == ["bad", "good"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_select_plan_continues_past_fast_account_batch():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
        )
        state = StateStore(settings.state_dir)
        accounts = [f"bad{index}" for index in range(8)] + ["good"]
        items = []
        for index, account in enumerate(accounts):
            image_path = root / f"{account}.jpg"
            Image.new("RGB", (32, 32), (10 + index, 20, 30)).save(image_path)
            items.append(_pool_item(account, f"{account}:POST{index}:0", image_path))
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": items,
            }
        )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            OnlyGoodSelector(),  # type: ignore[arg-type]
        )

        plan, tried = service.select_plan(accounts, VideoType.TYPE_3, Language.ES)

        assert plan.chosen_account == "good"
        assert tried == accounts
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_select_plan_can_make_multiple_type_1_videos_from_same_account_stock():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        accounts = []
        account = "alpha"
        accounts.append(account)
        for index in range(12):
            image_path = root / f"{account}_{index}.jpg"
            Image.new("RGB", (32, 32), (10 + index, 20, 30)).save(image_path)
            items.append(_pool_item(account, f"{account}:POST{index}:0", image_path))
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": items,
            }
        )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            RequiresSixSelector(),  # type: ignore[arg-type]
        )

        first, _ = service.select_plan(accounts, VideoType.TYPE_1, Language.ES)
        state.mark_media_used(first.used_media_ids, "job-1")
        second, _ = service.select_plan(accounts, VideoType.TYPE_1, Language.ES)

        assert len(first.used_media_ids) == 6
        assert len(second.used_media_ids) == 6
        assert set(first.used_media_ids).isdisjoint(second.used_media_ids)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_stock_counts_are_fast_and_viability_uses_minimum_counts():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(5):
            image_path = root / f"alpha_{index}.jpg"
            Image.new("RGB", (32, 32), (10 + index, 20, 30)).save(image_path)
            items.append(_pool_item("alpha", f"alpha:POST{index}:0", image_path))
        pool = {"version": 1, "cursor_by_type": {}, "items": items}
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            RequiresSixSelector(),  # type: ignore[arg-type]
        )

        counts = service._stock_counts(pool)

        assert counts["raw_total"] == 5
        assert counts["by_type"][VideoType.TYPE_1.value] == 0
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_stock_counts_type_photos_when_account_can_build_plan():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(6):
            image_path = root / f"alpha_{index}.jpg"
            Image.new("RGB", (32, 32), (10 + index, 20, 30)).save(image_path)
            items.append(_pool_item("alpha", f"alpha:POST{index}:0", image_path))
        pool = {"version": 1, "cursor_by_type": {}, "items": items}
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            RequiresSixSelector(),  # type: ignore[arg-type]
        )

        counts = service._stock_counts(pool)

        assert counts["raw_total"] == 6
        assert counts["by_type"][VideoType.TYPE_1.value] == 6
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == ["alpha"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_does_not_mark_landscape_only_account_viable_for_type_1():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(8):
            image_path = root / f"landscape_{index}.jpg"
            Image.new("RGB", (64, 32), (10 + index, 20, 30)).save(image_path)
            items.append(
                _pool_item(
                    "landscapes",
                    f"landscapes:POST{index}:{index}",
                    image_path,
                    faces=0,
                    is_landscape=True,
                    eligible_types=[VideoType.TYPE_1.value],
                )
            )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            ImageSelector(settings, state),
        )

        counts = service._stock_counts(
            {"version": 1, "cursor_by_type": {}, "items": items}
        )

        assert counts["raw_total"] == 8
        assert counts["by_type"][VideoType.TYPE_1.value] == 0
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_marks_five_people_and_one_landscape_viable_for_type_1():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(5):
            image_path = root / f"person_{index}.jpg"
            Image.new("RGB", (32, 64), (10 + index, 20, 30)).save(image_path)
            items.append(
                _pool_item(
                    "mixed",
                    f"mixed:PERSON{index}:{index}",
                    image_path,
                    eligible_types=[VideoType.TYPE_1.value],
                )
            )
        landscape_path = root / "landscape.jpg"
        Image.new("RGB", (64, 32), (30, 20, 10)).save(landscape_path)
        items.append(
            _pool_item(
                "mixed",
                "mixed:LANDSCAPE:5",
                landscape_path,
                faces=0,
                is_landscape=True,
                eligible_types=[VideoType.TYPE_1.value],
            )
        )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            ImageSelector(settings, state),
        )

        counts = service._stock_counts(
            {"version": 1, "cursor_by_type": {}, "items": items}
        )

        assert counts["by_type"][VideoType.TYPE_1.value] == 6
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == ["mixed"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_rejects_four_portraits_and_two_landscapes_for_type_1():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(4):
            image_path = root / f"portrait_{index}.jpg"
            Image.new("RGB", (32, 64), (10 + index, 20, 30)).save(image_path)
            items.append(
                _pool_item(
                    "mixed",
                    f"mixed:PORTRAIT{index}:{index}",
                    image_path,
                    faces=0,
                    eligible_types=[VideoType.TYPE_1.value],
                )
            )
        for index in range(2):
            image_path = root / f"landscape_{index}.jpg"
            Image.new("RGB", (64, 32), (30, 20 + index, 10)).save(image_path)
            items.append(
                _pool_item(
                    "mixed",
                    f"mixed:LANDSCAPE{index}:{index + 4}",
                    image_path,
                    faces=0,
                    is_landscape=True,
                    eligible_types=[VideoType.TYPE_1.value],
                )
            )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            ImageSelector(settings, state),
        )

        counts = service._stock_counts(
            {"version": 1, "cursor_by_type": {}, "items": items}
        )

        assert counts["by_type"][VideoType.TYPE_1.value] == 0
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_accepts_detector_miss_portraits_for_type_1_hook():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(6):
            image_path = root / f"portrait_{index}.jpg"
            Image.new("RGB", (32, 64), (10 + index, 20, 30)).save(image_path)
            items.append(
                _pool_item(
                    "portraits",
                    f"portraits:POST{index}:{index}",
                    image_path,
                    faces=0,
                    is_landscape=False,
                    eligible_types=[VideoType.TYPE_1.value],
                )
            )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            ImageSelector(settings, state),
        )

        pool = {"version": 1, "cursor_by_type": {}, "items": items}
        counts = service._stock_counts(pool)
        state.write_media_pool(pool)
        plan, tried = service.select_plan(
            ["portraits"],
            VideoType.TYPE_1,
            Language.ES,
        )

        assert counts["by_type"][VideoType.TYPE_1.value] == 6
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == [
            "portraits"
        ]
        assert plan.chosen_account == "portraits"
        assert tried == ["portraits"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_does_not_claim_large_type_stock_from_accounts_without_a_full_plan():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        items = []
        for index in range(6):
            path = root / f"good_{index}.jpg"
            Image.new("RGB", (32, 32), (10 + index, 20, 30)).save(path)
            items.append(
                _pool_item(
                    "good",
                    f"good:POST{index}:0",
                    path,
                    eligible_types=[VideoType.TYPE_1.value],
                )
            )
        for account_index in range(20):
            for image_index in range(5):
                path = root / f"short_{account_index}_{image_index}.jpg"
                Image.new("RGB", (32, 32), (10, 20 + image_index, 30)).save(path)
                items.append(
                    _pool_item(
                        f"short{account_index}",
                        f"short{account_index}:POST{image_index}:0",
                        path,
                        eligible_types=[VideoType.TYPE_1.value],
                    )
                )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        counts = service._stock_counts(
            {"version": 1, "cursor_by_type": {}, "items": items}
        )

        assert counts["raw_total"] == 106
        assert counts["by_type"][VideoType.TYPE_1.value] == 6
        assert counts["viable_accounts_by_type"][VideoType.TYPE_1.value] == ["good"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_ready_requires_target_stock_for_each_type():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        image_path = root / "alpha.jpg"
        Image.new("RGB", (32, 32), (10, 20, 30)).save(image_path)
        pool = {
            "version": 1,
            "cursor_by_type": {},
            "items": [
                _pool_item(
                    "alpha",
                    f"alpha:POST{index}:0",
                    image_path,
                    eligible_types=(
                        [VideoType.TYPE_1.value, VideoType.TYPE_2.value, VideoType.TYPE_3.value]
                        if index < 3
                        else [VideoType.TYPE_1.value]
                    ),
                )
                for index in range(10)
            ],
        }
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        assert service._pool_ready(pool, ["alpha"], 10) is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_ready_when_target_stock_is_met_for_every_type():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        image_path = root / "alpha.jpg"
        Image.new("RGB", (32, 32), (10, 20, 30)).save(image_path)
        pool = {
            "version": 1,
            "cursor_by_type": {},
            "items": [
                _pool_item(
                    "alpha",
                    f"alpha:POST{index}:0",
                    image_path,
                    eligible_types=[
                        VideoType.TYPE_1.value,
                        VideoType.TYPE_2.value,
                        VideoType.TYPE_3.value,
                    ],
                )
                for index in range(10)
            ],
        }
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        assert service._pool_ready(pool, ["alpha"], 10) is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_eligibility_uses_video_rules_with_downward_compatibility():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        selector = ImageSelector(settings, state)
        service = MediaPoolService(settings, state, None, selector)  # type: ignore[arg-type]
        object_photo = _candidate(root, "alpha:OBJECT:0", "dhash:1111111111111111")
        object_photo.metrics.faces = 0
        object_photo.metrics.is_landscape = False
        object_photo.metrics.portrait_focus_score = 0.0
        object_photo.metrics.face_area_ratio = 0.0
        landscape = _candidate(root, "alpha:LANDSCAPE:0", "dhash:2222222222222222")
        landscape.metrics.faces = 0
        landscape.metrics.is_landscape = True

        object_types = service._eligible_types(object_photo)
        landscape_types = service._eligible_types(landscape)

        assert object_types == []
        assert VideoType.TYPE_1.value in landscape_types
        assert VideoType.TYPE_2.value not in landscape_types
        assert VideoType.TYPE_3.value not in landscape_types
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_eligibility_flows_from_higher_types_to_lower_types():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            TypeCompatibilitySelector(),  # type: ignore[arg-type]
        )
        type_1_photo = _candidate(root, "alpha:TYPE1:0", "dhash:1111111111111111")
        type_2_photo = _candidate(root, "alpha:TYPE2:0", "dhash:2222222222222222")
        type_3_photo = _candidate(root, "alpha:TYPE3:0", "dhash:3333333333333333")

        assert service._eligible_types(type_1_photo) == [VideoType.TYPE_1.value]
        assert service._eligible_types(type_2_photo) == [
            VideoType.TYPE_1.value,
            VideoType.TYPE_2.value,
        ]
        assert service._eligible_types(type_3_photo) == [
            VideoType.TYPE_1.value,
            VideoType.TYPE_3.value,
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_item_with_type_2_eligibility_can_be_used_for_type_1_only_downwards():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        type_1_path = root / "type1.jpg"
        type_2_path = root / "type2.jpg"
        Image.new("RGB", (32, 32), (10, 20, 30)).save(type_1_path)
        Image.new("RGB", (32, 32), (30, 20, 10)).save(type_2_path)
        pool = {
            "version": 1,
            "cursor_by_type": {},
            "items": [
                _pool_item(
                    "alpha",
                    "alpha:TYPE1:0",
                    type_1_path,
                    eligible_types=[VideoType.TYPE_1.value],
                ),
                _pool_item(
                    "alpha",
                    "alpha:TYPE2:0",
                    type_2_path,
                    eligible_types=[VideoType.TYPE_2.value],
                ),
            ],
        }
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        type_1_candidates = service._available_candidates_by_account(
            pool,
            video_type=VideoType.TYPE_1,
            usernames=["alpha"],
            skip_accounts=[],
        )
        type_2_candidates = service._available_candidates_by_account(
            pool,
            video_type=VideoType.TYPE_2,
            usernames=["alpha"],
            skip_accounts=[],
        )

        assert [candidate.source_id for candidate in type_1_candidates["alpha"]] == [
            "alpha:TYPE1:0",
            "alpha:TYPE2:0",
        ]
        assert [candidate.source_id for candidate in type_2_candidates["alpha"]] == [
            "alpha:TYPE2:0",
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_extra_image_prefers_non_landscape_person_for_type_1():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        selector = ImageSelector(settings, state)
        service = MediaPoolService(settings, state, None, selector)  # type: ignore[arg-type]
        landscape_path = root / "landscape.jpg"
        person_path = root / "person.jpg"
        Image.new("RGB", (64, 32), (10, 20, 30)).save(landscape_path)
        Image.new("RGB", (32, 64), (30, 20, 10)).save(person_path)
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": [
                    _pool_item(
                        "alpha",
                        "alpha:LANDSCAPE:0",
                        landscape_path,
                        faces=0,
                        is_landscape=True,
                        quality=0.95,
                        eligible_types=[VideoType.TYPE_1.value, VideoType.TYPE_2.value],
                    ),
                    _pool_item(
                        "alpha",
                        "alpha:PERSON:0",
                        person_path,
                        faces=1,
                        is_landscape=False,
                        quality=0.65,
                        eligible_types=[VideoType.TYPE_1.value, VideoType.TYPE_2.value],
                    ),
                ],
            }
        )

        picked = service.pick_extra_image("alpha", VideoType.TYPE_1)

        assert picked.source_id == "alpha:PERSON:0"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_extra_image_falls_back_to_plan_compatible_landscape_for_type_1():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        selector = ImageSelector(settings, state)
        service = MediaPoolService(settings, state, None, selector)  # type: ignore[arg-type]
        image_path = root / "landscape.jpg"
        Image.new("RGB", (64, 32), (10, 20, 30)).save(image_path)
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": [
                    _pool_item(
                        "alpha",
                        "alpha:LANDSCAPE:0",
                        image_path,
                        faces=0,
                        is_landscape=True,
                        quality=0.95,
                        eligible_types=[VideoType.TYPE_1.value],
                    ),
                ],
            }
        )

        picked = service.pick_extra_image("alpha", VideoType.TYPE_1)

        assert picked.source_id == "alpha:LANDSCAPE:0"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_exclude_account_removes_items_and_blocks_future_selection():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        alpha_path = root / "alpha.jpg"
        beta_path = root / "beta.jpg"
        Image.new("RGB", (32, 32), (10, 20, 30)).save(alpha_path)
        Image.new("RGB", (32, 32), (30, 20, 10)).save(beta_path)
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": [
                    _pool_item("alpha", "alpha:POST1:0", alpha_path),
                    _pool_item("alpha", "alpha:POST2:0", alpha_path),
                    _pool_item("beta", "beta:POST1:0", beta_path),
                ],
            }
        )
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        removed = service.exclude_account("alpha")
        candidates = service._available_candidates_by_account(
            state.read_media_pool(),
            video_type=VideoType.TYPE_3,
            usernames=["alpha", "beta"],
            skip_accounts=[],
        )

        assert removed == 2
        assert state.read_excluded_accounts() == {"alpha"}
        assert "alpha" not in candidates
        assert list(candidates) == ["beta"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_refill_keeps_used_items_indexed_while_adding_replacement_stock():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=10,
        )
        state = StateStore(settings.state_dir)
        old = _candidate(root, "alpha:OLD:0", "dhash:1111111111111111")
        fresh = _candidate(root, "alpha:FRESH:0", "dhash:eeeeeeeeeeeeeeee")
        collector = RefreshingCollector([], [fresh])
        service = MediaPoolService(
            settings,
            state,
            collector,
            FakePlanSelector(),  # type: ignore[arg-type]
        )
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {},
                "items": [
                    service._candidate_to_item(
                        old,
                        [VideoType.TYPE_1.value, VideoType.TYPE_2.value, VideoType.TYPE_3.value],
                    )
                ],
            }
        )
        state.mark_media_used([old.source_id], "job-old")

        summary = service.refill(["alpha"])
        item_ids = {
            item["source_id"] for item in state.read_media_pool()["items"]
        }

        assert summary["pruned"] == 0
        assert old.source_id in item_ids
        assert fresh.source_id in item_ids
        assert summary["after"]["total"] == 1

        state.reset_used_media()

        assert service.stock_counts(["alpha"])["total"] == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_restore_cached_readds_every_account_without_network_or_limits():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            pool_target_images=1,
            pool_refill_max_accounts=1,
            pool_refill_max_fresh_accounts=1,
        )
        state = StateStore(settings.state_dir)
        existing = _candidate(root, "existing:POST:0", "dhash:1111111111111111")
        restored = {
            "alpha": [_candidate(root, "alpha:OLD:0", "dhash:2222222222222222")],
            "beta": [_candidate(root, "beta:OLD:0", "dhash:4444444444444444")],
            "gamma": [_candidate(root, "gamma:OLD:0", "dhash:8888888888888888")],
            "blocked": [
                _candidate(root, "blocked:OLD:0", "dhash:eeeeeeeeeeeeeeee")
            ],
        }
        service = MediaPoolService(
            settings,
            state,
            MappingCollector(restored),
            FakePlanSelector(),  # type: ignore[arg-type]
        )
        state.write_media_pool(
            {
                "version": 1,
                "cursor_by_type": {VideoType.TYPE_1.value: "existing"},
                "items": [
                    service._candidate_to_item(
                        existing,
                        [
                            VideoType.TYPE_1.value,
                            VideoType.TYPE_2.value,
                            VideoType.TYPE_3.value,
                        ],
                    )
                ],
            }
        )
        state.exclude_account("blocked")

        summary = service.restore_cached_candidates(
            ["alpha", "beta", "gamma", "alpha", "blocked"]
        )
        pool = state.read_media_pool()
        item_ids = {item["source_id"] for item in pool["items"]}

        assert summary["accounts_checked"] == 3
        assert summary["accounts_with_cache"] == 3
        assert summary["cached_candidates"] == 3
        assert summary["restored_count"] == 3
        assert summary["pool_items_before"] == 1
        assert summary["pool_items_after"] == 4
        assert item_ids == {
            existing.source_id,
            restored["alpha"][0].source_id,
            restored["beta"][0].source_id,
            restored["gamma"][0].source_id,
        }
        assert pool["cursor_by_type"] == {VideoType.TYPE_1.value: "existing"}

        repeated = service.restore_cached_candidates(["alpha", "beta", "gamma"])

        assert repeated["restored_count"] == 0
        assert len(state.read_media_pool()["items"]) == 4
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_addition_stops_analysis_as_soon_as_target_is_ready(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)

    class CountingSelector(FakePlanSelector):
        def __init__(self):
            self.prepared_batch_sizes: list[int] = []

        def _prepare_candidates(self, media_items):
            self.prepared_batch_sizes.append(len(media_items))

    try:
        settings = replace(get_settings(), data_dir=root, state_dir=root / "state")
        state = StateStore(settings.state_dir)
        selector = CountingSelector()
        service = MediaPoolService(settings, state, None, selector)  # type: ignore[arg-type]
        candidates = [
            _candidate(root, f"alpha:POST{index}:0", f"sha256:{index}")
            for index in range(40)
        ]
        ready_calls = 0

        def ready_after_first_batch(*args, **kwargs):
            nonlocal ready_calls
            ready_calls += 1
            return ready_calls >= 2

        monkeypatch.setattr(service, "_pool_ready", ready_after_first_batch)
        added, valid = service._add_candidates_to_pool(
            {"version": 1, "items": [], "cursor_by_type": {}},
            candidates,
            used_media={},
            usernames=["alpha"],
            target=100,
        )

        assert (added, valid) == (16, 16)
        assert selector.prepared_batch_sizes == [16]
        assert ready_calls == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _candidate(root: Path, source_id: str, dhash: str) -> MediaCandidate:
    path = root / (source_id.replace(":", "_") + ".jpg")
    Image.new("RGB", (32, 32), (100, 100, 100)).save(path)
    return MediaCandidate(
        source_account=source_id.split(":", maxsplit=1)[0],
        source_id=source_id,
        local_path=path,
        permalink="",
        caption="",
        width=32,
        height=32,
        created_at="",
        metrics=ImageMetrics(
            brightness=100,
            daylight=0.8,
            sharpness=100,
            faces=1,
            aspect_ratio=1,
            is_landscape=False,
            outdoor_score=0.2,
            casual_score=0.1,
            luxury_score=0.4,
            quality_score=0.8,
        ),
        content_fingerprint=dhash,
        content_fingerprints=[dhash],
    )


def _pool_item(
    account: str,
    source_id: str,
    path: Path,
    *,
    faces: int = 1,
    is_landscape: bool = False,
    quality: float = 0.8,
    eligible_types: list[str] | None = None,
) -> dict:
    return {
        "source_account": account,
        "source_id": source_id,
        "local_path": str(path),
        "permalink": "",
        "caption": "",
        "width": 32,
        "height": 32,
        "created_at": "",
        "metrics": {
            "brightness": 100,
            "daylight": 0.8,
            "sharpness": 100,
            "faces": faces,
            "aspect_ratio": 1.8 if is_landscape else 0.7,
            "is_landscape": is_landscape,
            "outdoor_score": 0.2,
            "casual_score": 0.1,
            "luxury_score": 0.4,
            "quality_score": quality,
            "sky_ratio": 0.25 if is_landscape else 0.05,
            "face_area_ratio": 0.04 if faces else 0.0,
            "face_center_score": 0.6 if faces else 0.0,
            "portrait_focus_score": 0.45 if faces else 0.0,
            "body_area_ratio": 0.0,
            "body_focus_score": 0.0,
        },
        "content_fingerprint": f"dhash:{source_id[-1] * 16}",
        "content_fingerprints": [f"dhash:{source_id[-1] * 16}"],
        "eligible_types": eligible_types or [VideoType.TYPE_3.value],
    }
