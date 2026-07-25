from __future__ import annotations

import gc
import shutil
import weakref
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw

from app.advice_cards import ADVICE_PACKS, AdviceBackground
from app.config import get_settings
from app.models import (
    ImageMetrics,
    Language,
    MediaCandidate,
    SlidePlan,
    SlideRole,
    VideoPlan,
    VideoType,
)
from app.opencv_compat import EmptyCascade, EmptyPeopleDetector
from app.render import (
    FEBRUARY_FIXED_SCREEN_TEXT_MARGIN,
    FEBRUARY_TITLE_MIN_BOX_WIDTH,
    FIXED_SCREEN_TEXT_MARGIN,
    HOOK_BASE_FONT_SIZE,
    HOOK_MIN_FONT_SIZE,
    HOOK_SIDE_MARGIN,
    HOOK_TEXT_STROKE_FILL,
    HOOK_TEXT_STROKE_WIDTH,
    SAFE_TEXT_BOTTOM_MARGIN,
    SAFE_TEXT_TOP_MARGIN,
    TEXT_CARD_CORNER_RADIUS,
    TEXT_CARD_BODY_FONT_SIZE,
    TEXT_CARD_BODY_MIN_FONT_SIZE,
    TEXT_CARD_PADDING_X,
    TEXT_CARD_PADDING_Y,
    TEXT_CARD_TITLE_FONT_SIZE,
    TEXT_CARD_TITLE_MIN_FONT_SIZE,
    TEXT_CARD_TITLE_PADDING_Y,
    TEXT_AVOID_CLEARANCE_MARGIN,
    TEXT_FACE_AVOID_WEIGHT,
    TEXT_FALLBACK_HEAD_AVOID_WEIGHT,
    TEXT_HEAD_AVOID_WEIGHT,
    TYPE_1_HOOK_SIDE_MARGIN,
    TYPE_2_HOOK_FONT_SCALE,
    TYPE_2_COSTLY_MISTAKES_HOOK_FONT_SCALE,
    TYPE_2_HOOK_INNER_STROKE_WIDTH,
    TYPE_2_HOOK_STROKE_WIDTH,
    TYPE_3_TITLE_FONT_SIZE,
    TYPE_4_EN_PAYMENTS_LABEL_EXTRA_WIDTH,
    TYPE_4_LABEL_FONT_SIZE,
    TYPE_4_TITLE_INNER_STROKE_WIDTH,
    TYPE_4_TITLE_STROKE_WIDTH,
    TYPE_4_STORY_CAPTION_PRIMARY_CENTER,
    TYPE_4_TEXT_STROKE_WIDTH,
    TYPE_4_TOOL_NAME_INNER_STROKE_WIDTH,
    VideoRenderer,
)


def test_type_4_flat_advice_cards_invert_background_and_text_colors():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    tips = ADVICE_PACKS[Language.ES][0]

    black = renderer.render_advice_card(tips, Language.ES, AdviceBackground.BLACK)
    white = renderer.render_advice_card(tips, Language.ES, AdviceBackground.WHITE)
    black_pixels = np.asarray(black)
    white_pixels = np.asarray(white)

    assert black.size == (360, 640)
    assert white.size == (360, 640)
    assert tuple(black_pixels[0, 0]) == (0, 0, 0)
    assert tuple(white_pixels[0, 0]) == (255, 255, 255)
    assert (black_pixels[..., :3] > 235).all(axis=2).mean() > 0.01
    assert (white_pixels[..., :3] < 25).all(axis=2).mean() > 0.01


def test_type_4_illustrated_advice_card_draws_header_cards_and_icons():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))

    result = renderer.render_advice_card(
        ADVICE_PACKS[Language.EN][1],
        Language.EN,
        AdviceBackground.ILLUSTRATED,
    )
    pixels = np.asarray(result)

    assert result.size == (360, 640)
    assert tuple(pixels[0, 0]) == (247, 247, 245)
    assert (pixels[..., 0] < 50).mean() > 0.01
    assert (
        (pixels[..., 2] > pixels[..., 0] + 25)
        & (pixels[..., 2] > pixels[..., 1])
    ).mean() > 0.001


def test_numbered_titleless_tip_keeps_number_with_body_for_rendering():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))

    title, body = renderer._split_slide_text(
        "1. Don't compete by slashing prices to the ground just to get your first quick sale."
    )

    assert title == ""
    assert body.startswith("1. Don't compete by slashing prices")


def test_numbered_titleless_tip_merges_line_broken_number_with_body():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))

    title, body = renderer._split_slide_text(
        "1.\nDon't compete by slashing prices to the ground just to get your first quick sale."
    )

    assert title == ""
    assert body.startswith("1. Don't compete by slashing prices")


def test_render_keeps_source_green_without_global_darkening():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "green.jpg"
        source_green = (20, 150, 55)
        Image.new("RGB", (360, 640), source_green).save(image_path)
        renderer = VideoRenderer(
            replace(
                get_settings(),
                root_dir=root,
                width=360,
                height=640,
                fonts_dir=root / "fonts",
            )
        )
        slide = SlidePlan(
            index=1,
            role=SlideRole.OCTOBER,
            text="",
            media=_candidate(image_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_1)
        bottom_pixel = np.asarray(still)[620, 180]

        assert np.allclose(bottom_pixel, source_green, atol=3)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_3_tool_slide_uses_icon_asset_and_hook_text_style():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        icons_dir = root / "tipo3" / "iconos"
        icons_dir.mkdir(parents=True)
        Image.new("RGBA", (512, 512), (99, 91, 255, 255)).save(icons_dir / "stripe.png")
        bg_path = root / "background.jpg"
        Image.new("RGB", (360, 640), (30, 30, 30)).save(bg_path)

        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        slide = SlidePlan(
            index=2,
            role=SlideRole.TOOL_PAYMENTS,
            text="4. Payments\nManage payments securely\nUse Stripe",
            media=_candidate(bg_path),
            fixed_asset=True,
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_3)
        pixels = np.asarray(still)
        icon_region = pixels[290:430, 120:240]
        text_region = pixels[50:250, 20:340]
        white_text_pixels = (
            (text_region[..., 0] > 230)
            & (text_region[..., 1] > 230)
            & (text_region[..., 2] > 230)
        )

        assert icon_region[..., 0].mean() > 70
        assert icon_region[..., 1].mean() > 60
        assert icon_region[..., 2].mean() > 150
        assert white_text_pixels.mean() > 0.005
        assert white_text_pixels.mean() < 0.12
        assert not (white_text_pixels.mean(axis=1) > 0.7).any()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_3_hook_still_keeps_photo_clean_without_hook_text():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        bg_path = root / "hook.jpg"
        Image.new("RGB", (360, 640), (0, 0, 0)).save(bg_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        slide = SlidePlan(
            index=1,
            role=SlideRole.HOOK,
            text="How to do Dropshipping in 2026",
            media=_candidate(bg_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_3)
        assert np.asarray(still).max() == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_hook_text_prefers_exactly_two_lines():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))

    _font, lines = renderer._fit_hook_two_lines(
        "How to do Dropshipping in 2026",
        draw,
        max_width=960,
        max_height=560,
        base_size=96,
        min_size=42,
        stroke_width=4,
    )

    assert len(lines) == 2


def test_hook_text_fallback_keeps_the_complete_hook():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (360, 640)))
    text = "4 consejos de Dropshipping que me habrían ahorrado muchos errores"

    font, lines = renderer._fit_hook_two_lines(
        text,
        draw,
        max_width=230,
        max_height=210,
        base_size=76,
        min_size=40,
        stroke_width=3,
    )

    assert " ".join(lines) == text
    assert renderer._block_height(lines, font, draw, stroke_width=3) <= 210
    assert len(lines) > 2


def test_hook_text_respects_manual_three_line_breaks(monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    text = (
        "Errores frecuentes que veo\n"
        "en dropshippers novatos\n"
        "cuando empiezan"
    )
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)

    def capture_lines(draw, lines, font, **kwargs):
        captured["lines"] = list(lines)

    monkeypatch.setattr(renderer, "_draw_lines", capture_lines)

    renderer._draw_hook_text(image, text)

    assert captured["lines"] == text.splitlines()


def test_hook_text_manual_lines_fit_inside_side_margins(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    text = (
        "How much I earned doing Dropshipping\n"
        "in my first 6 months and why I almost quit..."
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)

    def capture_lines(draw, lines, font, **kwargs):
        captured["draw"] = draw
        captured["lines"] = list(lines)
        captured["font"] = font
        captured["stroke_width"] = kwargs["stroke_width"]
        captured["inner_stroke_width"] = kwargs["inner_stroke_width"]

    monkeypatch.setattr(renderer, "_draw_lines", capture_lines)

    renderer._draw_hook_text(image, text)

    max_width = image.width - (HOOK_SIDE_MARGIN * 2)
    draw = captured["draw"]
    font = captured["font"]
    stroke_width = captured["stroke_width"]
    widths = [
        renderer._text_size(draw, line, font, stroke_width=stroke_width)[0]
        for line in captured["lines"]
    ]

    assert captured["lines"] == text.splitlines()
    assert max(widths) <= max_width


def test_type_2_balanced_spanish_hook_stays_large(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    text = "Errores que cuestan dinero\nal empezar en Dropshipping..."
    captured: dict[str, object] = {}

    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)

    def capture_lines(draw, lines, font, **kwargs):
        captured["draw"] = draw
        captured["lines"] = list(lines)
        captured["font"] = font
        captured["stroke_width"] = kwargs["stroke_width"]
        captured["inner_stroke_width"] = kwargs["inner_stroke_width"]

    monkeypatch.setattr(renderer, "_draw_lines", capture_lines)

    renderer._draw_hook_text(image, text, video_type=VideoType.TYPE_2)

    draw = captured["draw"]
    font = captured["font"]
    stroke_width = captured["stroke_width"]
    widths = [
        renderer._text_size(draw, line, font, stroke_width=stroke_width)[0]
        for line in captured["lines"]
    ]

    assert captured["lines"] == text.splitlines()
    assert getattr(font, "size", 0) >= 62
    assert abs(widths[0] - widths[1]) <= 100
    assert captured["inner_stroke_width"] == TYPE_2_HOOK_INNER_STROKE_WIDTH
    assert captured["stroke_width"] == TYPE_2_HOOK_STROKE_WIDTH


def test_costly_mistakes_hook_uses_its_smaller_scale(monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    captured = {}
    monkeypatch.setattr(
        renderer,
        "_fit_prebroken_lines",
        lambda *args, **kwargs: renderer._load_type_2_hook_font(100, True),
    )
    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)
    monkeypatch.setattr(
        renderer,
        "_draw_lines",
        lambda draw, lines, font, **kwargs: captured.update(font_size=font.size),
    )

    renderer._draw_hook_text(
        image,
        "Errores que cuestan dinero\nal empezar en Dropshipping...",
        video_type=VideoType.TYPE_2,
    )

    assert TYPE_2_COSTLY_MISTAKES_HOOK_FONT_SCALE == 0.92
    assert captured["font_size"] == 92


def test_type_2_hook_is_only_one_percent_smaller_with_stronger_outline(
    monkeypatch,
):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        renderer,
        "_fit_prebroken_lines",
        lambda *args, **kwargs: renderer._load_type_2_hook_font(100, True),
    )
    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)

    def capture_lines(draw, lines, font, **kwargs):
        captured["font_size"] = getattr(font, "size", 0)
        captured["stroke_width"] = kwargs["stroke_width"]

    monkeypatch.setattr(renderer, "_draw_lines", capture_lines)

    renderer._draw_hook_text(
        image,
        "Primera linea\nSegunda linea",
        video_type=VideoType.TYPE_2,
    )

    assert TYPE_2_HOOK_FONT_SCALE == 0.99
    assert captured["font_size"] == 99
    assert captured["stroke_width"] == TYPE_2_HOOK_STROKE_WIDTH == 5


def test_type_2_hook_uses_thinner_regular_face_without_changing_layout(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    regular_font_calls: list[tuple[int, bool]] = []
    original_load_font = renderer._load_font

    def capture_regular_font(*, size: int, bold: bool):
        regular_font_calls.append((size, bold))
        return original_load_font(size=size, bold=bold)

    def reject_bold_overlay(*args, **kwargs):
        raise AssertionError("Type 2 hook must not use the heavy overlay font")

    monkeypatch.setattr(renderer, "_load_font", capture_regular_font)
    monkeypatch.setattr(renderer, "_load_overlay_font", reject_bold_overlay)
    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)
    monkeypatch.setattr(renderer, "_draw_lines", lambda *args, **kwargs: None)

    renderer._draw_hook_text(
        image,
        "Errores que cuestan dinero\nal empezar en Dropshipping",
        video_type=VideoType.TYPE_2,
    )

    assert regular_font_calls
    assert all(bold is False for _size, bold in regular_font_calls)


def test_type_1_two_line_hook_reflows_to_larger_balanced_text(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGB", (1080, 1920), (0, 0, 0))
    text = (
        "Cuanto facturé haciendo Dropshipping\n"
        "en mis primeros 6 meses y por qué casi lo dejo..."
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 100)

    def capture_lines(draw, lines, font, **kwargs):
        captured["draw"] = draw
        captured["lines"] = list(lines)
        captured["font"] = font
        captured["stroke_width"] = kwargs["stroke_width"]

    monkeypatch.setattr(renderer, "_draw_lines", capture_lines)

    renderer._draw_hook_text(image, text, video_type=VideoType.TYPE_1)

    draw = captured["draw"]
    stroke_width = captured["stroke_width"]
    manual_font = renderer._fit_prebroken_lines(
        text.splitlines(),
        draw,
        max_width=1080 - (TYPE_1_HOOK_SIDE_MARGIN * 2),
        max_height=int(1920 * 0.40),
        base_size=HOOK_BASE_FONT_SIZE,
        min_size=HOOK_MIN_FONT_SIZE,
        bold=True,
        stroke_width=stroke_width,
        font_loader=renderer._load_overlay_font,
    )
    widths = [
        renderer._text_size(draw, line, captured["font"], stroke_width=stroke_width)[0]
        for line in captured["lines"]
    ]

    assert len(captured["lines"]) == 2
    assert captured["lines"] != text.splitlines()
    assert captured["font"].size > manual_font.size
    assert captured["font"].size >= 46
    assert max(widths) <= 1080 - (TYPE_1_HOOK_SIDE_MARGIN * 2)


def test_hook_text_renders_in_middle_third_without_avoid_regions(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        bg_path = root / "hook.jpg"
        Image.new("RGB", (360, 640), (0, 0, 0)).save(bg_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        slide = SlidePlan(
            index=1,
            role=SlideRole.HOOK,
            text="How to do Dropshipping in 2026",
            media=_candidate(bg_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_1)
        pixels = np.asarray(still)
        white = (
            (pixels[..., 0] > 220)
            & (pixels[..., 1] > 220)
            & (pixels[..., 2] > 220)
        )
        ys, _xs = np.where(white)
        center_y = (ys.min() + ys.max()) / 2

        assert abs((center_y / still.height) - 0.5) <= 0.08
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_safe_text_bounds_keep_larger_vertical_margins():
    min_y, max_y = VideoRenderer._safe_text_vertical_bounds(1920, 300)

    assert min_y == SAFE_TEXT_TOP_MARGIN
    assert max_y == 1920 - 300 - SAFE_TEXT_BOTTOM_MARGIN


def test_safe_text_start_avoids_detected_face_region(monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    image = Image.new("RGB", (1080, 1920), (25, 25, 25))
    face_region = (240, 700, 840, 1120)
    block_width = 820
    block_height = 260

    monkeypatch.setattr(
        renderer,
        "_text_avoid_regions",
        lambda _image: [(face_region, 260.0)],
    )

    y = renderer._safe_text_start_y(
        image,
        block_width=block_width,
        block_height=block_height,
        preferred_centers=(0.58, 0.62, 0.52, 0.66, 0.46),
    )
    x = (image.width - block_width) // 2
    text_box = (x, y, x + block_width, y + block_height)

    assert renderer._intersection_area(text_box, face_region) == 0
    assert y >= SAFE_TEXT_TOP_MARGIN
    assert y + block_height <= image.height - SAFE_TEXT_BOTTOM_MARGIN


def test_type_1_still_embeds_caption_cards(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "source.jpg"
        Image.new("RGB", (360, 640), (25, 30, 35)).save(image_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        slide = SlidePlan(
            index=2,
            role=SlideRole.OCTOBER,
            text=(
                "octubre - 0€\n"
                "empece con muchas ganas, pero no consegui ni una sola venta."
            ),
            media=_candidate(image_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_1)
        pixels = np.asarray(still)
        white_card_pixels = (
            (pixels[..., 0] > 230)
            & (pixels[..., 1] > 230)
            & (pixels[..., 2] > 230)
        )

        assert white_card_pixels.mean() > 0.015
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_1_numbered_tip_uses_hook_paragraph_style():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    slide = SlidePlan(
        index=2,
        role=SlideRole.TIP1,
        text=(
            "1. Don't compete by slashing prices to the ground just to get your "
            "first quick sale."
        ),
        media=_candidate(Path("source.jpg")),
    )

    assert renderer._uses_hook_paragraph_style(slide, VideoType.TYPE_1) is True


def test_hook_text_uses_slightly_softer_stroke(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (1080, 1920), (20, 20, 20, 255))
    captured: dict[str, object] = {}

    def fake_draw_lines(*args, **kwargs):
        captured["stroke_width"] = kwargs["stroke_width"]
        captured["stroke_fill"] = kwargs["stroke_fill"]

    monkeypatch.setattr(renderer, "_draw_lines", fake_draw_lines)

    renderer._draw_hook_text(image, "I would have paid to know these 4 things")

    assert captured["stroke_width"] == HOOK_TEXT_STROKE_WIDTH
    assert captured["stroke_fill"] == HOOK_TEXT_STROKE_FILL


def test_hook_text_uses_larger_two_line_fit(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (1080, 1920), (20, 20, 20, 255))
    captured: dict[str, int] = {}

    def fake_fit_hook_two_lines(*args, **kwargs):
        captured["max_width"] = kwargs["max_width"]
        captured["max_height"] = kwargs["max_height"]
        captured["base_size"] = kwargs["base_size"]
        captured["min_size"] = kwargs["min_size"]
        return renderer._load_font(size=48, bold=True), ["Line one", "Line two"]

    monkeypatch.setattr(renderer, "_fit_hook_two_lines", fake_fit_hook_two_lines)
    monkeypatch.setattr(renderer, "_safe_text_start_y", lambda *args, **kwargs: 200)
    monkeypatch.setattr(renderer, "_draw_lines", lambda *args, **kwargs: None)

    renderer._draw_hook_text(image, "Errores frecuentes que veo en dropshippers novatos")

    assert captured["max_width"] == 1080 - (HOOK_SIDE_MARGIN * 2)
    assert captured["max_height"] == int(1920 * 0.40)
    assert captured["base_size"] == HOOK_BASE_FONT_SIZE
    assert captured["min_size"] == HOOK_MIN_FONT_SIZE


def test_hook_text_uses_tiktok_overlay_font_loader(monkeypatch):
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (360, 640), (20, 20, 20, 255))
    calls: list[tuple[int, bool]] = []

    def fake_overlay_font(size: int, bold: bool):
        calls.append((size, bold))
        return renderer._load_font(size=size, bold=bold)

    monkeypatch.setattr(renderer, "_load_overlay_font", fake_overlay_font)

    renderer._draw_hook_text(image, "Mistakes I see small dropshippers making")

    assert calls
    assert all(bold for _size, bold in calls)


def test_repeated_numbered_hook_paragraph_is_collapsed():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))

    text = (
        "1. Don't compete by slashing prices. Instead, build a better offer. "
        "1. Don't compete by slashing prices. Instead, build a better offer."
    )

    assert (
        renderer._normalise_hook_paragraph_text(text)
        == "1. Don't compete by slashing prices. Instead, build a better offer."
    )


def test_type_2_long_titleless_tip_uses_hook_paragraph_style(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "source.jpg"
        Image.new("RGB", (360, 640), (25, 30, 35)).save(image_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        slide = SlidePlan(
            index=2,
            role=SlideRole.TIP1,
            text=(
                "1. Don't compete by slashing prices to the ground just to get your "
                "first quick sale. If your profit margin is tiny, any small unexpected "
                "expense in advertising or potential returns will put you in the red. "
                "Instead, focus your efforts on building an irresistible offer around "
                "your product. "
                "1. Don't compete by slashing prices to the ground just to get your "
                "first quick sale. If your profit margin is tiny, any small unexpected "
                "expense in advertising or potential returns will put you in the red."
            ),
            media=_candidate(image_path),
        )

        assert renderer._uses_hook_paragraph_style(slide, VideoType.TYPE_2) is True
        still = renderer.render_slide_still(slide, VideoType.TYPE_2)
        pixels = np.asarray(still)
        white = (
            (pixels[..., 0] > 235)
            & (pixels[..., 1] > 235)
            & (pixels[..., 2] > 235)
        )
        ys, _xs = np.where(white)

        assert white.mean() > 0.002
        assert white.mean() < 0.04
        assert ys.max() - ys.min() < int(still.height * 0.48)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_2_direct_variant_tip_uses_hook_paragraph_style():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    slide = SlidePlan(
        index=2,
        role=SlideRole.TIP1,
        text=(
            "1. Deja de probar suerte con productos y usa Dropradar para validar "
            "demanda, competencia y margen antes de gastar dinero en anuncios."
        ),
        media=_candidate(Path("source.jpg")),
    )

    assert renderer._uses_hook_paragraph_style(slide, VideoType.TYPE_2) is True


def test_caption_body_background_is_connected_and_keeps_side_margin(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "source.jpg"
        Image.new("RGB", (360, 640), (25, 30, 35)).save(image_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        slide = SlidePlan(
            index=2,
            role=SlideRole.OCTOBER,
            text=(
                "octubre - 0€\n"
                "lance mi primera tienda supermotivado. puse algo de dinero "
                "en anuncios, tuve un monton de vistas, pero nadie compro."
            ),
            media=_candidate(image_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_1)
        pixels = np.asarray(still)
        white = (
            (pixels[..., 0] > 235)
            & (pixels[..., 1] > 235)
            & (pixels[..., 2] > 235)
        )
        ys, xs = np.where(white)

        assert xs.min() >= 24
        assert xs.max() <= still.width - 24

        lower_half = white[still.height // 2 :, :]
        row_counts = lower_half.sum(axis=1)
        rows = np.where(row_counts > 24)[0]
        row_runs = np.split(rows, np.where(np.diff(rows) > 1)[0] + 1)
        body_run = max(row_runs, key=len)
        connected_rows = row_counts[body_run.min() : body_run.max() + 1]
        assert connected_rows.min() > 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_connected_caption_background_keeps_stepped_line_widths(monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    image = Image.new("RGBA", (360, 640), (20, 20, 20, 255))
    draw = ImageDraw.Draw(image)
    font = renderer._load_font(size=28, bold=False)
    captured: dict[str, list[tuple[tuple[int, int, int, int], tuple[int, int], str]]] = {}

    def capture_background(draw_arg, boxes, canvas_width):
        captured["boxes"] = list(boxes)

    monkeypatch.setattr(renderer, "_draw_connected_card_background", capture_background)

    renderer._draw_connected_pill_lines(
        draw,
        ["A much longer caption line", "short"],
        font,
        start_y=100,
        canvas_width=360,
        padding_x=18,
        padding_y=8,
        line_gap=-4,
    )

    widths = [box[0][2] - box[0][0] for box in captured["boxes"]]
    assert len(set(widths)) == 2


def test_caption_cards_keep_horizontal_shape_with_slightly_taller_background():
    assert TEXT_CARD_PADDING_X == 30
    assert TEXT_CARD_PADDING_Y == 13
    assert TEXT_CARD_TITLE_PADDING_Y == 16
    assert TEXT_CARD_CORNER_RADIUS == 20
    assert TEXT_CARD_TITLE_FONT_SIZE == 40
    assert TEXT_CARD_TITLE_MIN_FONT_SIZE == 31
    assert TEXT_CARD_BODY_FONT_SIZE == 38
    assert TEXT_CARD_BODY_MIN_FONT_SIZE == 29


def test_type_1_title_is_only_slightly_larger_than_body():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))

    title_font, _title_lines = renderer._fit_text(
        "1. Valida con poco presupuesto",
        draw,
        max_width=800,
        max_height=300,
        base_size=TEXT_CARD_TITLE_FONT_SIZE,
        min_size=TEXT_CARD_TITLE_MIN_FONT_SIZE,
        bold=False,
        stroke_width=0,
    )
    body_font, _body_lines = renderer._fit_text(
        "No trates la publicidad como una apuesta.",
        draw,
        max_width=800,
        max_height=300,
        base_size=TEXT_CARD_BODY_FONT_SIZE,
        min_size=TEXT_CARD_BODY_MIN_FONT_SIZE,
        bold=False,
        stroke_width=0,
    )

    assert 0 < title_font.size - body_font.size <= 4


def test_fixed_laptop_slide_places_caption_above_screen(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "fixed_laptop.jpg"
        canvas = np.full((640, 360, 3), (16, 18, 20), dtype=np.uint8)
        canvas[330:520, 50:330, :] = (185, 205, 195)
        Image.fromarray(canvas).save(image_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        slide = SlidePlan(
            index=3,
            role=SlideRole.TIP3,
            text=(
                "3. Prioriza nichos\n"
                "Usa Dropradar para validar productos con potencial."
            ),
            media=_candidate(image_path),
            fixed_asset=True,
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_2)
        pixels = np.asarray(still)
        white = (
            (pixels[..., 0] > 235)
            & (pixels[..., 1] > 235)
            & (pixels[..., 2] > 235)
        )
        ys, _xs = np.where(white)

        assert ys.max() < 330
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fixed_laptop_hook_paragraph_keeps_extra_screen_gap():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    slide = SlidePlan(
        index=3,
        role=SlideRole.TIP3,
        text="3. Vender lo mismo que todos",
        media=_candidate(Path("source.jpg")),
        fixed_asset=True,
    )

    y = renderer._clamp_fixed_screen_caption_y(
        slide,
        start_y=320,
        block_height=80,
        canvas_height=640,
    )

    screen_top = int(640 * 0.525)
    expected_margin = max(1, int(FIXED_SCREEN_TEXT_MARGIN * 640 / 1920))
    assert y + 80 <= screen_top - expected_margin


def test_type_2_english_tip3_title_stays_on_one_line():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
    text = "3. Sell the same as everyone else"

    font, lines = renderer._fit_caption_title_text(
        text,
        draw,
        max_width=820,
        max_height=int(1920 * 0.18),
        base_size=TEXT_CARD_TITLE_FONT_SIZE,
        min_size=TEXT_CARD_TITLE_MIN_FONT_SIZE,
        bold=False,
        stroke_width=0,
    )
    width, _height = renderer._text_size(draw, lines[0], font, stroke_width=0)

    assert lines == [text]
    assert width <= 820


def test_fixed_february_caption_sits_lower_but_above_screen():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    slide = SlidePlan(
        index=5,
        role=SlideRole.FEBRUARY,
        text="febrero - 680€\nElegí un producto usando los datos de Dropradar.",
        media=_candidate(Path("source.jpg")),
        fixed_asset=True,
    )

    assert renderer._caption_preferred_centers(slide)[0] == 0.38

    y = renderer._clamp_fixed_screen_caption_y(
        slide,
        start_y=270,
        block_height=92,
        canvas_height=640,
    )
    screen_top = int(640 * 0.525)
    expected_margin = max(1, int(FEBRUARY_FIXED_SCREEN_TEXT_MARGIN * 640 / 1920))

    assert y + 92 <= screen_top - expected_margin
    assert y > 200


def test_type_4_story_caption_prefers_lower_part_of_reserved_top_area():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    slide = SlidePlan(
        index=1,
        role=SlideRole.STORY_MCDONALD,
        text="Así es como pasé de trabajar en el MacDonald",
        media=_candidate(Path("source.jpg")),
    )

    assert renderer._caption_preferred_centers(slide)[0] == 0.30
    assert TYPE_4_STORY_CAPTION_PRIMARY_CENTER == 0.30


def test_type_4_success_caption_also_uses_reserved_top_area():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    slide = SlidePlan(
        index=6,
        role=SlideRole.STORY_SUCCESS_COMIC,
        text="Despues de mucho trabajo consegui mi objetivo",
        media=_candidate(Path("source.jpg")),
    )

    assert renderer._caption_preferred_centers(slide)[0] == 0.30


def test_lower_story_caption_still_clears_detected_head_region():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    slide = SlidePlan(
        index=2,
        role=SlideRole.STORY_BUILDING_STORE,
        text="Historia generada con IA",
        media=_candidate(Path("source.jpg")),
    )
    head_region = (65, 220, 315, 500)
    block_height = 80

    y = renderer._safe_text_start_y(
        Image.new("RGB", (360, 640), (220, 220, 220)),
        block_width=310,
        block_height=block_height,
        preferred_centers=renderer._caption_preferred_centers(slide),
        expect_person=True,
        avoid_regions=[(head_region, TEXT_HEAD_AVOID_WEIGHT)],
    )

    clearance = max(1, int(round(TEXT_AVOID_CLEARANCE_MARGIN * 640 / 1920)))
    assert y + block_height <= head_region[1] - clearance


def test_story_dropradar_browser_tab_is_projected_inside_detected_screen():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "dropradar-scene.png"
        source = Image.new("RGB", (360, 640), (226, 218, 205))
        draw = ImageDraw.Draw(source)
        draw.polygon(
            ((25, 320), (220, 300), (245, 535), (40, 550)),
            fill=(30, 35, 39),
        )
        expected_screen = np.asarray(
            ((35, 330), (210, 314), (232, 522), (49, 537)),
            dtype=np.float32,
        )
        draw.polygon(tuple(map(tuple, expected_screen.astype(int))), fill=(247, 248, 246))
        draw.rectangle((74, 410, 180, 475), fill=(54, 154, 91))
        source.save(image_path)
        renderer = VideoRenderer(
            replace(
                get_settings(),
                root_dir=root,
                width=360,
                height=640,
                fonts_dir=root / "fonts",
            )
        )
        slide = SlidePlan(
            index=5,
            role=SlideRole.STORY_DROPRADAR,
            text="",
            media=_candidate(image_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_4)

        detected = renderer._story_laptop_screen_quad(source)
        assert detected is not None
        assert np.allclose(detected, expected_screen, atol=5)
        before = np.asarray(source)
        after = np.asarray(still)
        browser_band = after[315:390, 35:220]
        assert int(np.abs(after.astype(int) - before.astype(int)).sum()) > 50_000
        assert np.count_nonzero(
            (browser_band[:, :, 1] > browser_band[:, :, 0] + 20)
        ) >= 10
        assert np.allclose(after[590, 320], before[590, 320], atol=2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_story_dropradar_never_draws_floating_fallback_without_a_screen():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    source = Image.new("RGB", (360, 640), (226, 218, 205))
    slide = SlidePlan(
        index=5,
        role=SlideRole.STORY_DROPRADAR,
        text="",
        media=_candidate(Path("source.jpg")),
    )
    composed = source.convert("RGBA")

    renderer._draw_story_screen_brand(composed, slide)

    assert np.array_equal(np.asarray(composed.convert("RGB")), np.asarray(source))


def test_front_and_profile_faces_are_combined_for_multi_person_images():
    class StaticCascade:
        def __init__(self, boxes):
            self.boxes = np.asarray(boxes, dtype=np.int32)

        def empty(self):
            return False

        def detectMultiScale(self, *args, **kwargs):
            return self.boxes

    class StaticPeopleDetector:
        def __init__(self):
            self.calls = 0

        def detectMultiScale(self, *args, **kwargs):
            self.calls += 1
            return np.empty((0, 4), dtype=np.int32), np.asarray([])

    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    renderer._face_detector = StaticCascade([(24, 110, 58, 58)])
    renderer._profile_face_detector = StaticCascade([(210, 180, 64, 64)])
    renderer._eye_detector = StaticCascade([])
    people_detector = StaticPeopleDetector()
    renderer._people_detector = people_detector

    regions = renderer._text_avoid_regions(
        Image.new("RGBA", (360, 640), (80, 100, 120, 255))
    )

    face_regions = [box for box, weight in regions if weight == TEXT_FACE_AVOID_WEIGHT]

    assert len(face_regions) >= 2
    assert any(box[0] == 0 for box in face_regions)
    assert any(box[0] > 100 for box in face_regions)
    assert people_detector.calls == 1


def test_profile_face_cascade_is_optional_at_renderer_startup(monkeypatch):
    cascade_calls = []

    def fake_build_cascade(filename, *, required=True):
        cascade_calls.append((filename, required))
        return EmptyCascade()

    monkeypatch.setattr("app.render.build_cascade", fake_build_cascade)

    VideoRenderer(replace(get_settings(), width=360, height=640))

    assert (
        "haarcascade_profileface.xml",
        False,
    ) in cascade_calls


def test_text_overlay_layout_is_computed_once_for_repeated_frames(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "source.jpg"
        Image.new("RGB", (360, 640), (30, 40, 50)).save(image_path)
        renderer = VideoRenderer(
            replace(
                get_settings(),
                root_dir=root,
                width=360,
                height=640,
                fonts_dir=root / "fonts",
            )
        )
        calls = 0

        def fixed_layout(*args, **kwargs):
            nonlocal calls
            calls += 1
            return 260

        monkeypatch.setattr(renderer, "_safe_text_start_y", fixed_layout)
        slide = SlidePlan(
            index=1,
            role=SlideRole.HOOK,
            text="Como crear una tienda rentable desde cero",
            media=_candidate(image_path),
        )

        renderer.render_slide_still(slide, VideoType.TYPE_1)
        renderer.render_slide_still(slide, VideoType.TYPE_1)

        assert calls == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_video_overlay_protects_face_across_the_full_zoom_path(monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    source = Image.new("RGB", (800, 640), (30, 40, 50))
    slide = SlidePlan(
        index=1,
        role=SlideRole.HOOK,
        text="Texto centrado y seguro",
        media=_candidate(Path("moving-face.jpg")),
    )
    detected_region = ((400, 100, 500, 220), TEXT_FACE_AVOID_WEIGHT)
    captured_regions = []
    detection_calls = 0

    def detect_once(image):
        nonlocal detection_calls
        detection_calls += 1
        return [detected_region]

    def capture_overlay(image, slide, video_type, *, avoid_regions=None):
        captured_regions.extend(avoid_regions or [])

    monkeypatch.setattr(renderer, "_text_avoid_regions", detect_once)
    monkeypatch.setattr(renderer, "_draw_text", capture_overlay)

    renderer._prepare_slide_text_overlay(slide, source, VideoType.TYPE_1)

    assert detection_calls == 1
    assert len(captured_regions) == 1
    swept_box, weight = captured_regions[0]
    assert weight == TEXT_FACE_AVOID_WEIGHT
    assert swept_box[0] < 100
    assert swept_box[2] == 360


def test_person_fallback_covers_story_scenes_and_missed_portraits():
    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    story = SlidePlan(
        index=1,
        role=SlideRole.STORY_MCDONALD,
        text="Historia",
        media=_candidate(Path("story.png")),
    )
    portrait_media = _candidate(Path("portrait.jpg"))
    portrait_media.metrics = ImageMetrics(
        brightness=130,
        daylight=0.70,
        sharpness=180,
        faces=0,
        aspect_ratio=0.80,
        is_landscape=False,
        outdoor_score=0.2,
        casual_score=0.2,
        luxury_score=0.2,
        quality_score=0.75,
    )
    portrait = SlidePlan(
        index=2,
        role=SlideRole.OCTOBER,
        text="Retrato",
        media=portrait_media,
    )

    assert renderer._slide_expects_person(story)
    assert renderer._slide_expects_person(portrait)
    story_fallback = renderer._fallback_slide_avoid_regions(story, 360, 640)
    assert min(region[1] for region, _weight in story_fallback) > int(640 * 0.25)


def test_repeated_fixed_background_is_decoded_only_once(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "background.jpg"
        Image.new("RGB", (1200, 1200), (30, 40, 50)).save(image_path)
        renderer = VideoRenderer(
            replace(get_settings(), root_dir=root, width=360, height=640)
        )
        original_load = renderer._load_source_image
        loads = 0

        def counting_load(path):
            nonlocal loads
            loads += 1
            return original_load(path)

        monkeypatch.setattr(renderer, "_load_source_image", counting_load)
        monkeypatch.setattr(
            renderer,
            "_composite_type_3_tool_overlay",
            lambda image, slide: None,
        )
        for index, role in enumerate(
            (SlideRole.TOOL_STORE, SlideRole.TOOL_PRODUCT_SEARCH),
            start=2,
        ):
            renderer.render_slide_still(
                SlidePlan(
                    index=index,
                    role=role,
                    text="Herramienta",
                    media=_candidate(image_path),
                    fixed_asset=True,
                ),
                VideoType.TYPE_3,
            )

        assert loads == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_video_render_reuses_fixed_background_for_every_frame(tmp_path, monkeypatch):
    image_path = tmp_path / "background.jpg"
    Image.new("RGB", (900, 900), (30, 40, 50)).save(image_path)
    renderer = VideoRenderer(
        replace(
            get_settings(),
            root_dir=tmp_path,
            width=180,
            height=320,
            fps=2,
            slide_seconds=1.0,
            transition_seconds=0.5,
        )
    )
    original_load = renderer._load_source_image
    loads = 0

    def counting_load(path):
        nonlocal loads
        loads += 1
        return original_load(path)

    class MemoryWriter:
        def __init__(self):
            self.frames = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def append_data(self, frame):
            self.frames.append(frame)

    writer = MemoryWriter()
    monkeypatch.setattr(renderer, "_load_source_image", counting_load)
    monkeypatch.setattr(
        renderer,
        "_composite_type_3_tool_overlay",
        lambda image, slide: None,
    )
    monkeypatch.setattr("app.render.imageio.get_writer", lambda *args, **kwargs: writer)
    monkeypatch.setattr(renderer, "_enforce_size_limit", lambda path: None)
    slides = [
        SlidePlan(
            index=index,
            role=role,
            text="",
            media=_candidate(image_path),
            fixed_asset=True,
        )
        for index, role in enumerate(
            (SlideRole.TOOL_STORE, SlideRole.TOOL_PRODUCT_SEARCH),
            start=1,
        )
    ]
    plan = VideoPlan(
        chosen_account="test",
        video_type=VideoType.TYPE_3,
        language=Language.ES,
        slides=slides,
    )

    renderer.render(plan, tmp_path / "job")

    assert loads == 1
    assert len(writer.frames) == 4


def test_face_detector_keeps_original_small_face_threshold_after_downscale():
    class RecordingCascade:
        def __init__(self):
            self.min_size = None

        def empty(self):
            return False

        def detectMultiScale(self, *args, **kwargs):
            self.min_size = kwargs["minSize"]
            return np.empty((0, 4), dtype=np.int32)

    renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
    detector = RecordingCascade()
    renderer._face_detector = detector

    renderer._detect_render_faces(np.zeros((720, 405), dtype=np.uint8))

    assert detector.min_size == (16, 16)


def test_font_cache_does_not_keep_renderer_instances_alive():
    def cached_renderer_reference():
        renderer = VideoRenderer(replace(get_settings(), width=360, height=640))
        renderer._load_font(size=24, bold=True)
        return weakref.ref(renderer)

    renderer_reference = cached_renderer_reference()
    gc.collect()

    assert renderer_reference() is None


def test_fixed_february_title_card_has_symmetric_minimum_width(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "dark_fixed.jpg"
        Image.new("RGB", (360, 640), (10, 12, 14)).save(image_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])
        slide = SlidePlan(
            index=5,
            role=SlideRole.FEBRUARY,
            text="Febrero\nx",
            media=_candidate(image_path),
            fixed_asset=True,
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_1)
        pixels = np.asarray(still)
        white = (
            (pixels[..., 0] > 235)
            & (pixels[..., 1] > 235)
            & (pixels[..., 2] > 235)
        )
        _ys, xs = np.where(white)
        expected_width = max(1, int(round(FEBRUARY_TITLE_MIN_BOX_WIDTH * 360 / 1080)))

        assert xs.max() - xs.min() + 1 >= expected_width - 2
        assert abs(((xs.min() + xs.max()) / 2) - (still.width / 2)) <= 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fixed_asset_is_fit_without_cropping_sides():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "wide_fixed.jpg"
        canvas = np.full((720, 500, 3), (30, 80, 30), dtype=np.uint8)
        canvas[:, :40, :] = (230, 20, 20)
        canvas[:, -40:, :] = (230, 20, 20)
        Image.fromarray(canvas).save(image_path)
        settings = replace(
            get_settings(),
            root_dir=root,
            width=360,
            height=640,
            fonts_dir=root / "fonts",
        )
        renderer = VideoRenderer(settings)
        slide = SlidePlan(
            index=3,
            role=SlideRole.TIP3,
            text="",
            media=_candidate(image_path),
            fixed_asset=True,
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_2)
        pixels = np.asarray(still)
        middle_rows = pixels[120:520]

        assert middle_rows[:, :12, 0].mean() > 150
        assert middle_rows[:, -12:, 0].mean() > 150
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_safe_text_position_avoids_face_region(monkeypatch):
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (360, 640), (20, 20, 20, 255))
    face_region = (100, 220, 260, 360)
    monkeypatch.setattr(
        renderer,
        "_text_avoid_regions",
        lambda image: [(face_region, 80.0)],
    )

    y = renderer._safe_text_start_y(
        image,
        block_width=260,
        block_height=90,
        preferred_centers=(0.44,),
    )
    text_box = (50, y, 310, y + 90)

    assert renderer._intersection_area(text_box, face_region) == 0


def test_text_avoid_regions_keeps_fallback_when_cv2_detectors_are_unavailable():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    renderer._face_detector = EmptyCascade()
    renderer._profile_face_detector = EmptyCascade()
    renderer._eye_detector = EmptyCascade()
    renderer._people_detector = EmptyPeopleDetector()
    image = Image.new("RGBA", (360, 640), (20, 20, 20, 255))

    regions = renderer._text_avoid_regions(image)
    fallback_regions = [
        region
        for region, weight in regions
        if weight >= TEXT_FALLBACK_HEAD_AVOID_WEIGHT
    ]

    assert fallback_regions

    block_height = 90
    y = renderer._safe_text_start_y(
        image,
        block_width=260,
        block_height=block_height,
        preferred_centers=(0.44,),
    )
    text_box = (50, y, 310, y + block_height)

    assert all(
        renderer._intersection_area(text_box, region) == 0
        for region in fallback_regions
    )


def test_safe_text_position_keeps_clearance_from_face_region(monkeypatch):
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (360, 640), (20, 20, 20, 255))
    face_region = (80, 240, 280, 330)
    monkeypatch.setattr(
        renderer,
        "_text_avoid_regions",
        lambda image: [(face_region, 150.0)],
    )

    block_height = 70
    y = renderer._safe_text_start_y(
        image,
        block_width=260,
        block_height=block_height,
        preferred_centers=(0.58,),
    )
    clearance = max(1, int(round(TEXT_AVOID_CLEARANCE_MARGIN * 640 / 1920)))

    assert y >= face_region[3] + clearance or y + block_height <= face_region[1] - clearance


def test_safe_text_position_centers_inside_clear_gap(monkeypatch):
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (360, 640), (80, 150, 210, 255))
    occupied_region = (20, 285, 340, 640)
    monkeypatch.setattr(
        renderer,
        "_text_avoid_regions",
        lambda image: [(occupied_region, 90.0)],
    )

    y = renderer._safe_text_start_y(
        image,
        block_width=280,
        block_height=80,
        preferred_centers=(0.50,),
    )

    assert y > 105
    assert y + 80 < occupied_region[1]


def test_safe_text_position_respects_top_and_bottom_margins(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (1080, 1920), (20, 20, 20, 255))
    monkeypatch.setattr(renderer, "_text_avoid_regions", lambda image: [])

    y = renderer._safe_text_start_y(
        image,
        block_width=760,
        block_height=300,
        preferred_centers=(0.02, 0.98),
    )

    assert y >= SAFE_TEXT_TOP_MARGIN
    assert y + 300 <= 1920 - SAFE_TEXT_BOTTOM_MARGIN


def test_safe_text_position_avoids_unnecessarily_high_caption(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    image = Image.new("RGBA", (1080, 1920), (20, 20, 20, 255))
    lower_person_region = (250, 980, 830, 1820)
    monkeypatch.setattr(
        renderer,
        "_text_avoid_regions",
        lambda image: [(lower_person_region, 90.0)],
    )

    block_height = 360
    y = renderer._safe_text_start_y(
        image,
        block_width=920,
        block_height=block_height,
        preferred_centers=(0.60, 0.66, 0.54, 0.72, 0.48, 0.40, 0.34),
    )

    assert y > SAFE_TEXT_TOP_MARGIN + 260
    assert y + block_height <= lower_person_region[1] - TEXT_AVOID_CLEARANCE_MARGIN


def test_type_3_spanish_tool_text_keeps_title_single_line_and_tool_on_second_body_line():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))

    title_font = renderer._fit_single_line_text(
        "2. Busqueda de productos",
        draw,
        max_width=1000,
        base_size=TYPE_3_TITLE_FONT_SIZE,
        min_size=TYPE_3_TITLE_FONT_SIZE,
        bold=False,
        stroke_width=4,
    )
    title_width, _ = renderer._text_size(
        draw,
        "2. Busqueda de productos",
        title_font,
        stroke_width=4,
    )

    assert title_width <= 1000
    assert getattr(title_font, "size", TYPE_3_TITLE_FONT_SIZE) == TYPE_3_TITLE_FONT_SIZE
    body_font = renderer._load_font(size=58, bold=False)
    assert renderer._type_3_body_lines(
        "Encuentra productos ganadores - Usa Dropradar",
        "",
        draw=draw,
        font=body_font,
        max_width=920,
    ) == ["Encuentra productos ganadores -", "Usa Dropradar"]


def test_type_3_spanish_descriptions_share_fixed_body_size_without_clipping():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
    font = renderer._load_font(size=58, bold=False)

    descriptions = [
        "Construye tu tienda por 1€ - Usa Shopify",
        "Encuentra productos ganadores - Usa Dropradar",
        "Crea guiones para tus videos - Usa ChatGPT",
        "Gestiona pagos seguros - Usa PayPal",
        "Edita videos con mas calidad - Usa CapCut",
        "Promociona tu producto - Usa TikTok",
    ]

    for description in descriptions:
        lines = renderer._type_3_body_lines(
            description,
            "",
            draw=draw,
            font=font,
            max_width=920,
        )
        assert lines
        assert all(
            renderer._text_size(draw, line, font, stroke_width=4)[0] <= 920
            for line in lines
        )


def test_type_3_icon_fitting_removes_padding_and_uses_common_box():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    icon = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    icon.paste(Image.new("RGBA", (160, 160), (10, 220, 30, 255)), (170, 170))

    fitted = renderer._fit_type_3_icon(icon, 180)
    alpha = np.asarray(fitted)[..., 3]
    ys, xs = np.where(alpha > 0)

    assert fitted.size == (180, 180)
    assert xs.max() - xs.min() >= 176
    assert ys.max() - ys.min() >= 176


def test_type_3_icon_fitting_can_reduce_visual_size_inside_common_box():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    icon = Image.new("RGBA", (500, 500), (0, 0, 0, 255))

    fitted = renderer._fit_type_3_icon(icon, 180, visual_scale=0.94)
    alpha = np.asarray(fitted)[..., 3]
    ys, xs = np.where(alpha > 0)

    assert fitted.size == (180, 180)
    assert 166 <= xs.max() - xs.min() <= 170
    assert 166 <= ys.max() - ys.min() <= 170


def test_type_3_icon_path_follows_selected_tool_text():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        icons_dir = root / "tipo3" / "iconos"
        icons_dir.mkdir(parents=True)
        for name in (
            "paypal.png",
            "stripe-v2-svgrepo-com.png",
            "canva.png",
            "capcut-icon.png",
            "Instagram_icon.png",
            "tiktok.png",
        ):
            Image.new("RGBA", (16, 16), (255, 255, 255, 255)).save(icons_dir / name)
        settings = replace(get_settings(), root_dir=root)
        renderer = VideoRenderer(settings)

        assert renderer._type_3_icon_path(
            SlideRole.TOOL_PAYMENTS,
            "4. Pagos\nGestiona tus pagos\nUsa PayPal",
        ).name == "paypal.png"
        assert renderer._type_3_icon_path(
            SlideRole.TOOL_PAYMENTS,
            "4. Pagos\nGestiona tus pagos\nUsa Stripe",
        ).name == "stripe-v2-svgrepo-com.png"
        assert renderer._type_3_icon_path(
            SlideRole.TOOL_EDITING,
            "5. Edicion\nCrea diseños\nUsa Canva",
        ).name == "canva.png"
        assert renderer._type_3_icon_path(
            SlideRole.TOOL_MARKETING,
            "6. Marketing\nCrea comunidad\nUsa Instagram",
        ).name == "Instagram_icon.png"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_4_template_overlay_draws_fixed_labels_icons_and_text():
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)

    overlay = renderer.build_type_4_template_overlay()
    pixels = np.asarray(overlay)
    alpha = pixels[..., 3]

    label_region = pixels[152:185, 30:105]
    icon_region = alpha[143:190, 120:175]
    title_region = alpha[80:135, 20:340]

    assert overlay.mode == "RGBA"
    assert title_region.max() == 255
    label_opaque = label_region[..., 3] > 180
    assert label_opaque.mean() > 0.70
    assert label_region[..., :3][label_opaque].mean() > 210
    assert icon_region.mean() > 60


def test_type_4_tool_template_uses_bold_title_and_regular_weight_names(
    monkeypatch,
):
    settings = replace(get_settings(), width=360, height=640)
    renderer = VideoRenderer(settings)
    captured_title_weights: list[bool] = []
    original_load_font = renderer._load_font

    def capture_font(*, size: int, bold: bool):
        captured_title_weights.append(bold)
        return original_load_font(size=size, bold=bold)

    monkeypatch.setattr(renderer, "_load_font", capture_font)
    renderer.build_type_4_template_overlay()

    assert captured_title_weights[0] is True
    assert TYPE_4_TITLE_STROKE_WIDTH == 3
    assert TYPE_4_TITLE_INNER_STROKE_WIDTH == 1
    assert TYPE_4_TEXT_STROKE_WIDTH == 4
    assert TYPE_4_TOOL_NAME_INNER_STROKE_WIDTH == 0


def test_type_4_english_payments_label_uses_full_size_in_wider_pill(monkeypatch):
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    captured: dict[str, object] = {}
    original_draw_centered = renderer._draw_centered_lines_in_box

    def capture_label(draw, lines, font, box, **kwargs):
        if lines == ["Payments:"]:
            captured["font_size"] = getattr(font, "size", 0)
            captured["box"] = box
        return original_draw_centered(draw, lines, font, box, **kwargs)

    monkeypatch.setattr(renderer, "_draw_centered_lines_in_box", capture_label)

    renderer.build_type_4_template_overlay(Language.EN)

    assert captured["font_size"] == TYPE_4_LABEL_FONT_SIZE
    box = captured["box"]
    assert isinstance(box, tuple)
    assert box[2] - box[0] == 176 + TYPE_4_EN_PAYMENTS_LABEL_EXTRA_WIDTH


def test_template_video_render_forces_output_without_audio(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    captured = {}
    try:
        source = root / "source.mp4"
        source.write_bytes(b"input")
        settings = replace(
            get_settings(),
            root_dir=root,
            outputs_dir=root / "outputs",
            width=360,
            height=640,
        )
        renderer = VideoRenderer(settings)
        monkeypatch.setattr(
            renderer,
            "_video_duration_seconds",
            lambda input_video: 13.0,
        )
        monkeypatch.setattr(
            "app.render.imageio_ffmpeg.get_ffmpeg_exe",
            lambda: "ffmpeg",
        )

        def fake_run(cmd, check, capture_output, text=False):
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"output")

        monkeypatch.setattr("app.render.subprocess.run", fake_run)

        output_path = renderer.render_template_video(source, root / "job")

        assert output_path.exists()
        assert "-an" in captured["cmd"]
        assert "0:a?" not in captured["cmd"]
        filtergraph = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
        assert "shortest=1" in filtergraph
        assert "trim=start=5.5:duration=7.5" in filtergraph
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _candidate(path: Path) -> MediaCandidate:
    return MediaCandidate(
        source_account="test",
        source_id=path.stem,
        local_path=path,
        permalink="",
        caption="",
        width=360,
        height=640,
        created_at="",
    )
