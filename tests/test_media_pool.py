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


def _pool_item(account: str, source_id: str, path: Path) -> dict:
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
            "faces": 1,
            "aspect_ratio": 1,
            "is_landscape": False,
            "outdoor_score": 0.2,
            "casual_score": 0.1,
            "luxury_score": 0.4,
            "quality_score": 0.8,
        },
        "content_fingerprint": f"dhash:{source_id[-1] * 16}",
        "content_fingerprints": [f"dhash:{source_id[-1] * 16}"],
        "eligible_types": [VideoType.TYPE_3.value],
    }
