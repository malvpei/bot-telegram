from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from app.face_detection import (
    YUNET_MODEL_PATH,
    YUNET_SCORE_THRESHOLD,
    YuNetFaceDetector,
    build_face_detector,
)


def _face(x: float, y: float, width: float, height: float, score=0.95):
    return [x, y, width, height, *([0.0] * 10), score]


class FakeDetector:
    def __init__(self, results):
        self.results = list(results)
        self.sizes = []
        self.images = []

    def setInputSize(self, size):
        self.sizes.append(size)

    def detect(self, image):
        self.images.append(image.copy())
        return 1, self.results.pop(0)


def test_detector_converts_rgb_and_restores_resized_coordinates():
    fake = FakeDetector([np.asarray([_face(32, 64, 64, 96)])])
    detector = YuNetFaceDetector(fake)
    rgb = np.full((1280, 720, 3), (17, 45, 81), dtype=np.uint8)

    boxes = detector.detect_faces(rgb)

    assert fake.sizes == [(360, 640)]
    assert tuple(fake.images[0][0, 0]) == (81, 45, 17)
    assert boxes.dtype == np.int32
    assert boxes.tolist() == [[64, 128, 128, 192]]


def test_detector_uses_actual_rounded_input_size_for_each_axis():
    fake = FakeDetector([np.asarray([_face(30, 50, 30, 50)])])
    detector = YuNetFaceDetector(fake)

    boxes = detector.detect_faces(np.zeros((1001, 333, 3), dtype=np.uint8))

    assert fake.sizes == [(213, 640)]
    assert boxes.tolist() == [[46, 78, 48, 79]]


def test_detector_clips_boxes_and_rejects_invalid_or_low_confidence_faces():
    fake = FakeDetector(
        [np.asarray([
            _face(-5.5, 5.5, 30.25, 90),
            _face(20, 20, 10, 10, score=0.40),
            _face(20, 20, -10, 10),
            _face(float("nan"), 10, 10, 10),
            _face(20, 20, 10, 10, score=float("nan")),
            _face(200, 200, 10, 10),
        ])]
    )

    boxes = YuNetFaceDetector(fake).detect_faces(np.zeros((80, 100, 3), dtype=np.uint8))

    assert boxes.tolist() == [[0, 5, 25, 75]]


def test_detector_retries_smaller_view_for_large_closeup_faces():
    fake = FakeDetector([None, np.asarray([_face(40, 60, 100, 150)])])

    boxes = YuNetFaceDetector(fake).detect_faces(np.zeros((640, 480, 3), dtype=np.uint8))

    assert fake.sizes == [(480, 640), (240, 320)]
    assert boxes.tolist() == [[80, 120, 200, 300]]


def test_detector_keeps_working_after_an_image_without_faces():
    fake = FakeDetector([None, np.asarray([_face(20, 20, 40, 50)])])
    detector = YuNetFaceDetector(fake)
    rgb = np.zeros((200, 200, 3), dtype=np.uint8)

    empty = detector.detect_faces(rgb)
    boxes = detector.detect_faces(rgb)

    assert empty.shape == (0, 4)
    assert boxes.tolist() == [[20, 20, 40, 50]]
    assert not detector.empty()


@pytest.mark.parametrize("failure_stage", ["setInputSize", "detect"])
def test_opencv_errors_disable_optional_detector_without_breaking_render(failure_stage):
    fake = FakeDetector([])

    def fail(*_args):
        raise cv2.error("Unsupported DNN runtime")

    setattr(fake, failure_stage, fail)
    detector = YuNetFaceDetector(fake)
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)

    assert detector.detect_faces(rgb).shape == (0, 4)
    assert detector.empty()
    assert detector.detect_faces(rgb).shape == (0, 4)


def test_builder_uses_bundled_model_and_preserves_detector_instance(monkeypatch):
    fake = FakeDetector([None, None])
    calls = []

    def create(*args):
        calls.append(args)
        return fake

    monkeypatch.setattr(cv2, "FaceDetectorYN", SimpleNamespace(create=create))

    detector = build_face_detector()
    detector.detect_faces(np.zeros((100, 100, 3), dtype=np.uint8))
    detector.detect_faces(np.zeros((200, 200, 3), dtype=np.uint8))

    assert len(calls) == 1
    assert calls[0][0] == str(YUNET_MODEL_PATH)
    assert calls[0][3] == YUNET_SCORE_THRESHOLD
    assert not detector.empty()


def test_builder_degrades_when_model_is_missing(tmp_path):
    detector = build_face_detector(tmp_path / "missing.onnx")

    assert detector.empty()
    assert detector.detect_faces(np.zeros((100, 100, 3), dtype=np.uint8)).shape == (0, 4)


def test_builder_degrades_when_opencv_feature_is_missing(monkeypatch):
    monkeypatch.delattr(cv2, "FaceDetectorYN", raising=False)

    assert build_face_detector().empty()


def test_builder_degrades_when_model_is_unsupported(monkeypatch):
    def create(*_args):
        raise cv2.error("Unsupported model")

    monkeypatch.setattr(cv2, "FaceDetectorYN", SimpleNamespace(create=create))

    assert build_face_detector().empty()


def test_bundled_model_is_verified_binary_not_a_git_lfs_pointer():
    model = YUNET_MODEL_PATH.read_bytes()

    assert len(model) == 232589
    assert hashlib.sha256(model).hexdigest() == (
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    )


def test_bundled_model_detects_profile_face_in_existing_type_1_photo():
    # This checked-in reference is HEIF despite its .png extension. It shows a
    # close side profile partly obscured by a glass, missed by the old cascades.
    import pillow_heif

    pillow_heif.register_heif_opener()
    reference = (
        Path(__file__).resolve().parents[1]
        / "tipo1"
        / "ejemplo1"
        / "b2c83e5a5e01a42133ab4ec73417d620.png"
    )
    with Image.open(reference) as image:
        rgb = np.asarray(image.convert("RGB"))
    detector = build_face_detector()

    boxes = detector.detect_faces(rgb)

    assert not detector.empty()
    assert any(
        x <= 650 <= x + width
        and y <= 550 <= y + height
        and width >= 250
        and height >= 350
        for x, y, width, height in boxes
    )
