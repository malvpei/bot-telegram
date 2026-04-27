import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.bot import (
    REGENERATE_ACCEPT,
    REGENERATE_CANCEL,
    REGENERATE_SKIP_ACCOUNT,
    _ask_for_another_same_account,
    _clear_wizard_state,
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


def test_type_3_slide_text_is_sent_before_image():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FakeContext()
        slide = SlidePlan(
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

        asyncio.run(_send_slides_text_then_image(context, 123, [slide]))

        assert context.bot.events == [
            ("message", "4. Payments"),
            ("message", "Manage payments securely\nUse Stripe"),
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
