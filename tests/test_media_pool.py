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


def test_pool_ready_requires_viable_plan_for_each_type():
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
                _pool_item("alpha", f"alpha:POST{index}:0", image_path)
                for index in range(60)
            ],
        }
        service = MediaPoolService(
            settings,
            state,
            None,  # type: ignore[arg-type]
            FakePlanSelector(),  # type: ignore[arg-type]
        )

        assert service._pool_ready(pool, ["alpha"], 50) is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_pool_eligibility_for_type_1_and_2_requires_person_or_landscape():
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

        assert VideoType.TYPE_1.value not in object_types
        assert VideoType.TYPE_2.value not in object_types
        assert VideoType.TYPE_1.value in landscape_types
        assert VideoType.TYPE_2.value in landscape_types
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
        },
        "content_fingerprint": f"dhash:{source_id[-1] * 16}",
        "content_fingerprints": [f"dhash:{source_id[-1] * 16}"],
        "eligible_types": eligible_types or [VideoType.TYPE_3.value],
    }
