from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import opencv_compat


def test_cascade_builder_requires_cv2_objdetect(monkeypatch):
    monkeypatch.setattr(opencv_compat, "cv2", SimpleNamespace(__file__="fake-cv2"))

    with pytest.raises(opencv_compat.OpenCVFeatureError, match="opencv-python-headless"):
        opencv_compat.build_cascade("missing.xml")


def test_people_detector_falls_back_when_cv2_hog_is_missing(monkeypatch):
    monkeypatch.setattr(opencv_compat, "cv2", SimpleNamespace(__file__="fake-cv2"))

    people_detector = opencv_compat.build_people_detector()

    boxes, weights = people_detector.detectMultiScale(None)
    assert boxes.shape == (0, 4)
    assert weights.shape == (0,)
