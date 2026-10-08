from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Lock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.advice_cards import AdviceBackground
from app.config import get_settings
from app.models import Language, SlideRole, VideoRequest, VideoType
from app.parkez_advice import (
    PARKEZ_ADVICE_BACKGROUNDS,
    PARKEZ_ADVICE_DESIGN_IDS,
    PARKEZ_ADVICE_HOOK_IDS,
    PARKEZ_ADVICE_HOOKS,
    PARKEZ_ADVICE_PACK_IDS,
    PARKEZ_ADVICE_PACKS,
    PARKEZ_ADVICE_PROMO,
    PARKEZ_ADVICE_SOCIAL_COPY_IDS,
    parkez_advice_social_copy,
    parkez_advice_tips,
)
from app.r2_storage import R2Object
from app.render import ADVICE_PARKEZ_BLUE, VideoRenderer
from app.service import VideoCreationService
from app.state import StateStore


@pytest.mark.parametrize("pack_id", PARKEZ_ADVICE_PACK_IDS)
@pytest.mark.parametrize("background", PARKEZ_ADVICE_BACKGROUNDS)
def test_parkez_designs_keep_the_layout_and_use_the_real_blue_icon(pack_id, background, monkeypatch):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    blocks = []
    draw_lines = renderer._draw_left_aligned_lines

    def record_lines(draw, lines, font, **kwargs):
        blocks.append((lines, font, kwargs))
        draw_lines(draw, lines, font, **kwargs)

    monkeypatch.setattr(renderer, "_draw_left_aligned_lines", record_lines)
    tips = parkez_advice_tips(pack_id, background)
    result = renderer.render_parkez_advice_card(tips, Language.ES, background)
    draw = ImageDraw.Draw(result)
    illustrated = background == AdviceBackground.ILLUSTRATED
    count = 4 if illustrated else 5
    assert result.size == (1080, 1920)
    assert result.getpixel((0, 0)) == ((247, 247, 245) if illustrated else (229, 229, 229))
    assert len(tips) == count
    assert len(blocks) == count * 2
    assert tips[-1] == PARKEZ_ADVICE_PROMO
    assert "ParkEz" in tips[-1].title
    for index, tip in enumerate(tips):
        top = 260 + index * 374 if illustrated else 280 + index * 274
        bottom = top + (338 if illustrated else 262)
        for lines, font, kwargs in blocks[index * 2:index * 2 + 2]:
            assert kwargs["x"] == (385 if illustrated else 412)
            assert kwargs["start_y"] >= top + (24 if illustrated else 12)
            block_height = renderer._block_height(lines, font, draw, stroke_width=0, line_gap=kwargs["line_gap"])
            assert kwargs["start_y"] + block_height <= bottom - (24 if illustrated else 12)
            assert all(draw.textlength(line, font=font) <= (585 if illustrated else 596) for line in lines)
        assert " ".join(blocks[index * 2 + 1][0]) == tip.body
        assert blocks[index * 2][2]["brand_fill"] == ADVICE_PARKEZ_BLUE
    pixels = np.asarray(result).astype(int)
    icon = pixels[1488:1620, 218:350] if illustrated else pixels[1432:1582, 212:362]
    blue = (icon[..., 2] > icon[..., 0] + 25) & (icon[..., 1] > icon[..., 0] + 10)
    white = icon.min(axis=2) > 240
    assert blue.sum() > 2500
    assert white.sum() > 1000


@pytest.mark.parametrize("pack_id", PARKEZ_ADVICE_PACK_IDS)
@pytest.mark.parametrize("background", PARKEZ_ADVICE_BACKGROUNDS)
def test_twenty_parkez_copies_match_only_the_visible_tips(pack_id, background):
    copies = [parkez_advice_social_copy(pack_id, background, copy_id=copy_id) for copy_id in PARKEZ_ADVICE_SOCIAL_COPY_IDS]
    assert len(copies) == len({copy.title for copy in copies}) == len({copy.description for copy in copies}) == 20
    for copy in copies:
        assert len(copy.messages) == 3
        assert all(len(message) <= 4096 for message in copy.messages)
        assert "GoGraduate" not in copy.description
        assert "Dropradar" not in copy.description
        for tip in parkez_advice_tips(pack_id, background):
            assert tip.title in copy.description
            assert tip.body in copy.description
        if background == AdviceBackground.ILLUSTRATED:
            assert PARKEZ_ADVICE_PACKS[pack_id][3].body not in copy.description
            assert "cinco" not in copy.description
            assert "5. " not in copy.description


class ParkEzR2Storage:
    is_configured = True

    def __init__(self):
        self.objects = [
            R2Object(key="cartools/a.png", size=100, etag="a"),
            R2Object(key="cartools/b.png", size=100, etag="b"),
            R2Object(key="cartools-other/outside.png", size=100, etag="outside"),
            R2Object(key="c/student.png", size=100, etag="student"),
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
        width=width, height=height, r2_bucket="videos", r2_parkez_advice_image_prefix="cartools",
    )
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = settings
    service.state = StateStore(settings.state_dir)
    service.renderer = VideoRenderer(settings)
    service.r2_storage = ParkEzR2Storage()
    service._job_lock = Lock()
    return service


def _request():
    return VideoRequest(chat_id=1, user_id=10, video_type=VideoType.PARKEZ_ADVICE, language=Language.ES, account_inputs=[])


def test_parkez_delivers_two_images_without_consuming_tools_gograduate_or_dropradar(tmp_path):
    service = _service(tmp_path)
    state = service.state
    state.peek_next_cartools_image_id(["tools-image"])
    state.peek_next_gograduate_image_id(["student-image"])
    state.peek_next_gograduate_hook_id(["student-hook"])
    state.peek_next_type_4_image_id(["dropradar-image"])
    state.peek_next_parkez_mode3_social_copy_id(["mode3-copy"])
    other_queues = {path.name: path.read_bytes() for path in service.settings.state_dir.glob("*_queue.json")}
    for index, pack_id in enumerate(PARKEZ_ADVICE_PACK_IDS):
        result = service.create_video(_request())
        assert result.video_type == VideoType.PARKEZ_ADVICE
        assert result.language == Language.ES
        assert result.video_path is None
        assert result.separate_slide_text is False
        assert result.chosen_account == f"parkez:consejos:illustrated:{pack_id}"
        assert [slide.role for slide in result.slides] == [SlideRole.ADVICE_CARD, SlideRole.ADVICE_R2_CLEAN]
        assert result.slides[1].text == ""
        assert result.slides[1].media.source_id == f"r2-parkez-advice:cartools/{'a' if index % 2 == 0 else 'b'}.png"
        assert result.social_copy.hook == PARKEZ_ADVICE_HOOKS[PARKEZ_ADVICE_HOOK_IDS[index % 2]]
        assert result.preview_text == result.slides[0].text
        assert result.preview_text in result.script_path.read_text(encoding="utf-8")
        assert PARKEZ_ADVICE_PROMO.body in result.preview_text
        assert PARKEZ_ADVICE_PACKS[pack_id][3].body not in result.preview_text
        for slide in result.slides:
            with Image.open(slide.media.local_path) as image:
                assert image.format == "PNG"
                assert image.size == (1080, 1920)
        service.state = StateStore(service.settings.state_dir)
    assert service.r2_storage.listed_prefixes == ["cartools/"] * 4
    assert service.r2_storage.downloaded_keys == ["cartools/a.png", "cartools/b.png"] * 2
    assert service.state.read_used_media() == {}
    for name, content in other_queues.items():
        assert (service.settings.state_dir / name).read_bytes() == content


def test_eighty_parkez_titles_both_designs_per_pack_and_hooks_survive_restart(tmp_path, monkeypatch):
    service = _service(tmp_path, width=72, height=128)
    monkeypatch.setattr(service.renderer, "render_parkez_advice_card", lambda *_: Image.new("RGB", (72, 128), "white"))
    copies_by_pack = {pack_id: [] for pack_id in PARKEZ_ADVICE_PACK_IDS}
    designs_by_pack = {pack_id: set() for pack_id in PARKEZ_ADVICE_PACK_IDS}
    for index in range(80):
        pack_id = PARKEZ_ADVICE_PACK_IDS[index % 4]
        result = service.create_video(_request())
        design = PARKEZ_ADVICE_BACKGROUNDS[(index // 4) % 2]
        assert result.chosen_account == f"parkez:consejos:{design.value}:{pack_id}"
        assert result.social_copy.hook == PARKEZ_ADVICE_HOOKS[PARKEZ_ADVICE_HOOK_IDS[index % 2]]
        designs_by_pack[pack_id].add(design)
        copies_by_pack[pack_id].append(result.social_copy)
        service.state = StateStore(service.settings.state_dir)
    assert len({copy.title for copies in copies_by_pack.values() for copy in copies}) == 80
    for pack_id, copies in copies_by_pack.items():
        assert len({copy.title for copy in copies}) == len({copy.description for copy in copies}) == 20
        assert designs_by_pack[pack_id] == set(PARKEZ_ADVICE_BACKGROUNDS)
        assert service.state.peek_next_parkez_advice_social_copy_id(pack_id, PARKEZ_ADVICE_SOCIAL_COPY_IDS) == (PARKEZ_ADVICE_SOCIAL_COPY_IDS[0], True)
    assert service.create_video(_request()).social_copy == copies_by_pack[PARKEZ_ADVICE_PACK_IDS[0]][0]


@pytest.mark.parametrize("stage", ["download", "render", "normalize", "script", "log"])
def test_failed_parkez_advice_job_does_not_consume_any_queue(tmp_path, monkeypatch, stage):
    service = _service(tmp_path)
    state = service.state
    pack = state.peek_next_parkez_advice_pack_id(PARKEZ_ADVICE_PACK_IDS)[0]
    design = state.peek_next_parkez_advice_design_id(pack, PARKEZ_ADVICE_DESIGN_IDS)[0]
    hook = state.peek_next_parkez_advice_hook_id(PARKEZ_ADVICE_HOOK_IDS)[0]
    copy = state.peek_next_parkez_advice_social_copy_id(pack, PARKEZ_ADVICE_SOCIAL_COPY_IDS)[0]
    image_ids = ["videos:cartools:etag:a:100", "videos:cartools:etag:b:100"]
    image = state.peek_next_parkez_advice_image_id(image_ids)[0]

    def fail(*args, **kwargs):
        raise OSError("job failed")

    owner, method = {
        "download": (service.r2_storage, "download"),
        "render": (service.renderer, "render_parkez_advice_card"),
        "normalize": (service, "_normalize_advice_image"),
        "script": (service.renderer, "write_script"),
        "log": (state, "log_job"),
    }[stage]
    monkeypatch.setattr(owner, method, fail)
    with pytest.raises(OSError, match="job failed"):
        service.create_video(_request())
    assert state.peek_next_parkez_advice_pack_id(PARKEZ_ADVICE_PACK_IDS)[0] == pack
    assert state.peek_next_parkez_advice_design_id(pack, PARKEZ_ADVICE_DESIGN_IDS)[0] == design
    assert state.peek_next_parkez_advice_hook_id(PARKEZ_ADVICE_HOOK_IDS)[0] == hook
    assert state.peek_next_parkez_advice_social_copy_id(pack, PARKEZ_ADVICE_SOCIAL_COPY_IDS)[0] == copy
    assert state.peek_next_parkez_advice_image_id(image_ids)[0] == image


def test_parkez_image_queue_deduplicates_and_prioritizes_new_uploads(tmp_path):
    service = _service(tmp_path)
    now = datetime.now(timezone.utc)
    service.r2_storage.objects = [
        R2Object(key="cartools/a.png", size=100, etag="a", last_modified=now),
        R2Object(key="cartools/a-copy.png", size=100, etag="a", last_modified=now - timedelta(seconds=1)),
        R2Object(key="cartools/b.png", size=100, etag="b", last_modified=now - timedelta(seconds=2)),
    ]
    first = service._download_next_parkez_advice_image_from_r2(tmp_path / "first")
    assert first.media.source_id == "r2-parkez-advice:cartools/a.png"
    assert len(first.queue_ids) == 2
    service.state.remember_parkez_advice_image_choice(first.queue_id, list(first.queue_ids))
    service.r2_storage.objects.append(R2Object(key="cartools/new.png", size=100, etag="new", last_modified=now + timedelta(seconds=1)))
    new = service._download_next_parkez_advice_image_from_r2(tmp_path / "new")
    assert new.media.source_id == "r2-parkez-advice:cartools/new.png"
    assert service._download_next_parkez_advice_image_from_r2(tmp_path / "retry").queue_id == new.queue_id
    service.state.remember_parkez_advice_image_choice(new.queue_id, list(new.queue_ids))
    pending = service._download_next_parkez_advice_image_from_r2(tmp_path / "pending")
    assert pending.media.source_id == "r2-parkez-advice:cartools/b.png"
    service.state.remember_parkez_advice_image_choice(pending.queue_id, list(pending.queue_ids))
    restarted = service._download_next_parkez_advice_image_from_r2(tmp_path / "restarted")
    assert restarted.queue_restarted is True
    assert restarted.queue_id == new.queue_id


@pytest.mark.parametrize("prefix", ["missing", "carts", "cartools-empty"])
def test_empty_parkez_folder_never_uses_student_or_other_park_images(tmp_path, prefix):
    service = _service(tmp_path)
    service.settings = replace(service.settings, r2_parkez_advice_image_prefix=prefix)
    with pytest.raises(ValueError, match="ParkEz necesita al menos una imagen"):
        service._download_next_parkez_advice_image_from_r2(tmp_path / "empty")
    assert service.r2_storage.downloaded_keys == []


def test_parkez_prefix_can_include_bucket_and_have_its_own_folder(tmp_path):
    service = _service(tmp_path)
    service.settings = replace(service.settings, r2_parkez_advice_image_prefix=" /videos/park-advice/ ")
    service.r2_storage.objects.append(R2Object(key="park-advice/photo.png", size=100, etag="custom"))
    selection = service._download_next_parkez_advice_image_from_r2(tmp_path / "custom")
    assert service.r2_storage.listed_prefixes == ["videos/park-advice/", "park-advice/"]
    assert selection.media.source_id == "r2-parkez-advice:park-advice/photo.png"
    assert selection.queue_id == "videos:park-advice:etag:custom:100"


@pytest.mark.parametrize("background", PARKEZ_ADVICE_BACKGROUNDS)
def test_missing_parkez_icon_fails_instead_of_substituting_another_brand(tmp_path, background):
    renderer = VideoRenderer(replace(get_settings(), root_dir=tmp_path))
    with pytest.raises(FileNotFoundError, match="icono de ParkEz"):
        renderer.render_parkez_advice_card(parkez_advice_tips(PARKEZ_ADVICE_PACK_IDS[0], background), Language.ES, background)


@pytest.mark.parametrize("pack_id", ["../outside", "", "/tmp/pack", "Pack"])
def test_parkez_scoped_queues_reject_invalid_pack_ids(tmp_path, pack_id):
    state = StateStore(tmp_path / "state")
    with pytest.raises(ValueError, match="ParkEz no es válido"):
        state.peek_next_parkez_advice_social_copy_id(pack_id, PARKEZ_ADVICE_SOCIAL_COPY_IDS)
