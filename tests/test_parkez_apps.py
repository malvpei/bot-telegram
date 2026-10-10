from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import pytest
from PIL import Image, ImageDraw

from app.config import get_settings
from app.models import Language, MediaCandidate, SlideRole, VideoRequest, VideoType
from app.parkez_apps import (
    APP_BY_KEY,
    PARKEZ_APP,
    PARKEZ_APPS_HOOKS,
    ROTATING_APPS,
    build_parkez_apps_social_copy,
)
from app.r2_storage import R2Object
from app.render import VideoRenderer
from app.service import VideoCreationService
from app.state import StateStore


HOOK_IDS = [str(index) for index in range(3)]
COPY_IDS = [str(index) for index in range(20)]


def test_requested_hooks_and_reference_app_store_cards_are_literal():
    assert PARKEZ_APPS_HOOKS == (
        "Si tu iphone no tienes esta apps, estas perdiendo el tiempo",
        "Apps que tu iphone  necesita para llevarte al siguiente nivel",
        "Las apps que literamente ponen la vida en modo facil",
    )
    expected = {
        "notion": ("Notion: notes, tasks, AI", "Notion Labs, Incorporated", "cloud",
                   "Te permite controlar tu tiempo y tus proyectos de una manera que ninguna app iguala"),
        "claude": ("Claude by Anthropic", "Anthropic PBC", "Update",
                   "Un gran poder conlleva una gran responsabilidad y esta app te da el poder de hacer lo que quieras"),
        "waze": ("Waze Navigation & Live Traffic", "Traffic alerts while you drive", "Get",
                 "Si conoces Google Maps, esta app es su evolución"),
        "mathway": ("Mathway", "Chegg, Inc.", "Get",
                    "Si tienes algún problema matemático que no sepas resolver, hazle una foto y lo tienes"),
    }
    assert {app.key for app in ROTATING_APPS} == {"notion", "claude", "waze", "mathway", "screenzen", "fintonic"}
    for key, metadata in expected.items():
        app = APP_BY_KEY[key]
        assert (app.title, app.subtitle, app.action, app.description) == metadata
    assert APP_BY_KEY["screenzen"].title == "ScreenZen- Screen Time Control"
    assert APP_BY_KEY["screenzen"].subtitle == "Bloquea apps, limita pantalla"
    assert APP_BY_KEY["fintonic"].title == "Fintonic | Ahorra y finánciate"
    assert APP_BY_KEY["fintonic"].subtitle == "Control de gastos y préstamos"
    assert "pausas" in APP_BY_KEY["screenzen"].description
    assert "límites" in APP_BY_KEY["screenzen"].description
    assert "gastos" in APP_BY_KEY["fintonic"].description
    assert PARKEZ_APP.description == (
        "Te indica donde habra aparcamiento gratuito libre cerca de tu destino, "
        "evitando calles con el aparcamiento lleno"
    )
    assert "garantiz" not in PARKEZ_APP.description.lower()
    assert all(app.icon_file for app in (*ROTATING_APPS, PARKEZ_APP))


@pytest.mark.parametrize("selected", [ROTATING_APPS[:3], ROTATING_APPS[3:]])
def test_twenty_social_copies_are_distinct_and_match_only_the_visible_apps(selected):
    copies = [build_parkez_apps_social_copy(PARKEZ_APPS_HOOKS[0], selected, index) for index in range(20)]
    assert len({copy.title for copy in copies}) == 20
    assert len({copy.description for copy in copies}) == 20
    expected_names = [selected[0].name, selected[1].name, "ParkEz", selected[2].name]
    absent = set(app.name for app in ROTATING_APPS) - set(expected_names)
    for copy in copies:
        assert copy.hook == PARKEZ_APPS_HOOKS[0]
        assert len(copy.messages) == 3
        assert all(len(message) <= 4096 for message in copy.messages)
        numbered_rows = [line for line in copy.description.splitlines() if line[:1].isdigit()]
        assert [row.split(". ", 1)[1].split(":", 1)[0] for row in numbered_rows] == expected_names
        assert not any(name in copy.description for name in absent)
    assert build_parkez_apps_social_copy(PARKEZ_APPS_HOOKS[0], selected, 20) == copies[0]


@pytest.mark.parametrize("apps", [(), ROTATING_APPS[:2], (ROTATING_APPS[0],) * 3, (ROTATING_APPS[0], ROTATING_APPS[1], PARKEZ_APP)])
def test_social_copy_rejects_missing_duplicate_or_promotional_app_in_rotation(apps):
    with pytest.raises(ValueError, match="tres aplicaciones distintas"):
        build_parkez_apps_social_copy(PARKEZ_APPS_HOOKS[0], apps, 0)


def _queue_inputs(image_count=7):
    return (
        [f"app-{index}" for index in range(6)],
        [f"image-{index}" for index in range(image_count)],
        HOOK_IDS,
        COPY_IDS,
    )


def test_apps_queue_peek_is_read_only_and_all_rotations_survive_restart(tmp_path):
    inputs = _queue_inputs()
    state = StateStore(tmp_path / "state")
    path = state.state_dir / "parkez_apps_queues.json"
    first = state.peek_parkez_apps_choices(*inputs)
    assert not path.exists()
    assert state.peek_parkez_apps_choices(*inputs) == first
    hooks = []
    copies = []
    previous_apps = set()
    previous_images = set()
    for index in range(20):
        choices = state.peek_parkez_apps_choices(*inputs)
        assert len(choices["app_ids"]) == len(set(choices["app_ids"])) == 3
        assert len(choices["image_ids"]) == len(set(choices["image_ids"])) == 5
        assert set(choices["app_ids"]) <= set(inputs[0])
        assert set(choices["image_ids"]) <= set(inputs[1])
        if index % 2:
            assert not previous_apps.intersection(choices["app_ids"])
        if index == 1:
            assert set(inputs[1]) - previous_images <= set(choices["image_ids"])
        previous_apps = set(choices["app_ids"])
        previous_images = set(choices["image_ids"])
        hooks.append(choices["hook_id"])
        copies.append(choices["copy_id"])
        before = path.read_bytes() if path.exists() else None
        assert state.peek_parkez_apps_choices(*inputs) == choices
        assert (path.read_bytes() if path.exists() else None) == before
        state.commit_parkez_apps_choices(choices, *inputs)
        state = StateStore(state.state_dir)
    assert hooks == [HOOK_IDS[index % 3] for index in range(20)]
    assert copies == COPY_IDS
    assert state.peek_parkez_apps_choices(*inputs)["copy_id"] == COPY_IDS[0]


@pytest.mark.parametrize("image_count", range(5, 16))
def test_background_queue_wraps_without_duplicate_photo_in_any_carousel(tmp_path, image_count):
    inputs = _queue_inputs(image_count)
    state = StateStore(tmp_path / "state")
    seen = set()
    for _ in range(image_count * 2):
        choices = state.peek_parkez_apps_choices(*inputs)
        assert len(set(choices["image_ids"])) == 5
        if seen != set(inputs[1]):
            pending = set(inputs[1]) - seen
            if len(pending) >= 5:
                assert not seen.intersection(choices["image_ids"])
            else:
                assert pending <= set(choices["image_ids"])
        seen.update(choices["image_ids"])
        state.commit_parkez_apps_choices(choices, *inputs)


def test_new_backgrounds_are_prioritized_without_resetting_app_hook_or_copy_queues(tmp_path):
    inputs = _queue_inputs(10)
    state = StateStore(tmp_path / "state")
    first = state.peek_parkez_apps_choices(*inputs)
    state.commit_parkez_apps_choices(first, *inputs)
    pending = state.peek_parkez_apps_choices(*inputs)
    changed = (inputs[0], ["new-upload"] + inputs[1], inputs[2], inputs[3])
    next_choices = state.peek_parkez_apps_choices(*changed)
    assert next_choices["image_ids"][0] == "new-upload"
    assert next_choices["app_ids"] == pending["app_ids"]
    assert next_choices["hook_id"] == pending["hook_id"]
    assert next_choices["copy_id"] == pending["copy_id"]
    assert set(next_choices["image_ids"]) - {"new-upload"} <= set(pending["image_ids"])


def test_apps_queue_commit_is_one_atomic_update_and_rejects_stale_choices(tmp_path, monkeypatch):
    inputs = _queue_inputs()
    state = StateStore(tmp_path / "state")
    choices = state.peek_parkez_apps_choices(*inputs)
    calls = []
    write = state._write_json

    def record_write(path, payload):
        calls.append(Path(path).name)
        return write(path, payload)

    monkeypatch.setattr(state, "_write_json", record_write)
    state.commit_parkez_apps_choices(choices, *inputs)
    assert calls == ["parkez_apps_queues.json"]
    before = (state.state_dir / "parkez_apps_queues.json").read_bytes()
    with pytest.raises(RuntimeError, match="cola"):
        state.commit_parkez_apps_choices(choices, *inputs)
    assert calls == ["parkez_apps_queues.json"]
    assert (state.state_dir / "parkez_apps_queues.json").read_bytes() == before


@pytest.mark.parametrize("kind,count", [(0, 2), (1, 4), (2, 0), (3, 0)])
def test_incomplete_queue_inputs_fail_without_creating_queue_file(tmp_path, kind, count):
    inputs = list(_queue_inputs())
    inputs[kind] = inputs[kind][:count]
    state = StateStore(tmp_path / "state")
    with pytest.raises(ValueError, match="Apps iPhone"):
        state.peek_parkez_apps_choices(*inputs)
    assert not (state.state_dir / "parkez_apps_queues.json").exists()


class AppsR2Storage:
    is_configured = True

    def __init__(self, count=10):
        self.objects = [R2Object(key=f"apps/{index:02}.png", size=100, etag=f"photo-{index}") for index in range(count)]
        self.objects.extend([
            R2Object(key="apps-other/outside.png", size=100, etag="outside"),
            R2Object(key="cartools/car.png", size=100, etag="car"),
            R2Object(key="c/student.png", size=100, etag="student"),
            R2Object(key="4/drop.png", size=100, etag="drop"),
        ])
        self.listed_prefixes = []
        self.downloaded_keys = []

    def list_images(self, prefix):
        self.listed_prefixes.append(prefix)
        # Deliberately return extra folders: the service must constrain results.
        return list(self.objects)

    def download(self, key, destination):
        self.downloaded_keys.append(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        color = (30, 70, 120)
        Image.new("RGB", (90, 160), color).save(destination, format="PNG")
        return destination


def _service(tmp_path, monkeypatch, count=10):
    settings = replace(get_settings(), outputs_dir=tmp_path / "outputs", state_dir=tmp_path / "state",
                       width=180, height=320, r2_bucket="videos", r2_parkez_apps_image_prefix="apps")
    service = VideoCreationService.__new__(VideoCreationService)
    service.settings = settings
    service.state = StateStore(settings.state_dir)
    service.renderer = VideoRenderer(settings)
    service.r2_storage = AppsR2Storage(count)
    service._job_lock = Lock()
    service.rendered_apps = []
    service.rendered_hooks = []

    def hook(background, text, output_path):
        service.rendered_hooks.append(text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (180, 320), "white").save(output_path, format="PNG")
        return output_path

    def app(background, metadata, output_path):
        service.rendered_apps.append(metadata)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (180, 320), "blue").save(output_path, format="PNG")
        return output_path

    monkeypatch.setattr(service.renderer, "render_parkez_apps_hook", hook)
    monkeypatch.setattr(service.renderer, "render_parkez_apps_slide", app)
    return service


def _request():
    return VideoRequest(chat_id=1, user_id=10, video_type=VideoType.PARKEZ_APPS, language=Language.ES, account_inputs=[])


def test_apps_generation_delivers_hook_three_rotating_apps_and_fixed_fourth_parkez_without_instagram(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    service.state.peek_next_cartools_image_id(["old-tools"])
    service.state.peek_next_gograduate_image_id(["old-students"])
    service.state.peek_next_parkez_advice_image_id(["old-advice"])
    other_queues = {path.name: path.read_bytes() for path in service.settings.state_dir.glob("*_queue.json")}
    all_apps = []
    for index in range(3):
        result = service.create_video(_request())
        rendered = service.rendered_apps[-4:]
        assert len(result.slides) == 5
        assert [slide.index for slide in result.slides] == list(range(1, 6))
        assert [slide.role for slide in result.slides] == [SlideRole.HOOK, SlideRole.APP_STORE, SlideRole.APP_STORE, SlideRole.PARKEZ_PROMO, SlideRole.APP_STORE]
        assert rendered[2] == PARKEZ_APP
        rotating = [rendered[0], rendered[1], rendered[3]]
        assert len({app.key for app in rotating}) == 3
        assert all(app in ROTATING_APPS for app in rotating)
        all_apps.extend(app.key for app in rotating)
        assert result.video_path is None
        assert result.video_type == VideoType.PARKEZ_APPS
        assert result.separate_slide_text is False
        assert result.fallback_accounts == []
        assert result.social_copy.hook == PARKEZ_APPS_HOOKS[index % 3]
        assert service.rendered_hooks[-1] == result.social_copy.hook
        assert result.social_copy.hook in result.script_path.read_text(encoding="utf-8")
        assert "ParkEz" in result.script_path.read_text(encoding="utf-8")
        assert service.r2_storage.listed_prefixes[-1] == "apps/"
        keys = service.r2_storage.downloaded_keys[-5:]
        assert len(keys) == len(set(keys)) == 5
        assert all(key.startswith("apps/") for key in keys)
        for slide in result.slides:
            with Image.open(slide.media.local_path) as image:
                assert image.format == "PNG"
                assert image.size == (180, 320)
        service.state = StateStore(service.settings.state_dir)
    assert len(set(all_apps[:6])) == 6
    assert service.r2_storage.downloaded_keys[:5] == [f"apps/{index:02}.png" for index in range(5)]
    assert service.r2_storage.downloaded_keys[5:10] == [f"apps/{index:02}.png" for index in range(5, 10)]
    assert service.state.read_used_media() == {}
    for name, content in other_queues.items():
        assert (service.settings.state_dir / name).read_bytes() == content


@pytest.mark.parametrize("stage", ["download", "hook", "app", "script", "log"])
def test_failed_apps_job_preserves_all_queue_bytes_and_retries_same_choices(tmp_path, monkeypatch, stage):
    service = _service(tmp_path, monkeypatch)
    service.create_video(_request())
    queue_path = service.settings.state_dir / "parkez_apps_queues.json"
    before = queue_path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("apps job failed")

    owner, method = {
        "download": (service.r2_storage, "download"),
        "hook": (service.renderer, "render_parkez_apps_hook"),
        "app": (service.renderer, "render_parkez_apps_slide"),
        "script": (service.renderer, "write_script"),
        "log": (service.state, "log_job"),
    }[stage]
    with monkeypatch.context() as patched:
        patched.setattr(owner, method, fail)
        with pytest.raises(OSError, match="apps job failed"):
            service.create_video(_request())
    assert queue_path.read_bytes() == before
    service.state = StateStore(service.settings.state_dir)
    result = service.create_video(_request())
    assert result.social_copy.hook == PARKEZ_APPS_HOOKS[1]
    assert service.r2_storage.downloaded_keys[-5:] == [f"apps/{index:02}.png" for index in range(5, 10)]


def test_failure_on_fifth_background_download_does_not_partially_advance_queue(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    service.create_video(_request())
    queue_path = service.settings.state_dir / "parkez_apps_queues.json"
    before = queue_path.read_bytes()
    download = service.r2_storage.download
    attempts = 0

    def fail_on_fifth(key, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 5:
            raise OSError("last background failed")
        return download(key, destination)

    monkeypatch.setattr(service.r2_storage, "download", fail_on_fifth)
    with pytest.raises(OSError, match="last background failed"):
        service.create_video(_request())
    assert attempts == 5
    assert queue_path.read_bytes() == before
    assert service.rendered_hooks == [PARKEZ_APPS_HOOKS[0]]


def test_unreadable_background_is_reported_without_creating_any_rotation_state(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    def unreadable(key, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.touch()
        return destination

    monkeypatch.setattr(service.r2_storage, "download", unreadable)
    with pytest.raises(ValueError, match="no se pudo abrir"):
        service.create_video(_request())
    assert not (service.settings.state_dir / "parkez_apps_queues.json").exists()
    assert service.rendered_hooks == []


@pytest.mark.parametrize("count", [0, 1, 4])
def test_apps_folder_requires_five_distinct_backgrounds_and_never_borrows_other_folders(tmp_path, monkeypatch, count):
    service = _service(tmp_path, monkeypatch, count=count)
    with pytest.raises(ValueError, match="(cinco|5).*(imagen|foto)|(imagen|foto).*(cinco|5)"):
        service.create_video(_request())
    assert service.r2_storage.downloaded_keys == []
    assert service.r2_storage.listed_prefixes == ["apps/"]
    assert not (service.settings.state_dir / "parkez_apps_queues.json").exists()


def test_duplicate_r2_content_does_not_count_as_five_different_backgrounds(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch, count=4)
    service.r2_storage.objects.append(R2Object(key="apps/copy.png", size=100, etag="photo-0"))
    with pytest.raises(ValueError, match="(cinco|5)"):
        service.create_video(_request())
    assert service.r2_storage.downloaded_keys == []


def test_r2_dedup_and_new_upload_priority_apply_to_the_five_background_batch(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    originals = [replace(obj, last_modified=now - timedelta(seconds=index)) for index, obj in enumerate(service.r2_storage.objects)]
    service.r2_storage.objects = originals + [R2Object(key="apps/copy.png", size=100, etag="photo-0", last_modified=now - timedelta(days=1))]
    service.create_video(_request())
    service.r2_storage.objects.append(R2Object(key="apps/new.png", size=100, etag="fresh", last_modified=now + timedelta(seconds=1)))
    result = service.create_video(_request())
    assert service.r2_storage.downloaded_keys[-5] == "apps/new.png"
    assert "apps/copy.png" not in service.r2_storage.downloaded_keys
    assert result.social_copy.hook == PARKEZ_APPS_HOOKS[1]
    assert len(set(service.r2_storage.downloaded_keys[-5:])) == 5


def test_apps_r2_prefix_can_include_bucket_name_without_changing_the_bucket(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch, count=5)
    service.settings = replace(service.settings, r2_parkez_apps_image_prefix=" /videos/apps/ ")
    service.create_video(_request())
    assert service.r2_storage.listed_prefixes == ["apps/"]
    assert service.settings.r2_bucket == "videos"
    assert all(key.startswith("apps/") for key in service.r2_storage.downloaded_keys)


def _background(tmp_path):
    path = tmp_path / "background.png"
    Image.new("RGB", (1080, 1920), (30, 70, 120)).save(path)
    return MediaCandidate(source_account="r2_parkez_apps", source_id="background", local_path=path,
                          permalink="", caption="", width=1080, height=1920, created_at="")


def _drawn_words_once(calls):
    # The existing caption renderer draws each line twice, one pixel apart,
    # to emulate the heavier TikTok font; this is one visible line, not two.
    return " ".join(
        text for _y, text in dict.fromkeys((xy[1], text) for xy, text, _ in calls)
    )


@pytest.mark.parametrize("app", (*ROTATING_APPS, PARKEZ_APP), ids=lambda app: app.key)
def test_every_app_has_white_store_card_real_left_icon_and_exact_separate_caption(tmp_path, monkeypatch, app):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    calls = []
    draw_text = ImageDraw.ImageDraw.text

    def record_text(draw, xy, text, *args, **kwargs):
        calls.append((xy, text, kwargs))
        return draw_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    output = tmp_path / f"{app.key}.png"
    assert renderer.render_parkez_apps_slide(_background(tmp_path), app, output) == output
    with Image.open(output) as result:
        assert result.format == "PNG"
        assert result.size == (1080, 1920)
        assert result.getpixel((0, 0)) == result.getpixel((1079, 1919)) == (30, 70, 120)
        card_top = round(1920 * 0.345)
        card_bottom = card_top + round(1080 * 0.285)
        assert result.getpixel((109, card_top + 1)) == (255, 255, 255)
        left_icon = result.crop((132, card_top + 27, 384, card_bottom - 27))
        assert len(set(left_icon.get_flattened_data())) > 40
        assert renderer._parkez_apps_icon_path(app).is_file()
        button_blue = sum(
            pixel == (0, 147, 244)
            for pixel in result.crop((422, card_bottom - 96, 900, card_bottom - 12)).get_flattened_data()
        )
        assert button_blue > (200 if app.action == "cloud" else 3000)
    header = [(xy, text, kwargs) for xy, text, kwargs in calls if xy[1] < card_bottom]
    caption = [(xy, text, kwargs) for xy, text, kwargs in calls if xy[1] >= card_bottom]
    assert " ".join(text for _, text, kwargs in header if kwargs["fill"] == (0, 0, 0)) == app.title
    assert " ".join(text for _, text, kwargs in header if kwargs["fill"] == (143, 143, 143)) == app.subtitle
    assert _drawn_words_once(caption) == app.description
    assert all(Path(kwargs["font"].path).name == "Inter-Medium.ttf" for _, _, kwargs in caption)
    # Descriptions use one Medium-weight draw per line, not artificial bold.
    assert len(caption) == len({(xy[1], text) for xy, text, _ in caption})
    title = [kwargs for _, _, kwargs in header if kwargs["fill"] == (0, 0, 0)]
    assert all(Path(kwargs["font"].path).name == "Inter-Bold.ttf" for kwargs in title)
    if app.action != "cloud":
        assert any(text == app.action and kwargs["fill"] == (255, 255, 255) for _, text, kwargs in header)
    for (x, y), text, kwargs in calls:
        bbox = ImageDraw.Draw(Image.new("RGB", (1080, 1920))).textbbox((x, y), text, font=kwargs.get("font"))
        assert 0 <= bbox[0] <= bbox[2] < 1080
        assert 0 <= bbox[1] <= bbox[3] < 1920
        if y < card_bottom:
            assert x > 384
            assert bbox[3] < card_bottom


@pytest.mark.parametrize("hook", PARKEZ_APPS_HOOKS)
def test_hook_keeps_requested_words_on_white_boxes_and_red_save_prompt(tmp_path, monkeypatch, hook):
    renderer = VideoRenderer(replace(get_settings(), width=1080, height=1920))
    calls = []
    draw_text = ImageDraw.ImageDraw.text

    def record_text(draw, xy, text, *args, **kwargs):
        calls.append((xy, text, kwargs))
        return draw_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    output = tmp_path / "hook.png"
    renderer.render_parkez_apps_hook(_background(tmp_path), hook, output)
    words = _drawn_words_once([(xy, text, kwargs) for xy, text, kwargs in calls if kwargs["fill"] == (0, 0, 0)])
    assert words.split() == hook.split()
    assert all(
        Path(kwargs["font"].path).name == "Inter-Bold.ttf"
        for _, _, kwargs in calls if kwargs["fill"] == (0, 0, 0)
    )
    save = [(xy, text, kwargs) for xy, text, kwargs in calls if text == "(Guarda esto)"]
    assert len(save) == 1
    assert save[0][2]["fill"] == (244, 59, 63)
    with Image.open(output) as result:
        assert result.format == "PNG"
        assert result.size == (1080, 1920)
        assert result.getpixel((0, 0)) == (30, 70, 120)
    for (x, y), text, kwargs in calls:
        bbox = ImageDraw.Draw(Image.new("RGB", (1080, 1920))).textbbox((x, y), text, font=kwargs.get("font"))
        assert 0 <= bbox[0] <= bbox[2] < 1080
        assert 0 <= bbox[1] <= bbox[3] < 1920


def test_missing_icon_does_not_silently_render_a_generic_icon(tmp_path):
    renderer = VideoRenderer(replace(get_settings(), root_dir=tmp_path))
    with pytest.raises(FileNotFoundError, match="icono real"):
        renderer.render_parkez_apps_slide(_background(tmp_path), APP_BY_KEY["notion"], tmp_path / "result.png")
    assert not (tmp_path / "result.png").exists()


def test_invalid_icon_filename_cannot_escape_packaged_app_assets(tmp_path):
    renderer = VideoRenderer(get_settings())
    with pytest.raises(ValueError, match="icono no válido"):
        renderer.render_parkez_apps_slide(_background(tmp_path), replace(PARKEZ_APP, icon_file="../private.png"), tmp_path / "result.png")
