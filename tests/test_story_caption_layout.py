from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoType
from app.render import (
    TEXT_AVOID_CLEARANCE_MARGIN,
    TEXT_BODY_AVOID_WEIGHT,
    TEXT_CARD_BODY_FONT_SIZE,
    TEXT_EYE_AVOID_WEIGHT,
    TEXT_FACE_AVOID_WEIGHT,
    TEXT_HEAD_AVOID_WEIGHT,
    TYPE_4_STORY_CAPTION_ROLES,
    VideoRenderer,
)
from app.texts import ScriptGenerator
from app.story_layout import write_story_subject_box


@pytest.fixture(params=(Language.ES, Language.EN), ids=("es", "en"))
def story_texts(request, monkeypatch):
    # Use the published story copy without touching any rotation or calling AI.
    generator = ScriptGenerator.__new__(ScriptGenerator)
    monkeypatch.setattr(generator, "_compose_type_4", lambda language, texts: texts)
    builder = generator._build_type_4_es if request.param == Language.ES else generator._build_type_4_en
    return builder()


@pytest.fixture(params=((1080, 1920), (360, 640)), ids=("1080px", "360px"))
def renderer(request):
    width, height = request.param
    return VideoRenderer(replace(get_settings(), width=width, height=height))


def _slide(role, text):
    return SlidePlan(
        index=1,
        role=role,
        text=text,
        media=MediaCandidate(
            source_account="ai_story",
            source_id="caption-layout",
            local_path=Path("unused-story-caption.png"),
            permalink="",
            caption="",
            width=1080,
            height=1920,
            created_at="",
        ),
    )


def _render_caption(renderer, role, text, monkeypatch, *, regions=None, legacy_center=False):
    size = (renderer.settings.width, renderer.settings.height)
    source = Image.new("RGB", size, (205, 215, 225))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    blocks = []
    original = renderer._draw_connected_pill_lines

    def record(draw, lines, font, **kwargs):
        blocks.append({"lines": list(lines), "font": font, **kwargs})
        return original(draw, lines, font, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(renderer, "_draw_connected_pill_lines", record)
        if legacy_center:
            patch.setattr(renderer, "_caption_preferred_centers", lambda slide: (0.30, 0.32, 0.28))
        renderer._draw_caption_card_text(
            overlay,
            text,
            slide=_slide(role, text),
            layout_image=source,
            avoid_regions=regions,
        )
    return overlay, blocks


@pytest.mark.parametrize(
    ("role", "detection"),
    [
        *((role, "detected") for role in sorted(TYPE_4_STORY_CAPTION_ROLES, key=lambda role: role.value)),
        (SlideRole.STORY_DEEP_FAILURE, "missing"),
        (SlideRole.STORY_DEEP_FAILURE, "portrait-fallback"),
    ],
)
def test_real_story_copy_is_larger_lower_and_clear_of_the_protagonist(
    renderer, story_texts, role, detection, monkeypatch,
):
    width, height = renderer.settings.width, renderer.settings.height
    text = story_texts[role]
    subject_top = round(height * 0.54) if detection == "detected" else int(height * 0.39)
    regions = [((round(width * 0.18), subject_top, round(width * 0.82), round(height * 0.90)), TEXT_HEAD_AVOID_WEIGHT)]
    if detection == "missing":
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        actual_regions = None
    elif detection == "portrait-fallback":
        monkeypatch.setattr(
            renderer, "_text_avoid_regions",
            lambda image: renderer._fallback_portrait_avoid_regions(width, height),
        )
        actual_regions = None
    else:
        actual_regions = regions

    # Model the previous typography and top-area preference. When faces are
    # missed, its former conservative head estimate began at 34% of the frame.
    baseline_top = subject_top if detection == "detected" else int(height * 0.34)
    baseline_regions = [((round(width * 0.10), baseline_top, round(width * 0.90), height), TEXT_HEAD_AVOID_WEIGHT)]
    before, normal_blocks = _render_caption(
        renderer, SlideRole.OCTOBER, text, monkeypatch,
        regions=baseline_regions, legacy_center=True,
    )
    after, story_blocks = _render_caption(
        renderer, role, text, monkeypatch, regions=actual_regions,
    )

    assert len(story_blocks) == len(normal_blocks) == 1
    assert story_blocks[0]["font"].size > normal_blocks[0]["font"].size
    assert " ".join(story_blocks[0]["lines"]).split() == text.split()
    old_box, box = before.getbbox(), after.getbbox()
    assert old_box is not None and box is not None
    assert box[1] + box[3] > old_box[1] + old_box[3]
    assert 0 <= box[0] < box[2] <= width
    assert 0 <= box[1] < box[3] < height
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * height / 1920))
    # Pillow includes the final boundary pixel in its rounded rectangles.
    assert box[3] == subject_top - clearance + 1
    assert story_blocks[0]["start_y"] < subject_top


@pytest.mark.parametrize("subject_kind", ("head", "eyes", "raised-arm-body"))
def test_story_card_leaves_margin_from_the_highest_detected_subject_part(renderer, subject_kind, monkeypatch):
    width, height = renderer.settings.width, renderer.settings.height
    subject_top = round(height * 0.42)
    weight = {"head": TEXT_HEAD_AVOID_WEIGHT, "eyes": TEXT_EYE_AVOID_WEIGHT, "raised-arm-body": TEXT_BODY_AVOID_WEIGHT}[subject_kind]
    regions = [
        ((round(width * 0.24), round(height * 0.52), round(width * 0.76), round(height * 0.82)), TEXT_HEAD_AVOID_WEIGHT),
        ((round(width * 0.14), subject_top, round(width * 0.86), round(height * 0.95)), weight),
    ]
    overlay, _blocks = _render_caption(
        renderer, SlideRole.STORY_DEEP_FAILURE,
        "Los primeros meses fueron difíciles, pero seguí aprendiendo.",
        monkeypatch, regions=regions,
    )
    box = overlay.getbbox()
    assert box is not None
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * height / 1920))
    assert box[3] == subject_top - clearance + 1


def test_long_story_copy_stays_above_a_high_protagonist(renderer, monkeypatch):
    width, height = renderer.settings.width, renderer.settings.height
    subject_top = round(height * 0.20)
    regions = [((round(width * 0.15), subject_top, round(width * 0.85), height), TEXT_HEAD_AVOID_WEIGHT)]
    text = (
        "Los meses siguientes fueron peores: probé 3 productos, no vendí "
        "ninguno y estuve a punto de dejarlo para siempre."
    )

    overlay, blocks = _render_caption(
        renderer, SlideRole.STORY_DEEP_FAILURE, text, monkeypatch, regions=regions,
    )

    assert " ".join(blocks[0]["lines"]).split() == text.split()
    box = overlay.getbbox()
    assert box is not None
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * height / 1920))
    assert box[3] == subject_top - clearance + 1


@pytest.mark.parametrize("subject_top_ratio", (0.28, 0.43, 0.63))
@pytest.mark.parametrize("text", (
    "Después de un año y medio...",
    "Los meses siguientes fueron peores: probé 3 productos, no vendí ninguno "
    "y estuve a punto de dejarlo para siempre.",
), ids=("short", "long"))
def test_story_clearance_follows_subject_height_instead_of_fixed_text_center(
    renderer, subject_top_ratio, text, monkeypatch,
):
    width, height = renderer.settings.width, renderer.settings.height
    subject_top = round(height * subject_top_ratio)
    regions = [((round(width * 0.25), subject_top, round(width * 0.86), height), TEXT_HEAD_AVOID_WEIGHT)]

    overlay, blocks = _render_caption(
        renderer, SlideRole.STORY_DEEP_FAILURE, text, monkeypatch, regions=regions,
    )

    box = overlay.getbbox()
    assert box is not None
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * height / 1920))
    assert box[3] == subject_top - clearance + 1
    assert " ".join(blocks[0]["lines"]).split() == text.split()


def test_segmented_geometry_keeps_independent_faces_and_ignores_body_false_positives(renderer, monkeypatch):
    source = Image.new("RGB", (864, 1536), (205, 215, 225))
    source.info["story_subject_box"] = "[0.25, 0.4375, 0.875, 0.9375]"
    source.info["story_subject_source"] = "segmentation"
    slide = _slide(SlideRole.STORY_MCDONALD, "Mi primera historia.")

    face = ((250, 600, 740, 980), TEXT_FACE_AVOID_WEIGHT)
    false_body = ((30, 200, 180, 1400), TEXT_BODY_AVOID_WEIGHT)
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [face, false_body])

    regions = renderer._slide_text_avoid_regions(slide, source)

    assert len(regions) == 2
    box, weight = regions[0]
    assert box == (216, 672, 756, 1440)
    assert weight >= TEXT_HEAD_AVOID_WEIGHT
    assert face in regions
    assert false_body not in regions


@pytest.mark.parametrize("source_tag", (None, "review"))
def test_unverified_geometry_keeps_the_reserved_top_area(renderer, monkeypatch, source_tag):
    width, height = renderer.settings.width, renderer.settings.height
    source = Image.new("RGB", (width, height), (205, 215, 225))
    source.info["story_subject_box"] = "[0.25, 0.58, 0.875, 0.9375]"
    if source_tag is not None:
        source.info["story_subject_source"] = source_tag
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])

    regions = renderer._slide_text_avoid_regions(
        _slide(SlideRole.STORY_DROPRADAR, "Entonces encontré Dropradar."), source,
    )

    assert regions[0][0][1] == int(height * 0.39)


def test_missing_reviewed_geometry_keeps_detection_for_story_and_other_formats(renderer, monkeypatch):
    source = Image.new("RGB", (864, 1536), (205, 215, 225))
    detected = [((40, 600, 750, 1500), TEXT_HEAD_AVOID_WEIGHT)]
    calls = []

    def photo_detection(image):
        calls.append(image)
        return detected

    monkeypatch.setattr(renderer, "_text_avoid_regions", photo_detection)
    story = _slide(SlideRole.STORY_MCDONALD, "Una historia.")
    assert renderer._slide_text_avoid_regions(story, source) == detected
    source.info["story_subject_box"] = "[0.25, 0.4375, 0.875, 0.9375]"
    ordinary = _slide(SlideRole.TIP1, "Otro formato.")
    assert renderer._slide_text_avoid_regions(ordinary, source) == detected
    assert len(calls) == 2


def test_still_and_video_keep_caption_clear_during_the_complete_camera_move(renderer, tmp_path, monkeypatch):
    source = Image.new("RGB", (864, 1536), (205, 215, 225))
    path = tmp_path / "reviewed-scene.png"
    source.save(path)
    write_story_subject_box(path, (0.25, 0.4375, 0.875, 0.9375), source="segmentation")
    slide = _slide(SlideRole.STORY_SUCCESS_COMIC, "Después de un año y medio...")
    slide.media.local_path = path

    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    still = renderer.render_slide_still(slide, VideoType.TYPE_4)
    loaded = renderer._load_source_image(path)
    cache_key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, still.size)
    overlay = renderer._text_overlay_cache[cache_key]
    box = overlay.getbbox()
    assert box is not None
    width, height = still.size
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * height / 1920))
    swept_tops = []
    for progress in (0.0, 0.5, 1.0):
        scale = max(width / 864, height / 1536) * (1.0 + 0.06 * progress)
        offset_y = int(max(0, int(1536 * scale) - height) * 0.5)
        subject_top = int(672 * scale) - offset_y
        swept_tops.append(subject_top)
        assert box[3] <= subject_top - clearance + 1
        frame = renderer._render_slide_frame(slide, loaded, progress, VideoType.TYPE_4)
        assert renderer._text_overlay_cache[cache_key].getbbox() == box
        if progress == 1.0:
            assert still.tobytes() == Image.fromarray(frame).tobytes()
    assert box[3] == min(swept_tops) - clearance + 1


@pytest.mark.parametrize("role", (SlideRole.STORY_DROPRADAR, SlideRole.STORY_SUCCESS_COMIC))
@pytest.mark.parametrize("weight", (TEXT_FACE_AVOID_WEIGHT, TEXT_EYE_AVOID_WEIGHT), ids=("face", "eyes"))
def test_independent_face_guard_wins_over_incorrect_lower_subject_metadata(
    renderer, tmp_path, monkeypatch, role, weight,
):
    source = Image.new("RGB", (864, 1536), (225, 201, 161))
    path = tmp_path / "incorrect-lower-subject.png"
    source.save(path)
    # This models the reported failure: a lower shirt/sideburn estimate must
    # never erase a separate face detection higher in the same image.
    write_story_subject_box(path, (0.35, 0.58, 0.95, 0.99), source="segmentation")
    face = (400, 630, 800, 1040)
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [(face, weight)])
    text = (
        "Entonces encontré Dropradar, validé un producto con datos "
        "y ese mes conseguí mi primera venta."
        if role == SlideRole.STORY_DROPRADAR else "Después de un año y medio..."
    )
    slide = _slide(role, text)
    slide.media.local_path = path
    renderer.render_slide_still(slide, VideoType.TYPE_4)
    size = (renderer.settings.width, renderer.settings.height)
    overlay = renderer._text_overlay_cache[renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, size)]
    card = overlay.getbbox()
    assert card is not None
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * size[1] / 1920))

    for progress in (0.0, 0.5, 1.0):
        scale = max(size[0] / 864, size[1] / 1536) * (1 + 0.06 * progress)
        offset_y = int(max(0, int(1536 * scale) - size[1]) * 0.5)
        face_top = int(face[1] * scale) - offset_y
        assert card[3] - 1 <= face_top - clearance


@pytest.mark.parametrize("role", (SlideRole.OCTOBER, SlideRole.TIP1, SlideRole.PARKEZ_PROMO, SlideRole.STORY_ORIGINAL_REFERENCE))
def test_other_caption_formats_keep_their_original_font_size(renderer, role, monkeypatch):
    _overlay, blocks = _render_caption(
        renderer, role, "Un consejo breve.", monkeypatch, regions=[],
    )
    assert len(blocks) == 1
    assert blocks[0]["font"].size == max(17, round(TEXT_CARD_BODY_FONT_SIZE * renderer.settings.width / 1080))


def test_story_original_reference_is_delivered_without_a_caption(renderer, story_texts, tmp_path):
    size = (renderer.settings.width, renderer.settings.height)
    source = Image.new("RGB", size, (37, 73, 109))
    ImageDraw.Draw(source).rectangle((20, 30, 80, 90), fill=(180, 70, 30))
    path = tmp_path / "reference.png"
    source.save(path)
    slide = _slide(SlideRole.STORY_ORIGINAL_REFERENCE, story_texts[SlideRole.STORY_ORIGINAL_REFERENCE])
    slide.media.local_path = path
    slide.fixed_asset = True

    result = renderer.render_slide_still(slide, VideoType.TYPE_4)

    assert slide.text == ""
    assert result.size == source.size
    assert result.tobytes() == source.tobytes()
