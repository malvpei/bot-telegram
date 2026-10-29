from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoType
from app.render import (
    TEXT_AVOID_CLEARANCE_MARGIN,
    TEXT_BODY_AVOID_WEIGHT,
    TEXT_CARD_BODY_FONT_SIZE,
    TEXT_CARD_BODY_MIN_FONT_SIZE,
    TEXT_EYE_AVOID_WEIGHT,
    TEXT_FACE_AVOID_WEIGHT,
    TEXT_HEAD_AVOID_WEIGHT,
    TEXT_OVERLAY_CACHE_MAX_ITEMS,
    TYPE_4_STORY_CAPTION_FONT_SCALE,
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


def test_long_story_copy_stays_above_a_high_protagonist(renderer, tmp_path, monkeypatch):
    path, subject_color, _subject_box = _high_subject_scene(tmp_path, 0.20)
    text = (
        "Los meses siguientes fueron peores: probé 3 productos, no vendí "
        "ninguno y estuve a punto de dejarlo para siempre."
    )
    slide = _slide(SlideRole.STORY_DEEP_FAILURE, text)
    slide.media.local_path = path
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    still = renderer.render_slide_still(slide, VideoType.TYPE_4)
    key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, still.size)
    box = renderer._text_overlay_cache[key].getbbox()
    assert box is not None
    subject_top = _painted_subject_top(still, subject_color)
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * still.height / 1920))
    assert subject_top - box[3] + 1 >= clearance


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


def _high_subject_scene(
    tmp_path, top_ratio, *, metadata_top_ratio=None,
    size=(864, 1536), subject_color=(40, 83, 129),
):
    """Paint a visible subject so tests can inspect the final composed pixels."""
    source = Image.new("RGB", size, (225, 201, 161))
    subject_box = (round(size[0] * 0.25), round(size[1] * top_ratio), round(size[0] * 0.875), round(size[1] * 0.9375))
    ImageDraw.Draw(source).rectangle(
        (subject_box[0], subject_box[1], subject_box[2] - 1, subject_box[3] - 1),
        fill=subject_color,
    )
    path = tmp_path / "high-subject-scene.png"
    source.save(path)
    write_story_subject_box(
        path,
        (0.25, top_ratio if metadata_top_ratio is None else metadata_top_ratio, 0.875, 0.9375),
        source="segmentation",
    )
    return path, subject_color, subject_box


def _painted_subject_top(image, color):
    pixels = np.asarray(image.convert("RGB"))
    rows = np.flatnonzero(np.any(np.all(pixels == color, axis=2), axis=1))
    assert len(rows), "The scene must preserve the visible protagonist."
    return int(rows[0])


def _record_story_headroom(renderer, monkeypatch):
    composed_regions = []
    original = renderer._compose_story_with_headroom

    def record(*args, **kwargs):
        scene, regions = original(*args, **kwargs)
        composed_regions.extend(regions)
        return scene, regions

    monkeypatch.setattr(renderer, "_compose_story_with_headroom", record)
    return composed_regions


@pytest.mark.parametrize("subject_top_ratio", (0.0, 0.02, 0.10), ids=("at-top", "2-percent", "10-percent"))
def test_story_adds_headroom_instead_of_failing_or_using_tiny_text(
    renderer, story_texts, tmp_path, monkeypatch, subject_top_ratio,
):
    path, subject_color, _subject_box = _high_subject_scene(tmp_path, subject_top_ratio)
    text = story_texts[SlideRole.STORY_DEEP_FAILURE]
    slide = _slide(SlideRole.STORY_DEEP_FAILURE, text)
    slide.media.local_path = path
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    composed_regions = _record_story_headroom(renderer, monkeypatch)
    blocks = []
    original = renderer._draw_connected_pill_lines

    def record(draw, lines, font, **kwargs):
        blocks.append((list(lines), font.size))
        return original(draw, lines, font, **kwargs)

    monkeypatch.setattr(renderer, "_draw_connected_pill_lines", record)
    still = renderer.render_slide_still(slide, VideoType.TYPE_4)
    key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, still.size)
    scene = renderer._story_scene_cache[key]
    card = renderer._text_overlay_cache[key].getbbox()
    assert card is not None
    assert blocks
    assert " ".join(blocks[-1][0]).split() == text.split()
    minimum_font = round(
        max(14, round(TEXT_CARD_BODY_MIN_FONT_SIZE * still.width / 1080))
        * TYPE_4_STORY_CAPTION_FONT_SCALE
    )
    assert blocks[-1][1] >= minimum_font
    assert 0 <= card[0] < card[2] <= still.width
    assert 0 <= card[1] < card[3] < still.height
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * still.height / 1920))
    subject_top = _painted_subject_top(scene, subject_color)
    projected_top = min(box[1] for box, _weight in composed_regions)
    assert card[3] == projected_top - clearance + 1
    # Lanczos blends the first subject rows; the first fully coloured pixel
    # may be a few pixels below the conservative projected boundary.
    assert 0 <= subject_top - projected_top <= 5
    assert subject_top - card[3] + 1 >= clearance
    top_row = np.asarray(scene.convert("RGB"))[0]
    assert np.all(top_row == top_row[0])

    loaded = renderer._load_source_image(path)
    for progress in (0.0, 0.25, 0.5, 0.75, 1.0):
        frame = Image.fromarray(renderer._render_slide_frame(slide, loaded, progress, VideoType.TYPE_4))
        assert frame.tobytes() == still.tobytes()
        assert _painted_subject_top(frame, subject_color) == subject_top


def test_story_headroom_also_respects_faces_above_incorrect_subject_metadata(
    renderer, tmp_path, monkeypatch,
):
    path, subject_color, face = _high_subject_scene(tmp_path, 0.02, metadata_top_ratio=0.58)
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [(face, TEXT_FACE_AVOID_WEIGHT)])
    composed_regions = _record_story_headroom(renderer, monkeypatch)
    slide = _slide(SlideRole.STORY_SUCCESS_COMIC, "Después de un año y medio...")
    slide.media.local_path = path

    still = renderer.render_slide_still(slide, VideoType.TYPE_4)

    key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, still.size)
    card = renderer._text_overlay_cache[key].getbbox()
    assert card is not None
    subject_top = _painted_subject_top(renderer._story_scene_cache[key], subject_color)
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * still.height / 1920))
    projected_top = min(box[1] for box, _weight in composed_regions)
    assert card[3] == projected_top - clearance + 1
    assert 0 <= subject_top - projected_top <= 5
    assert subject_top - card[3] + 1 >= clearance


def test_direct_story_frames_rebuild_the_matching_scene_after_overlay_eviction(
    renderer, tmp_path, monkeypatch,
):
    path, _subject_color, _subject_box = _high_subject_scene(tmp_path, 0.0)
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    slide = _slide(SlideRole.STORY_DEEP_FAILURE, "Probé tres productos y seguí aprendiendo de mis errores.")
    slide.media.local_path = path
    loaded = renderer._load_source_image(path)
    # Exercise the frame entry point with no still or explicit preparation first.
    first = renderer._render_slide_frame(slide, loaded, 0.0, VideoType.TYPE_4)
    size = (renderer.settings.width, renderer.settings.height)
    key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, size)
    assert key in renderer._story_scene_cache
    assert key in renderer._text_overlay_cache

    for index in range(TEXT_OVERLAY_CACHE_MAX_ITEMS):
        renderer._remember_text_overlay(("another-slide", index), Image.new("RGBA", size))

    assert key not in renderer._text_overlay_cache
    assert key not in renderer._story_scene_cache
    rebuilt = renderer._render_slide_frame(slide, loaded, 1.0, VideoType.TYPE_4)
    assert np.array_equal(first, rebuilt)
    assert key in renderer._story_scene_cache
    assert key in renderer._text_overlay_cache


@pytest.mark.parametrize("source_size", ((1920, 1080), (540, 2400)), ids=("landscape", "very-tall"))
def test_story_headroom_preserves_the_whole_scene_with_unusual_dimensions(
    renderer, tmp_path, monkeypatch, source_size,
):
    path, subject_color, _subject_box = _high_subject_scene(tmp_path, 0.0, size=source_size)
    with Image.open(path) as image:
        source = image.copy()
    marker_width, marker_height = round(source.width * 0.08), round(source.height * 0.05)
    markers = (
        ((0, 0), (190, 10, 30)),
        ((source.width - marker_width, 0), (10, 170, 40)),
        ((0, source.height - marker_height), (10, 40, 220)),
        ((source.width - marker_width, source.height - marker_height), (180, 20, 200)),
    )
    for (x, y), color in markers:
        ImageDraw.Draw(source).rectangle((x, y, x + marker_width - 1, y + marker_height - 1), fill=color)
    source.save(path)
    write_story_subject_box(path, (0.25, 0.0, 0.875, 0.9375), source="segmentation")
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    slide = _slide(SlideRole.STORY_DEEP_FAILURE, "Los primeros meses fueron difíciles, pero seguí aprendiendo.")
    slide.media.local_path = path

    still = renderer.render_slide_still(slide, VideoType.TYPE_4)

    key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, still.size)
    scene = renderer._story_scene_cache[key]
    scene_pixels = np.asarray(scene.convert("RGB"))
    for _corner, color in markers:
        assert np.any(np.all(scene_pixels == color, axis=2)), "All four image corners must remain visible."
    card = renderer._text_overlay_cache[key].getbbox()
    assert card is not None
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * still.height / 1920))
    assert _painted_subject_top(scene, subject_color) - card[3] + 1 >= clearance


def test_replacing_a_story_source_rebuilds_its_scene_and_caption(renderer, tmp_path, monkeypatch):
    path, old_subject_color, _subject_box = _high_subject_scene(tmp_path, 0.0)
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    slide = _slide(SlideRole.STORY_DEEP_FAILURE, "Probé tres productos y seguí aprendiendo de mis errores.")
    slide.media.local_path = path
    first = renderer.render_slide_still(slide, VideoType.TYPE_4)
    old_key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, first.size)

    path, new_subject_color, _subject_box = _high_subject_scene(tmp_path, 0.02, subject_color=(140, 44, 90))
    loaded = renderer._load_source_image(path)
    second = renderer._render_slide_frame(slide, loaded, 0.5, VideoType.TYPE_4)
    new_key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, first.size)

    assert new_key != old_key
    assert new_key in renderer._story_scene_cache
    assert new_key in renderer._text_overlay_cache
    scene = renderer._story_scene_cache[new_key]
    assert _painted_subject_top(scene, new_subject_color) > 0
    assert not np.any(np.all(np.asarray(scene.convert("RGB")) == old_subject_color, axis=2))
    assert not np.array_equal(np.asarray(first), second)


def test_story_headroom_never_changes_the_following_original_reference(
    renderer, story_texts, tmp_path, monkeypatch,
):
    path, _subject_color, _subject_box = _high_subject_scene(tmp_path, 0.0)
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
    story = _slide(SlideRole.STORY_DEEP_FAILURE, story_texts[SlideRole.STORY_DEEP_FAILURE])
    story.media.local_path = path
    renderer.render_slide_still(story, VideoType.TYPE_4)
    assert renderer._story_scene_cache

    size = (renderer.settings.width, renderer.settings.height)
    original = Image.new("RGB", size, (37, 73, 109))
    ImageDraw.Draw(original).rectangle((20, 30, 80, 90), fill=(180, 70, 30))
    reference_path = tmp_path / "original-after-fallback.png"
    original.save(reference_path)
    reference = _slide(SlideRole.STORY_ORIGINAL_REFERENCE, story_texts[SlideRole.STORY_ORIGINAL_REFERENCE])
    reference.media.local_path = reference_path
    reference.fixed_asset = True

    result = renderer.render_slide_still(reference, VideoType.TYPE_4)

    assert reference.text == ""
    assert result.tobytes() == original.tobytes()
    key = renderer._slide_overlay_cache_key(reference, VideoType.TYPE_4, size)
    assert key not in renderer._story_scene_cache


def _wall_story(source_tag, *, subtle_noise=False):
    """Reproduce a high false face on a plain illustrated wall, without fixtures."""
    width, height = 864, 1536
    pixels = np.full((height, width, 3), (225, 201, 161), dtype=np.int16)
    if subtle_noise:
        noise = (np.arange(height)[:, None] // 5 + np.arange(width)[None, :] // 7) % 3 - 1
        pixels += noise[:, :, None]
    image = Image.fromarray(pixels.astype(np.uint8))
    ImageDraw.Draw(image).rectangle((240, 765, 790, 1535), fill=(40, 83, 129))
    if source_tag is not None:
        image.info["story_subject_source"] = source_tag
        image.info["story_subject_box"] = f"[{240 / width}, {765 / height}, {791 / width}, 1.0]"
    return image


def _stub_story_detectors(
    renderer, monkeypatch, source_size, *, frontal=(), profile=(), eyes=(), neural=(),
):
    """Mock every detector, returning its real resized-image coordinate format."""
    def at_detection_size(image, boxes):
        if not boxes:
            return np.empty((0, 4), dtype=np.int32)
        scale = image.shape[0] / source_size[1]
        return np.rint(np.asarray(boxes, dtype=np.float64) * scale).astype(np.int32)

    monkeypatch.setattr(renderer, "_detect_render_faces", lambda gray: at_detection_size(gray, frontal))
    monkeypatch.setattr(renderer, "_detect_render_profile_faces", lambda gray: at_detection_size(gray, profile))
    monkeypatch.setattr(renderer, "_detect_render_eyes", lambda gray: at_detection_size(gray, eyes))
    monkeypatch.setattr(renderer, "_detect_render_people", lambda rgb: np.empty((0, 4), dtype=np.int32))
    monkeypatch.setattr(renderer._neural_face_detector, "detect_faces", lambda rgb: at_detection_size(rgb, neural))
    monkeypatch.setattr(renderer, "_face_avoid_detectors_unavailable", lambda: False)


@pytest.mark.parametrize("subtle_noise", (False, True), ids=("flat-wall", "soft-texture"))
@pytest.mark.parametrize("detector", ("frontal", "profile", "eyes"))
def test_segmented_story_ignores_false_cascades_on_flat_wall(
    renderer, monkeypatch, subtle_noise, detector,
):
    source = _wall_story("segmentation", subtle_noise=subtle_noise)
    # This models the reported wall false positive, well above the SAM body.
    false_detection = ((391, 152, 206, 151),)
    _stub_story_detectors(renderer, monkeypatch, source.size, **{detector: false_detection})

    assert renderer._text_avoid_regions(source) == []
    regions = renderer._slide_text_avoid_regions(
        _slide(SlideRole.STORY_DEEP_FAILURE, "Seguí aprendiendo."), source,
    )
    assert len(regions) == 1
    assert regions[0][0][1] == 765
    assert regions[0][1] == TEXT_HEAD_AVOID_WEIGHT


@pytest.mark.parametrize("source_tag", (None, "review"), ids=("ordinary-photo", "review-only"))
@pytest.mark.parametrize("detector", ("frontal", "profile", "eyes"))
def test_non_segmented_images_keep_their_existing_cascade_guards(
    renderer, monkeypatch, source_tag, detector,
):
    source = _wall_story(source_tag, subtle_noise=True)
    detection = ((391, 152, 206, 151),)
    _stub_story_detectors(renderer, monkeypatch, source.size, **{detector: detection})

    regions = renderer._text_avoid_regions(source)

    expected_weight = TEXT_EYE_AVOID_WEIGHT if detector == "eyes" else TEXT_FACE_AVOID_WEIGHT
    assert len(regions) == 1
    assert regions[0][1] == expected_weight
    assert regions[0][0][1] < 152


@pytest.mark.parametrize("detector", ("frontal", "profile", "eyes"))
def test_segmented_story_keeps_detailed_faces_above_the_sam_body(
    renderer, monkeypatch, detector,
):
    source = _wall_story("segmentation")
    # Two small dark eyes are enough evidence even if most of the crop is skin.
    draw = ImageDraw.Draw(source)
    draw.ellipse((440, 480, 454, 496), fill=(0, 0, 0))
    draw.ellipse((529, 480, 543, 496), fill=(0, 0, 0))
    real_detection = ((391, 450, 206, 151),)
    _stub_story_detectors(renderer, monkeypatch, source.size, **{detector: real_detection})

    regions = renderer._text_avoid_regions(source)
    protected = renderer._slide_text_avoid_regions(
        _slide(SlideRole.STORY_DEEP_FAILURE, "Seguí aprendiendo."), source,
    )

    expected_weight = TEXT_EYE_AVOID_WEIGHT if detector == "eyes" else TEXT_FACE_AVOID_WEIGHT
    assert len(regions) == 1
    assert regions[0][1] == expected_weight
    assert regions[0][0][1] < 450
    assert regions[0] in protected
    assert any(weight == TEXT_HEAD_AVOID_WEIGHT and box[1] == 765 for box, weight in protected)


def test_segmented_story_preserves_neural_faces_even_in_a_flat_patch(renderer, monkeypatch):
    source = _wall_story("segmentation", subtle_noise=True)
    detection = ((391, 152, 206, 151),)
    # The same flat cascade is discarded before merging; the independent
    # YuNet result must still survive, protecting the higher face.
    _stub_story_detectors(renderer, monkeypatch, source.size, frontal=detection, neural=detection)

    regions = renderer._text_avoid_regions(source)
    protected = renderer._slide_text_avoid_regions(
        _slide(SlideRole.STORY_DEEP_FAILURE, "Seguí aprendiendo."), source,
    )

    assert len(regions) == 1
    assert regions[0][1] == TEXT_FACE_AVOID_WEIGHT
    assert regions[0][0][1] < 152
    assert regions[0] in protected


def test_false_face_on_wall_does_not_force_unnecessary_scene_shrinking(renderer, tmp_path, monkeypatch):
    source = _wall_story("segmentation", subtle_noise=True)
    path = tmp_path / "story-with-false-wall-face.png"
    source.save(path)
    write_story_subject_box(path, (240 / 864, 765 / 1536, 791 / 864, 1.0), source="segmentation")
    _stub_story_detectors(
        renderer, monkeypatch, source.size,
        frontal=((391, 152, 206, 151),),
    )
    slide = _slide(
        SlideRole.STORY_DEEP_FAILURE,
        "Los meses siguientes fueron peores: probé 3 productos, no vendí "
        "ninguno y estuve a punto de dejarlo para siempre.",
    )
    slide.media.local_path = path

    result = renderer.render_slide_still(slide, VideoType.TYPE_4)

    key = renderer._slide_overlay_cache_key(slide, VideoType.TYPE_4, result.size)
    assert key not in renderer._story_scene_cache
    card = renderer._text_overlay_cache[key].getbbox()
    assert card is not None
    clearance = max(1, round(TEXT_AVOID_CLEARANCE_MARGIN * result.height / 1920))
    assert _painted_subject_top(result, (40, 83, 129)) - card[3] + 1 >= clearance
