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
    def create_plan(self, catalog, video_type, language):
        account = next(iter(catalog))
        return VideoPlan(
            chosen_account=account,
            video_type=video_type,
            language=language,
            slides=[],
            used_media_ids=[catalog[account][0].source_id],
        )

    def create_mixed_pool_plan(self, catalog, video_type, language):
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

    def create_mixed_pool_plan(self, catalog, video_type, language):
        candidates = [
            candidate
            for account_candidates in catalog.values()
            for candidate in account_candidates
        ]
        if video_type == VideoType.TYPE_1 and len(candidates) < 6:
            raise ValueError("need six mixed")
        picked = candidates[:6] if video_type == VideoType.TYPE_1 else candidates[:1]
        return VideoPlan(
            chosen_account=picked[0].source_account,
            video_type=video_type,
            language=language,
            slides=[],
            used_media_ids=[candidate.source_id for candidate in picked],
        )


class TypeCompatibilitySelector(FakePlanSelector):
    def _is_type_1_person_visible_media(self, candidate):
        return candidate.source_id.endswith(":TYPE1:0")

    def _is_type_2_user_visible_media(self, candidate):
        return candidate.source_id.endswith(":TYPE2:0")

    def _score_type_3_hook(self, candidate):
        return 1.0 if candidate.source_id.endswith(":TYPE3:0") else 0.0


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


def test_pool_select_plan_can_mix_accounts_when_no_single_account_has_enough():
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

        plan, tried = service.select_plan(
            [f"account{index}" for index in range(6)],
            VideoType.TYPE_1,
            Language.ES,
        )

        assert len(tried) == 6
        assert len(plan.used_media_ids) == 6
        assert len({source_id.split(":", 1)[0] for source_id in plan.used_media_ids}) == 6
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_select_plan_respects_account_attempt_limit():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"pool-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            data_dir=root,
            state_dir=root / "state",
            account_pick_attempts=2,
        )
        state = StateStore(settings.state_dir)
        items = []
        accounts = ["alpha", "beta", "gamma"]
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
            RequiresSixSelector(),  # type: ignore[arg-type]
        )

        try:
            service.select_plan(accounts, VideoType.TYPE_1, Language.ES)
        except ValueError as error:
            assert "2/3 cuentas probadas" in str(error)
        else:  # pragma: no cover - defensive assertion for readability
            raise AssertionError("pool picker should stop at the configured limit")
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


def test_pool_stock_counts_only_marks_type_viable_when_account_can_build_plan():
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


def test_pool_ready_uses_global_stock_not_legacy_type_buckets():
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
                        else [VideoType.TYPE_2.value, VideoType.TYPE_3.value]
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

        assert service._pool_ready(pool, ["alpha"], 10) is True
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
        assert VideoType.TYPE_2.value in landscape_types
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
            VideoType.TYPE_2.value,
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


def test_pool_extra_image_excludes_landscape_exception_for_type_1():
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
