from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoType
from app.render import (
    FEBRUARY_FIXED_SCREEN_TEXT_MARGIN,
    FIXED_SCREEN_TEXT_MARGIN,
    HOOK_BASE_FONT_SIZE,
    HOOK_MIN_FONT_SIZE,
    HOOK_SIDE_MARGIN,
    HOOK_TEXT_STROKE_FILL,
    VideoRenderer,
)


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


def test_type_3_tool_slide_uses_icon_asset():
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
        white_card_pixels = (
            (text_region[..., 0] > 230)
            & (text_region[..., 1] > 230)
            & (text_region[..., 2] > 230)
        )

        assert icon_region[..., 0].mean() > 70
        assert icon_region[..., 1].mean() > 60
        assert icon_region[..., 2].mean() > 150
        assert white_card_pixels.mean() > 0.08
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_3_hook_still_renders_hook_text():
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
        assert np.asarray(still).max() > 200
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

        assert still.height / 3 <= center_y <= still.height * 2 / 3
    finally:
        shutil.rmtree(root, ignore_errors=True)


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

    assert captured["stroke_width"] == 3
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

    assert captured["max_width"] == 1080 - HOOK_SIDE_MARGIN
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
        connected_rows = row_counts[rows.min() : rows.max() + 1]
        assert connected_rows.min() > 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_1_title_is_only_slightly_larger_than_body():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))

    title_font, _title_lines = renderer._fit_text(
        "1. Valida con poco presupuesto",
        draw,
        max_width=800,
        max_height=300,
        base_size=39,
        min_size=30,
        bold=False,
        stroke_width=0,
    )
    body_font, _body_lines = renderer._fit_text(
        "No trates la publicidad como una apuesta.",
        draw,
        max_width=800,
        max_height=300,
        base_size=37,
        min_size=28,
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

    assert renderer._caption_preferred_centers(slide)[0] == 0.34

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


def test_type_3_spanish_tool_text_keeps_title_single_line_and_tool_on_second_body_line():
    settings = replace(get_settings(), width=1080, height=1920)
    renderer = VideoRenderer(settings)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))

    title_font = renderer._fit_single_line_text(
        "2. Busqueda de productos",
        draw,
        max_width=1000,
        base_size=72,
        min_size=46,
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
