"""The publication engine runs after successful media creation, across brands."""

from copy import deepcopy
from dataclasses import replace
from threading import Lock

import pytest

from app.config import get_settings
from app.models import (
    GenerationResult, Language, MediaCandidate, SlidePlan, SlideRole,
    SocialCopy, VideoRequest, VideoType,
)
from app.publication_writer import PublicationWriter
from app.service import TEMPLATE_VIDEO_SOCIAL_COPIES, VideoCreationService
from app.state import StateStore


_PARKEZ = {
    VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.PARKEZ_ADVICE,
    VideoType.PARKEZ_APPS, VideoType.TOOLS,
}


@pytest.fixture(autouse=True)
def no_external_publication_requests(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Publication service tests must never call external services")

    monkeypatch.setattr("app.publication_writer.requests.post", unexpected)


@pytest.fixture
def service(tmp_path):
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = replace(
        get_settings(), root_dir=tmp_path, data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs", state_dir=tmp_path / "state",
        template_videos_dir=tmp_path / "templates",
    )
    service.state = StateStore(service.settings.state_dir)
    service._job_lock = Lock()
    service._cleanup_old_outputs = lambda: None
    return service


def _brand(video_type):
    if video_type in _PARKEZ:
        return "parkez", "#coches"
    if video_type == VideoType.GOGRADUATE_TYPE_1:
        return "gograduate", "#estudiantes"
    return "dropradar", "#dropshipping"


def _result(tmp_path, video_type, language=Language.ES):
    brand, _tag = _brand(video_type)
    text = {
        "dropradar": "Dropradar ayuda a investigar productos antes de lanzar una tienda.",
        "parkez": "ParkEz orienta la búsqueda de aparcamiento cerca del destino.",
        "gograduate": "GoGraduate ayuda a trabajar con los apuntes y repasar las dudas.",
    }[brand]
    media = MediaCandidate(
        source_account="test", source_id="slide", local_path=tmp_path / "slide.png",
        permalink="", caption="", width=1080, height=1920, created_at="",
    )
    return GenerationResult(
        video_path=None, script_path=tmp_path / "script.txt", preview_text=text,
        social_copy=SocialCopy(
            title="Título anterior", description="Descripción anterior",
            hashtags=["#anterior"], hook="Hook literal #1 · Apps que son literalmente...",
        ),
        chosen_account="test", video_type=video_type, language=language,
        fallback_accounts=[], slides=[SlidePlan(1, SlideRole.ADVICE_CARD, text, media)],
    )


class FakeWriter:
    def __init__(self):
        self.calls = []

    def write(self, context, history, style):
        self.calls.append((deepcopy(context), deepcopy(history), style))
        if context["language"] == "en":
            title = "A practical way to organize your next steps"
            description = "Consider the tools you need before starting your online store."
        else:
            title = "Una forma sencilla de preparar tu próxima tienda"
            description = "Revisa las herramientas que necesitas antes de abrir tu tienda online."
        return {"title": title, "description": "" if style == "none" else description}


@pytest.mark.parametrize("video_type", list(VideoType), ids=lambda video_type: video_type.value)
def test_public_creation_replaces_only_publication_copy_after_success(service, tmp_path, monkeypatch, video_type):
    original = _result(tmp_path, video_type)
    snapshot = deepcopy(original)
    history_path = service.settings.state_dir / "publication_copy_history.json"

    def rendered(request):
        assert not history_path.exists()
        return original

    monkeypatch.setattr(service, "_create_video_locked", rendered)
    request = VideoRequest(1, 1, video_type, Language.ES, [])

    result = service.create_video(request)

    brand, essential = _brand(video_type)
    assert result is not original
    assert result.social_copy is not original.social_copy
    assert result.social_copy.title
    assert essential in result.social_copy.hashtags
    assert 4 <= len(result.social_copy.hashtags) <= 6
    assert result.social_copy.hook == original.social_copy.hook
    assert result.slides is original.slides
    assert original == snapshot
    history = service.state.publication_copy_snapshot(brand)
    assert history["count"] == 1
    record = history["languages"]["es"][-1]
    assert record["title"] == result.social_copy.title
    assert record["description"] == result.social_copy.description
    assert record["hashtags"] == result.social_copy.hashtags


def test_configured_writer_receives_delivered_content_after_render(service, tmp_path, monkeypatch):
    original = _result(tmp_path, VideoType.TYPE_2)
    service.publication_writer = FakeWriter()
    monkeypatch.setattr(service, "_create_video_locked", lambda request: original)

    result = service.create_video(VideoRequest(1, 1, VideoType.TYPE_2, Language.ES, []))

    assert result.social_copy.title == "Una forma sencilla de preparar tu próxima tienda"
    assert len(service.publication_writer.calls) == 1
    context, history, _style = service.publication_writer.calls[0]
    assert context["content"] == original.slides[0].text
    assert context["brand"] == "dropradar"
    assert history == {"titles": [], "descriptions": []}
    assert original.social_copy.title == "Título anterior"


def test_render_failure_never_calls_writer_or_consumes_publication_history(service, monkeypatch):
    service.publication_writer = FakeWriter()

    def failed(request):
        raise RuntimeError("render failed")

    monkeypatch.setattr(service, "_create_video_locked", failed)

    with pytest.raises(RuntimeError, match="render failed"):
        service.create_video(VideoRequest(1, 1, VideoType.TYPE_2, Language.ES, []))

    assert service.publication_writer.calls == []
    assert not (service.settings.state_dir / "publication_copy_history.json").exists()


def test_unavailable_writer_keeps_the_successful_video_and_uses_local_copy(service, tmp_path, monkeypatch):
    original = _result(tmp_path, VideoType.TYPE_2)
    writer = FakeWriter()
    writer.write = lambda context, history, style: None
    service.publication_writer = writer
    monkeypatch.setattr(service, "_create_video_locked", lambda request: original)

    result = service.create_video(VideoRequest(1, 1, VideoType.TYPE_2, Language.ES, []))

    assert result.script_path == original.script_path
    assert result.social_copy.title
    assert result.social_copy.title != original.social_copy.title
    assert "#dropshipping" in result.social_copy.hashtags
    assert service.state.publication_copy_snapshot("dropradar")["count"] == 1


@pytest.mark.parametrize("video_type,lowercase", ((VideoType.TYPE_2, True), (VideoType.TYPE_4, False)))
def test_publication_respects_lowercase_without_changing_literal_hooks(
    service, tmp_path, monkeypatch, video_type, lowercase,
):
    original = _result(tmp_path, video_type)
    service.publication_writer = FakeWriter()
    monkeypatch.setattr(service, "_create_video_locked", lambda request: original)

    result = service.create_video(VideoRequest(
        1, 1, video_type, Language.ES, [], lowercase_text=True,
    ))

    expected = "Una forma sencilla de preparar tu próxima tienda"
    assert result.social_copy.title == (expected.lower() if lowercase else expected)
    assert result.social_copy.hook == original.social_copy.hook
    assert original.slides[0].text.startswith("Dropradar")


def test_publication_cycles_include_title_and_tags_without_description(service, tmp_path, monkeypatch):
    original = _result(tmp_path, VideoType.PARKEZ_APPS)
    monkeypatch.setattr(service, "_create_video_locked", lambda request: original)
    request = VideoRequest(1, 1, VideoType.PARKEZ_APPS, Language.ES, [])

    copies = [service.create_video(request).social_copy for _ in range(3)]

    assert sum(not copy.description for copy in copies) == 1
    assert len({copy.title for copy in copies}) == 3
    assert len({tuple(sorted(copy.hashtags)) for copy in copies}) == 3
    empty = next(copy for copy in copies if not copy.description)
    assert empty.messages == [empty.hook, empty.title, empty.hashtag_line]
    assert "#coches" in empty.hashtags


def test_regular_service_configures_the_optional_writer(tmp_path, monkeypatch):
    settings = replace(get_settings(), state_dir=tmp_path / "state")
    monkeypatch.setattr("app.service.get_settings", lambda: settings)
    monkeypatch.setattr(VideoCreationService, "_ensure_directories", lambda self: None)
    for constructor in (
        "InstagramCollector", "ImageSelector", "MediaPoolService", "ScriptGenerator",
        "VideoRenderer", "R2StorageClient", "StoryCarouselImageGenerator",
    ):
        monkeypatch.setattr(f"app.service.{constructor}", lambda *args, **kwargs: object())

    service = VideoCreationService()

    assert isinstance(service.publication_writer, PublicationWriter)
    assert service.publication_writer.settings is settings


class TemplateRenderer:
    def __init__(self, state_dir, *, fail=False):
        self.state_dir, self.fail, self.calls = state_dir, fail, []

    def render_template_video(self, source, job_dir, language):
        assert not (self.state_dir / "publication_copy_history.json").exists()
        self.calls.append((source, job_dir, language))
        if self.fail:
            raise RuntimeError("template render failed")
        job_dir.mkdir(parents=True, exist_ok=True)
        output = job_dir / "template.mp4"
        output.write_bytes(b"rendered")
        return output


def _template_source(service, tmp_path, monkeypatch, *, fail=False):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    service.renderer = TemplateRenderer(service.settings.state_dir, fail=fail)
    monkeypatch.setattr(service, "_pick_template_video", lambda folder: (source, True))
    return source


def test_templates_use_the_same_publication_engine_and_preserve_the_queue_flag(service, tmp_path, monkeypatch):
    source = _template_source(service, tmp_path, monkeypatch)
    service.publication_writer = FakeWriter()
    original_copies = deepcopy(TEMPLATE_VIDEO_SOCIAL_COPIES[Language.EN])

    result = service.create_template_video(language=Language.EN)

    assert result.video_path.exists()
    assert result.queue_restarted is True
    assert result.social_copy.title == "A practical way to organize your next steps"
    assert "#dropshipping" in result.social_copy.hashtags
    assert service.renderer.calls[0][0] == source
    context, _history, _style = service.publication_writer.calls[0]
    assert context["brand"] == "dropradar"
    assert context["language"] == "en"
    assert context["video_type"] == "template"
    assert service.state.publication_copy_snapshot("dropradar")["count"] == 1
    assert TEMPLATE_VIDEO_SOCIAL_COPIES[Language.EN] == original_copies


def test_failed_template_render_does_not_select_or_remember_publication_copy(service, tmp_path, monkeypatch):
    _template_source(service, tmp_path, monkeypatch, fail=True)
    service.publication_writer = FakeWriter()

    with pytest.raises(RuntimeError, match="template render failed"):
        service.create_template_video()

    assert service.publication_writer.calls == []
    assert not (service.settings.state_dir / "publication_copy_history.json").exists()
