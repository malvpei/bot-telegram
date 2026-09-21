from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.render import (
    TEXT_BODY_AVOID_WEIGHT,
    TEXT_EYE_AVOID_WEIGHT,
    TEXT_FACE_AVOID_WEIGHT,
    TEXT_HEAD_AVOID_WEIGHT,
    VideoRenderer,
)


def _boxes(boxes):
    return np.asarray(boxes, dtype=np.int32).reshape((-1, 4))


def _renderer(monkeypatch, *, neural=(), frontal=(), profile=(), eyes=(), people=()):
    # Keep the integration between detectors, deduplication, and expansion real,
    # without loading networks or depending on cascade accuracy in these tests.
    renderer = VideoRenderer.__new__(VideoRenderer)
    renderer._neural_face_detector = SimpleNamespace(
        detect_faces=lambda _rgb: _boxes(neural)
    )
    for method, boxes in (
        ("_detect_render_faces", frontal),
        ("_detect_render_profile_faces", profile),
        ("_detect_render_eyes", eyes),
        ("_detect_render_people", people),
    ):
        monkeypatch.setattr(renderer, method, lambda _image, boxes=boxes: _boxes(boxes))
    monkeypatch.setattr(renderer, "_face_avoid_detectors_unavailable", lambda: False)
    return renderer


def _covers(box, point):
    x, y = point
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def test_neural_face_keeps_additional_cascade_face_without_visible_eyes(monkeypatch):
    renderer = _renderer(
        monkeypatch,
        neural=[(150, 100, 60, 80)],
        frontal=[(20, 420, 55, 50)],
    )

    regions = renderer._text_avoid_regions(Image.new("RGB", (360, 640)))
    faces = [box for box, weight in regions if weight == TEXT_FACE_AVOID_WEIGHT]

    assert len(faces) == 2
    assert any(_covers(box, (180, 140)) for box in faces)
    assert any(_covers(box, (45, 445)) for box in faces)


def test_eye_inside_located_face_does_not_extrapolate_second_head(monkeypatch):
    renderer = _renderer(
        monkeypatch,
        neural=[(55, 110, 50, 70)],
        profile=[(220, 320, 60, 80)],
        eyes=[(238, 337, 14, 10)],
    )

    regions = renderer._text_avoid_regions(Image.new("RGB", (360, 640)))
    faces = [box for box, weight in regions if weight == TEXT_FACE_AVOID_WEIGHT]

    assert len(faces) == 2
    assert any(_covers(box, (80, 145)) for box in faces)
    assert any(_covers(box, (250, 360)) for box in faces)
    # The confirmed second face already protects the eye; do not extrapolate
    # another head down into the chest from the same eye detection.
    assert not any(weight == TEXT_EYE_AVOID_WEIGHT for _box, weight in regions)


def test_located_face_replaces_redundant_hog_head_but_keeps_body(monkeypatch):
    renderer = _renderer(
        monkeypatch,
        neural=[(55, 110, 50, 70)],
        people=[(30, 80, 140, 440)],
    )

    regions = renderer._text_avoid_regions(Image.new("RGB", (360, 640)))
    faces = [box for box, weight in regions if weight == TEXT_FACE_AVOID_WEIGHT]

    assert len(faces) == 1
    assert _covers(faces[0], (80, 145))
    assert any(weight == TEXT_BODY_AVOID_WEIGHT for _box, weight in regions)
    assert not any(weight == TEXT_HEAD_AVOID_WEIGHT for _box, weight in regions)


def test_hog_head_of_another_person_is_preserved(monkeypatch):
    renderer = _renderer(
        monkeypatch,
        neural=[(55, 110, 50, 70)],
        people=[(30, 80, 140, 440), (205, 200, 130, 400)],
    )

    regions = renderer._text_avoid_regions(Image.new("RGB", (360, 640)))
    heads = [box for box, weight in regions if weight == TEXT_HEAD_AVOID_WEIGHT]

    assert len(heads) == 1
    assert _covers(heads[0], (270, 240))


def test_cascade_faces_remain_available_without_neural_detections(monkeypatch):
    renderer = _renderer(
        monkeypatch,
        frontal=[(55, 110, 50, 70)],
        profile=[(220, 320, 60, 80)],
    )

    regions = renderer._text_avoid_regions(Image.new("RGB", (360, 640)))
    faces = [box for box, weight in regions if weight == TEXT_FACE_AVOID_WEIGHT]

    assert len(faces) == 2
    assert any(_covers(box, (80, 145)) for box in faces)
    assert any(_covers(box, (250, 360)) for box in faces)


def test_cascade_and_neural_boxes_are_restored_to_original_coordinates(monkeypatch):
    renderer = _renderer(
        monkeypatch,
        neural=[(55, 110, 50, 70)],
        frontal=[(250, 380, 60, 80)],
        eyes=[(267, 399, 14, 10)],
    )

    regions = renderer._text_avoid_regions(Image.new("RGB", (1080, 1920)))
    faces = [box for box, weight in regions if weight == TEXT_FACE_AVOID_WEIGHT]

    # Detection runs at 405 x 720; both outputs must refer to the source photo.
    assert len(faces) == 2
    assert any(_covers(box, (213, 387)) for box in faces)
    assert any(_covers(box, (747, 1120)) for box in faces)
