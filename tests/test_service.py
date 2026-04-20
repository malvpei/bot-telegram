from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoPlan, VideoType
from app.service import VideoCreationService


class FakeRenderer:
    def __init__(self) -> None:
        self.render_called = False
        self.write_script_called = False

    def render(self, plan: VideoPlan, job_dir: Path):
        self.render_called = True
        raise AssertionError("tipo3 should not render a full MP4")

    def write_script(self, plan: VideoPlan, job_dir: Path) -> Path:
        self.write_script_called = True
        job_dir.mkdir(parents=True, exist_ok=True)
        script_path = job_dir / "script.txt"
        script_path.write_text("script", encoding="utf-8")
        return script_path

    def render_slide_still(self, slide: SlidePlan, video_type: VideoType) -> Image.Image:
        return Image.new("RGB", (72, 128), (40, 80, 120))


def test_type_3_outputs_skip_full_video_render():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            width=72,
            height=128,
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()

        source_hook = root / "source_hook.jpg"
        source_tool = root / "source_tool.jpg"
        Image.new("RGB", (72, 128), (120, 120, 120)).save(source_hook)
        Image.new("RGB", (72, 128), (80, 120, 160)).save(source_tool)
        hook_media = MediaCandidate(
            source_account="alpha",
            source_id="alpha:1",
            local_path=source_hook,
            permalink="",
            caption="",
            width=72,
            height=128,
            created_at="",
        )
        tool_media = MediaCandidate(
            source_account="tipo3_fondo",
            source_id="tipo3_fondo:1",
            local_path=source_tool,
            permalink="",
            caption="",
            width=72,
            height=128,
            created_at="",
        )
        plan = VideoPlan(
            chosen_account="alpha",
            video_type=VideoType.TYPE_3,
            language=Language.ES,
            slides=[
                SlidePlan(index=1, role=SlideRole.HOOK, text="Hook", media=hook_media),
                SlidePlan(
                    index=2,
                    role=SlideRole.TOOL_STORE,
                    text="Tool",
                    media=tool_media,
                    fixed_asset=True,
                ),
            ],
            used_media_ids=[hook_media.source_id],
        )

        video_path, script_path = service._render_outputs(plan, root / "outputs" / "job")

        assert video_path is None
        assert script_path.exists()
        assert service.renderer.write_script_called is True
        assert service.renderer.render_called is False
        assert plan.slides[0].media.local_path.name == "slide_01.jpg"
        assert plan.slides[1].media.local_path.name == "slide_02.jpg"
        assert plan.slides[0].media.local_path.exists()
        assert plan.slides[1].media.local_path.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)
