from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

import app.render as render_module
from app.car_tools import CAR_TOOLS_SLIDE_TEXTS
from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, TYPE_3_ROLES
from app.render import VideoRenderer
from app.texts import ScriptGenerator


@pytest.fixture(params=(Language.ES, Language.EN), ids=("es", "en"))
def type_3_texts(request, monkeypatch):
    # Read the actual tool copy without creating or consuming a state queue.
    generator = ScriptGenerator.__new__(ScriptGenerator)
    monkeypatch.setattr(
        generator, "_compose_type_3", lambda language, hooks, tools: tools
    )
    monkeypatch.setattr("app.texts.random.choice", lambda choices: choices[0])
    builder = (
        generator._build_type_3_es
        if request.param == Language.ES
        else generator._build_type_3_en
    )
    return builder()


@pytest.fixture(params=((1080, 1920), (360, 640)), ids=("1080px", "360px"))
def renderer(request):
    width, height = request.param
    return VideoRenderer(replace(get_settings(), width=width, height=height))


def _slide(role: SlideRole, text: str) -> SlidePlan:
    return SlidePlan(
        index=2,
        role=role,
        text=text,
        media=MediaCandidate(
            source_account="fixed",
            source_id="type3-typography",
            local_path=Path("unused-type3-typography.png"),
            permalink="",
            caption="",
            width=1080,
            height=1920,
            created_at="",
        ),
        fixed_asset=True,
    )


def _render_and_capture(renderer, slide, monkeypatch):
    blocks = []
    icons = []
    original_draw_lines = renderer._draw_lines

    def record_lines(draw, lines, font, **kwargs):
        blocks.append((list(lines), font, dict(kwargs)))
        return original_draw_lines(draw, lines, font, **kwargs)

    def record_icon(image, role, text, width, top, size):
        icons.append((role, text, width, top, size))

    size = (renderer.settings.width, renderer.settings.height)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    with monkeypatch.context() as patch:
        patch.setattr(renderer, "_draw_lines", record_lines)
        patch.setattr(renderer, "_draw_type_3_icon", record_icon)
        renderer._draw_type_3_tool_slide(image, slide)
    return image, blocks, icons


def _ink_bounds(renderer, block):
    lines, font, kwargs = block
    layer = Image.new(
        "RGBA", (renderer.settings.width, renderer.settings.height), (0, 0, 0, 0)
    )
    renderer._draw_lines(ImageDraw.Draw(layer), lines, font, **kwargs)
    return layer.getbbox()


@pytest.mark.parametrize("role", TYPE_3_ROLES[1:], ids=lambda role: role.value)
def test_type_3_matches_parkez_tools_lettering_and_preserves_its_layout(
    renderer, type_3_texts, role, monkeypatch
):
    def reject_erosion(*args, **kwargs):
        pytest.fail("Tool lettering must use the font's full white fill")

    # These renders draw only text, so image/background processing is excluded.
    monkeypatch.setattr(ImageFilter, "MinFilter", reject_erosion)
    slide = _slide(role, type_3_texts[role])
    image, blocks, icons = _render_and_capture(renderer, slide, monkeypatch)
    _, reference_blocks, _ = _render_and_capture(
        renderer,
        _slide(
            SlideRole.CAR_TOOL_PARKEZ,
            CAR_TOOLS_SLIDE_TEXTS[SlideRole.CAR_TOOL_PARKEZ],
        ),
        monkeypatch,
    )

    assert len(blocks) == len(reference_blocks) == 2
    width, height = image.size
    scale_x = lambda value: max(1, int(round(value * width / 1080)))
    scale_y = lambda value: max(1, int(round(value * height / 1920)))
    assert render_module.CAR_TOOLS_TEXT_BOLD is False
    assert render_module.TYPE_3_TITLE_FONT_SIZE == (
        render_module.CAR_TOOLS_TITLE_FONT_SIZE
    ) == 74
    assert render_module.TYPE_3_BODY_FONT_SIZE == 58
    for block, reference, size in zip(
        blocks, reference_blocks, (scale_x(74), scale_x(58)), strict=True
    ):
        lines, font, kwargs = block
        assert font is reference[1] is renderer._load_font(size=size, bold=False)
        assert font.size == size
        for key, expected in {
            "fill": (255, 255, 255),
            "stroke_width": max(2, scale_x(4)),
            "stroke_fill": (12, 12, 12),
            "inner_stroke_width": max(1, scale_x(1)),
        }.items():
            assert kwargs[key] == reference[2][key] == expected
        assert kwargs["width"] == width
        assert "fill_reduction" not in kwargs
        draw = ImageDraw.Draw(image)
        assert all(
            renderer._text_size(
                draw, line, font, stroke_width=kwargs["stroke_width"]
            )[0]
            <= width - 2 * scale_x(render_module.TEXT_CARD_EDGE_MARGIN)
            for line in lines
        )

    title_lines, title_font, title_kwargs = blocks[0]
    body_lines, _, body_kwargs = blocks[1]
    title, description = slide.text.split("\n", 1)
    assert title_lines == [title]
    assert " ".join(body_lines) == description
    title_height = renderer._block_height(
        title_lines,
        title_font,
        ImageDraw.Draw(image),
        stroke_width=max(2, scale_x(4)),
        line_gap=0,
    )
    nudge = int(height * 0.015)
    assert title_kwargs["start_y"] == int(height * 0.270) - title_height // 2 + nudge
    assert title_kwargs["line_gap"] == 0
    assert body_kwargs["start_y"] == int(height * 0.32) + nudge
    assert body_kwargs["line_gap"] == scale_y(8)

    tool_key = renderer._type_3_tool_key(role, slide.text)
    icon_top = int(
        height * render_module.TYPE_3_ICON_TOP_RATIO.get(tool_key, 0.434)
    ) + nudge
    icon_size = int(width * 0.44)
    assert icons == [(role, slide.text, width, icon_top, icon_size)]
    assert icon_top + icon_size <= height
    title_bounds, body_bounds = [_ink_bounds(renderer, block) for block in blocks]
    assert title_bounds is not None
    assert body_bounds is not None
    assert title_bounds[3] < body_bounds[1]
    assert body_bounds[3] < icon_top
    for left, top, right, bottom in (title_bounds, body_bounds):
        assert 0 < left < right < width
        assert 0 < top < bottom < height


def test_type_3_and_tools_shared_font_loader_always_uses_regular_weight(renderer):
    for size in (74, 58):
        expected = renderer._load_font(size=size, bold=False)
        assert renderer._load_type_3_tool_font(size, False) is expected
        assert renderer._load_type_3_tool_font(size, True) is expected
