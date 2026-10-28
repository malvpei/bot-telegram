from __future__ import annotations

import math

import pytest
from PIL import Image, PngImagePlugin

from app.story_layout import (
    parse_story_subject_box,
    story_subject_box,
    write_story_subject_box,
)


@pytest.mark.parametrize("value", (
    [0.2, 0.35, 0.9, 1.0],
    (0.2, 0.35, 0.9, 1.0),
))
def test_subject_box_uses_normalized_bounds(value):
    assert parse_story_subject_box(value) == (0.2, 0.35, 0.9, 1.0)


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
        assert story_subject_box(saved.convert("RGB").copy()) == (0.2, 0.35, 0.9, 1.0)


def test_missing_or_malformed_png_geometry_is_ignored():
    source = Image.new("RGB", (96, 160))
    assert story_subject_box(source) is None
    source.info["story_subject_box"] = "[0.2, 0.35, 0.9, 0.3]"
    assert story_subject_box(source) is None
