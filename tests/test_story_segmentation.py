from __future__ import annotations

import base64
import math
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, PngImagePlugin

from app.story_segmentation import segmentation_input, subject_box_from_segmentation


def _bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _mask(box=(20, 60, 70, 199), *, size=(100, 200)):
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).rectangle(box, fill=255)
    return image


def _entry(image, **extra):
    return {
        "url": "data:image/png;base64," + base64.b64encode(_bytes(image)).decode("ascii"),
        "width": image.width,
        "height": image.height,
        **extra,
    }


def _read(result, **kwargs):
    def unexpected_download(url):
        pytest.fail(f"Data URI should not require a download: {url}")
    return subject_box_from_segmentation(result, download=kwargs.get("download", unexpected_download))


@pytest.mark.parametrize("size,expected", [((1080, 1920), (576, 1024)), ((1920, 1080), (1024, 576)), ((100, 200), (100, 200))])
def test_request_preserves_scene_aspect_ratio_and_excludes_coordinate_guide(tmp_path, size, expected):
    path = tmp_path / "scene.png"
    image = Image.new("RGB", size, (193, 143, 83))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("story_subject_box", "[0.3,0.5,0.9,1]")
    image.save(path, pnginfo=metadata)
    original = path.read_bytes()

    payload = segmentation_input(path)

    assert payload["prompt"] == "person"
    assert payload["apply_mask"] is False
    assert payload["sync_mode"] is True
    assert payload["include_scores"] is True
    assert payload["return_multiple_masks"] is True
    with Image.open(BytesIO(base64.b64decode(payload["image_url"].split(",", 1)[1]))) as sent:
        assert sent.size == expected
        assert sent.getpixel((0, 0)) == (193, 143, 83)
        assert "story_subject_box" not in sent.info
    assert path.read_bytes() == original


def test_mask_pixels_override_inaccurate_provider_boxes():
    result = {"masks": [_entry(_mask())], "scores": [0.927], "boxes": [[0.1, 0.9, 0.1, 0.1]]}

    assert _read(result) == (0.2, 0.3, 0.71, 1.0)


def test_largest_person_wins_over_small_high_confidence_background_person():
    result = {
        "masks": [_entry(_mask((5, 20, 15, 60))), _entry(_mask())],
        "scores": [0.99, 0.8],
    }

    assert _read(result) == (0.2, 0.3, 0.71, 1.0)


def test_low_confidence_large_shape_is_skipped():
    result = {
        "masks": [_entry(_mask((1, 5, 98, 199))), _entry(_mask())],
        "scores": [0.49, 0.8],
    }

    assert _read(result) == (0.2, 0.3, 0.71, 1.0)


def test_largest_subject_is_compared_in_scene_coordinates_across_mask_resolutions():
    result = {
        "masks": [
            _entry(_mask((50, 100, 150, 400), size=(1000, 2000))),
            _entry(_mask()),
        ],
        "scores": [0.99, 0.8],
    }

    assert _read(result) == (0.2, 0.3, 0.71, 1.0)


def test_metadata_indices_supply_scores_without_assuming_list_order():
    result = {
        "masks": [_entry(_mask()), _entry(_mask((5, 20, 15, 60)))],
        "metadata": [{"index": 1, "score": 0.99}, {"index": 0, "score": 0.8}],
    }

    assert _read(result) == (0.2, 0.3, 0.71, 1.0)


def test_disconnected_hair_and_raised_hand_pixels_remain_protected():
    image = _mask()
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 50, 40), fill=255)
    draw.rectangle((75, 45, 80, 55), fill=255)

    assert _read({"masks": [_entry(image)], "scores": [0.9]}) == (0.2, 0.15, 0.81, 1.0)


@pytest.mark.parametrize("score", [None, False, "0.9", 0.49, 1.1, math.nan, math.inf])
def test_missing_or_invalid_confidence_rejects_mask(score):
    assert _read({"masks": [_entry(_mask())], "scores": [score]}) is None


@pytest.mark.parametrize("color", [0, 255])
def test_empty_and_full_masks_are_not_person_geometry(color):
    assert _read({"masks": [_entry(Image.new("L", (100, 200), color))], "scores": [0.9]}) is None


def test_inverse_background_mask_is_rejected():
    image = Image.new("L", (100, 200), 255)
    ImageDraw.Draw(image).rectangle((20, 60, 70, 199), fill=0)

    assert _read({"masks": [_entry(image)], "scores": [0.9]}) is None


@pytest.mark.parametrize("change", [{"width": 120}, {"height": 201}, {"width": True}, {"height": "200"}])
def test_inconsistent_mask_dimensions_are_rejected(change):
    assert _read({"masks": [_entry(_mask(), **change)], "scores": [0.9]}) is None


@pytest.mark.parametrize("mode,color", [("RGB", (30, 80, 180)), ("RGBA", (255, 255, 255, 0))])
def test_applied_color_cutouts_are_not_binary_masks(mode, color):
    assert _read({"masks": [_entry(Image.new(mode, (100, 200), color))], "scores": [0.9]}) is None


def test_https_mask_download_is_delegated_and_geometry_is_normalized():
    urls = []
    def download(url):
        urls.append(url)
        return _bytes(_mask())

    result = {"masks": [{"url": "https://fal.media/mask.png"}], "scores": [0.9]}

    assert _read(result, download=download) == (0.2, 0.3, 0.71, 1.0)
    assert urls == ["https://fal.media/mask.png"]


@pytest.mark.parametrize("url", ["http://fal.media/mask.png", "file:///tmp/mask.png", "data:image/svg+xml;base64,AAAA", "data:image/png;base64,%%%", "https://user:secret@example.com/mask.png", None])
def test_malformed_mask_locations_do_not_trigger_download(url):
    assert _read({"masks": [{"url": url}], "scores": [0.9]}) is None


@pytest.mark.parametrize("result", [None, [], {}, {"masks": []}, {"masks": "bad"}, {"masks": [None], "scores": [0.9]}])
def test_malformed_results_have_no_geometry(result):
    assert _read(result) is None


def test_broken_mask_is_skipped_without_losing_next_valid_person():
    result = {
        "masks": [{"url": "data:image/png;base64," + base64.b64encode(b"bad PNG").decode()}, _entry(_mask())],
        "scores": [0.9, 0.8],
    }

    assert _read(result) == (0.2, 0.3, 0.71, 1.0)
