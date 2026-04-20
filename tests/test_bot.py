import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.bot import _send_slides_text_then_image
from app.models import ImageMetrics, MediaCandidate, SlidePlan, SlideRole


class FakeTelegramBot:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.events.append(("message", text))

    async def send_photo(self, *, chat_id: int, photo) -> None:
        self.events.append(("photo", Path(photo.name).name))


class FakeContext:
    def __init__(self) -> None:
        self.bot = FakeTelegramBot()


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
