from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Lock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.advice_cards import AdviceBackground
from app.config import get_settings
from app.gograduate import (
    GOGRADUATE_BACKGROUNDS,
    GOGRADUATE_DESIGN_IDS,
    GOGRADUATE_HOOK_IDS,
    GOGRADUATE_HOOKS,
    GOGRADUATE_PACK_IDS,
    GOGRADUATE_PACKS,
    GOGRADUATE_PROMO,
    GOGRADUATE_SOCIAL_COPY_IDS,
    gograduate_social_copy,
    gograduate_tips,
)
from app.models import Language, SlideRole, VideoRequest, VideoType
from app.r2_storage import R2Object
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
    assert social.hook == GOGRADUATE_HOOKS["oxford"]
    assert "GoGraduate" in social.description
    if illustrated:
        assert "cinco" not in social.description.lower()
        assert "quinto" not in social.description.lower()


class StudentR2Storage:
    is_configured = True

    def __init__(self):
        self.objects = [
            R2Object(key="c/a.png", size=100, etag="a"),
            R2Object(key="c/b.png", size=100, etag="b"),
            R2Object(key="4/outside.png", size=100, etag="outside"),
        ]
        self.listed_prefixes = []
        self.downloaded_keys = []

    def list_images(self, prefix):
        self.listed_prefixes.append(prefix)
        return list(self.objects)

    def download(self, key, destination):
        self.downloaded_keys.append(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (90, 160), (30, 60, 90)).save(destination, format="PNG")
        return destination


def _service(tmp_path, *, width=1080, height=1920):
    settings = replace(
        get_settings(), outputs_dir=tmp_path / "outputs", state_dir=tmp_path / "state",
        width=width, height=height, r2_bucket="videos", r2_gograduate_image_prefix="c",
    )
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = settings
    service.state = StateStore(settings.state_dir)
    service.renderer = VideoRenderer(settings)
    service.r2_storage = StudentR2Storage()
    service._job_lock = Lock()
    return service


def test_gograduate_delivers_two_images_and_rotates_without_touching_dropradar(tmp_path):
    service = _service(tmp_path)
    request = VideoRequest(
        chat_id=1, user_id=10, video_type=VideoType.GOGRADUATE_TYPE_1,
        language=Language.ES, account_inputs=[],
    )
    service.state.advance_type_4_advice_phase(cycle_length=12)
    type4_next = service.state.peek_next_type_4_image_id(["dropradar-image"])
    chosen = []
    for index, _ in enumerate(GOGRADUATE_PACK_IDS):
        pack_id, _ = service.state.peek_next_gograduate_type_1_pack_id(GOGRADUATE_PACK_IDS)
        background = GOGRADUATE_BACKGROUNDS[index % 2]
        result = service.create_video(request)
        chosen.append(result.chosen_account)
        assert result.video_type == VideoType.GOGRADUATE_TYPE_1
        assert result.language == Language.ES
        assert result.video_path is None
        assert [slide.role for slide in result.slides] == [SlideRole.ADVICE_CARD, SlideRole.ADVICE_R2_CLEAN]
        assert result.slides[1].text == ""
        assert result.slides[1].media.source_id == f"r2-gograduate:c/{'a' if index % 2 == 0 else 'b'}.png"
        assert result.separate_slide_text is False
        assert GOGRADUATE_PROMO.body in result.preview_text
        assert result.preview_text == result.slides[0].text
        assert result.preview_text in result.script_path.read_text(encoding="utf-8")
        assert "GoGraduate" in result.social_copy.description
        assert f":{background.value}:" in result.chosen_account
        assert result.social_copy.hook == GOGRADUATE_HOOKS[GOGRADUATE_HOOK_IDS[index % 2]]
        if background == AdviceBackground.ILLUSTRATED:
            assert GOGRADUATE_PACKS[pack_id][3].body not in result.preview_text
            assert "5. " not in result.preview_text
        else:
            assert GOGRADUATE_PACKS[pack_id][3].body in result.preview_text
            assert "5. " in result.preview_text
        with Image.open(result.slides[0].media.local_path) as image:
            assert image.format == "PNG"
            assert image.size == (1080, 1920)
        with Image.open(result.slides[1].media.local_path) as image:
            assert image.format == "PNG"
            assert image.size == (1080, 1920)
            assert (np.asarray(image) == (30, 60, 90)).all()
        # Queue position survives a new state-store instance.
        service.state = StateStore(service.settings.state_dir)
        next_design, _ = service.state.peek_next_gograduate_type_1_design_id(GOGRADUATE_DESIGN_IDS)
        assert next_design == GOGRADUATE_BACKGROUNDS[(index + 1) % 2].value
    assert len(set(chosen)) == len(GOGRADUATE_PACK_IDS)
    assert service.state.get_type_4_advice_phase(cycle_length=12) == 1
    assert service.state.peek_next_type_4_image_id(["dropradar-image"]) == type4_next
    assert service.state.read_used_media() == {}
    assert service.r2_storage.listed_prefixes == ["c/"] * 4
    assert service.r2_storage.downloaded_keys == ["c/a.png", "c/b.png"] * 2


@pytest.mark.parametrize("stage", ["download", "render", "normalize", "script", "log"])
def test_failed_gograduate_job_does_not_advance_any_queue(tmp_path, monkeypatch, stage):
    service = _service(tmp_path)
    before = service.state.peek_next_gograduate_type_1_pack_id(GOGRADUATE_PACK_IDS)[0]
    before_design = service.state.peek_next_gograduate_type_1_design_id(GOGRADUATE_DESIGN_IDS)[0]
    before_hook = service.state.peek_next_gograduate_hook_id(GOGRADUATE_HOOK_IDS)[0]
    before_copy = service.state.peek_next_gograduate_social_copy_id(before, GOGRADUATE_SOCIAL_COPY_IDS)[0]
    image_ids = ["videos:c:etag:a:100", "videos:c:etag:b:100"]
    before_image = service.state.peek_next_gograduate_image_id(image_ids)[0]

    def fail(*args, **kwargs):
        raise OSError("render failed")

    owner, method = {
        "download": (service.r2_storage, "download"),
        "render": (service.renderer, "render_gograduate_card"),
        "normalize": (service, "_normalize_advice_image"),
        "script": (service.renderer, "write_script"),
        "log": (service.state, "log_job"),
    }[stage]
    monkeypatch.setattr(owner, method, fail)
    with pytest.raises(OSError, match="render failed"):
        service.create_video(VideoRequest(
            chat_id=1, user_id=10, video_type=VideoType.GOGRADUATE_TYPE_1,
            language=Language.ES, account_inputs=[],
        ))
    assert service.state.peek_next_gograduate_type_1_pack_id(GOGRADUATE_PACK_IDS)[0] == before
    assert service.state.peek_next_gograduate_type_1_design_id(GOGRADUATE_DESIGN_IDS)[0] == before_design
    assert service.state.peek_next_gograduate_hook_id(GOGRADUATE_HOOK_IDS)[0] == before_hook
    assert service.state.peek_next_gograduate_social_copy_id(before, GOGRADUATE_SOCIAL_COPY_IDS)[0] == before_copy
    assert service.state.peek_next_gograduate_image_id(image_ids)[0] == before_image


@pytest.mark.parametrize("background", GOGRADUATE_BACKGROUNDS)
def test_gograduate_requires_its_own_logo_instead_of_using_dropradar(tmp_path, background):
    renderer = VideoRenderer(replace(get_settings(), root_dir=tmp_path))
    with pytest.raises(FileNotFoundError, match="icono de GoGraduate"):
        renderer.render_gograduate_card(
            gograduate_tips(GOGRADUATE_PACK_IDS[0], background), Language.ES, background,
        )


@pytest.mark.parametrize("pack_id", GOGRADUATE_PACK_IDS)
@pytest.mark.parametrize("background", GOGRADUATE_BACKGROUNDS)
def test_twenty_unique_copies_describe_only_the_visible_tips(pack_id, background):
    copies = [gograduate_social_copy(pack_id, background, copy_id=copy_id) for copy_id in GOGRADUATE_SOCIAL_COPY_IDS]
    assert len(copies) == len({copy.title for copy in copies}) == len({copy.description for copy in copies}) == 20
    for copy in copies:
        assert all(len(message) <= 4096 for message in copy.messages)
        for tip in gograduate_tips(pack_id, background):
            assert tip.title in copy.description
            assert tip.body in copy.description
        if background == AdviceBackground.ILLUSTRATED:
            assert GOGRADUATE_PACKS[pack_id][3].body not in copy.description
            assert "cinco" not in copy.description.lower()


def test_service_exhausts_twenty_copies_per_pack_and_preserves_hooks_on_restart(tmp_path, monkeypatch):
    service = _service(tmp_path, width=72, height=128)
    monkeypatch.setattr(service.renderer, "render_gograduate_card", lambda *_: Image.new("RGB", (72, 128), "white"))
    request = VideoRequest(chat_id=1, user_id=10, video_type=VideoType.GOGRADUATE_TYPE_1, language=Language.ES, account_inputs=[])
    copies_by_pack = {pack_id: [] for pack_id in GOGRADUATE_PACK_IDS}
    for index in range(80):
        pack_id = GOGRADUATE_PACK_IDS[index % 4]
        result = service.create_video(request)
        assert result.chosen_account.endswith(f":{pack_id}")
        assert result.social_copy.hook == GOGRADUATE_HOOKS[GOGRADUATE_HOOK_IDS[index % 2]]
        copies_by_pack[pack_id].append(result.social_copy)
        service.state = StateStore(service.settings.state_dir)
    assert len({copy.title for copies in copies_by_pack.values() for copy in copies}) == 80
    for pack_id, copies in copies_by_pack.items():
        assert len({copy.title for copy in copies}) == len({copy.description for copy in copies}) == 20
        assert service.state.peek_next_gograduate_social_copy_id(pack_id, GOGRADUATE_SOCIAL_COPY_IDS) == (GOGRADUATE_SOCIAL_COPY_IDS[0], True)
    repeated = service.create_video(request)
    assert repeated.social_copy == copies_by_pack[GOGRADUATE_PACK_IDS[0]][0]


def test_gograduate_r2_queue_deduplicates_prioritizes_new_uploads_and_never_uses_other_folders(tmp_path):
    service = _service(tmp_path)
    now = datetime.now(timezone.utc)
    storage = service.r2_storage
    storage.objects = [
        R2Object(key="c/b.png", size=100, etag="b", last_modified=now - timedelta(days=1)),
        R2Object(key="c/a.png", size=100, etag="a", last_modified=now),
        R2Object(key="c/a-copy.png", size=100, etag="a", last_modified=now - timedelta(seconds=1)),
        R2Object(key="cartools/not-student.png", size=100, etag="outside", last_modified=now),
    ]
    first = service._download_next_gograduate_image_from_r2(tmp_path / "first")
    assert first.media.source_id == "r2-gograduate:c/a.png"
    assert len(first.queue_ids) == 2
    service.state.remember_gograduate_image_choice(first.queue_id, list(first.queue_ids))
    storage.objects.append(R2Object(key="c/new.png", size=100, etag="new", last_modified=now + timedelta(days=1)))
    new = service._download_next_gograduate_image_from_r2(tmp_path / "new")
    assert new.media.source_id == "r2-gograduate:c/new.png"
    retry = service._download_next_gograduate_image_from_r2(tmp_path / "retry")
    assert retry.queue_id == new.queue_id
    service.state.remember_gograduate_image_choice(new.queue_id, list(new.queue_ids))
    pending = service._download_next_gograduate_image_from_r2(tmp_path / "pending")
    assert pending.media.source_id == "r2-gograduate:c/b.png"
    service.state.remember_gograduate_image_choice(pending.queue_id, list(pending.queue_ids))
    wrapped = service._download_next_gograduate_image_from_r2(tmp_path / "wrapped")
    assert wrapped.queue_restarted is True
    assert wrapped.media.source_id == "r2-gograduate:c/new.png"


def test_gograduate_empty_folder_fails_instead_of_using_dropradar_images(tmp_path):
    service = _service(tmp_path)
    service.r2_storage.objects = [R2Object(key="4/only-dropradar.png", size=100, etag="outside")]
    with pytest.raises(ValueError, match="GoGraduate.*prefijo 'c'"):
        service._download_next_gograduate_image_from_r2(tmp_path / "empty")
    assert service.r2_storage.downloaded_keys == []


def test_gograduate_hooks_preserve_both_requested_phrases():
    assert GOGRADUATE_HOOKS == {
        "oxford": "Un amigo que entro en Oxford me dio el consejo numero #1 para aprobar cualquier examen",
        "biomedicina": "Un amigo que se graduo en biomedicina con matricula de honor me dio el consejo numero #1 para aprobar cualquier examen",
    }


def test_gograduate_tolerates_bucket_name_in_prefix_without_reading_another_folder(tmp_path):
    service = _service(tmp_path)
    service.settings = replace(service.settings, r2_gograduate_image_prefix=" /videos/c/ ")
    selection = service._download_next_gograduate_image_from_r2(tmp_path / "fallback")
    assert selection.prefix == "c"
    assert selection.media.source_id == "r2-gograduate:c/a.png"
    assert service.r2_storage.listed_prefixes == ["videos/c/", "c/"]
