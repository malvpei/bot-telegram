"""Protagonist geometry recorded by the existing story image review."""

from __future__ import annotations

import json
import math
import os
from numbers import Real
from pathlib import Path

from PIL import Image, PngImagePlugin


STORY_SUBJECT_BOX_KEY = "story_subject_box"
STORY_SUBJECT_SOURCE_KEY = "story_subject_source"
StorySubjectBox = tuple[float, float, float, float]


def parse_story_subject_box(value: object) -> StorySubjectBox | None:
    """Accept only a finite normalized (left, top, right, bottom) rectangle."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in value):
        return None
    box = tuple(float(item) for item in value)
    if not all(math.isfinite(item) and 0 <= item <= 1 for item in box):
        return None
    left, top, right, bottom = box
    if left >= right or top >= bottom:
        return None
    return left, top, right, bottom


def _native_coordinates(value: object, count: int) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        return None
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in value):
        return None
    values = tuple(float(item) for item in value)
    if not all(math.isfinite(item) and item.is_integer() and 0 <= item <= 1000 for item in values):
        return None
    return tuple(item / 1000 for item in values)


def parse_story_subject_box_2d(value: object) -> StorySubjectBox | None:
    coordinates = _native_coordinates(value, 4)
    if coordinates is None:
        return None
    top, left, bottom, right = coordinates
    return parse_story_subject_box((left, top, right, bottom))


def parse_story_subject_point_2d(value: object) -> tuple[float, float] | None:
    coordinates = _native_coordinates(value, 2)
    if coordinates is None:
        return None
    top, left = coordinates
    return left, top


def story_subject_box(image: Image.Image) -> StorySubjectBox | None:
    raw = image.info.get(STORY_SUBJECT_BOX_KEY)
    if not isinstance(raw, str):
        return None
    try:
        return parse_story_subject_box(json.loads(raw))
    except (ValueError, TypeError):
        return None


def story_subject_source(image: Image.Image) -> str | None:
    value = image.info.get(STORY_SUBJECT_SOURCE_KEY)
    return value if value in {"review", "segmentation"} else None


def write_story_subject_box(
    path: Path,
    box: StorySubjectBox | None,
    *,
    anchor_point: tuple[float, float] | None = None,
    source: str = "review",
) -> None:
    """Keep reviewed geometry with its PNG, including selected retry fallbacks."""
    normalized = parse_story_subject_box(box)
    if source not in {"review", "segmentation"}:
        raise ValueError("Origen de la geometría del protagonista no válido.")
    with Image.open(path) as original:
        if normalized is None and not any(
            key in original.info for key in (STORY_SUBJECT_BOX_KEY, STORY_SUBJECT_SOURCE_KEY)
        ):
            return
        original.load()
        image = original.copy()
        if source != "segmentation" and normalized is not None and anchor_point is not None:
            from app.story_subject_detection import refine_story_subject_box

            normalized = refine_story_subject_box(image, normalized, anchor_point)
        info = PngImagePlugin.PngInfo()
        for key, value in original.info.items():
            if key not in {STORY_SUBJECT_BOX_KEY, STORY_SUBJECT_SOURCE_KEY} and isinstance(value, str):
                info.add_text(key, value)
        if normalized is not None:
            info.add_text(STORY_SUBJECT_BOX_KEY, json.dumps(normalized))
            info.add_text(STORY_SUBJECT_SOURCE_KEY, source)
        save_options = {
            key: original.info[key] for key in ("icc_profile", "exif")
            if key in original.info
        }
    temporary = path.with_name(path.name + ".layout.tmp")
    try:
        image.save(temporary, format="PNG", pnginfo=info, **save_options)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
