"""Protagonist geometry recorded by the existing story image review."""

from __future__ import annotations

import json
import math
import os
from numbers import Real
from pathlib import Path

from PIL import Image, PngImagePlugin


STORY_SUBJECT_BOX_KEY = "story_subject_box"
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


def story_subject_box(image: Image.Image) -> StorySubjectBox | None:
    raw = image.info.get(STORY_SUBJECT_BOX_KEY)
    if not isinstance(raw, str):
        return None
    try:
        return parse_story_subject_box(json.loads(raw))
    except (ValueError, TypeError):
        return None


def write_story_subject_box(path: Path, box: StorySubjectBox | None) -> None:
    """Keep reviewed geometry with its PNG, including selected retry fallbacks."""
    normalized = parse_story_subject_box(box)
    with Image.open(path) as source:
        if normalized is None and STORY_SUBJECT_BOX_KEY not in source.info:
            return
        source.load()
        image = source.copy()
        info = PngImagePlugin.PngInfo()
        for key, value in source.info.items():
            if key != STORY_SUBJECT_BOX_KEY and isinstance(value, str):
                info.add_text(key, value)
        if normalized is not None:
            info.add_text(STORY_SUBJECT_BOX_KEY, json.dumps(normalized))
        save_options = {
            key: source.info[key] for key in ("icc_profile", "exif")
            if key in source.info
        }
    temporary = path.with_name(path.name + ".layout.tmp")
    try:
        image.save(temporary, format="PNG", pnginfo=info, **save_options)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
