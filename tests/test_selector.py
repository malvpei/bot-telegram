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
from app.selector import (
    ImageSelector,
    TYPE_1_REPLACEABLE_FOR_LANDSCAPE,
    TYPE_2_TIP3_FIXED_IMAGE_NAME,
)
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
    _write_sample_image(
        fixed_dir / TYPE_2_TIP3_FIXED_IMAGE_NAME,
        color=(80, 90, 100),
        landscape=False,
    )
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


def test_memory_does_not_block_every_image_from_same_post(temp_workspace):
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

    assert "post:alpha:POST1" not in used_keys
    assert not selector._is_candidate_used(second)


def test_type_1_plan_aligns_fixed_slide_and_roles(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "alpha"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="alpha", idx=i, caption="beach sunset")
        for i in range(8)
    ]
    # Force enough faces to satisfy hook-friendly scoring paths.
    for index, candidate in enumerate(candidates):
        candidate.metrics = _metrics_stub(
            quality=0.85,
            daylight=0.8,
            faces=1,
            is_landscape=index == 0,
            outdoor=0.7,
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
    assert tip3_slide.media.source_id == "fixed:tip3_dropradar"


def test_type_2_rejects_pool_without_visible_people(temp_workspace):
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


def test_type_2_rejects_lifestyle_landscapes_when_user_detection_is_weak(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "lifestyle_landscape"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="lifestyle_landscape", idx=i)
        for i in range(6)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.82,
            daylight=0.75,
            faces=0,
            is_landscape=True,
            outdoor=0.7,
        )

    selector = ImageSelector(settings, state)
    with pytest.raises(ValueError):
        selector.create_plan(
            {"lifestyle_landscape": candidates},
            VideoType.TYPE_2,
            Language.ES,
        )


def test_type_1_never_uses_landscape_from_another_account(temp_workspace):
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
    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    assert hook_slide.media.source_account == "main"
    assert all(media.source_account == "main" for media in non_fixed)
    assert plan.fallback_accounts == []


def test_type_1_does_not_force_landscape_when_all_images_have_people(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "all_people"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="all_people", idx=i)
        for i in range(7)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.82,
            daylight=0.75,
            faces=1,
            is_landscape=False,
            outdoor=0.2,
            casual=0.2,
            luxury=0.05,
            portrait_focus=0.55,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"all_people": candidates}, VideoType.TYPE_1, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    assert all(selector._is_type_1_person_visible_media(media) for media in non_fixed)
    assert not any(media.metrics.is_landscape for media in non_fixed)


def test_type_1_allows_at_most_one_landscape_without_person(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "mostly_people"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="mostly_people", idx=i)
        for i in range(10)
    ]
    candidates[0].metrics = _metrics_stub(
        quality=0.7,
        daylight=0.7,
        faces=1,
        is_landscape=False,
        outdoor=0.15,
        casual=0.1,
        luxury=0.05,
        portrait_focus=0.55,
    )
    for candidate in candidates[1:4]:
        candidate.metrics = _metrics_stub(
            quality=0.99,
            daylight=0.95,
            faces=0,
            is_landscape=True,
            outdoor=1.0,
            casual=0.0,
            luxury=0.05,
            portrait_focus=0.0,
        )
    for candidate in candidates[4:]:
        candidate.metrics = _metrics_stub(
            quality=0.42,
            daylight=0.42,
            faces=1,
            is_landscape=False,
            outdoor=0.05,
            casual=0.05,
            luxury=0.02,
            portrait_focus=0.1,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"mostly_people": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    without_person = [
        media for media in non_fixed
        if not selector._is_type_1_person_visible_media(media)
    ]
    assert len(without_person) <= 1
    assert all(media.metrics.is_landscape for media in without_person)


def test_type_1_allows_landscape_photos_when_person_is_visible(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "landscape_people"
    account_dir.mkdir()

    candidates = [
        _make_candidate(
            account_dir,
            username="landscape_people",
            idx=i,
            landscape=True,
        )
        for i in range(7)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.72,
            daylight=0.68,
            faces=1,
            is_landscape=True,
            outdoor=0.4,
            casual=0.12,
            luxury=0.04,
            portrait_focus=0.5,
        )
    candidates[0].metrics = _metrics_stub(
        quality=0.74,
        daylight=0.7,
        faces=1,
        is_landscape=False,
        outdoor=0.25,
        casual=0.12,
        luxury=0.04,
        portrait_focus=0.55,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"landscape_people": candidates}, VideoType.TYPE_1, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert all(selector._is_type_1_person_visible_media(media) for media in non_fixed)
    assert not selector._is_landscape_media(hook_slide.media)
    assert any(selector._is_landscape_media(media) for media in non_fixed)


def test_type_1_moves_single_landscape_exception_to_secondary_role(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "movable_exception"
    account_dir.mkdir()

    scenic = _make_candidate(
        account_dir,
        username="movable_exception",
        idx=0,
        caption="mountain view",
        landscape=True,
    )
    scenic.metrics = _metrics_stub(
        quality=0.99,
        daylight=0.95,
        faces=0,
        is_landscape=True,
        outdoor=1.0,
        casual=0.0,
        luxury=0.04,
        portrait_focus=0.0,
    )
    candidates = [scenic] + [
        _make_candidate(account_dir, username="movable_exception", idx=i)
        for i in range(1, 6)
    ]
    for candidate in candidates[1:]:
        candidate.metrics = _metrics_stub(
            quality=0.54,
            daylight=0.52,
            faces=1,
            is_landscape=False,
            outdoor=0.08,
            casual=0.08,
            luxury=0.02,
            portrait_focus=0.34,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"movable_exception": candidates}, VideoType.TYPE_1, Language.ES)

    non_fixed_slides = [slide for slide in plan.slides if not slide.fixed_asset]
    scenic_slide = next(
        slide for slide in non_fixed_slides if slide.media.source_id == scenic.source_id
    )
    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert scenic_slide.role in TYPE_1_REPLACEABLE_FOR_LANDSCAPE
    assert selector._is_type_1_person_visible_media(hook_slide.media)


def test_type_1_uses_constrained_fallback_for_known_viable_set(
    temp_workspace,
    monkeypatch,
):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "constrained_fallback"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="constrained_fallback", idx=index)
        for index in range(5)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.68,
            daylight=0.64,
            faces=1,
            is_landscape=False,
            outdoor=0.18,
            casual=0.12,
            luxury=0.04,
            portrait_focus=0.42,
        )
    landscape = _make_candidate(
        account_dir,
        username="constrained_fallback",
        idx=5,
        landscape=True,
    )
    landscape.metrics = _metrics_stub(
        quality=0.96,
        daylight=0.9,
        faces=0,
        is_landscape=True,
        outdoor=0.9,
        portrait_focus=0.0,
    )
    candidates.append(landscape)

    selector = ImageSelector(settings, state)
    monkeypatch.setattr(
        selector,
        "_enforce_type_1_person_visibility",
        lambda *args, **kwargs: False,
    )

    plan = selector.create_plan(
        {"constrained_fallback": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    non_fixed = [slide for slide in plan.slides if not slide.fixed_asset]
    without_person = [
        slide
        for slide in non_fixed
        if not selector._is_type_1_person_visible_media(slide.media)
    ]
    assert len(non_fixed) == 6
    assert len(without_person) == 1
    assert without_person[0].role in TYPE_1_REPLACEABLE_FOR_LANDSCAPE


def test_type_1_treats_scenic_vertical_photos_as_landscape_exceptions(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "scenic_vertical"
    account_dir.mkdir()

    candidates = [
        _make_candidate(
            account_dir,
            username="scenic_vertical",
            idx=i,
            caption="mountain view",
        )
        for i in range(10)
    ]
    for candidate in candidates[:4]:
        candidate.metrics = _metrics_stub(
            quality=0.96,
            daylight=0.92,
            faces=0,
            is_landscape=False,
            outdoor=0.92,
            sky=0.7,
            casual=0.0,
            luxury=0.05,
            portrait_focus=0.0,
        )
        candidate.metrics.aspect_ratio = 0.75
    for candidate in candidates[4:]:
        candidate.metrics = _metrics_stub(
            quality=0.48,
            daylight=0.46,
            faces=1,
            is_landscape=False,
            outdoor=0.12,
            casual=0.08,
            luxury=0.03,
            portrait_focus=0.32,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"scenic_vertical": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    scenic_without_person = [
        media for media in non_fixed
        if not selector._is_type_1_person_visible_media(media)
    ]
    assert len(scenic_without_person) <= 1
    assert all(selector._is_landscape_media(media) for media in scenic_without_person)


def test_tiny_face_detection_does_not_count_as_visible_person(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "tiny_false_face"
    account_dir.mkdir()

    candidate = _make_candidate(account_dir, username="tiny_false_face", idx=1)
    candidate.metrics = _metrics_stub(
        quality=0.9,
        daylight=0.9,
        faces=1,
        is_landscape=False,
        outdoor=0.85,
        sky=0.65,
        face_area=0.001,
        portrait_focus=0.05,
    )

    selector = ImageSelector(settings, state)

    assert not selector._is_person_visible_media(candidate)
    assert selector._is_landscape_media(candidate)


def test_type_1_accepts_full_body_person_without_detected_face(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "full_body"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="full_body", idx=i)
        for i in range(7)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.72,
            daylight=0.68,
            faces=0,
            is_landscape=False,
            outdoor=0.2,
            casual=0.12,
            luxury=0.05,
            portrait_focus=0.0,
            body_area=0.08,
            body_focus=0.42,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"full_body": candidates}, VideoType.TYPE_1, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    assert all(selector._is_type_1_person_visible_media(media) for media in non_fixed)


def test_type_1_extra_image_requires_person_visible(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "extra_people"
    account_dir.mkdir()

    landscape = _make_candidate(
        account_dir,
        username="extra_people",
        idx=1,
        landscape=True,
    )
    person = _make_candidate(account_dir, username="extra_people", idx=2)
    landscape.metrics = _metrics_stub(
        quality=0.99,
        daylight=0.95,
        faces=0,
        is_landscape=True,
        outdoor=1.0,
        casual=0.0,
        luxury=0.05,
        portrait_focus=0.0,
    )
    person.metrics = _metrics_stub(
        quality=0.55,
        daylight=0.55,
        faces=1,
        is_landscape=False,
        outdoor=0.1,
        casual=0.1,
        luxury=0.05,
        portrait_focus=0.3,
    )

    selector = ImageSelector(settings, state)
    picked = selector.pick_extra_image([landscape, person], VideoType.TYPE_1)

    assert picked.source_id == person.source_id


def test_extra_image_requires_non_landscape_person_for_every_type(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "extra_global"
    account_dir.mkdir()

    landscape = _make_candidate(
        account_dir,
        username="extra_global",
        idx=1,
        landscape=True,
    )
    object_photo = _make_candidate(account_dir, username="extra_global", idx=2)
    person = _make_candidate(account_dir, username="extra_global", idx=3)
    landscape.metrics = _metrics_stub(
        quality=0.99,
        daylight=0.95,
        faces=1,
        is_landscape=True,
        outdoor=1.0,
        portrait_focus=0.8,
    )
    object_photo.metrics = _metrics_stub(
        quality=0.98,
        daylight=0.95,
        faces=0,
        is_landscape=False,
        outdoor=0.8,
        portrait_focus=0.0,
    )
    person.metrics = _metrics_stub(
        quality=0.55,
        daylight=0.55,
        faces=1,
        is_landscape=False,
        outdoor=0.1,
        portrait_focus=0.3,
    )

    selector = ImageSelector(settings, state)

    for video_type in (VideoType.TYPE_1, VideoType.TYPE_2, VideoType.TYPE_3):
        picked = selector.pick_extra_image(
            [landscape, object_photo, person],
            video_type,
        )
        assert picked.source_id == person.source_id


def test_extra_image_plan_compatible_fallback_allows_type_1_landscape(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "extra_fallback"
    account_dir.mkdir()

    landscape = _make_candidate(
        account_dir,
        username="extra_fallback",
        idx=1,
        landscape=True,
    )
    landscape.metrics = _metrics_stub(
        quality=0.99,
        daylight=0.95,
        faces=0,
        is_landscape=True,
        outdoor=1.0,
        casual=0.1,
        portrait_focus=0.0,
    )

    selector = ImageSelector(settings, state)

    with pytest.raises(ValueError):
        selector.pick_extra_image([landscape], VideoType.TYPE_1)

    picked = selector.pick_extra_image(
        [landscape],
        VideoType.TYPE_1,
        allow_plan_compatible_fallback=True,
    )

    assert picked.source_id == landscape.source_id


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
        1 for media in non_fixed if selector._is_landscape_media(media)
    )
    assert landscape_count <= 1


def test_type_2_prefers_people_over_higher_quality_landscapes(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "people_first"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="people_first", idx=i, caption="travel")
        for i in range(6)
    ]
    for candidate in candidates[:4]:
        candidate.metrics = _metrics_stub(
            quality=0.58,
            daylight=0.55,
            faces=1,
            is_landscape=False,
            outdoor=0.12,
            casual=0.08,
            portrait_focus=0.34,
        )
    for candidate in candidates[4:]:
        candidate.metrics = _metrics_stub(
            quality=0.99,
            daylight=0.95,
            faces=0,
            is_landscape=True,
            outdoor=1.0,
            casual=0.0,
            portrait_focus=0.0,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"people_first": candidates}, VideoType.TYPE_2, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    assert not any(selector._is_landscape_media(media) for media in non_fixed)


def test_type_2_rejects_object_only_account(temp_workspace):
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
    assert all(
        media.metrics.is_landscape
        for media in non_fixed
        if selector._is_type_2_non_user_media(media)
    )


def test_type_1_hook_accepts_any_high_quality_global_photo(temp_workspace):
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
    assert hook_slide.media.source_id in {candidate.source_id for candidate in candidates}


def test_type_1_hook_never_uses_landscape_photo(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "hook_no_landscape"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="hook_no_landscape", idx=i)
        for i in range(8)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.76,
            daylight=0.7,
            faces=1,
            is_landscape=False,
            outdoor=0.2,
            casual=0.2,
            portrait_focus=0.35,
        )
    landscape = candidates[0]
    landscape.metrics = _metrics_stub(
        quality=0.98,
        daylight=0.95,
        faces=1,
        is_landscape=True,
        outdoor=1.0,
        casual=0.8,
        portrait_focus=0.9,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"hook_no_landscape": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert hook_slide.media.source_id != landscape.source_id
    assert not selector._is_landscape_media(hook_slide.media)


def test_type_1_hook_prefers_detected_person_signal_when_available(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "hook_requires_person"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="hook_requires_person", idx=i)
        for i in range(8)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.92,
            daylight=0.86,
            faces=0,
            is_landscape=False,
            outdoor=0.25,
            casual=0.15,
            portrait_focus=0.0,
        )
        candidate.metrics.aspect_ratio = 0.72

    person = candidates[-1]
    person.metrics = _metrics_stub(
        quality=0.74,
        daylight=0.68,
        faces=1,
        is_landscape=False,
        outdoor=0.18,
        casual=0.18,
        face_area=0.04,
        face_center=0.72,
        portrait_focus=0.55,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"hook_requires_person": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert hook_slide.media.source_id == person.source_id
    assert selector._is_hook_person_visible_media(hook_slide.media)


def test_type_2_hook_never_uses_landscape_photo(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type2_hook_no_landscape"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="type2_hook_no_landscape", idx=i)
        for i in range(6)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.78,
            daylight=0.72,
            faces=1,
            is_landscape=False,
            outdoor=0.25,
            casual=0.2,
            portrait_focus=0.35,
        )
    landscape = candidates[0]
    landscape.metrics = _metrics_stub(
        quality=0.99,
        daylight=0.95,
        faces=1,
        is_landscape=True,
        outdoor=1.0,
        casual=0.9,
        portrait_focus=0.9,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"type2_hook_no_landscape": candidates},
        VideoType.TYPE_2,
        Language.ES,
    )

    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert hook_slide.media.source_id != landscape.source_id
    assert not selector._is_landscape_media(hook_slide.media)


def test_type_3_hook_never_scores_landscape_photo(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3_hook_no_landscape"
    account_dir.mkdir()
    candidate = _make_candidate(
        account_dir,
        username="type3_hook_no_landscape",
        idx=1,
        landscape=True,
    )
    candidate.metrics = _metrics_stub(
        quality=0.98,
        daylight=0.9,
        faces=1,
        is_landscape=True,
        outdoor=1.0,
        luxury=0.8,
        portrait_focus=0.8,
    )

    selector = ImageSelector(settings, state)

    assert selector._score_type_3_hook(candidate) == 0.0


def test_type_3_hook_requires_person_over_laptop_only_photo(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3_hook_requires_person"
    account_dir.mkdir()

    laptop_only = _make_candidate(
        account_dir,
        username="type3_hook_requires_person",
        idx=1,
        caption="old money laptop desk",
    )
    laptop_only.metrics = _metrics_stub(
        quality=0.96,
        daylight=0.9,
        faces=0,
        is_landscape=False,
        outdoor=0.2,
        luxury=0.75,
        portrait_focus=0.0,
        affluent=0.9,
        laptop=1.0,
        hands=1.0,
    )
    person = _make_candidate(
        account_dir,
        username="type3_hook_requires_person",
        idx=2,
        caption="old money laptop",
    )
    person.metrics = _metrics_stub(
        quality=0.72,
        daylight=0.68,
        faces=1,
        is_landscape=False,
        outdoor=0.12,
        luxury=0.45,
        face_area=0.04,
        portrait_focus=0.5,
        affluent=0.55,
        laptop=0.2,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"type3_hook_requires_person": [laptop_only, person]},
        VideoType.TYPE_3,
        Language.ES,
    )

    assert selector._score_type_3_hook(laptop_only) == 0.0
    assert plan.slides[0].media.source_id == person.source_id
    assert selector._is_hook_person_visible_media(plan.slides[0].media)


def test_type_3_hook_accepts_type_2_hook_photo(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3_type2_compatible"
    account_dir.mkdir()

    candidate = _make_candidate(
        account_dir,
        username="type3_type2_compatible",
        idx=1,
    )
    candidate.metrics = _metrics_stub(
        quality=0.24,
        daylight=0.62,
        faces=1,
        is_landscape=False,
        outdoor=0.18,
        casual=0.2,
        luxury=0.05,
        face_area=0.04,
        portrait_focus=0.42,
        affluent=0.05,
        laptop=0.0,
        hands=0.0,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"type3_type2_compatible": [candidate]},
        VideoType.TYPE_3,
        Language.ES,
    )

    assert selector._score_type_2(candidate, SlideRole.HOOK) > 0.0
    assert selector._score_type_3_hook(candidate) > 0.0
    assert plan.slides[0].media.source_id == candidate.source_id


def test_type_3_hook_accepts_quality_portrait_when_detectors_miss_person(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3_detector_miss"
    account_dir.mkdir()

    candidate = _make_candidate(
        account_dir,
        username="type3_detector_miss",
        idx=1,
    )
    candidate.metrics = _metrics_stub(
        quality=0.78,
        daylight=0.64,
        faces=0,
        is_landscape=False,
        casual=0.08,
        luxury=0.42,
        portrait_focus=0.0,
        affluent=0.48,
        laptop=0.0,
        hands=0.0,
    )
    candidate.metrics.aspect_ratio = 0.82

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"type3_detector_miss": [candidate]},
        VideoType.TYPE_3,
        Language.ES,
    )

    assert selector._score_type_3_hook(candidate) > 0.0
    assert plan.slides[0].media.source_id == candidate.source_id


def test_type_1_hook_candidate_must_pass_quality_gate(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "hook_quality"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="hook_quality", idx=i)
        for i in range(8)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.72,
            daylight=0.72,
            faces=1,
            is_landscape=False,
            outdoor=0.25,
            casual=0.25,
            luxury=0.05,
            portrait_focus=0.35,
        )
    candidates[0].metrics = _metrics_stub(
        quality=0.20,
        daylight=0.20,
        faces=3,
        is_landscape=False,
        outdoor=1.0,
        casual=1.0,
        luxury=0.0,
        portrait_focus=1.0,
    )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"hook_quality": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert hook_slide.media.source_id != candidates[0].source_id


def test_type_1_generates_when_face_detector_misses_clear_vertical_photos(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "vertical_no_face"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="vertical_no_face", idx=i)
        for i in range(7)
    ]
    for candidate in candidates:
        candidate.metrics = _metrics_stub(
            quality=0.82,
            daylight=0.74,
            faces=0,
            is_landscape=False,
            outdoor=0.25,
            casual=0.2,
            luxury=0.05,
            portrait_focus=0.0,
        )
        candidate.metrics.aspect_ratio = 0.72
    selector = ImageSelector(settings, state)
    plan = selector.create_plan(
        {"vertical_no_face": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    hook_slide = next(slide for slide in plan.slides if slide.role == SlideRole.HOOK)
    assert [slide.role for slide in plan.slides] == list(TYPE_1_ROLES)
    assert not any(selector._has_person_signal(candidate) for candidate in candidates)
    assert selector._is_type_1_hook_media(hook_slide.media)


def test_type_1_detector_miss_fallback_accepts_moderately_lit_portraits(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "moderate_portraits"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="moderate_portraits", idx=i)
        for i in range(6)
    ]
    for index, candidate in enumerate(candidates):
        candidate.metrics = _metrics_stub(
            quality=0.48 if index == 0 else 0.18,
            daylight=0.24 if index == 0 else 0.14,
            faces=0,
            is_landscape=False,
            outdoor=0.12,
            casual=0.08,
            luxury=0.03,
            portrait_focus=0.0,
        )
        candidate.metrics.aspect_ratio = 0.8

    selector = ImageSelector(settings, state)
    summary = selector.type_1_candidate_summary(candidates)
    plan = selector.create_plan(
        {"moderate_portraits": candidates},
        VideoType.TYPE_1,
        Language.ES,
    )

    assert summary == {
        "total": 6,
        "people": 6,
        "strict_people": 0,
        "fallback_portraits": 6,
        "hooks": 1,
        "landscapes": 0,
    }
    assert plan.chosen_account == "moderate_portraits"


def test_type_1_vertical_person_with_sky_can_score_as_hook(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "vertical_sky_person"
    account_dir.mkdir()
    candidate = _make_candidate(
        account_dir,
        username="vertical_sky_person",
        idx=0,
        caption="beach sky",
    )
    candidate.metrics = _metrics_stub(
        quality=0.72,
        daylight=0.68,
        faces=1,
        is_landscape=True,
        outdoor=0.8,
        casual=0.25,
        luxury=0.04,
        face_area=0.04,
        portrait_focus=0.55,
        sky=0.5,
    )
    candidate.metrics.aspect_ratio = 0.75

    selector = ImageSelector(settings, state)

    assert selector._is_landscape_media(candidate)
    assert selector._is_type_1_hook_media(candidate)
    assert selector._score_type_1(candidate, SlideRole.HOOK) > 0.0


def test_type_1_can_use_multiple_images_from_same_carousel_when_needed(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "carousel_stock"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="carousel_stock", idx=i)
        for i in range(9)
    ]
    for index, candidate in enumerate(candidates):
        candidate.source_id = f"carousel_stock:POST{index // 3}:IMG{index}"
        candidate.metrics = _metrics_stub(
            quality=0.76,
            daylight=0.7,
            faces=1,
            is_landscape=False,
            outdoor=0.18,
            casual=0.14,
            luxury=0.04,
            portrait_focus=0.42,
        )

    selector = ImageSelector(settings, state)
    plan = selector.create_plan({"carousel_stock": candidates}, VideoType.TYPE_1, Language.ES)

    non_fixed = [slide.media for slide in plan.slides if not slide.fixed_asset]
    assert len(non_fixed) == 6
    assert len({media.source_id for media in non_fixed}) == 6


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


def test_type_3_backgrounds_are_cached_between_plan_builds(temp_workspace, monkeypatch):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3_cache"
    account_dir.mkdir()

    candidates = [
        _make_candidate(account_dir, username="type3_cache", idx=i, caption="old money laptop")
        for i in range(2)
    ]
    for index, candidate in enumerate(candidates):
        candidate.metrics = _metrics_stub(
            quality=0.84,
            daylight=0.76,
            faces=1 if index == 0 else 0,
            is_landscape=False,
            casual=0.05,
            luxury=0.72,
            portrait_focus=0.68 if index == 0 else 0.12,
            affluent=0.82,
            laptop=1.0 if index == 0 else 0.2,
            hands=0.4,
        )
        candidate.content_fingerprints = [
            f"sha256:type3-cache-{index}",
            f"dhash:{index + 1:016x}",
        ]
        candidate.content_fingerprint = candidate.content_fingerprints[0]

    selector = ImageSelector(settings, state)
    original_analyze = selector._analyze_image
    analyzed_ids: list[str] = []

    def counting_analyze(media: MediaCandidate) -> ImageMetrics:
        analyzed_ids.append(media.source_id)
        return original_analyze(media)

    monkeypatch.setattr(selector, "_analyze_image", counting_analyze)

    selector.create_plan({"type3_cache": candidates}, VideoType.TYPE_3, Language.ES)
    selector.create_plan({"type3_cache": candidates}, VideoType.TYPE_3, Language.ES)

    background_calls = [source_id for source_id in analyzed_ids if source_id.startswith("tipo3_fondo:")]
    # Decorative backgrounds do not need face/body metrics. Reading only their
    # dimensions avoids decoding and analysing several huge 8K assets.
    assert background_calls == []


def test_type_3_background_catalog_skips_truncated_images(temp_workspace):
    settings, state = temp_workspace
    backgrounds_dir = settings.root_dir / "tipo3" / "fondocolores"
    truncated_path = backgrounds_dir / "truncated.png"
    Image.new("RGB", (320, 480), (40, 80, 120)).save(truncated_path)
    payload = truncated_path.read_bytes()
    truncated_path.write_bytes(payload[: len(payload) // 2])

    backgrounds = ImageSelector(settings, state)._type_3_backgrounds()

    assert truncated_path not in {background.local_path for background in backgrounds}


def test_image_analysis_is_restored_from_persistent_cache(temp_workspace, monkeypatch):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "analysis_cache"
    account_dir.mkdir()
    first = _make_candidate(
        account_dir,
        username="analysis_cache",
        idx=1,
        caption="portrait",
    )
    selector = ImageSelector(settings, state)
    original_analyze = selector._analyze_image
    analyze_calls = 0

    def counting_analyze(media):
        nonlocal analyze_calls
        analyze_calls += 1
        return original_analyze(media)

    monkeypatch.setattr(selector, "_analyze_image", counting_analyze)
    selector._prepare_candidates([first])

    restored = replace(
        first,
        metrics=None,
        content_fingerprint=None,
        content_fingerprints=[],
    )
    second_selector = ImageSelector(settings, state)
    monkeypatch.setattr(
        second_selector,
        "_analyze_image",
        lambda media: (_ for _ in ()).throw(
            AssertionError("cached image must not be analysed again")
        ),
    )
    second_selector._prepare_candidates([restored])

    assert analyze_calls == 1
    assert restored.metrics == first.metrics
    assert restored.content_fingerprints == first.content_fingerprints


def test_image_analysis_cache_is_invalidated_when_caption_changes(
    temp_workspace,
    monkeypatch,
):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "analysis_caption_cache"
    account_dir.mkdir()
    first = _make_candidate(
        account_dir,
        username="analysis_caption_cache",
        idx=1,
        caption="portrait indoors",
    )
    ImageSelector(settings, state)._prepare_candidates([first])
    changed = replace(
        first,
        caption="outdoor mountain landscape",
        metrics=None,
        content_fingerprint=None,
        content_fingerprints=[],
    )
    selector = ImageSelector(settings, state)
    original_analyze = selector._analyze_image
    analyze_calls = 0

    def counting_analyze(media):
        nonlocal analyze_calls
        analyze_calls += 1
        return original_analyze(media)

    monkeypatch.setattr(selector, "_analyze_image", counting_analyze)
    selector._prepare_candidates([changed])

    assert analyze_calls == 1
    assert changed.metrics is not None


def test_used_media_snapshot_avoids_repeated_state_reads(temp_workspace, monkeypatch):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "used_snapshot"
    account_dir.mkdir()
    candidate = _make_candidate(account_dir, username="used_snapshot", idx=1)
    state.mark_media_used([candidate.source_id], "old-job")
    selector = ImageSelector(settings, state)
    selector._used_media_snapshot = state.read_used_media()
    monkeypatch.setattr(
        state,
        "any_media_used",
        lambda keys: (_ for _ in ()).throw(
            AssertionError("snapshot should avoid per-candidate JSON reads")
        ),
    )

    assert selector._is_candidate_used(candidate) is True


def test_type_3_background_rotation_is_global_across_languages(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "type3_rotation"
    account_dir.mkdir()

    candidates = [
        _make_candidate(
            account_dir,
            username="type3_rotation",
            idx=i,
            caption="old money laptop",
        )
        for i in range(2)
    ]
    for index, candidate in enumerate(candidates):
        candidate.metrics = _metrics_stub(
            quality=0.84,
            daylight=0.76,
            faces=1 if index == 0 else 0,
            is_landscape=False,
            casual=0.05,
            luxury=0.72,
            portrait_focus=0.68 if index == 0 else 0.12,
            affluent=0.82,
            laptop=1.0 if index == 0 else 0.2,
            hands=0.4,
        )

    selector = ImageSelector(settings, state)

    first_plan = selector.create_plan(
        {"type3_rotation": candidates},
        VideoType.TYPE_3,
        Language.EN,
    )
    state.remember_type_3_background_choice(
        first_plan.type_3_background_id or "",
        first_plan.type_3_background_candidates,
    )

    second_plan = selector.create_plan(
        {"type3_rotation": candidates},
        VideoType.TYPE_3,
        Language.ES,
    )

    assert first_plan.type_3_background_id is not None
    assert second_plan.type_3_background_id is not None
    assert second_plan.type_3_background_id != first_plan.type_3_background_id


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


def test_perceptual_fingerprint_blocks_resized_same_image(temp_workspace):
    settings, state = temp_workspace
    account_dir = settings.downloads_dir / "near_fingerprint"
    account_dir.mkdir()

    first = _make_candidate(account_dir, username="near_fingerprint", idx=1)
    second = _make_candidate(account_dir, username="near_fingerprint", idx=2)
    with Image.open(first.local_path) as image:
        changed = image.convert("RGB").resize((image.width - 8, image.height - 8))
        changed.save(second.local_path)
    second.source_id = "near_fingerprint:other_post:0"
    second.permalink = "https://instagram.com/near_fingerprint/p/other_post"
    for candidate in (first, second):
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
    selector._prepare_candidates([first])
    state.reserve_media(selector.reservation_keys_for([first]), job_id="previous")

    with pytest.raises(ValueError):
        selector.create_plan({"near_fingerprint": [second]}, VideoType.TYPE_3, Language.ES)


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
    sky: float | None = None,
    body_area: float = 0.0,
    body_focus: float = 0.0,
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
        sky_ratio=(0.25 if is_landscape else 0.05) if sky is None else sky,
        face_area_ratio=face_area if faces else 0.0,
        face_center_score=face_center if faces else 0.0,
        portrait_focus_score=portrait_focus,
        affluent_lifestyle_score=luxury if affluent is None else affluent,
        laptop_score=laptop,
        hands_score=hands,
        body_area_ratio=body_area,
        body_focus_score=body_focus,
    )
