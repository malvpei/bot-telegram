import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from telegram.error import NetworkError

from app.bot import (
    GENDER_STATE,
    REGENERATE_ACCEPT,
    REGENERATE_CANCEL,
    REGENERATE_SKIP_ACCOUNT,
    TELEGRAM_TEXT_LIMIT,
    TEMPLATE_VIDEO_CREATE,
    TEMPLATE_VIDEO_CREATE_EN,
    _ask_for_another_same_account,
    _clear_wizard_state,
    _format_account_audit,
    _format_pool_refill_summary,
    _format_pool_status,
    _main_menu_markup,
    _execute_template_video,
    _send_message,
    _send_slides_text_then_image,
    create_command,
)
from app.models import (
    ImageMetrics,
    MediaCandidate,
    SlidePlan,
    SlideRole,
    SocialCopy,
    TemplateVideoResult,
    VideoGender,
)


class FakeTelegramBot:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.reply_markup = None

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None) -> None:
        self.events.append(("message", text))
        self.reply_markup = reply_markup

    async def send_photo(self, *, chat_id: int, photo) -> None:
        self.events.append(("photo", Path(photo.name).name))

    async def send_video(self, *, chat_id: int, video, supports_streaming=True) -> None:
        self.events.append(("video", Path(video.name).name))


class FakeContext:
    def __init__(self) -> None:
        self.bot = FakeTelegramBot()
        self.user_data = {}


class FakeReplyMessage:
    def __init__(self) -> None:
        self.text = ""
        self.reply_markup = None

    async def reply_text(self, text: str, reply_markup=None) -> None:
        self.text = text
        self.reply_markup = reply_markup


class FakeUpdate:
    def __init__(self) -> None:
        self.effective_message = FakeReplyMessage()
        self.effective_chat = None
        self.effective_user = None


class FakeStatusMessage:
    def __init__(self) -> None:
        self.edits: list[str] = []

    async def edit_text(self, text: str) -> None:
        self.edits.append(text)


class FakeTemplateMessage:
    def __init__(self) -> None:
        self.status = FakeStatusMessage()

    async def reply_text(self, text: str):
        self.status.edits.append(text)
        return self.status


class FakeChat:
    id = 123


class FakeApplication:
    def __init__(self, service) -> None:
        self.bot_data = {"service": service}


class FakeTemplateContext(FakeContext):
    def __init__(self, service) -> None:
        super().__init__()
        self.application = FakeApplication(service)


class FakeTemplateUpdate:
    def __init__(self) -> None:
        self.effective_message = FakeTemplateMessage()
        self.effective_chat = FakeChat()


class FakeTemplateService:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path

    def create_template_video(self, source=None, language=None):
        return TemplateVideoResult(
            video_path=self.video_path,
            social_copy=SocialCopy(
                title="Titulo",
                description="Descripcion",
                hashtags=["#dropshipping"],
            ),
            queue_restarted=True,
        )


class FlakyMessageTelegramBot(FakeTelegramBot):
    def __init__(self) -> None:
        super().__init__()
        self.failures_left = 1

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None) -> None:
        if self.failures_left:
            self.failures_left -= 1
            raise NetworkError("temporary read error")
        await super().send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


class FlakyContext(FakeContext):
    def __init__(self) -> None:
        self.bot = FlakyMessageTelegramBot()
        self.user_data = {}


async def _fast_sleep(delay: float) -> None:
    return None


def test_type_3_sends_embedded_text_images_without_slide_messages():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FakeContext()
        hook_slide = SlidePlan(
            index=1,
            role=SlideRole.HOOK,
            text="Como empezar en Dropshipping en 2026",
            media=MediaCandidate(
                source_account="alpha",
                source_id="hook",
                local_path=image_path,
                permalink="",
                caption="",
                width=10,
                height=10,
                created_at="",
            ),
        )
        tool_slide = SlidePlan(
            index=4,
            role=SlideRole.TOOL_PAYMENTS,
            text="4. Payments\nManage payments securely\nUse Stripe",
            media=MediaCandidate(
                source_account="tipo3_fondo",
                source_id="bg",
                local_path=image_path,
                permalink="",
                caption="",
                width=10,
                height=10,
                created_at="",
                metrics=ImageMetrics(
                    brightness=0,
                    daylight=0,
                    sharpness=0,
                    faces=0,
                    aspect_ratio=1,
                    is_landscape=False,
                    outdoor_score=0,
                    casual_score=0,
                    luxury_score=0,
                    quality_score=0,
                ),
            ),
            fixed_asset=True,
        )

        asyncio.run(_send_slides_text_then_image(context, 123, [hook_slide, tool_slide]))

        assert context.bot.events == [
            ("photo", "slide.jpg"),
            ("photo", "slide.jpg"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_send_message_retries_after_network_error():
    context = FlakyContext()

    with patch("app.bot.asyncio.sleep", new=_fast_sleep):
        asyncio.run(_send_message(context, 123, "Hook text"))

    assert context.bot.events == [("message", "Hook text")]


def test_type_1_sends_embedded_text_image_without_slide_messages():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FakeContext()
        slide = SlidePlan(
            index=1,
            role=SlideRole.HOOK,
            text="Hook text",
            media=MediaCandidate(
                source_account="tipo1",
                source_id="img",
                local_path=image_path,
                permalink="",
                caption="",
                width=10,
                height=10,
                created_at="",
            ),
        )

        asyncio.run(_send_slides_text_then_image(context, 123, [slide]))

        assert context.bot.events == [
            ("photo", "slide.jpg"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_repeat_prompt_has_accept_and_cancel_buttons():
    context = FakeContext()

    asyncio.run(_ask_for_another_same_account(context, 123, "alpha"))

    assert context.bot.events == [
        (
            "message",
            "¿Quieres otra imagen distinta de @alpha por si alguna no te convence?",
        )
    ]
    buttons = context.bot.reply_markup.inline_keyboard[0]
    assert [button.text for button in buttons] == ["Aceptar", "Pasar cuenta", "Cancelar"]
    assert [button.callback_data for button in buttons] == [
        REGENERATE_ACCEPT,
        REGENERATE_SKIP_ACCOUNT,
        REGENERATE_CANCEL,
    ]


def test_main_menu_has_template_video_button():
    markup = _main_menu_markup()

    es_button = markup.inline_keyboard[0][0]
    en_button = markup.inline_keyboard[0][1]

    assert es_button.text == "Crear video R2 ES"
    assert es_button.callback_data == TEMPLATE_VIDEO_CREATE
    assert en_button.text == "Create R2 video EN"
    assert en_button.callback_data == TEMPLATE_VIDEO_CREATE_EN


def test_create_command_offers_template_video_without_accounts():
    async def allow(update):
        return True

    context = FakeContext()
    update = FakeUpdate()
    empty_accounts = {VideoGender.MALE: [], VideoGender.FEMALE: []}

    with patch("app.bot._ensure_allowed", allow), patch(
        "app.bot._load_accounts_by_gender",
        return_value=empty_accounts,
    ):
        state = asyncio.run(create_command(update, context))

    assert state == GENDER_STATE
    buttons = update.effective_message.reply_markup.inline_keyboard
    assert len(buttons) == 1
    assert buttons[0][0].text == "Video herramientas R2 ES"
    assert buttons[0][0].callback_data == TEMPLATE_VIDEO_CREATE
    assert buttons[0][1].text == "Video tools R2 EN"
    assert buttons[0][1].callback_data == TEMPLATE_VIDEO_CREATE_EN


def test_template_video_sends_queue_restart_warning():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        video_path = root / "template_video.mp4"
        video_path.write_bytes(b"video")
        update = FakeTemplateUpdate()
        context = FakeTemplateContext(FakeTemplateService(video_path))

        asyncio.run(_execute_template_video(update, context, None))

        events = context.bot.events
        assert events[0] == (
            "message",
            "Aviso: la cola de videos ha llegado al final y se ha reiniciado desde el principio.",
        )
        assert events[1] == ("video", "template_video.mp4")
        assert events[2:] == [
            ("message", "Titulo"),
            ("message", "Descripcion"),
            ("message", "#dropshipping"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_clear_wizard_state_keeps_repeat_request():
    context = FakeContext()
    context.user_data.update(
        {
            "accounts_snapshot": ["alpha", "beta"],
            "video_type": "1",
            "repeat_request": {"chosen_account": "alpha"},
        }
    )

    _clear_wizard_state(context)

    assert context.user_data == {"repeat_request": {"chosen_account": "alpha"}}


def test_pool_status_distinguishes_raw_photos_from_usable_plan_photos():
    text = _format_pool_status(
        {
            "total": 0,
            "raw_total": 2155,
            "by_type": {"1": 0, "2": 12, "3": 20},
            "by_account": {},
            "viable_accounts_by_type": {"1": [], "2": ["alpha"], "3": ["alpha"]},
        }
    )

    assert "Fotos aptas para planes: 0" in text
    assert "Fotos en disco sin usar: 2155" in text
    assert "Tipo 1 aptas: 0 (0 cuentas con stock minimo)" in text


def test_account_audit_summary_prioritizes_exhausted_accounts():
    text = _format_account_audit(
        {
            "accounts": [
                {
                    "account": "ready",
                    "status": "ready",
                    "total": 8,
                    "available": 8,
                    "used": 0,
                    "usable_by_type": {"1": 8, "2": 6, "3": 2},
                },
                {
                    "account": "spent",
                    "status": "exhausted",
                    "total": 6,
                    "available": 0,
                    "used": 6,
                    "usable_by_type": {"1": 0, "2": 0, "3": 0},
                },
            ],
            "status_counts": {"ready": 1, "exhausted": 1},
            "minimums": {"1": 6, "2": 4, "3": 1},
        },
        "hombres",
    )

    assert "gastadas=1" in text
    assert text.index("@spent") < text.index("@ready")
    assert "Minimos para poder usar una cuenta: T1=6, T2=4, T3=1" in text


def test_pool_refill_summary_fits_telegram_limit_with_many_accounts():
    accounts = {f"cuenta_{index:03d}": 1 for index in range(114)}
    text = _format_pool_refill_summary(
        {
            "target": 100,
            "before": {"total": 0},
            "after": {
                "total": 100,
                "raw_total": 2246,
                "by_type": {"1": 100, "2": 100, "3": 100},
            },
            "added": 100,
            "pruned": 0,
            "ready": True,
            "ready_by_type": {"1": True, "2": True, "3": True},
            "viable_accounts_after": {
                "1": ["alpha"],
                "2": ["alpha"],
                "3": ["alpha"],
            },
            "added_by_account": accounts,
            "valid_by_account": accounts,
            "valid_by_type_by_account": {
                account: {"1": 1, "2": 1, "3": 1} for account in accounts
            },
        }
    )

    assert len(text) <= TELEGRAM_TEXT_LIMIT
    assert "... y 102 cuentas mas" in text
    assert "Stock suficiente por tipo: T1=si, T2=si, T3=si" in text


def test_pool_refill_summary_bounds_long_errors_and_account_names():
    text = _format_pool_refill_summary(
        {
            "target": 100,
            "after": {"by_type": {}},
            "ready": False,
            "errors": {
                f"account_{index}" + "a" * 500: "error " + "x" * 10000
                for index in range(30)
            },
        }
    )

    assert len(text) <= TELEGRAM_TEXT_LIMIT
    assert "... y 26 errores mas" in text
    assert "Aun no hay stock suficiente" in text
