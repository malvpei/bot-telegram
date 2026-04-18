import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.config import Settings, get_settings
from app.models import (
    ImageMetrics,
    Language,
    MediaCandidate,
    SlideRole,
    TYPE_1_ROLES,
    TYPE_2_ROLES,
    VideoType,
)
from app.selector import ImageSelector
from app.state import StateStore


@pytest.fixture()
def temp_workspace():
    root = Path(tempfile.mkdtemp(prefix="selector-test-"))
    fixed_dir = root / "fixed"
    fixed_dir.mkdir()
    fixed_image_path = fixed_dir / "imagen6.png"
    _write_sample_image(fixed_image_path, color=(120, 120, 120), landscape=False)

    state_dir = root / "state"
    state_dir.mkdir()
    downloads_dir = root / "downloads"
    downloads_dir.mkdir()

    base = get_settings()
    settings = replace(
        base,
        root_dir=root,
        app_dir=root / "app",
        data_dir=root,
        downloads_dir=downloads_dir,
        outputs_dir=root / "outputs",
        state_dir=state_dir,
        fixed_assets_dir=fixed_dir,
        fonts_dir=root / "fonts",
        fixed_image_path=fixed_image_path,
    )
    try:
        yield settings, StateStore(state_dir)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _write_sample_image(path: Path, *, color: tuple[int, int, int], landscape: bool) -> None:
    if landscape:
        width, height = 1280, 720
    else:
        width, height = 1080, 1080
    array = np.full((height, width, 3), color, dtype=np.uint8)
    # Give the "sky" heuristic something to latch onto.
    array[: height // 3, :] = (150, 190, 230)
    Image.fromarray(array).save(path)


def _make_candidate(
    path: Path,
    *,
    username: str,
    idx: int,
    caption: str = "",
    landscape: bool = False,
    color: tuple[int, int, int] = (180, 180, 180),
) -> MediaCandidate:
    local_path = path / f"{username}_{idx}.jpg"
    _write_sample_image(local_path, color=color, landscape=landscape)
    with Image.open(local_path) as image:
        width, height = image.size
    return MediaCandidate(
        source_account=username,
        source_id=f"{username}:{idx}",
        local_path=local_path,
        permalink=f"https://instagram.com/{username}/p/{idx}",
        caption=caption,
        width=width,
        height=height,
        created_at="2026-01-01T00:00:00",
    )


def test_type_1_plan_aligns_fixed_slide_and_roles(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "alpha"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="alpha", idx=i, caption="beach sunset")
        for i in range(8)
    ]
    # Force enough faces to satisfy hook-friendly scoring paths.
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.85, daylight=0.8, faces=1, is_landscape=True, outdoor=0.7
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"alpha": candidates}, VideoType.TYPE_1, Language.ES)

    assert len(plan.slides) == 7
    assert [slide.role for slide in plan.slides] == list(TYPE_1_ROLES)
    february_slide = next(slide for slide in plan.slides if slide.role == SlideRole.FEBRUARY)
    assert february_slide.fixed_asset is True
    assert february_slide.media.source_account == "fixed"
    # Fixed slide is not counted as a "used" ID so it can recur.
    assert "fixed:imagen6" not in plan.used_media_ids


def test_type_2_plan_fixed_tip3_and_hook_requires_face(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "beta"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="beta", idx=i, caption="luxury")
        for i in range(6)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.8, daylight=0.7, faces=1, is_landscape=False, luxury=0.8
        )
    # One landscape is enough to pass the "at least one landscape" rule.
    candidates[-1].metrics = _metrics_stub(
        quality=0.8, daylight=0.7, faces=1, is_landscape=True, luxury=0.8, outdoor=0.6
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"beta": candidates}, VideoType.TYPE_2, Language.ES)

    assert [slide.role for slide in plan.slides] == list(TYPE_2_ROLES)
    tip3_slide = next(slide for slide in plan.slides if slide.role == SlideRole.TIP3)
    assert tip3_slide.fixed_asset is True
    assert tip3_slide.media.source_account == "fixed"


def test_type_2_rejects_account_without_any_face(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "gamma"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="gamma", idx=i) for i in range(6)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.8, daylight=0.8, faces=0, is_landscape=False
        )

    selector = ImageSelector(settings, state)
    with pytest.raises(ValueError):
        selector.create_plan({"gamma": candidates}, VideoType.TYPE_2, Language.ES)


def test_type_1_landscape_fallback_does_not_touch_february(temp_workspace):
    settings, state = temp_workspace
    main_dir = settings.downloads_dir / "main"
    main_dir.mkdir()
    backup_dir = settings.downloads_dir / "backup"
    backup_dir.mkdir()

    main_candidates = [
        _make_candidate(main_dir, username="main", idx=i) for i in range(7)
    ]
    for candidate in main_candidates:
        candidate.metrics = _metrics_stub(
            quality=0.85, daylight=0.8, faces=1, is_landscape=False, outdoor=0.3
        )

    backup_candidates = [
        _make_candidate(backup_dir, username="backup", idx=i, landscape=True)
        for i in range(3)
    ]
    for candidate in backup_candidates:
        candidate.metrics = _metrics_stub(
            quality=0.8, daylight=0.8, faces=0, is_landscape=True, outdoor=0.8
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"main": main_candidates, "backup": backup_candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    february_slide = next(slide for slide in plan.slides if slide.role == SlideRole.FEBRUARY)
    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert february_slide.media.source_account == "fixed"
    # Landscape fallback must never replace the hook; it should land on
    # October/November/January.
    assert hook_slide.media.source_account == "main"
    assert plan.fallback_accounts == ["backup"]


def _metrics_stub(
    *,
    quality: float,
    daylight: float,
    faces: int,
    is_landscape: bool,
    outdoor: float = 0.5,
    casual: float = 0.5,
    luxury: float = 0.2,
) -> ImageMetrics:
    return ImageMetrics(
        brightness=150.0,
        daylight=daylight,
        sharpness=500.0,
        faces=faces,
        aspect_ratio=1.3 if is_landscape else 1.0,
        is_landscape=is_landscape,
        outdoor_score=outdoor,
        casual_score=casual,
        luxury_score=luxury,
        quality_score=quality,
        has_visual_luxury=luxury > 0.6,
        sky_ratio=0.25 if is_landscape else 0.05,
    )
