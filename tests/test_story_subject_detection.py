from __future__ import annotations

import math

import pytest
from PIL import Image, ImageDraw

from app.story_layout import story_subject_box, write_story_subject_box
from app.story_subject_detection import refine_story_subject_box


@pytest.fixture(params=((1080, 1920), (360, 640)), ids=("1080px", "360px"))
def scene(request):
    width, height = request.param
    return _draw_scene(width, height)


def _draw_scene(width, height, *, hair=(42, 32, 24), bridge=True):
    image = Image.new("RGB", (width, height), (225, 201, 161))
    draw = ImageDraw.Draw(image)

    def box(left, top, right, bottom):
        return tuple(round(value * length) for value, length in zip(
            (left, top, right, bottom), (width, height, width, height),
        ))

    # A dark cabinet well above the protagonist must never become the anchor.
    draw.rectangle(box(0.49, 0.20, 0.91, 0.29), fill=(35, 30, 22))
    if bridge:
        # Illustration outlines can connect otherwise unrelated foreground and
        # background shapes; local opening must break this thin connection.
        draw.line(
            (round(0.70 * width), round(0.28 * height), round(0.70 * width), round(0.49 * height)),
            fill=(22, 20, 17), width=max(1, round(2 * width / 1080)),
        )
    draw.ellipse(box(0.55, 0.43, 0.85, 0.59), fill=hair)
    draw.rectangle(box(0.62, 0.57, 0.82, 0.68), fill=(224, 161, 111))
    draw.rectangle(box(0.52, 0.68, 0.93, 0.99), fill=(25, 25, 25))
    return image


def _assert_hair_top_was_refined(image, refined, *, left=0.45):
    width, height = image.size
    hair_top = round(0.43 * height)
    allowance = max(3, round(12 * width / 1080))
    assert hair_top - allowance <= refined[1] * height <= hair_top + 2
    assert refined[1] > 0.40
    assert refined[0] == left
    assert refined[2:] == (0.95, 0.99)


def test_anchor_selects_hair_instead_of_higher_furniture_and_breaks_thin_outlines(scene):
    reviewed = (0.45, 0.48, 0.95, 0.99)

    refined = refine_story_subject_box(scene, reviewed, (0.70, 0.50))

    _assert_hair_top_was_refined(scene, refined)


def test_refined_geometry_is_saved_without_changing_scene_pixels(scene, tmp_path):
    path = tmp_path / "scene.png"
    scene.save(path)

    write_story_subject_box(path, (0.45, 0.48, 0.95, 0.99), anchor_point=(0.70, 0.50))

    with Image.open(path) as saved:
        assert saved.convert("RGB").tobytes() == scene.tobytes()
        _assert_hair_top_was_refined(saved, story_subject_box(saved))


@pytest.mark.parametrize("point", (
    None, (), (0.7,), (0.7, 0.5, 0.3), (True, 0.5), ("0.7", 0.5),
    (math.nan, 0.5), (0.7, math.inf), (1.1, 0.5), (0.7, -0.1),
    (0.15, 0.15),  # Empty background outside the reviewed protagonist.
    (0.70, 0.83),  # Low point on a dark shirt, rather than the hair.
    (0.70, 0.245),  # A point on the cabinet above the reviewed silhouette.
))
def test_uncertain_or_invalid_anchor_keeps_reviewed_box(scene, point):
    reviewed = (0.45, 0.48, 0.95, 0.99)

    assert refine_story_subject_box(scene, reviewed, point) == reviewed


def test_light_hair_keeps_reviewed_box_instead_of_searching_for_another_dark_object(scene):
    width, height = scene.size
    image = _draw_scene(width, height, hair=(205, 177, 99), bridge=False)
    reviewed = (0.45, 0.48, 0.95, 0.99)

    assert refine_story_subject_box(image, reviewed, (0.70, 0.50)) == reviewed


def test_ambiguous_nearby_dark_components_keep_reviewed_box(scene):
    width, height = scene.size
    image = Image.new("RGB", scene.size, (225, 201, 161))
    draw = ImageDraw.Draw(image)
    center_x, center_y = round(width * 0.70), round(height * 0.50)
    gap = max(2, round(3 * width / 1080))
    draw.rectangle((round(width * 0.55), round(height * 0.43), center_x - gap, round(height * 0.59)), fill=(42, 32, 24))
    draw.rectangle((center_x + gap, round(height * 0.43), round(width * 0.85), round(height * 0.59)), fill=(42, 32, 24))
    reviewed = (0.45, 0.48, 0.95, 0.99)

    assert refine_story_subject_box(image, reviewed, (center_x / width, center_y / height)) == reviewed


def test_thick_connection_to_background_keeps_reviewed_box_when_shapes_cannot_be_separated(scene):
    width, height = scene.size
    draw = ImageDraw.Draw(scene)
    draw.rectangle(
        (round(width * 0.65), round(height * 0.28), round(width * 0.75), round(height * 0.50)),
        fill=(42, 32, 24),
    )
    reviewed = (0.45, 0.48, 0.95, 0.99)

    assert refine_story_subject_box(scene, reviewed, (0.70, 0.50)) == reviewed


def test_small_dark_mark_is_not_mistaken_for_the_protagonists_hair(scene):
    width, height = scene.size
    image = Image.new("RGB", scene.size, (225, 201, 161))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (round(width * 0.69), round(height * 0.49), round(width * 0.71), round(height * 0.51)),
        fill=(42, 32, 24),
    )
    reviewed = (0.45, 0.48, 0.95, 0.99)

    assert refine_story_subject_box(image, reviewed, (0.70, 0.50)) == reviewed


def test_unique_hair_component_can_correct_a_small_horizontal_vision_point_error(scene):
    reviewed = (0.30, 0.48, 0.95, 0.99)

    refined = refine_story_subject_box(scene, reviewed, (0.43, 0.50))

    _assert_hair_top_was_refined(scene, refined, left=0.30)


@pytest.mark.parametrize("point", ((0.43, 0.35), (0.20, 0.50)))
def test_horizontal_correction_never_searches_another_height_or_too_far_away(scene, point):
    reviewed = (0.15, 0.30, 0.95, 0.99)

    assert refine_story_subject_box(scene, reviewed, point) == reviewed


def test_horizontal_correction_keeps_reviewed_box_when_two_components_match_the_same_row(scene):
    width, height = scene.size
    image = Image.new("RGB", scene.size, (225, 201, 161))
    draw = ImageDraw.Draw(image)
    for left, right in ((0.35, 0.45), (0.61, 0.71)):
        draw.rectangle(
            (round(left * width), round(0.43 * height), round(right * width), round(0.59 * height)),
            fill=(42, 32, 24),
        )
    reviewed = (0.20, 0.30, 0.95, 0.99)

    assert refine_story_subject_box(image, reviewed, (0.53, 0.50)) == reviewed


def test_horizontal_correction_does_not_replace_an_occupied_point_with_another_shape(scene):
    width, height = scene.size
    draw = ImageDraw.Draw(scene)
    draw.rectangle(
        (round(0.42 * width), round(0.49 * height), round(0.44 * width), round(0.51 * height)),
        fill=(42, 32, 24),
    )
    reviewed = (0.30, 0.48, 0.95, 0.99)

    # A point already on an unrelated small mark is uncertain. It must not be
    # silently redirected to a different object further along the same row.
    assert refine_story_subject_box(scene, reviewed, (0.43, 0.50)) == reviewed


def test_horizontal_correction_requires_component_overlap_with_reviewed_protagonist(scene):
    reviewed = (0.80, 0.30, 0.99, 0.99)

    # Hair outside this reviewed person touches only a thin sliver of its box.
    # Being at the right height and near the point is insufficient evidence.
    assert refine_story_subject_box(scene, reviewed, (0.94, 0.50)) == reviewed


def test_dark_component_never_moves_an_existing_safe_top_downward(scene):
    reviewed = (0.45, 0.30, 0.95, 0.99)

    refined = refine_story_subject_box(scene, reviewed, (0.70, 0.50))

    assert refined[1] == reviewed[1]


def test_brown_crown_is_not_discarded_when_only_a_lower_dark_patch_is_detected(scene):
    width, height = scene.size
    image = _draw_scene(width, height, hair=(126, 75, 43), bridge=False)
    ImageDraw.Draw(image).ellipse(
        (round(width * 0.60), round(height * 0.50), round(width * 0.80), round(height * 0.58)),
        fill=(45, 30, 20),
    )
    reviewed = (0.45, 0.43, 0.95, 0.99)

    refined = refine_story_subject_box(image, reviewed, (0.70, 0.54))

    assert refined[1] == reviewed[1]
