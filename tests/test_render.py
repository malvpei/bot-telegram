from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoType
from app.render import VideoRenderer


def test_type_3_tool_slide_uses_icon_asset():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"render-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        icons_dir = root / "tipo3" / "iconos"
        icons_dir.mkdir(parents=True)
        Image.new("RGBA", (512, 512), (220, 20, 20, 255)).save(icons_dir / "paypal.png")
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
            text="4. Payments\nManage payments securely\nUse PayPal",
            media=_candidate(bg_path),
            fixed_asset=True,
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_3)
        pixels = np.asarray(still)
        icon_region = pixels[290:430, 120:240]

        assert icon_region[..., 0].mean() > 150
        assert icon_region[..., 1].mean() < 80
        assert icon_region[..., 2].mean() < 80
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_3_hook_still_does_not_render_hook_text():
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
            text="This should be sent by Telegram",
            media=_candidate(bg_path),
        )

        still = renderer.render_slide_still(slide, VideoType.TYPE_3)
        assert np.asarray(still).max() == 0
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
