from dataclasses import replace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.advice_cards import AdviceBackground, advice_selection
from app.config import get_settings
from app.models import Language
from app.render import (
    ADVICE_DROPRADAR_GREEN,
    ADVICE_DROPRADAR_GREEN_ON_DARK,
    VideoRenderer,
)


@pytest.mark.parametrize("phase", range(5))
@pytest.mark.parametrize("language", list(Language))
def test_dropradar_text_is_green_in_every_advice_design_and_language(phase, language):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    background, tips, _ = advice_selection(phase, language)
    result = renderer.render_advice_card(tips, language, background)
    pixels = np.asarray(result)
    brand_color = (
        ADVICE_DROPRADAR_GREEN_ON_DARK
        if background in {AdviceBackground.BLACK, AdviceBackground.BROWN}
        else ADVICE_DROPRADAR_GREEN
    )

    assert (pixels == brand_color).all(axis=2).sum() > 20


def test_advice_only_colors_the_brand_word_and_keeps_surrounding_text_gray():
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    font = renderer._load_advice_font(size=32, weight=400)
    image = Image.new("RGB", (800, 100), "white")
    draw = ImageDraw.Draw(image)
    text = "Usa Dropradar, antes de elegir el producto."
    renderer._draw_advice_text(draw, (10, 10), text, font=font, fill=(83, 83, 92))
    pixels = np.asarray(image)
    brand_pixels = (pixels == ADVICE_DROPRADAR_GREEN).all(axis=2)
    brand_x = np.where(brand_pixels)[1]
    start = 10 + draw.textlength("Usa ", font=font)
    end = 10 + draw.textlength("Usa Dropradar", font=font)

    assert brand_x.size > 100
    assert brand_x.min() >= int(start) - 1
    assert brand_x.max() <= int(end) + 1
    assert (pixels[:, :int(start) - 1] == (83, 83, 92)).all(axis=2).any()
    assert (pixels[:, int(end) + 2:] == (83, 83, 92)).all(axis=2).any()


def test_illustrated_fourth_advice_uses_the_dropradar_app_icon():
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    background, tips, _ = advice_selection(2, Language.ES)
    image = renderer.render_advice_card(tips, Language.ES, background)
    pixels = np.asarray(image).astype(int)
    # Same card and icon position as the user's four-card reference.
    icon_region = pixels[1488:1620, 218:350]
    vivid_green = (
        (icon_region[..., 1] > 180)
        & (icon_region[..., 1] - icon_region[..., 0] > 40)
        & (icon_region[..., 0] - icon_region[..., 2] > 40)
    )
    assert background == AdviceBackground.ILLUSTRATED
    assert "Dropradar" in tips[3].body
    assert vivid_green.mean() > 0.25
    # The first three illustrations keep their original colors and symbols.
    for center_y in (429, 803, 1177):
        region = pixels[center_y - 62:center_y + 62, 223:347]
        lime = (
            (region[..., 1] > 180)
            & (region[..., 1] - region[..., 0] > 40)
            & (region[..., 0] - region[..., 2] > 40)
        )
        assert lime.mean() < 0.01


@pytest.mark.parametrize("language", list(Language))
def test_editorial_fifth_advice_uses_dropradar_icon_and_keeps_first_four(language, monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    background, tips, _ = advice_selection(3, language)
    generic_icons = []
    draw_icon = renderer._draw_editorial_advice_icon

    def record_icon(image, center, size, index):
        generic_icons.append(index)
        draw_icon(image, center, size, index)

    monkeypatch.setattr(renderer, "_draw_editorial_advice_icon", record_icon)
    image = renderer.render_advice_card(tips, language, background)
    icon = np.asarray(image).astype(int)[1432:1582, 212:362]
    vivid_green = (
        (icon[..., 1] > 180)
        & (icon[..., 1] - icon[..., 0] > 40)
        & (icon[..., 0] - icon[..., 2] > 40)
    )
    assert background == AdviceBackground.EDITORIAL
    assert "Dropradar" in tips[4].body
    assert generic_icons == [1, 2, 3, 4]
    assert vivid_green.mean() > 0.25
