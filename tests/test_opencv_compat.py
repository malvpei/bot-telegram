from __future__ import annotations

from types import SimpleNamespace

from app import opencv_compat


def test_detector_builders_fall_back_when_cv2_objdetect_is_missing(monkeypatch):
    monkeypatch.setattr(opencv_compat, "cv2", SimpleNamespace(__file__="fake-cv2"))

    cascade = opencv_compat.build_cascade("missing.xml")
    people_detector = opencv_compat.build_people_detector()

    assert cascade.empty() is True
    assert cascade.detectMultiScale(None).shape == (0, 4)
    boxes, weights = people_detector.detectMultiScale(None)
    assert boxes.shape == (0, 4)
    assert weights.shape == (0,)
