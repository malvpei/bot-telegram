from __future__ import annotations

import os
import shutil
import time
from dataclasses import replace
from pathlib import Path
from threading import Lock
from uuid import uuid4

from PIL import Image
import pytest

from app.config import get_settings
from app.models import Language, MediaCandidate, SlidePlan, SlideRole, VideoPlan, VideoRequest, VideoType
from app.r2_storage import R2Object
from app.service import VideoCreationService
from app.state import StateStore
from app.texts import ScriptGenerator


class FakeRenderer:
    def __init__(self) -> None:
        self.render_called = False
        self.write_script_called = False
        self.template_input_video: Path | None = None
        self.template_language = None
        self.render_slide_still_calls: list[VideoType] = []
        self.render_slide_still_sources: list[Path] = []
        self.render_slide_still_texts: list[str] = []
        self.written_plan: VideoPlan | None = None

    def render(self, plan: VideoPlan, job_dir: Path):
        self.render_called = True
        raise AssertionError("tipo3 should not render a full MP4")

    def write_script(self, plan: VideoPlan, job_dir: Path) -> Path:
        self.write_script_called = True
        self.written_plan = plan
        job_dir.mkdir(parents=True, exist_ok=True)
        script_path = job_dir / "script.txt"
        script_path.write_text("script", encoding="utf-8")
        return script_path

    def render_slide_still(self, slide: SlidePlan, video_type: VideoType) -> Image.Image:
        self.render_slide_still_calls.append(video_type)
        self.render_slide_still_sources.append(slide.media.local_path)
        self.render_slide_still_texts.append(slide.text)
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
        self.max_posts_seen: list[int | None] = []

    def collect_one(self, username: str, *, max_posts: int | None = None) -> list[str]:
        self.seen.append(username)
        self.max_posts_seen.append(max_posts)
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
        self.listed_image_prefix: str | None = None
        self.downloaded_key: str | None = None
        self.download_count = 0

    def list_videos(self, prefix: str):
        self.listed_prefix = prefix
        return [R2Object(key="videos/source.mp4", size=123)]

    def list_images(self, prefix: str):
        self.listed_image_prefix = prefix
        return [R2Object(key="videos/imagenes/reference.jpg", size=123)]

    def download(self, key: str, destination: Path) -> Path:
        self.downloaded_key = key
        self.download_count += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        if Path(key).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            Image.new("RGB", (90, 120), (20, 40, 60)).save(destination)
        else:
            destination.write_bytes(b"r2-video")
        return destination


class PrefixFallbackR2Storage(FakeR2Storage):
    def __init__(self) -> None:
        super().__init__()
        self.listed_image_prefixes: list[str] = []

    def list_images(self, prefix: str):
        self.listed_image_prefixes.append(prefix)
        if prefix == "videos/imagenes":
            return []
        if prefix == "":
            return [R2Object(key="otra/carpeta/reference.jpg", size=123)]
        return []


class DuplicateTemplateR2Storage(FakeR2Storage):
    def list_videos(self, prefix: str):
        self.listed_prefix = prefix
        return [
            R2Object(key="videos/copy-a.mp4", size=10, etag="same-etag"),
            R2Object(key="videos/copy-b.mp4", size=10, etag="same-etag"),
            R2Object(key="videos/different.mp4", size=20, etag="different-etag"),
        ]

    def download(self, key: str, destination: Path) -> Path:
        self.downloaded_key = key
        self.download_count += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            b"same-video" if "copy-" in key else b"different-video"
        )
        return destination


class FakeStoryImageGenerator:
    def __init__(self) -> None:
        self.reference_image_path: Path | None = None
        self.job_dir: Path | None = None

    def generate_slides(
        self,
        reference_image_path: Path,
        job_dir: Path,
    ) -> list[MediaCandidate]:
        self.reference_image_path = reference_image_path
        self.job_dir = job_dir
        generated_dir = job_dir / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        media: list[MediaCandidate] = []
        roles = [
            SlideRole.STORY_MCDONALD,
            SlideRole.STORY_BUILDING_STORE,
            SlideRole.STORY_FIRST_FAILURE,
            SlideRole.STORY_DEEP_FAILURE,
            SlideRole.STORY_DROPRADAR,
            SlideRole.STORY_SUCCESS_COMIC,
        ]
        for index, role in enumerate(roles, start=1):
            path = generated_dir / f"generated_{index}.png"
            Image.new("RGB", (72, 128), (index * 20, 80, 120)).save(path)
            media.append(
                MediaCandidate(
                    source_account="ai_story",
                    source_id=f"ai:{index}",
                    local_path=path,
                    permalink="",
                    caption=role.value,
                    width=72,
                    height=128,
                    created_at="generated",
                )
            )
        return media


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


def test_render_outputs_can_keep_slide_text_out_of_images():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        source_path = root / "source.jpg"
        Image.new("RGB", (72, 128), (10, 20, 30)).save(source_path)
        renderer = FakeRenderer()
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(get_settings(), width=72, height=128)
        service.renderer = renderer
        plan = VideoPlan(
            chosen_account="alpha",
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            slides=[
                SlidePlan(
                    index=1,
                    role=SlideRole.HOOK,
                    text="Hook text",
                    media=MediaCandidate(
                        source_account="alpha",
                        source_id="one",
                        local_path=source_path,
                        permalink="",
                        caption="",
                        width=72,
                        height=128,
                        created_at="",
                    ),
                ),
            ],
        )

        service._render_outputs(
            plan,
            root / "outputs" / "job",
            embed_slide_text=False,
        )

        assert renderer.written_plan is plan
        assert renderer.render_slide_still_texts == [""]
        assert plan.slides[0].text == "Hook text"
        assert plan.slides[0].media.local_path.name == "slide_01.jpg"
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


def test_type_4_generates_six_ai_slides_and_normalizes_original_reference():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            state_dir=root / "state",
            width=72,
            height=128,
        )
        reference = root / "reference.jpg"
        Image.new("RGB", (90, 120), (20, 40, 60)).save(reference)
        renderer = FakeRenderer()
        story_generator = FakeStoryImageGenerator()
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.state = StateStore(settings.state_dir)
        service.script_generator = ScriptGenerator(service.state)
        service.renderer = renderer
        service.story_image_generator = story_generator
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            account_inputs=[],
            reference_image_path=reference,
        )

        result = service._create_story_carousel_locked(request)

        assert result.video_path is None
        assert result.video_type == VideoType.TYPE_4
        assert len(result.slides) == 7
        assert story_generator.reference_image_path == reference
        assert renderer.render_slide_still_calls == [VideoType.TYPE_4] * 7
        assert result.slides[-1].role == SlideRole.STORY_ORIGINAL_REFERENCE
        assert result.slides[-1].media.local_path.name == "slide_07.jpg"
        assert root / "outputs" / "users" / "1" in result.slides[-1].media.local_path.parents
        assert Image.open(result.slides[-1].media.local_path).size == (72, 128)
        assert result.slides[-1].media.local_path.read_bytes() != reference.read_bytes()
        assert service.state.get_last_social_choice(
            VideoType.TYPE_4,
            Language.ES,
        ) == "es_story_1"
        assert renderer.written_plan is not None
        assert renderer.written_plan.slides[0].text.startswith("Así pasé")
        assert renderer.written_plan.slides[4].text.startswith("Entonces encontré")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_4_renders_complete_english_story():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            state_dir=root / "state",
            width=72,
            height=128,
        )
        reference = root / "reference.jpg"
        Image.new("RGB", (90, 120), (20, 40, 60)).save(reference)
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.state = StateStore(settings.state_dir)
        service.script_generator = ScriptGenerator(service.state)
        service.renderer = FakeRenderer()
        service.story_image_generator = FakeStoryImageGenerator()

        result = service._create_story_carousel_locked(
            VideoRequest(
                chat_id=1,
                user_id=1,
                video_type=VideoType.TYPE_4,
                language=Language.EN,
                account_inputs=[],
                reference_image_path=reference,
            )
        )

        assert result.language == Language.EN
        assert result.slides[0].text.startswith("This is how I went")
        assert result.slides[4].text.startswith("Then I found Dropradar")
        assert service.state.get_last_social_choice(
            VideoType.TYPE_4,
            Language.EN,
        ) == "en_story_1"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_4_downloads_reference_from_r2_when_no_photo_is_passed():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            state_dir=root / "state",
            r2_image_prefix="videos/imagenes",
            width=72,
            height=128,
        )
        renderer = FakeRenderer()
        story_generator = FakeStoryImageGenerator()
        r2_storage = FakeR2Storage()
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.state = StateStore(settings.state_dir)
        service.script_generator = ScriptGenerator(service.state)
        service.renderer = renderer
        service.story_image_generator = story_generator
        service.r2_storage = r2_storage
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            account_inputs=[],
        )

        result = service._create_story_carousel_locked(request)

        assert result.video_type == VideoType.TYPE_4
        assert r2_storage.listed_image_prefix == "videos/imagenes"
        assert r2_storage.downloaded_key == "videos/imagenes/reference.jpg"
        assert story_generator.reference_image_path is not None
        assert story_generator.reference_image_path.name == "source.jpg"
        assert story_generator.reference_image_path.exists()
        assert result.chosen_account == "r2:videos/imagenes/reference.jpg"
        assert result.slides[-1].media.local_path.name == "slide_07.jpg"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_4_r2_reference_is_globally_consumed_across_users():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            state_dir=root / "state",
            r2_image_prefix="videos/imagenes",
            width=72,
            height=128,
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.state = StateStore(settings.state_dir)
        service.script_generator = ScriptGenerator(service.state)
        service.renderer = FakeRenderer()
        service.story_image_generator = FakeStoryImageGenerator()
        service.r2_storage = FakeR2Storage()

        first_request = VideoRequest(
            chat_id=101,
            user_id=1,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            account_inputs=[],
        )
        second_request = VideoRequest(
            chat_id=202,
            user_id=2,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            account_inputs=[],
        )

        service._create_story_carousel_locked(first_request)
        with pytest.raises(ValueError, match="No quedan imagenes de referencia sin usar"):
            service._create_story_carousel_locked(second_request)

        used = service.state.read_used_media()
        assert "r2-story:videos/imagenes/reference.jpg" in used
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_4_falls_back_to_any_r2_image_when_configured_prefix_is_empty():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            state_dir=root / "state",
            r2_image_prefix="videos/imagenes",
            width=72,
            height=128,
        )
        renderer = FakeRenderer()
        story_generator = FakeStoryImageGenerator()
        r2_storage = PrefixFallbackR2Storage()
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.state = StateStore(settings.state_dir)
        service.script_generator = ScriptGenerator(service.state)
        service.renderer = renderer
        service.story_image_generator = story_generator
        service.r2_storage = r2_storage
        request = VideoRequest(
            chat_id=1,
            user_id=1,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            account_inputs=[],
        )

        result = service._create_story_carousel_locked(request)

        assert result.video_type == VideoType.TYPE_4
        assert r2_storage.listed_image_prefixes == ["videos/imagenes", ""]
        assert r2_storage.downloaded_key == "otra/carpeta/reference.jpg"
        assert result.chosen_account == "r2:otra/carpeta/reference.jpg"
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
        assert result.social_copy.title == ""
        assert len(result.social_copy.hashtags) == 5
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
        assert result.social_copy.title == ""
        assert len(result.social_copy.hashtags) == 5
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

        service.create_template_video("campaign-a")
        assert service.r2_storage.download_count == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r2_template_queue_deduplicates_objects_with_same_content_etag():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        settings = replace(
            get_settings(),
            root_dir=root,
            data_dir=root,
            outputs_dir=root / "outputs",
            r2_input_prefix="videos",
        )
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = settings
        service.renderer = FakeRenderer()
        service.r2_storage = DuplicateTemplateR2Storage()
        service.state = StateStore(root / "state")
        service._job_lock = Lock()

        first = service.create_template_video()
        first_bytes = service.renderer.template_input_video.read_bytes()
        second = service.create_template_video()
        second_bytes = service.renderer.template_input_video.read_bytes()
        third = service.create_template_video()
        third_bytes = service.renderer.template_input_video.read_bytes()

        assert first.queue_restarted is False
        assert second.queue_restarted is False
        assert first_bytes != second_bytes
        assert third.queue_restarted is True
        assert third_bytes == first_bytes
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_r2_template_cache_is_bounded_and_prunes_stale_partials(
    tmp_path,
    monkeypatch,
):
    cache_dir = tmp_path / "template_cache"
    cache_dir.mkdir()
    files = []
    now = time.time()
    for index in range(4):
        path = cache_dir / f"template-{index}.mp4"
        path.write_bytes(b"x" * 10)
        os.utime(path, (now - (40 - index), now - (40 - index)))
        files.append(path)
    stale_partial = cache_dir / "old.mp4.part"
    stale_partial.write_bytes(b"partial")
    stale_time = now - (7 * 60 * 60)
    os.utime(stale_partial, (stale_time, stale_time))
    monkeypatch.setattr("app.service.R2_TEMPLATE_CACHE_MAX_ITEMS", 2)
    monkeypatch.setattr("app.service.R2_TEMPLATE_CACHE_MAX_BYTES", 25)

    VideoCreationService._prune_r2_template_cache(
        cache_dir,
        keep_path=files[-1],
    )

    remaining = sorted(cache_dir.glob("*.mp4"))
    assert remaining == files[-2:]
    assert not stale_partial.exists()


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


def test_template_video_queue_deduplicates_identical_file_copies():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"service-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        source_dir = root / "template_videos"
        source_dir.mkdir()
        (source_dir / "copy-a.mp4").write_bytes(b"same-video")
        (source_dir / "copy-b.mp4").write_bytes(b"same-video")
        (source_dir / "different.mp4").write_bytes(b"different-video")
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

        first = service.create_template_video()
        first_bytes = service.renderer.template_input_video.read_bytes()
        second = service.create_template_video()
        second_bytes = service.renderer.template_input_video.read_bytes()
        third = service.create_template_video()
        third_bytes = service.renderer.template_input_video.read_bytes()

        assert first.queue_restarted is False
        assert second.queue_restarted is False
        assert first_bytes != second_bytes
        assert third.queue_restarted is True
        assert third_bytes == first_bytes
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


def test_dynamic_picker_limits_posts_per_account(monkeypatch):
    monkeypatch.setattr("app.service.random.shuffle", lambda values: None)
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"picker-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        service = VideoCreationService.__new__(VideoCreationService)
        service.settings = replace(
            get_settings(),
            account_pick_attempts=0,
            dynamic_pick_max_posts_per_account=12,
            max_posts_per_account=100,
        )
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
        assert service.collector.max_posts_seen == [12, 12]
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
