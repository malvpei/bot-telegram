from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoPlan, VideoRequest, VideoType
from app.service import VideoCreationService
from app.state import StateStore


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


class FakeCollector:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def collect_one(self, username: str) -> list[str]:
        self.seen.append(username)
        return [username]


class PlanWhenGoodSelector:
    def create_plan(self, catalog, video_type, language):
        if "good" not in catalog:
            raise ValueError("no viable account yet")
        return VideoPlan(
            chosen_account="good",
            video_type=video_type,
            language=language,
            slides=[],
            used_media_ids=["good:1"],
        )


class ExtraImageSelector:
    def pick_extra_image(self, candidates, video_type):
        return candidates[0]

    def reservation_keys_for(self, media_items):
        return [media.source_id for media in media_items]


class ExtraImageCollector:
    def __init__(self, media: MediaCandidate) -> None:
        self.media = media
        self.seen: list[str] = []

    def collect_one(self, username: str) -> list[MediaCandidate]:
        self.seen.append(username)
        return [self.media]


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


def test_create_extra_image_returns_one_normalized_photo():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"extra-{uuid4().hex}"
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
        source_path = root / "source.jpg"
        Image.new("RGB", (200, 100), (120, 80, 40)).save(source_path)
        media = MediaCandidate(
            source_account="alpha",
            source_id="alpha:extra:1",
            local_path=source_path,
            permalink="",
            caption="",
            width=200,
            height=100,
            created_at="",
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.state = StateStore(root / "state")
        service.collector = ExtraImageCollector(media)
        service.selector = ExtraImageSelector()
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            account_inputs=["alpha"],
        )

        result = service._create_extra_image_locked(request)

        assert result.local_path.name == "extra_01.jpg"
        assert result.local_path.exists()
        assert result.width == 72
        assert result.height == 128
        assert service.collector.seen == ["alpha"]
        assert service.state.any_media_used(["alpha:extra:1"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_keeps_searching_beyond_first_failed_accounts(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), account_pick_attempts=0)
        service.state = StateStore(root / "state")
        service.collector = FakeCollector()
        service.selector = PlanWhenGoodSelector()
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            account_inputs=[],
        )

        plan, tried = service._pick_account_with_plan(
            ["bad1", "bad2", "bad3", "good"],
            request,
        )

        assert plan.chosen_account == "good"
        assert tried == ["bad1", "bad2", "bad3", "good"]
        assert service.collector.seen == tried
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_prioritizes_accounts_not_recently_used(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), account_pick_attempts=0)
        service.state = StateStore(root / "state")
        service.state.log_job(
            service.state.build_job_record(
                job_id="job-old",
                chosen_account="old",
                requested_accounts=["old"],
                fallback_accounts=[],
                video_type=VideoType.TYPE_1,
                language=Language.ES,
                video_path=None,
                script_path="script.txt",
            )
        )

        ordered = service._ordered_accounts_for_pick(
            ["old", "fresh"],
            VideoType.TYPE_1,
        )

        assert ordered == ["fresh", "old"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_uses_oldest_recent_account_before_newest(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), account_pick_attempts=0)
        service.state = StateStore(root / "state")
        service.state.log_job(
            service.state.build_job_record(
                job_id="job-oldest",
                chosen_account="oldest",
                requested_accounts=["oldest"],
                fallback_accounts=[],
                video_type=VideoType.TYPE_1,
                language=Language.ES,
                video_path=None,
                script_path="script.txt",
            )
        )
        service.state.log_job(
            service.state.build_job_record(
                job_id="job-newest",
                chosen_account="newest",
                requested_accounts=["newest"],
                fallback_accounts=[],
                video_type=VideoType.TYPE_1,
                language=Language.ES,
                video_path=None,
                script_path="script.txt",
            )
        )

        ordered = service._ordered_accounts_for_pick(
            ["newest", "oldest"],
            VideoType.TYPE_1,
        )

        assert ordered == ["oldest", "newest"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
