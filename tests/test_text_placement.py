from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.config import get_settings
from app.models import MediaCandidate, SlidePlan, SlideRole, VideoType
from app.render import (
    SAFE_TEXT_BOTTOM_MARGIN,
    SAFE_TEXT_TOP_MARGIN,
    TEXT_AVOID_CLEARANCE_MARGIN,
    TEXT_BODY_AVOID_WEIGHT,
    TEXT_EYE_AVOID_WEIGHT,
    TEXT_FACE_AVOID_WEIGHT,
    TEXT_FALLBACK_BODY_AVOID_WEIGHT,
    TEXT_HEAD_AVOID_WEIGHT,
    VideoRenderer,
)


@pytest.fixture
def renderer():
    return VideoRenderer(replace(get_settings(), width=360, height=640))


@pytest.fixture
def portrait():
    return Image.new("RGBA", (360, 640), (80, 80, 80, 255))


def test_text_finds_exact_face_free_gap_even_when_body_covers_it(renderer, portrait):
    # The only possible position is between two faces, off the regular search grid.
    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        avoid_regions=[
            ((50, 0, 310, 261), TEXT_FACE_AVOID_WEIGHT),
            ((50, 341, 310, 640), TEXT_FACE_AVOID_WEIGHT),
            ((0, 200, 360, 640), TEXT_BODY_AVOID_WEIGHT),
        ],
    )

    assert y >= 261
    assert y + 80 <= 341


def test_text_keeps_available_face_clearance_in_narrow_gap_with_body(renderer, portrait):
    clearance = round(TEXT_AVOID_CLEARANCE_MARGIN * portrait.height / 1920)

    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        avoid_regions=[
            ((50, 0, 310, 243), TEXT_FACE_AVOID_WEIGHT),
            ((50, 365, 310, 640), TEXT_FACE_AVOID_WEIGHT),
            ((0, 220, 360, 640), TEXT_BODY_AVOID_WEIGHT),
        ],
    )

    assert y >= 243 + clearance
    assert y + 80 <= 365 - clearance


@pytest.mark.parametrize("face_weight", [TEXT_FACE_AVOID_WEIGHT, TEXT_EYE_AVOID_WEIGHT])
def test_detected_face_takes_priority_over_inferred_head(renderer, portrait, face_weight):
    # A face at the edge occupies few text pixels. A much larger HOG head estimate
    # must not make that real face look cheaper to cover than the estimate.
    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        avoid_regions=[
            ((300, 0, 360, 330), face_weight),
            ((50, 330, 280, 640), TEXT_HEAD_AVOID_WEIGHT),
        ],
    )

    assert y >= 330


@pytest.mark.parametrize("body_weight", [TEXT_BODY_AVOID_WEIGHT, TEXT_FALLBACK_BODY_AVOID_WEIGHT])
def test_body_does_not_push_safe_chest_text_above_face(renderer, portrait, body_weight):
    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        prefer_chest=True,
        avoid_regions=[
            ((80, 170, 280, 260), TEXT_FACE_AVOID_WEIGHT),
            ((40, 260, 320, 640), body_weight),
        ],
    )

    assert 260 <= y <= 350


def test_real_face_is_not_sacrificed_to_an_extrapolated_eye_region(renderer, portrait):
    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        avoid_regions=[
            ((300, 0, 360, 330), TEXT_FACE_AVOID_WEIGHT),
            ((50, 330, 280, 640), TEXT_EYE_AVOID_WEIGHT),
        ],
    )

    assert y >= 330


def test_exact_gap_between_real_faces_survives_broad_eye_estimate(renderer, portrait):
    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        avoid_regions=[
            ((50, 0, 310, 261), TEXT_FACE_AVOID_WEIGHT),
            ((50, 341, 310, 640), TEXT_FACE_AVOID_WEIGHT),
            ((20, 0, 340, 640), TEXT_EYE_AVOID_WEIGHT),
        ],
    )

    assert y == 261


def test_chest_wins_over_equally_open_space_above_face(renderer, portrait):
    clearance = round(TEXT_AVOID_CLEARANCE_MARGIN * portrait.height / 1920)

    y = renderer._safe_text_start_y(
        portrait,
        block_width=260,
        block_height=80,
        preferred_centers=(0.5,),
        prefer_chest=True,
        avoid_regions=[((80, 260, 280, 380), TEXT_FACE_AVOID_WEIGHT)],
    )

    assert y >= 380 + clearance


@pytest.mark.parametrize("size,block_height", [((360, 640), 70), ((720, 1280), 200), ((1080, 1920), 600)])
@pytest.mark.parametrize("preferred_center", [0.01, 0.99])
def test_editing_margins_survive_edge_preferences_and_unavoidable_face(
    size, block_height, preferred_center
):
    width, height = size
    renderer = VideoRenderer(replace(get_settings(), width=width, height=height))
    image = Image.new("RGBA", size, (80, 80, 80, 255))

    y = renderer._safe_text_start_y(
        image,
        block_width=round(width * 0.8),
        block_height=block_height,
        preferred_centers=(preferred_center,),
        prefer_chest=True,
        avoid_regions=[((0, 0, width, height), TEXT_FACE_AVOID_WEIGHT)],
    )

    assert y >= round(SAFE_TEXT_TOP_MARGIN * height / 1920)
    assert y + block_height <= height - round(SAFE_TEXT_BOTTOM_MARGIN * height / 1920)


def test_type_1_hook_pixels_avoid_side_face_and_keep_editing_margins(tmp_path: Path):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    slide = SlidePlan(
        index=1,
        role=SlideRole.HOOK,
        text=(
            "Cuanto facturé haciendo Dropshipping\n"
            "en mis primeros 6 meses y por qué casi lo dejo..."
        ),
        media=MediaCandidate(
            source_account="test",
            source_id="portrait",
            local_path=tmp_path / "portrait.jpg",
            permalink="",
            caption="",
            width=1080,
            height=1920,
            created_at="",
        ),
    )
    side_face = (0, 0, 40, 1250)
    unprotected = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    renderer._draw_text(unprotected, slide, VideoType.TYPE_1, avoid_regions=[])
    # This hook really reaches the lateral strip; the assertion below cannot pass
    # merely because the test text was narrower than the side face.
    assert unprotected.getchannel("A").crop(side_face).getbbox() is not None
    renderer._text_overlay_cache.clear()

    protected = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    renderer._draw_text(
        protected,
        slide,
        VideoType.TYPE_1,
        avoid_regions=[(side_face, TEXT_FACE_AVOID_WEIGHT)],
    )

    alpha = protected.getchannel("A")
    assert alpha.crop(side_face).getbbox() is None
    rows = np.where(np.asarray(alpha).any(axis=1))[0]
    assert len(rows) > 0
    assert rows.min() >= SAFE_TEXT_TOP_MARGIN
    assert rows.max() < protected.height - SAFE_TEXT_BOTTOM_MARGIN


@pytest.mark.parametrize(
    "video_type,role,text",
    [
        (VideoType.TYPE_1, SlideRole.HOOK, "Cuánto facturé en mis primeros seis meses"),
        (VideoType.TYPE_2, SlideRole.HOOK, "Empieza bien en dropshipping"),
        (VideoType.TYPE_1, SlideRole.OCTOBER, "Octubre\nAprende a vender con tu tienda"),
        (VideoType.TYPE_2, SlideRole.TIP1, "1. Aprende a vender con tu tienda."),
        (VideoType.TYPE_2, SlideRole.TIP2, "2. Elige tu producto\nComprueba que tiene demanda"),
    ],
)
def test_photo_text_keeps_every_pixel_when_face_free_gap_is_too_small(
    tmp_path, video_type, role, text
):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    size = (1080, 1920)
    media = MediaCandidate(
        source_account="test",
        source_id="portrait",
        local_path=tmp_path / "portrait.jpg",
        permalink="",
        caption="",
        width=size[0],
        height=size[1],
        created_at="",
    )
    slide = SlidePlan(1, role, text, media)
    original = Image.new("RGBA", size, (0, 0, 0, 0))
    renderer._draw_text(original, slide, video_type, avoid_regions=[])
    original_bbox = original.getchannel("A").getbbox()
    assert original_bbox is not None
    original_content = original.crop(original_bbox)

    # Faces occupy both sides of the sole gap, which is too short for the text.
    # Face avoidance may move the complete block, but must never shrink or crop it.
    gap_height = int(original_content.height * 0.8)
    gap_top = (size[1] - gap_height) // 2
    regions = [
        ((0, 0, size[0], gap_top), TEXT_FACE_AVOID_WEIGHT),
        ((0, gap_top + gap_height, size[0], size[1]), TEXT_FACE_AVOID_WEIGHT),
    ]
    renderer._text_overlay_cache.clear()
    protected = Image.new("RGBA", size, (0, 0, 0, 0))
    renderer._draw_text(protected, slide, video_type, avoid_regions=regions)

    protected_bbox = protected.getchannel("A").getbbox()
    assert protected_bbox is not None
    protected_content = protected.crop(protected_bbox)
    assert protected_content.size == original_content.size
    np.testing.assert_array_equal(np.asarray(protected_content), np.asarray(original_content))
    assert protected_bbox[1] >= SAFE_TEXT_TOP_MARGIN
    assert protected_bbox[3] <= size[1] - SAFE_TEXT_BOTTOM_MARGIN


@pytest.mark.parametrize(
    "video_type,role,text",
    [
        (VideoType.TYPE_2, SlideRole.HOOK, "Empieza bien en dropshipping"),
        (VideoType.TYPE_1, SlideRole.OCTOBER, "Octubre\nAprende a vender"),
        (VideoType.TYPE_2, SlideRole.TIP1, "1. Aprende a vender con tu tienda."),
    ],
)
def test_photo_text_styles_place_ink_on_chest_through_draw_text(
    renderer, portrait, tmp_path, monkeypatch, video_type, role, text
):
    media = MediaCandidate(
        source_account="test",
        source_id="portrait",
        local_path=tmp_path / "portrait.jpg",
        permalink="",
        caption="",
        width=360,
        height=640,
        created_at="",
    )
    monkeypatch.setattr(
        renderer,
        "_text_avoid_regions",
        lambda image: [
            ((80, 260, 280, 380), TEXT_FACE_AVOID_WEIGHT),
            ((40, 380, 320, 640), TEXT_BODY_AVOID_WEIGHT),
        ],
    )
    overlay = Image.new("RGBA", portrait.size, (0, 0, 0, 0))

    renderer._draw_text(overlay, SlidePlan(1, role, text, media), video_type)

    bbox = overlay.getchannel("A").getbbox()
    assert bbox is not None
    assert bbox[1] >= 380
    assert bbox[3] <= portrait.height - round(SAFE_TEXT_BOTTOM_MARGIN * portrait.height / 1920)
