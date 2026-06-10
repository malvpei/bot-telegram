import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from telegram.error import NetworkError

from app.bot import (
    REGENERATE_ACCEPT,
    REGENERATE_CANCEL,
    REGENERATE_SKIP_ACCOUNT,
    TELEGRAM_TEXT_LIMIT,
    _ask_for_another_same_account,
    _clear_wizard_state,
    _format_pool_refill_summary,
    _format_pool_status,
    _send_slides_text_then_image,
)
from app.models import ImageMetrics, MediaCandidate, SlidePlan, SlideRole


class FakeTelegramBot:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.reply_markup = None

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None) -> None:
        self.events.append(("message", text))
        self.reply_markup = reply_markup

    async def send_photo(self, *, chat_id: int, photo) -> None:
        self.events.append(("photo", Path(photo.name).name))


class FakeContext:
    def __init__(self) -> None:
        self.bot = FakeTelegramBot()
        self.user_data = {}


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


def test_type_3_sends_hook_text_but_not_tool_slide_messages():
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
            ("message", "Como empezar en Dropshipping en 2026"),
            ("photo", "slide.jpg"),
            ("photo", "slide.jpg"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_slide_text_send_retries_after_network_error():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FlakyContext()
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
        )

        with patch("app.bot.asyncio.sleep", new=_fast_sleep):
            asyncio.run(_send_slides_text_then_image(context, 123, [slide]))

        assert context.bot.events == [
            ("message", "Hook text"),
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
