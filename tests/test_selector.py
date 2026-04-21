import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

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
    TYPE_3_ROLES,
    VideoType,
)
from app.selector import ImageSelector
from app.state import StateStore


@pytest.fixture()
def temp_workspace():
    workspace_tmp = Path(__file__).resolve().parents[1] / "data" / "_test_tmp"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    root = workspace_tmp / f"selector-test-{uuid4().hex}"
    root.mkdir()
    fixed_dir = root / "fixed"
    fixed_dir.mkdir()
    fixed_image_path = fixed_dir / "imagen6.png"
    _write_sample_image(fixed_image_path, color=(120, 120, 120), landscape=False)
    type3_backgrounds = root / "tipo3" / "fondocolores"
    type3_backgrounds.mkdir(parents=True)
    for index, color in enumerate(((50, 80, 120), (120, 60, 80), (80, 120, 70))):
        _write_sample_image(
            type3_backgrounds / f"bg_{index}.jpg",
            color=color,
            landscape=False,
        )

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


def test_reservation_keys_block_every_image_from_same_post(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "alpha"
    account_dir.mkdir()
    first = _make_candidate(account_dir, username="alpha", idx=1)
    second = _make_candidate(account_dir, username="alpha", idx=2)
    first.source_id = "alpha:POST1:0"
    second.source_id = "alpha:POST1:1"
    selector = ImageSelector(settings, state)

    used_keys = selector.reservation_keys_for([first])
    state.mark_media_used([first.source_id], "job-1")

    assert "post:alpha:POST1" in used_keys
    assert selector._is_candidate_used(second)


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


def test_type_2_allows_zero_landscapes_even_if_another_account_has_them(temp_workspace):
    settings, state = temp_workspace
    main_dir = settings.downloads_dir / "lifestyle"
    main_dir.mkdir()
    backup_dir = settings.downloads_dir / "backup_landscapes"
    backup_dir.mkdir()

    main_candidates = [
        _make_candidate(main_dir, username="lifestyle", idx=i, caption="old money")
        for i in range(5)
    ]
    for candidate in main_candidates:
        candidate.metrics = _metrics_stub(
            quality=0.86,
            daylight=0.78,
            faces=1,
            is_landscape=False,
            outdoor=0.35,
            casual=0.08,
            luxury=0.72,
            portrait_focus=0.72,
            affluent=0.84,
        )

    backup_candidates = [
        _make_candidate(backup_dir, username="backup_landscapes", idx=i, landscape=True)
        for i in range(3)
    ]
    for candidate in backup_candidates:
        candidate.metrics = _metrics_stub(
            quality=0.82,
            daylight=0.75,
            faces=0,
            is_landscape=True,
            outdoor=0.85,
            casual=0.05,
            luxury=0.45,
            portrait_focus=0.0,
            affluent=0.48,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"lifestyle": main_candidates, "backup_landscapes": backup_candidates},
        VideoType.TYPE_2,
        Language.ES,
    )

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    assert plan.chosen_account == "lifestyle"
    assert not any(media.metrics.is_landscape for media in non_fixed)
    assert plan.fallback_accounts == []


def test_type_2_caps_landscape_dominant_images_to_one(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "delta"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="delta", idx=i, caption="quiet luxury")
        for i in range(6)
    ]
    candidates[0].metrics = _metrics_stub(
        quality=0.78,
        daylight=0.72,
        faces=1,
        is_landscape=False,
        casual=0.08,
        luxury=0.7,
        portrait_focus=0.8,
        affluent=0.82,
    )
    candidates[1].metrics = _metrics_stub(
        quality=0.92,
        daylight=0.82,
        faces=0,
        is_landscape=True,
        outdoor=0.86,
        casual=0.04,
        luxury=0.76,
        portrait_focus=0.05,
        affluent=0.86,
    )
    candidates[2].metrics = _metrics_stub(
        quality=0.9,
        daylight=0.8,
        faces=0,
        is_landscape=True,
        outdoor=0.82,
        casual=0.05,
        luxury=0.73,
        portrait_focus=0.04,
        affluent=0.82,
    )
    candidates[3].metrics = _metrics_stub(
        quality=0.84,
        daylight=0.74,
        faces=1,
        is_landscape=False,
        casual=0.06,
        luxury=0.68,
        portrait_focus=0.7,
        affluent=0.8,
    )
    candidates[4].metrics = _metrics_stub(
        quality=0.8,
        daylight=0.7,
        faces=1,
        is_landscape=False,
        casual=0.1,
        luxury=0.66,
        portrait_focus=0.64,
        affluent=0.76,
    )
    candidates[5].metrics = _metrics_stub(
        quality=0.76,
        daylight=0.68,
        faces=1,
        is_landscape=False,
        casual=0.12,
        luxury=0.62,
        portrait_focus=0.58,
        affluent=0.72,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"delta": candidates}, VideoType.TYPE_2, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    landscape_count = sum(
        1 for media in non_fixed if selector._is_landscape_dominant_media(media)
    )
    assert landscape_count <= 1


def test_type_2_rejects_if_non_user_images_cannot_be_replaced(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "no_user"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="no_user", idx=i, caption="old money")
        for i in range(4)
    ]
    candidates[0].metrics = _metrics_stub(
        quality=0.86,
        daylight=0.8,
        faces=1,
        is_landscape=False,
        luxury=0.7,
        portrait_focus=0.78,
        affluent=0.84,
    )
    for candidate in candidates[1:]:
        candidate.metrics = _metrics_stub(
            quality=0.9,
            daylight=0.8,
            faces=0,
            is_landscape=False,
            outdoor=0.55,
            luxury=0.8,
            portrait_focus=0.0,
            affluent=0.9,
        )

    selector = ImageSelector(settings, state)
    with pytest.raises(ValueError):
        selector.create_plan({"no_user": candidates}, VideoType.TYPE_2, Language.ES)


def test_type_2_replaces_square_non_user_images_until_only_one_remains(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "mixed_user"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="mixed_user", idx=i, caption="quiet luxury")
        for i in range(7)
    ]
    candidates[0].metrics = _metrics_stub(
        quality=0.82,
        daylight=0.75,
        faces=1,
        is_landscape=False,
        luxury=0.68,
        portrait_focus=0.76,
        affluent=0.8,
    )
    for candidate in candidates[1:4]:
        candidate.metrics = _metrics_stub(
            quality=0.94,
            daylight=0.82,
            faces=0,
            is_landscape=False,
            outdoor=0.58,
            luxury=0.82,
            portrait_focus=0.0,
            affluent=0.92,
        )
    for candidate in candidates[4:]:
        candidate.metrics = _metrics_stub(
            quality=0.78,
            daylight=0.72,
            faces=1,
            is_landscape=False,
            luxury=0.55,
            portrait_focus=0.62,
            affluent=0.7,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"mixed_user": candidates}, VideoType.TYPE_2, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    non_user_count = sum(
        1 for media in non_fixed if selector._is_type_2_non_user_media(media)
    )
    assert non_user_count <= 1


def test_type_1_hook_prefers_most_face_visible_image(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "hookface"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="hookface", idx=i) for i in range(7)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.78,
            daylight=0.7,
            faces=1,
            is_landscape=False,
            outdoor=0.2,
            casual=0.2,
            luxury=0.1,
            portrait_focus=0.35,
        )

    candidates[0].metrics = _metrics_stub(
        quality=0.8,
        daylight=0.72,
        faces=1,
        is_landscape=False,
        outdoor=0.15,
        casual=0.18,
        luxury=0.08,
        face_area=0.16,
        face_center=0.92,
        portrait_focus=0.94,
    )
    candidates[1].metrics = _metrics_stub(
        quality=0.85,
        daylight=0.75,
        faces=2,
        is_landscape=False,
        outdoor=0.2,
        casual=0.18,
        luxury=0.08,
        face_area=0.05,
        face_center=0.55,
        portrait_focus=0.28,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"hookface": candidates}, VideoType.TYPE_1, Language.ES)

    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert hook_slide.media.source_id == candidates[0].source_id


def test_type_3_uses_one_real_hook_and_one_background_for_all_tools(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="type3", idx=i, caption="old money laptop")
        for i in range(3)
    ]
    candidates[0].metrics = _metrics_stub(
        quality=0.86,
        daylight=0.78,
        faces=1,
        is_landscape=False,
        casual=0.05,
        luxury=0.75,
        portrait_focus=0.72,
        affluent=0.84,
        laptop=1.0,
        hands=0.5,
    )
    for candidate in candidates[1:]:
        candidate.metrics = _metrics_stub(
            quality=0.6,
            daylight=0.65,
            faces=0,
            is_landscape=True,
            casual=0.3,
            luxury=0.2,
            portrait_focus=0.0,
            affluent=0.25,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"type3": candidates}, VideoType.TYPE_3, Language.ES)

    assert [slide.role for slide in plan.slides] == list(TYPE_3_ROLES)
    assert plan.slides[0].media.source_id == candidates[0].source_id
    assert candidates[0].source_id in plan.used_media_ids
    assert candidates[0].content_fingerprint in plan.used_media_ids
    assert all(slide.fixed_asset for slide in plan.slides[1:])
    assert all(slide.media.source_account == "tipo3_fondo" for slide in plan.slides[1:])
    assert len({slide.media.local_path for slide in plan.slides[1:]}) == 1


def test_visual_fingerprint_blocks_reusing_same_image(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "fingerprint"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="fingerprint", idx=i, caption="old money laptop")
        for i in range(2)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.86,
            daylight=0.78,
            faces=1,
            is_landscape=False,
            casual=0.05,
            luxury=0.75,
            portrait_focus=0.72,
            affluent=0.84,
            laptop=1.0,
            hands=0.5,
        )

    selector = ImageSelector(settings, state)
    selector._prepare_candidates(candidates)
    assert candidates[0].content_fingerprint == candidates[1].content_fingerprint
    state.reserve_media([candidates[0].content_fingerprint], job_id="previous")

    with pytest.raises(ValueError):
        selector.create_plan({"fingerprint": [candidates[1]]}, VideoType.TYPE_3, Language.ES)


def _metrics_stub(
    *,
    quality: float,
    daylight: float,
    faces: int,
    is_landscape: bool,
    outdoor: float = 0.5,
    casual: float = 0.5,
    luxury: float = 0.2,
    face_area: float = 0.04,
    face_center: float = 0.6,
    portrait_focus: float = 0.45,
    affluent: float | None = None,
    laptop: float = 0.0,
    hands: float = 0.0,
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
        face_area_ratio=face_area if faces else 0.0,
        face_center_score=face_center if faces else 0.0,
        portrait_focus_score=portrait_focus,
        affluent_lifestyle_score=luxury if affluent is None else affluent,
        laptop_score=laptop,
        hands_score=hands,
    )
