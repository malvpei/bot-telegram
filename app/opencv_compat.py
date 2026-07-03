from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np


LOGGER = logging.getLogger(__name__)


class EmptyCascade:
    def empty(self) -> bool:
        return True

    def detectMultiScale(self, *args, **kwargs) -> np.ndarray:  # noqa: N802
        return np.empty((0, 4), dtype=np.int32)


class EmptyPeopleDetector:
    def detectMultiScale(self, *args, **kwargs) -> tuple[np.ndarray, np.ndarray]:  # noqa: N802
        return (
            np.empty((0, 4), dtype=np.int32),
            np.empty((0,), dtype=np.float32),
        )


def build_cascade(filename: str):
    cascade_factory = getattr(cv2, "CascadeClassifier", None)
    data = getattr(cv2, "data", None)
    haarcascades = getattr(data, "haarcascades", "")
    if cascade_factory is None or not haarcascades:
        LOGGER.warning(
            "OpenCV objdetect is unavailable; disabling cascade %s. cv2=%s",
            filename,
            getattr(cv2, "__file__", "unknown"),
        )
        return EmptyCascade()

    detector = cascade_factory(str(Path(haarcascades) / filename))
    if detector.empty():
        LOGGER.warning("OpenCV cascade %s could not be loaded.", filename)
    return detector


def build_people_detector():
    hog_factory = getattr(cv2, "HOGDescriptor", None)
    default_detector = getattr(cv2, "HOGDescriptor_getDefaultPeopleDetector", None)
    if hog_factory is None or default_detector is None:
        LOGGER.warning(
            "OpenCV HOG people detector is unavailable; body detection disabled. cv2=%s",
            getattr(cv2, "__file__", "unknown"),
        )
        return EmptyPeopleDetector()

    detector = hog_factory()
    detector.setSVMDetector(default_detector())
    return detector
