from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from threading import Lock
from uuid import uuid4

from PIL import Image

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoPlan, VideoRequest, VideoType
from app.r2_storage import R2Object
from app.service import VideoCreationService
from app.state import StateStore


class FakeRenderer:
    def __init__(self) -> None:
        self.render_called = False
        self.write_script_called = False
        self.template_input_video: Path | None = None
        self.template_language = None
        self.render_slide_still_calls: list[VideoType] = []
        self.render_slide_still_sources: list[Path] = []

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
        self.render_slide_still_calls.append(video_type)
        self.render_slide_still_sources.append(slide.media.local_path)
        return Image.new("RGB", (72, 128), (40, 80, 120))

    def render_template_video(self, input_video: Path, job_dir: Path, language=None) -> Path:
        self.template_input_video = input_video
        self.template_language = language
        job_dir.mkdir(parents=True, exist_ok=True)
        output_path = job_dir / "template_video.mp4"
        output_path.write_bytes(b"video")
        return output_path


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
    def pick_extra_image(
        self,
        candidates,
        video_type,
        *,
        allow_plan_compatible_fallback=False,
    ):
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


class ExtraImageCollectorNoCache(ExtraImageCollector):
    def collect_one(
        self,
        username: str,
        use_cache: bool = True,
    ) -> list[MediaCandidate]:
        self.seen.append(f"{username}:{use_cache}")
        return [self.media]


class EmptyExtraPool:
    def pick_extra_image(self, account: str, video_type: VideoType):
        raise ValueError("No quedan fotos disponibles")


class EmptyPlanPool:
    def __init__(self) -> None:
        self.noted: list[tuple[str, VideoType]] = []

    def select_plan(self, usernames, video_type, language, *, skip_accounts=None):
        raise ValueError("pool empty")

    def note_account_used(self, account: str, video_type: VideoType) -> None:
        self.noted.append((account, video_type))


class FakeR2Storage:
    is_configured = True

    def __init__(self) -> None:
        self.listed_prefix: str | None = None
        self.downloaded_key: str | None = None

    def list_videos(self, prefix: str):
        self.listed_prefix = prefix
        return [R2Object(key="videos/source.mp4", size=123)]

    def download(self, key: str, destination: Path) -> Path:
        self.downloaded_key = key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"r2-video")
        return destination


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
        assert service.renderer.render_slide_still_calls == [
            VideoType.TYPE_3,
            VideoType.TYPE_3,
        ]
        assert plan.slides[0].media.local_path.name == "slide_01.jpg"
        assert plan.slides[1].media.local_path.name == "slide_02.jpg"
        assert plan.slides[0].media.local_path.exists()
        assert plan.slides[1].media.local_path.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_slide_normalization_does_not_mutate_shared_media_candidate():
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
        renderer = FakeRenderer()
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = renderer

        source_path = root / "fixed_tip.jpg"
        Image.new("RGB", (72, 128), (120, 120, 120)).save(source_path)
        shared_media = MediaCandidate(
            source_account="fixed",
            source_id="fixed:tip3",
            local_path=source_path,
            permalink="",
            caption="",
            width=72,
            height=128,
            created_at="",
        )

        first_plan = VideoPlan(
            chosen_account="fixed",
            video_type=VideoType.TYPE_2,
            language=Language.EN,
            slides=[
                SlidePlan(
                    index=1,
                    role=SlideRole.TOOL_STORE,
                    text="First",
                    media=shared_media,
                    fixed_asset=True,
                )
            ],
            used_media_ids=[],
        )
        second_plan = VideoPlan(
            chosen_account="fixed",
            video_type=VideoType.TYPE_2,
            language=Language.EN,
            slides=[
                SlidePlan(
                    index=1,
                    role=SlideRole.TOOL_STORE,
                    text="Second",
                    media=shared_media,
                    fixed_asset=True,
                )
            ],
            used_media_ids=[],
        )

        service._render_outputs(first_plan, root / "outputs" / "job-a")
        service._render_outputs(second_plan, root / "outputs" / "job-b")

        assert renderer.render_slide_still_sources == [source_path, source_path]
        assert shared_media.local_path == source_path
        assert first_plan.slides[0].media.local_path.name == "slide_01.jpg"
        assert second_plan.slides[0].media.local_path.name == "slide_01.jpg"
        assert first_plan.slides[0].media.local_path.parent.name == "slides"
        assert second_plan.slides[0].media.local_path.parent.name == "slides"
        assert first_plan.slides[0].media.local_path != second_plan.slides[0].media.local_path
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_1_outputs_skip_full_video_render():
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

        source_path = root / "source.jpg"
        Image.new("RGB", (72, 128), (120, 120, 120)).save(source_path)
        media = MediaCandidate(
            source_account="alpha",
            source_id="alpha:1",
            local_path=source_path,
            permalink="",
            caption="",
            width=72,
            height=128,
            created_at="",
        )
        plan = VideoPlan(
            chosen_account="alpha",
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            slides=[SlidePlan(index=1, role=SlideRole.HOOK, text="Hook", media=media)],
            used_media_ids=[media.source_id],
        )

        video_path, script_path = service._render_outputs(plan, root / "outputs" / "job")

        assert video_path is None
        assert script_path.exists()
        assert service.renderer.render_called is False
        assert service.renderer.write_script_called is True
        assert service.renderer.render_slide_still_calls == [VideoType.TYPE_1]
        assert plan.slides[0].media.local_path.name == "slide_01.jpg"
        assert plan.slides[0].media.local_path.exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_create_template_video_picks_video_from_configured_folder():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        source_dir = root / "template_videos"
        source_dir.mkdir()
        chosen = source_dir / "source.mp4"
        chosen.write_bytes(b"fake")
        (source_dir / "notes.txt").write_text("ignored", encoding="utf-8")
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            template_videos_dir=source_dir,
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()
        service.state = StateStore(root / "state")
        service._job_lock = Lock()

        result = service.create_template_video()

        assert result.video_path.exists()
        assert result.social_copy.hashtag_line.startswith("#")
        assert service.renderer.template_input_video == chosen
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_create_template_video_can_render_english_version(monkeypatch):
    monkeypatch.setattr("app.service.random.choice", lambda values: values[0])
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        source_dir = root / "template_videos"
        source_dir.mkdir()
        (source_dir / "source.mp4").write_bytes(b"fake")
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            template_videos_dir=source_dir,
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()
        service.state = StateStore(root / "state")
        service._job_lock = Lock()

        result = service.create_template_video(language=Language.EN)

        assert result.video_path.exists()
        assert service.renderer.template_language == Language.EN
        assert result.social_copy.title == (
            "Tools to start dropshipping without overcomplicating it"
        )
        assert result.social_copy.description.startswith("If you want to launch")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_create_template_video_downloads_from_r2_when_configured(monkeypatch):
    monkeypatch.setattr("app.service.random.choice", lambda values: values[0])
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            r2_input_prefix="fallback-prefix",
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()
        service.r2_storage = FakeR2Storage()
        service.state = StateStore(root / "state")
        service._job_lock = Lock()

        result = service.create_template_video("campaign-a")

        assert result.video_path.exists()
        assert result.social_copy.hashtag_line.startswith("#")
        assert service.r2_storage.listed_prefix == "campaign-a"
        assert service.r2_storage.downloaded_key == "videos/source.mp4"
        assert service.renderer.template_input_video is not None
        assert service.renderer.template_input_video.read_bytes() == b"r2-video"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_template_video_queue_cycles_and_reports_restart():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        source_dir = root / "template_videos"
        source_dir.mkdir()
        first = source_dir / "a.mp4"
        second = source_dir / "b.mp4"
        first.write_bytes(b"a")
        second.write_bytes(b"b")
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            template_videos_dir=source_dir,
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()
        service.state = StateStore(root / "state")
        service._job_lock = Lock()

        result_a = service.create_template_video()
        picked_a = service.renderer.template_input_video
        result_b = service.create_template_video()
        picked_b = service.renderer.template_input_video
        result_restart = service.create_template_video()
        picked_restart = service.renderer.template_input_video

        assert picked_a == first
        assert result_a.queue_restarted is False
        assert picked_b == second
        assert result_b.queue_restarted is False
        assert picked_restart == first
        assert result_restart.queue_restarted is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_template_video_queue_appends_new_videos_to_end():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        source_dir = root / "template_videos"
        source_dir.mkdir()
        first = source_dir / "a.mp4"
        second = source_dir / "b.mp4"
        third = source_dir / "c.mp4"
        first.write_bytes(b"a")
        second.write_bytes(b"b")
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            template_videos_dir=source_dir,
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()
        service.state = StateStore(root / "state")
        service._job_lock = Lock()

        service.create_template_video()
        third.write_bytes(b"c")
        service.create_template_video()
        picked_second = service.renderer.template_input_video
        service.create_template_video()
        picked_third = service.renderer.template_input_video
        result_restart = service.create_template_video()
        picked_restart = service.renderer.template_input_video

        assert picked_second == second
        assert picked_third == third
        assert picked_restart == first
        assert result_restart.queue_restarted is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_service_rejects_plan_that_mixes_source_accounts():
    service = VideoCreationService.__new__(VideoCreationService)
    first = MediaCandidate(
        source_account="alpha",
        source_id="alpha:1",
        local_path=Path("alpha.jpg"),
        permalink="",
        caption="",
        width=1,
        height=1,
        created_at="",
    )
    second = MediaCandidate(
        source_account="beta",
        source_id="beta:1",
        local_path=Path("beta.jpg"),
        permalink="",
        caption="",
        width=1,
        height=1,
        created_at="",
    )
    plan = VideoPlan(
        chosen_account="alpha",
        video_type=VideoType.TYPE_1,
        language=Language.ES,
        slides=[
            SlidePlan(index=1, role=SlideRole.HOOK, text="", media=first),
            SlidePlan(index=2, role=SlideRole.OCTOBER, text="", media=second),
        ],
        used_media_ids=["alpha:1", "beta:1"],
    )

    try:
        service._assert_single_source_account(plan)
    except RuntimeError as error:
        assert "@alpha" in str(error)
        assert "@beta" in str(error)
    else:  # pragma: no cover - defensive assertion for readability
        raise AssertionError("mixed-account plans must be rejected")


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


def test_create_extra_image_falls_back_to_same_account_fetch_when_pool_has_none():
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
            source_id="alpha:fresh:1",
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
        service.pool = EmptyExtraPool()
        service.collector = ExtraImageCollectorNoCache(media)
        service.selector = ExtraImageSelector()
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            account_inputs=["alpha"],
        )

        result = service._create_extra_image_locked(request)

        assert result.source_id == "alpha:fresh:1"
        assert service.collector.seen == ["alpha:False"]
        assert service.state.any_media_used(["alpha:fresh:1"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_keeps_searching_beyond_first_failed_accounts(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    monkeypatch.setattr("app.service.random.random", lambda: 0.0)
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


def test_plan_picker_falls_back_to_dynamic_when_pool_has_no_plan(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), account_pick_attempts=0)
        service.state = StateStore(root / "state")
        service.pool = EmptyPlanPool()
        service.collector = FakeCollector()
        service.selector = PlanWhenGoodSelector()
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            account_inputs=[],
        )

        plan, tried = service._pick_and_reserve_plan(
            ["bad", "good"],
            request,
            "job-1",
        )

        assert plan.chosen_account == "good"
        assert tried == ["bad", "good"]
        assert service.collector.seen == ["bad", "good"]
        assert service.pool.noted == [("good", VideoType.TYPE_1)]
        assert service.state.any_media_used(["good:1"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dynamic_picker_respects_skipped_accounts(monkeypatch):
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
            skip_accounts=["bad"],
        )

        plan, tried = service._pick_account_with_plan(
            ["bad", "good"],
            request,
        )

        assert plan.chosen_account == "good"
        assert tried == ["good"]
        assert service.collector.seen == ["good"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_respects_account_attempt_limit(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), account_pick_attempts=2)
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

        try:
            service._pick_account_with_plan(["bad1", "bad2", "good"], request)
        except Exception as error:  # noqa: BLE001
            assert "Ninguna de las 2 cuentas probadas" in str(error)
        else:  # pragma: no cover - defensive assertion for readability
            raise AssertionError("picker should stop at the configured limit")
        assert service.collector.seen == ["bad1", "bad2"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_uses_pure_random_account_order(monkeypatch):
    def reverse_shuffle(values):
        values.reverse()

    monkeypatch.setattr("app.service.random.shuffle", reverse_shuffle)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), account_pick_attempts=0)
        service.state = StateStore(root / "state")

        ordered = service._ordered_accounts_for_pick(
            ["one", "two", "three"],
            VideoType.TYPE_1,
        )

        assert ordered == ["three", "two", "one"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_picker_tries_next_random_account_when_video_cannot_be_made(monkeypatch):
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
            ["bad", "good"],
            request,
        )

        assert plan.chosen_account == "good"
        assert tried == ["bad", "good"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_persistence_status_warns_when_container_data_dir_is_not_app_data(monkeypatch):
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = replace(
        get_settings(),
        data_dir=Path("/tmp/bot-data"),
        state_dir=Path("/tmp/bot-data/state"),
    )
    monkeypatch.setattr("app.service._running_in_container", lambda: True)

    status = service.persistence_status()

    assert status["in_container"] is True
    assert status["is_expected_path"] is False
    assert "DATA_DIR=" in status["warning"]


def test_persistence_status_warns_when_app_data_is_not_mounted(monkeypatch):
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = replace(
        get_settings(),
        data_dir=Path("/app/data"),
        state_dir=Path("/app/data/state"),
    )
    monkeypatch.setattr("app.service._running_in_container", lambda: True)

    status = service.persistence_status()

    assert status["in_container"] is True
    assert status["is_expected_path"] is True
    assert status["is_mount"] is False
    assert "Persistent Storage" in status["warning"]
