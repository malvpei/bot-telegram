from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

import cv2
import numpy as np

from app.opencv_compat import CV2_ERROR


LOGGER = logging.getLogger(__name__)
YUNET_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "models"
    / "yunet"
    / "face_detection_yunet_2023mar.onnx"
)
YUNET_SCORE_THRESHOLD = 0.70
YUNET_MAX_DIMENSION = 640


class YuNetFaceDetector:
    """Optional local face detector; results use the caller's RGB coordinates."""

    def __init__(self, detector: object | None = None) -> None:
        self._detector = detector
        self._lock = Lock()

    def empty(self) -> bool:
        return self._detector is None

    def detect_faces(self, rgb: np.ndarray) -> np.ndarray:
        """Return clipped integer (x, y, width, height) boxes, or an empty array."""
        empty = np.empty((0, 4), dtype=np.int32)
        if (
            self.empty()
            or rgb.ndim != 3
            or rgb.shape[2] != 3
            or rgb.dtype != np.uint8
            or min(rgb.shape[:2]) <= 0
        ):
            return empty
        height, width = rgb.shape[:2]
        with self._lock:
            if self.empty():
                return empty
            try:
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                # YuNet was trained on faces up to about 300 pixels. A second,
                # smaller view helps close portraits when the first finds none.
                previous_size = None
                for max_dimension in (YUNET_MAX_DIMENSION, 320):
                    scale = min(1.0, max_dimension / max(width, height))
                    input_size = (
                        max(1, int(round(width * scale))),
                        max(1, int(round(height * scale))),
                    )
                    if input_size == previous_size:
                        continue
                    previous_size = input_size
                    source = (
                        bgr
                        if input_size == (width, height)
                        else cv2.resize(bgr, input_size, interpolation=cv2.INTER_AREA)
                    )
                    self._detector.setInputSize(input_size)
                    _retval, faces = self._detector.detect(source)
                    boxes = self._restore_boxes(faces, input_size, (width, height))
                    if len(boxes):
                        return boxes
            except (CV2_ERROR, AttributeError, TypeError):
                LOGGER.warning(
                    "YuNet face detection failed; continuing with cascade detection."
                )
                self._detector = None
        return empty

    @staticmethod
    def _restore_boxes(
        faces: np.ndarray | None,
        input_size: tuple[int, int],
        image_size: tuple[int, int],
    ) -> np.ndarray:
        empty = np.empty((0, 4), dtype=np.int32)
        if faces is None:
            return empty
        faces = np.asarray(faces)
        if faces.ndim != 2 or faces.shape[1] < 15:
            return empty
        width, height = image_size
        scale_x = width / input_size[0]
        scale_y = height / input_size[1]
        boxes: list[tuple[int, int, int, int]] = []
        for face in faces:
            if not np.isfinite(face[[0, 1, 2, 3, 14]]).all():
                continue
            x, y, box_width, box_height = (float(value) for value in face[:4])
            if face[14] < YUNET_SCORE_THRESHOLD or box_width <= 0 or box_height <= 0:
                continue
            # Floor/ceil outwards to retain all pixels at the detected boundary.
            left = max(0, min(width, int(np.floor(x * scale_x))))
            top = max(0, min(height, int(np.floor(y * scale_y))))
            right = max(0, min(width, int(np.ceil((x + box_width) * scale_x))))
            bottom = max(0, min(height, int(np.ceil((y + box_height) * scale_y))))
            if right > left and bottom > top:
                boxes.append((left, top, right - left, bottom - top))
        return np.asarray(boxes, dtype=np.int32).reshape((-1, 4))


def build_face_detector(model_path: Path | None = None) -> YuNetFaceDetector:
    """Load the bundled model once; never download or require YuNet at runtime."""
    model_path = YUNET_MODEL_PATH if model_path is None else Path(model_path)
    detector_type = getattr(cv2, "FaceDetectorYN", None)
    factory = getattr(detector_type, "create", None)
    if not callable(factory) or not model_path.is_file():
        LOGGER.warning(
            "YuNet model or OpenCV FaceDetectorYN unavailable; using cascade detection."
        )
        return YuNetFaceDetector()
    try:
        detector = factory(
            str(model_path),
            "",
            (320, 320),
            YUNET_SCORE_THRESHOLD,
            0.3,
            5000,
        )
    except (CV2_ERROR, AttributeError, TypeError):
        LOGGER.warning("YuNet model could not be loaded; using cascade detection.")
        return YuNetFaceDetector()
    return YuNetFaceDetector(detector)
