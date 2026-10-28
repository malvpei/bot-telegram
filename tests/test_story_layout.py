from __future__ import annotations

import math

import pytest
from PIL import Image, PngImagePlugin

from app.story_layout import (
    parse_story_subject_box,
    parse_story_subject_box_2d,
    parse_story_subject_point_2d,
    story_subject_box,
    story_subject_source,
    write_story_subject_box,
)


@pytest.mark.parametrize("value", (
    [0.2, 0.35, 0.9, 1.0],
    (0.2, 0.35, 0.9, 1.0),
))
def test_subject_box_uses_normalized_bounds(value):
    assert parse_story_subject_box(value) == (0.2, 0.35, 0.9, 1.0)


def test_native_vision_geometry_converts_yx_to_normalized_xy():
    assert parse_story_subject_box_2d([350, 200, 1000, 900]) == (0.2, 0.35, 0.9, 1.0)
    assert parse_story_subject_point_2d([475, 650]) == (0.65, 0.475)
    # Integer-valued JSON floats are still precise native coordinates.
    assert parse_story_subject_box_2d([350.0, 200.0, 1000.0, 900.0]) == (0.2, 0.35, 0.9, 1.0)
    assert parse_story_subject_point_2d([0, 1000]) == (1.0, 0.0)


@pytest.mark.parametrize("value", (
    None, [], [200, 300, 400], [200, 300, 400, 500, 600],
    [False, 300, 700, 800], ["200", 300, 700, 800],
    [-1, 300, 700, 800], [200, 300, 1001, 800],
    [200.5, 300, 700, 800], [math.nan, 300, 700, 800],
    [200, math.inf, 700, 800], [700, 300, 200, 800],
    [200, 800, 700, 300], [200, 300, 200, 800],
))
def test_invalid_native_box_is_ignored(value):
    assert parse_story_subject_box_2d(value) is None


@pytest.mark.parametrize("value", (
    None, [], [200], [200, 300, 400], [False, 300], ["200", 300],
    [-1, 300], [200, 1001], [200.5, 300], [math.nan, 300], [200, math.inf],
))
def test_invalid_native_anchor_point_is_ignored(value):
    assert parse_story_subject_point_2d(value) is None


@pytest.mark.parametrize("value", (
    None,
    "",
    "not JSON",
    "{}",
    [0.1, 0.2, 0.3],
    [0.1, 0.2, 0.3, 0.4, 0.5],
    [False, 0.2, 0.8, 0.9],
    ["0.1", 0.2, 0.8, 0.9],
    [-0.1, 0.2, 0.8, 0.9],
    [0.1, 0.2, 1.1, 0.9],
    [0.8, 0.2, 0.1, 0.9],
    [0.1, 0.9, 0.8, 0.2],
    [0.1, 0.2, 0.1, 0.9],
    [0.1, 0.2, 0.8, 0.2],
    [math.nan, 0.2, 0.8, 0.9],
    [0.1, math.inf, 0.8, 0.9],
))
def test_invalid_subject_geometry_is_ignored(value):
    assert parse_story_subject_box(value) is None


def test_saved_geometry_survives_loading_without_changing_scene_pixels(tmp_path):
    path = tmp_path / "scene.png"
    source = Image.new("RGB", (96, 160), (182, 141, 95))
    source.putpixel((20, 70), (30, 25, 20))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("existing_note", "Preserve this note")
    source.save(path, pnginfo=metadata)

    write_story_subject_box(path, (0.2, 0.35, 0.9, 1.0))

    with Image.open(path) as saved:
        assert saved.size == source.size
        assert saved.convert("RGB").tobytes() == source.tobytes()
        assert saved.info["existing_note"] == "Preserve this note"
        assert story_subject_box(saved) == (0.2, 0.35, 0.9, 1.0)
        assert story_subject_source(saved) == "review"
        assert story_subject_box(saved.convert("RGB").copy()) == (0.2, 0.35, 0.9, 1.0)


def test_missing_or_malformed_png_geometry_is_ignored():
    source = Image.new("RGB", (96, 160))
    assert story_subject_box(source) is None
    source.info["story_subject_box"] = "[0.2, 0.35, 0.9, 0.3]"
    assert story_subject_box(source) is None


def test_segmented_geometry_bypasses_color_refinement_and_preserves_pixels(tmp_path, monkeypatch):
    path = tmp_path / "segmented.png"
    source = Image.new("RGB", (96, 160), (126, 75, 43))
    source.save(path)

    def unexpected_color_refinement(*args):
        pytest.fail("Pixel segmentation must not be replaced by a hair color estimate")

    monkeypatch.setattr("app.story_subject_detection.refine_story_subject_box", unexpected_color_refinement)
    box = (0.2, 0.35, 0.9, 1.0)
    write_story_subject_box(path, box, anchor_point=(0.6, 0.5), source="segmentation")

    with Image.open(path) as saved:
        assert story_subject_box(saved) == box
        assert story_subject_source(saved) == "segmentation"
        assert saved.convert("RGB").tobytes() == source.tobytes()
        assert story_subject_source(saved.convert("RGB").copy()) == "segmentation"


def test_clearing_geometry_removes_the_previous_source_tag(tmp_path):
    path = tmp_path / "scene.png"
    source = Image.new("RGB", (96, 160), (182, 141, 95))
    source.save(path)
    write_story_subject_box(path, (0.2, 0.35, 0.9, 1.0), source="segmentation")

    write_story_subject_box(path, None)

    with Image.open(path) as saved:
        assert story_subject_box(saved) is None
        assert story_subject_source(saved) is None
        assert saved.convert("RGB").tobytes() == source.tobytes()


def test_unknown_source_tag_is_not_treated_as_segmentation(tmp_path):
    image = Image.new("RGB", (96, 160))
    image.info["story_subject_source"] = "untrusted"
    assert story_subject_source(image) is None
    path = tmp_path / "scene.png"
    image.save(path)

    with pytest.raises(ValueError, match="geometría"):
        write_story_subject_box(path, (0.2, 0.35, 0.9, 1.0), source="untrusted")
