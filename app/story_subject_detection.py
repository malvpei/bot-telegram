"""Conservative local refinement of reviewed cartoon protagonist geometry."""

from __future__ import annotations

import math
from numbers import Real

import cv2
import numpy as np
from PIL import Image

from app.opencv_compat import CV2_ERROR
from app.story_layout import StorySubjectBox, parse_story_subject_box


def refine_story_subject_box(
    image: Image.Image,
    box: StorySubjectBox,
    anchor_point: tuple[float, float] | None,
) -> StorySubjectBox:
    """Refine dark hair only when the review point identifies one compact shape.

    The point is inside the highest part of the foreground protagonist, normally
    their hair. Never search for an unrelated higher dark shape in the room.
    Other hair colors, ambiguous points and connected furniture keep the reviewed
    rectangle unchanged.
    """
    normalized = parse_story_subject_box(box)
    if normalized is None or not isinstance(anchor_point, (list, tuple)) or len(anchor_point) != 2:
        return box
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in anchor_point
    ):
        return box
    anchor_x, anchor_y = (float(value) for value in anchor_point)
    left, top, right, bottom = normalized
    # A low point can land on a shirt or bag rather than the upper silhouette.
    if (
        anchor_y - top > 0.23
        or not left - 0.03 <= anchor_x <= right + 0.03
        or not top - 0.03 <= anchor_y <= bottom + 0.03
    ):
        return box
    width, height = image.size
    if min(width, height) < 16:
        return box

    scale = width / 1080
    kernel_size = max(3, round(7 * scale)) | 1
    radius = max(2, round(8 * scale))
    try:
        rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
        red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        mask = (
            (red < 85) & (green < 85) & (blue < 85)
            & (red >= green - 3) & (green >= blue - 3)
        ).astype(np.uint8)
        # Remove thin outlines that can join hair to a wardrobe, desk or menu.
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN,
            np.ones((kernel_size, kernel_size), dtype=np.uint8),
        )
        _count, labels, statistics, _centroids = cv2.connectedComponentsWithStats(mask)
    except (CV2_ERROR, AttributeError, TypeError, ValueError):
        return box

    point_x = min(width - 1, round(anchor_x * width))
    point_y = min(height - 1, round(anchor_y * height))

    def eligible_component(component_label: int) -> bool:
        _x, _y, component_width, component_height, area = statistics[component_label]
        return bool(
            area >= width * height * 0.002
            and width * 0.06 <= component_width <= width * 0.55
            and height * 0.025 <= component_height <= height * 0.23
        )

    label = int(labels[point_y, point_x])
    if label == 0:
        local = labels[
            max(0, point_y - radius):min(height, point_y + radius + 1),
            max(0, point_x - radius):min(width, point_x + radius + 1),
        ]
        candidates = np.unique(local[local > 0])
        if len(candidates) > 1:
            return box
        if len(candidates) == 1:
            label = int(candidates[0])
        else:
            # Vision can get the head's row right but its horizontal point wrong.
            # Correct only a unique compact shape on that same row, never a
            # higher object or a best guess among several furniture/hair shapes.
            row_start = max(0, point_y - radius)
            row_end = min(height, point_y + radius + 1)
            row_labels = labels[row_start:row_end]
            corrected_candidates = []
            for possible in np.unique(row_labels[row_labels > 0]):
                possible = int(possible)
                if not eligible_component(possible):
                    continue
                x, _y, component_width, _component_height, _area = statistics[possible]
                overlap = max(0, min(x + component_width, right * width) - max(x, left * width))
                if overlap < component_width * 0.25:
                    continue
                _row_y, row_x = np.where(row_labels == possible)
                horizontal_distance = float(np.min(np.abs(row_x - point_x)))
                if horizontal_distance <= width * 0.18:
                    corrected_candidates.append(possible)
            if len(corrected_candidates) != 1:
                return box
            label = corrected_candidates[0]

    x, y, component_width, component_height, area = (
        int(value) for value in statistics[label]
    )
    if not eligible_component(label):
        return box
    refined_top = max(0, y - radius) / height
    return (
        min(left, x / width),
        min(top, refined_top),
        max(right, (x + component_width) / width),
        max(bottom, (y + component_height) / height),
    )
