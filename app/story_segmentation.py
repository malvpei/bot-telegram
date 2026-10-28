"""Read precise protagonist bounds from SAM person masks, without color guesses."""

from __future__ import annotations

import base64
import binascii
import math
from collections.abc import Callable
from io import BytesIO
from numbers import Real
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from PIL import Image, ImageOps


STORY_SEGMENTATION_MODEL = "fal-ai/sam-3/image"
_MAX_MASK_BYTES = 8 * 1024 * 1024
_MAX_MASK_DIMENSION = 4096


def segmentation_input(image_path: Path) -> dict[str, object]:
    """Send only scene pixels; the coordinate guide and PNG metadata are excluded."""
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "image_url": f"data:image/png;base64,{encoded}",
        "prompt": "person",
        "apply_mask": False,
        "sync_mode": True,
        "return_multiple_masks": True,
        "max_masks": 8,
        "include_scores": True,
        "include_boxes": True,
        "output_format": "png",
    }


def _mask_score(result: dict, index: int) -> float | None:
    scores = result.get("scores")
    if isinstance(scores, list) and index < len(scores):
        score = scores[index]
    else:
        metadata = result.get("metadata")
        matches = [
            item for item in metadata or []
            if isinstance(item, dict)
            and isinstance(item.get("index"), int)
            and not isinstance(item.get("index"), bool)
            and item["index"] == index
        ] if isinstance(metadata, list) else []
        if len(matches) != 1:
            return None
        score = matches[0].get("score")
    if isinstance(score, bool) or not isinstance(score, Real):
        return None
    score = float(score)
    return score if math.isfinite(score) and 0.5 <= score <= 1 else None


def _mask_bytes(url: object, download: Callable[[str], bytes]) -> bytes | None:
    if not isinstance(url, str):
        return None
    if url.startswith("data:"):
        header, separator, payload = url.partition(",")
        if (
            not separator
            or header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}
            or len(payload) > _MAX_MASK_BYTES * 4 // 3 + 4
        ):
            return None
        try:
            contents = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error):
            return None
    else:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        # The caller owns HTTP authorization, timeouts and destination validation.
        contents = download(url)
    if not isinstance(contents, bytes) or len(contents) > _MAX_MASK_BYTES:
        return None
    return contents


def _mask_geometry(contents: bytes, metadata: dict) -> tuple[float, tuple[float, float, float, float]] | None:
    with Image.open(BytesIO(contents)) as image:
        width, height = image.size
        if min(width, height) < 16 or max(width, height) > _MAX_MASK_DIMENSION:
            return None
        for key, actual in (("width", width), ("height", height)):
            value = metadata.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value != actual
            ):
                return None
        # An applied color cutout is not a binary person mask. Reject it instead
        # of treating pale skin, clothes or transparency as background geometry.
        if image.mode in {"RGB", "RGBA", "P"}:
            rgba = np.asarray(image.convert("RGBA"))
            if (
                not np.all(rgba[:, :, 3] == 255)
                or not np.array_equal(rgba[:, :, 0], rgba[:, :, 1])
                or not np.array_equal(rgba[:, :, 1], rgba[:, :, 2])
            ):
                return None
        elif image.mode not in {"1", "L"}:
            return None
        gray = np.asarray(image.convert("L"))
    # Binary output can contain a narrow antialiased edge, but not a photograph.
    if np.mean((gray <= 8) | (gray >= 247)) < 0.95:
        return None
    foreground = gray >= 128
    area = int(np.count_nonzero(foreground))
    ratio = area / (width * height)
    if not 0.015 <= ratio <= 0.95:
        return None
    rows, columns = np.nonzero(foreground)
    left, top = int(columns.min()), int(rows.min())
    right, bottom = int(columns.max()) + 1, int(rows.max()) + 1
    if (left, top, right, bottom) == (0, 0, width, height):
        return None
    # Keep every foreground pixel: fine hair or hands can be disconnected from
    # the torso, and discarding smaller components can hide the true upper edge.
    return ratio, (left / width, top / height, right / width, bottom / height)


def subject_box_from_segmentation(
    result: object,
    *,
    download: Callable[[str], bytes],
) -> tuple[float, float, float, float] | None:
    """Choose the largest confident person mask and normalize its pixel bounds."""
    if not isinstance(result, dict) or not isinstance(result.get("masks"), list):
        return None
    best = None
    for index, mask in enumerate(result["masks"][:32]):
        if not isinstance(mask, dict) or _mask_score(result, index) is None:
            continue
        try:
            contents = _mask_bytes(mask.get("url"), download)
            geometry = _mask_geometry(contents, mask) if contents is not None else None
        except (OSError, ValueError, TypeError, RuntimeError, Image.DecompressionBombError):
            continue
        if geometry is not None and (best is None or geometry[0] > best[0]):
            best = geometry
    return best[1] if best is not None else None
