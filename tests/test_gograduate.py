from dataclasses import replace
from threading import Lock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.advice_cards import AdviceBackground
from app.config import get_settings
from app.gograduate import (
    GOGRADUATE_BACKGROUNDS,
    GOGRADUATE_DESIGN_IDS,
    GOGRADUATE_PACK_IDS,
    GOGRADUATE_PACKS,
    GOGRADUATE_PROMO,
    gograduate_social_copy,
    gograduate_tips,
)
from app.models import Language, VideoRequest, VideoType
from app.render import VideoRenderer
from app.service import VideoCreationService
from app.state import StateStore


@pytest.mark.parametrize("pack_id", GOGRADUATE_PACK_IDS)
@pytest.mark.parametrize("background", GOGRADUATE_BACKGROUNDS)
def test_student_designs_fit_and_use_gograduate_icon(pack_id, background, monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    blocks = []
    draw_lines = renderer._draw_left_aligned_lines

    def record_lines(draw, lines, font, **kwargs):
        blocks.append((lines, font, kwargs))
        draw_lines(draw, lines, font, **kwargs)

    monkeypatch.setattr(renderer, "_draw_left_aligned_lines", record_lines)
    tips = gograduate_tips(pack_id, background)
    result = renderer.render_gograduate_card(tips, Language.ES, background)
    draw = ImageDraw.Draw(result)
    illustrated = background == AdviceBackground.ILLUSTRATED
    count = 4 if illustrated else 5
    assert result.size == (1080, 1920)
    assert result.getpixel((0, 0)) == ((247, 247, 245) if illustrated else (229, 229, 229))
    assert len(tips) == count
    assert len(blocks) == count * 2
    if illustrated:
        assert tips == GOGRADUATE_PACKS[pack_id][:3] + (GOGRADUATE_PROMO,)
        assert len({font.size for _, font, _ in blocks[::2]}) == 1
        assert len({font.size for _, font, _ in blocks[1::2]}) == 1
    else:
        assert tips == GOGRADUATE_PACKS[pack_id]
    for index, tip in enumerate(tips):
        top = (260 + index * (338 + 36)) if illustrated else (280 + index * (262 + 12))
        bottom = top + (338 if illustrated else 262)
        if illustrated:
            assert result.getpixel((80, top + 132)) == (255, 255, 255)
        for lines, font, kwargs in blocks[index * 2:index * 2 + 2]:
            assert kwargs["x"] == (385 if illustrated else 412)
            assert kwargs["start_y"] >= top + (24 if illustrated else 12)
            block_height = renderer._block_height(
                lines, font, draw, stroke_width=0, line_gap=kwargs["line_gap"],
            )
            assert kwargs["start_y"] + block_height <= bottom - (24 if illustrated else 12)
            assert all(
                draw.textlength(line, font=font) <= (585 if illustrated else 596)
                for line in lines
            )
        assert " ".join(blocks[index * 2 + 1][0]) == tip.body

    # The final card contains the black/gold official cap, not Dropradar's lime box.
    pixels = np.asarray(result).astype(int)
    icon = pixels[1488:1620, 218:350] if illustrated else pixels[1432:1582, 212:362]
    gold = (icon[..., 0] > 170) & (icon[..., 1] > 100) & (icon[..., 2] < 100)
    dark = icon.max(axis=2) < 90
    assert gold.sum() > 200
    assert dark.sum() > 1000
    assert tips[-1] == GOGRADUATE_PROMO
    social = gograduate_social_copy(pack_id, background)
    assert social.hook.startswith(f"{count} trucos")
    assert "GoGraduate" in social.description
    if illustrated:
        assert "cinco" not in social.description.lower()
        assert "quinto" not in social.description.lower()


def _service(tmp_path):
    settings = replace(
        get_settings(), outputs_dir=tmp_path / "outputs", state_dir=tmp_path / "state",
        width=1080, height=1920,
    )
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = settings
    service.state = StateStore(settings.state_dir)
    service.renderer = VideoRenderer(settings)
    service._job_lock = Lock()
    return service


def test_gograduate_creates_png_and_rotates_independently_without_instagram_or_r2(tmp_path):
    service = _service(tmp_path)
    request = VideoRequest(
        chat_id=1, user_id=10, video_type=VideoType.GOGRADUATE_TYPE_1,
        language=Language.ES, account_inputs=[],
    )
    service.state.advance_type_4_advice_phase(cycle_length=12)
    chosen = []
    for index, _ in enumerate(GOGRADUATE_PACK_IDS):
        pack_id, _ = service.state.peek_next_gograduate_type_1_pack_id(GOGRADUATE_PACK_IDS)
        background = GOGRADUATE_BACKGROUNDS[index % 2]
        result = service.create_video(request)
        chosen.append(result.chosen_account)
        assert result.video_type == VideoType.GOGRADUATE_TYPE_1
        assert result.language == Language.ES
        assert result.video_path is None
        assert len(result.slides) == 1
        assert result.separate_slide_text is False
        assert GOGRADUATE_PROMO.body in result.preview_text
        assert result.preview_text == result.slides[0].text
        assert result.preview_text in result.script_path.read_text(encoding="utf-8")
        assert "GoGraduate" in result.social_copy.description
        assert f":{background.value}:" in result.chosen_account
        assert result.social_copy.hook.startswith(
            "4 trucos" if background == AdviceBackground.ILLUSTRATED else "5 trucos"
        )
        if background == AdviceBackground.ILLUSTRATED:
            assert GOGRADUATE_PACKS[pack_id][3].body not in result.preview_text
            assert "5. " not in result.preview_text
        else:
            assert GOGRADUATE_PACKS[pack_id][3].body in result.preview_text
            assert "5. " in result.preview_text
        with Image.open(result.slides[0].media.local_path) as image:
            assert image.format == "PNG"
            assert image.size == (1080, 1920)
        # Queue position survives a new state-store instance.
        service.state = StateStore(service.settings.state_dir)
        next_design, _ = service.state.peek_next_gograduate_type_1_design_id(GOGRADUATE_DESIGN_IDS)
        assert next_design == GOGRADUATE_BACKGROUNDS[(index + 1) % 2].value
    assert len(set(chosen)) == len(GOGRADUATE_PACK_IDS)
    assert service.state.get_type_4_advice_phase(cycle_length=12) == 1
    assert service.state.read_used_media() == {}


def test_failed_gograduate_render_does_not_advance_its_queue(tmp_path, monkeypatch):
    service = _service(tmp_path)
    before = service.state.peek_next_gograduate_type_1_pack_id(GOGRADUATE_PACK_IDS)[0]
    before_design = service.state.peek_next_gograduate_type_1_design_id(GOGRADUATE_DESIGN_IDS)[0]

    def fail(*args, **kwargs):
        raise OSError("render failed")

    monkeypatch.setattr(service.renderer, "render_gograduate_card", fail)
    with pytest.raises(OSError, match="render failed"):
        service.create_video(VideoRequest(
            chat_id=1, user_id=10, video_type=VideoType.GOGRADUATE_TYPE_1,
            language=Language.ES, account_inputs=[],
        ))
    assert service.state.peek_next_gograduate_type_1_pack_id(GOGRADUATE_PACK_IDS)[0] == before
    assert service.state.peek_next_gograduate_type_1_design_id(GOGRADUATE_DESIGN_IDS)[0] == before_design


@pytest.mark.parametrize("background", GOGRADUATE_BACKGROUNDS)
def test_gograduate_requires_its_own_logo_instead_of_using_dropradar(tmp_path, background):
    renderer = VideoRenderer(replace(get_settings(), root_dir=tmp_path))
    with pytest.raises(FileNotFoundError, match="icono de GoGraduate"):
        renderer.render_gograduate_card(
            gograduate_tips(GOGRADUATE_PACK_IDS[0], background), Language.ES, background,
        )
