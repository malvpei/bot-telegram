import asyncio
import shutil
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from telegram.error import NetworkError
from telegram.ext import ConversationHandler

from app.bot import (
    DELIVERY_STATE,
    GENDER_STATE,
    LANGUAGE_STATE,
    REGENERATE_ACCEPT,
    REGENERATE_CANCEL,
    REGENERATE_SKIP_ACCOUNT,
    STORY_PHOTO_STATE,
    TELEGRAM_TEXT_LIMIT,
    TEMPLATE_VIDEO_CREATE,
    TEMPLATE_VIDEO_CREATE_EN,
    _ask_for_another_same_account,
    _clear_wizard_state,
    _create_and_send_batch_generated_video,
    _ensure_allowed,
    _execute_job,
    _format_account_audit,
    _format_pool_refill_summary,
    _format_pool_status,
    _type_1_pool_status_for_accounts,
    _main_menu_markup,
    regenerate_choice,
    reset_photos_command,
    _execute_template_video,
    _send_message,
    _send_slides_text_then_image,
    create_command,
    createp_command,
    parkez_gender,
    story_carousel_command,
    wizard_delivery,
    wizard_advice_language,
    wizard_gender,
    wizard_story_language,
    wizard_type,
    wizard_type_5_language,
)
from app.config import get_settings
from app.batches import BatchItem, BatchItemKind
from app.state import StateStore
from app.models import (
    GenerationResult,
    ImageMetrics,
    MediaCandidate,
    SlidePlan,
    SlideRole,
    SocialCopy,
    TemplateVideoResult,
    Language,
    VideoGender,
    VideoRequest,
    VideoType,
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

    async def send_media_group(self, *, chat_id: int, media, **kwargs):
        filenames = ",".join(item.media.filename for item in media)
        self.events.append(("album", filenames))
        return tuple(media)


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
        self.bot = FakeTelegramBot()


class FakeTemplateContext(FakeContext):
    def __init__(self, service) -> None:
        super().__init__()
        self.application = FakeApplication(service)


class FakeTemplateUpdate:
    def __init__(self) -> None:
        self.effective_message = FakeTemplateMessage()
        self.effective_chat = FakeChat()
        self.effective_user = FakeUser()


class FakeTemplateService:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path

    def create_template_video(
        self,
        source=None,
        language=None,
        user_id=None,
        chat_id=None,
    ):
        return TemplateVideoResult(
            video_path=self.video_path,
            social_copy=SocialCopy(
                title="",
                description="Descripcion",
                hashtags=[
                    "#dropshipping",
                    "#ecommerce",
                    "#shopify",
                    "#dropradar",
                    "#capcut",
                ],
            ),
            queue_restarted=True,
        )


class FakePhotoResetService:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.batch_lock: asyncio.Lock | None = None
        self.batch_lock_was_held = False
        self.calls = 0
        self.account_inputs: list[str] = []

    def reset_photo_usage(self, account_inputs: list[str]) -> dict[str, object]:
        self.calls += 1
        self.account_inputs = list(account_inputs)
        if self.batch_lock is not None:
            self.batch_lock_was_held = self.batch_lock.locked()
        return {
            "reset_count": self.store.reset_used_media(),
            "restored_count": 3,
            "cached_candidates": 12,
            "accounts_with_cache": 2,
        }


class FakeRegenerateQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answered = False
        self.edited_text = ""
        self.reply_markup = None

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:
        self.edited_text = text
        self.reply_markup = reply_markup


class FakeUser:
    id = 456
    username = "tester"
    full_name = "Tester"


class FakeRegenerateUpdate:
    def __init__(self, query: FakeRegenerateQuery) -> None:
        self.callback_query = query
        self.effective_chat = FakeChat()
        self.effective_user = FakeUser()
        self.effective_message = None


class FakeRegenerateService:
    def __init__(self) -> None:
        self.excluded_accounts: list[str] = []

    def exclude_account(self, account: str) -> int:
        self.excluded_accounts.append(account)
        return 3


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


def test_type_3_sends_hook_text_message_then_clean_images():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FakeContext()
        hook_slide = SlidePlan(
            index=1,
            role=SlideRole.HOOK,
            text="Como hacer dropshipping en 2026",
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

        asyncio.run(
            _send_slides_text_then_image(
                context,
                123,
                [hook_slide, tool_slide],
                video_type=VideoType.TYPE_3,
            )
        )

        assert context.bot.events == [
            ("message", "Como hacer dropshipping en 2026"),
            ("album", "slide.jpg,slide.jpg"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_send_message_retries_after_network_error():
    context = FlakyContext()

    with patch("app.bot.asyncio.sleep", new=_fast_sleep):
        asyncio.run(_send_message(context, 123, "Hook text"))

    assert context.bot.events == [("message", "Hook text")]


def test_type_4_sends_all_story_images_as_one_album():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 4):
            image_path = root / f"slide_{index:02d}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.STORY_MCDONALD,
                    text="",
                    media=MediaCandidate(
                        source_account="ai_story",
                        source_id=f"story:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )
        context = FakeContext()

        asyncio.run(
            _send_slides_text_then_image(
                context,
                123,
                slides,
                video_type=VideoType.TYPE_4,
            )
        )

        assert context.bot.events == [
            ("album", "slide_01.jpg,slide_02.jpg,slide_03.jpg")
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_regular_carousel_sends_all_images_as_one_album():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 4):
            image_path = root / f"regular_{index:02d}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.HOOK,
                    text=f"Texto {index}",
                    media=MediaCandidate(
                        source_account="regular",
                        source_id=f"regular:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )
        context = FakeContext()

        asyncio.run(
            _send_slides_text_then_image(
                context,
                123,
                slides,
                video_type=VideoType.TYPE_1,
            )
        )

        assert context.bot.events == [
            ("album", "regular_01.jpg,regular_02.jpg,regular_03.jpg")
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_scheduled_ai_batch_needs_no_instagram_accounts():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 3):
            image_path = root / f"ai_{index}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.STORY_MCDONALD,
                    text="",
                    media=MediaCandidate(
                        source_account="ai_story",
                        source_id=f"ai:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )

        class FakeAIService:
            def __init__(self):
                self.request = None

            def create_video(self, request):
                self.request = request
                return GenerationResult(
                    video_path=None,
                    script_path=root / "script.txt",
                    preview_text="",
                    social_copy=SocialCopy(title="", description="", hashtags=[]),
                    chosen_account="r2:imagenes/reference.jpg",
                    video_type=VideoType.TYPE_4,
                    language=Language.ES,
                    fallback_accounts=[],
                    slides=slides,
                    pool_remaining=0,
                    pool_low_stock=False,
                )

        service = FakeAIService()
        application = FakeApplication(service)
        item = BatchItem(
            position=4,
            kind=BatchItemKind.AI,
            language=Language.ES,
            gender=VideoGender.MALE,
            video_type=VideoType.TYPE_4,
        )

        asyncio.run(
            _create_and_send_batch_generated_video(
                application,
                chat_id=123,
                user_id=456,
                item=item,
                count=5,
                accounts=[],
            )
        )

        assert service.request is not None
        assert service.request.account_inputs == []
        assert service.request.language == Language.ES
        assert service.request.video_type == VideoType.TYPE_4
        assert service.request.gender == VideoGender.MALE
        assert application.bot.events[0][0] == "message"
        assert "generada por IA en ES" in application.bot.events[0][1]
        assert application.bot.events[1] == ("album", "ai_1.jpg,ai_2.jpg")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_scheduled_regular_batch_sends_carousel_as_one_album():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 3):
            image_path = root / f"scheduled_{index}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.HOOK,
                    text=f"Texto {index}",
                    media=MediaCandidate(
                        source_account="regular",
                        source_id=f"scheduled:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )

        class FakeRegularService:
            def create_video(self, request):
                return GenerationResult(
                    video_path=None,
                    script_path=root / "script.txt",
                    preview_text="",
                    social_copy=SocialCopy(title="", description="", hashtags=[]),
                    chosen_account="regular",
                    video_type=VideoType.TYPE_1,
                    language=Language.ES,
                    fallback_accounts=[],
                    slides=slides,
                )

        application = FakeApplication(FakeRegularService())
        item = BatchItem(
            position=1,
            kind=BatchItemKind.GENERATED,
            language=Language.ES,
            gender=VideoGender.MALE,
            video_type=VideoType.TYPE_1,
        )

        asyncio.run(
            _create_and_send_batch_generated_video(
                application,
                chat_id=123,
                user_id=456,
                item=item,
                count=5,
                accounts=["regular"],
            )
        )

        assert application.bot.events[-1] == (
            "album",
            "scheduled_1.jpg,scheduled_2.jpg",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manual_create_sends_regular_carousel_as_one_album():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 3):
            image_path = root / f"manual_{index}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.HOOK,
                    text=f"Texto {index}",
                    media=MediaCandidate(
                        source_account="manual",
                        source_id=f"manual:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )

        class FakeManualService:
            def create_video(self, request):
                return GenerationResult(
                    video_path=None,
                    script_path=root / "script.txt",
                    preview_text="",
                    social_copy=SocialCopy(title="", description="", hashtags=[]),
                    chosen_account="manual",
                    video_type=VideoType.TYPE_1,
                    language=Language.ES,
                    fallback_accounts=[],
                    slides=slides,
                )

        class FakeManualBot(FakeTelegramBot):
            async def send_message(
                self,
                *,
                chat_id: int,
                text: str,
                reply_markup=None,
            ):
                await super().send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return FakeStatusMessage()

        context = FakeContext()
        context.bot = FakeManualBot()
        context.application = FakeApplication(FakeManualService())
        update = FakeUpdate()
        update.effective_chat = FakeChat()
        request = VideoRequest(
            chat_id=123,
            user_id=456,
            video_type=VideoType.TYPE_1,
            language=Language.ES,
            account_inputs=["manual"],
        )

        asyncio.run(_execute_job(update, context, request))

        assert ("album", "manual_1.jpg,manual_2.jpg") in context.bot.events
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manual_type_5_sends_one_title_description_four_texts_and_clean_album():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 5):
            image_path = root / f"type5_{index}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.HOOK,
                    text=f"Texto {index}",
                    media=MediaCandidate(
                        source_account="r2_type_5",
                        source_id=f"type5:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )
        social_copy = SocialCopy(
            title="Titulo elegido",
            description="Descripcion elegida",
            hashtags=["#tipo5"],
        )

        class FakeType5Service:
            def create_video(self, request):
                return GenerationResult(
                    video_path=None,
                    script_path=root / "script.txt",
                    preview_text="",
                    social_copy=social_copy,
                    chosen_account="r2:tipo4/imagenstipo4",
                    video_type=VideoType.TYPE_5,
                    language=Language.ES,
                    fallback_accounts=[],
                    slides=slides,
                    separate_slide_text=True,
                )

        class FakeType5Bot(FakeTelegramBot):
            async def send_message(
                self,
                *,
                chat_id: int,
                text: str,
                reply_markup=None,
            ):
                await super().send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return FakeStatusMessage()

        context = FakeContext()
        context.bot = FakeType5Bot()
        context.application = FakeApplication(FakeType5Service())
        update = FakeUpdate()
        update.effective_chat = FakeChat()
        request = VideoRequest(
            chat_id=123,
            user_id=456,
            video_type=VideoType.TYPE_5,
            language=Language.ES,
            account_inputs=[],
        )

        asyncio.run(_execute_job(update, context, request))

        messages = [text for event, text in context.bot.events if event == "message"]
        assert "Titulo elegido" in messages
        assert "Descripcion elegida #tipo5" in messages
        for index in range(1, 5):
            assert f"Texto {index}" in messages
        assert context.bot.events[-1] == (
            "album",
            "type5_1.jpg,type5_2.jpg,type5_3.jpg,type5_4.jpg",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_parkez_sends_clean_album_and_offers_another_photo():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        slides = []
        for index in range(1, 5):
            image_path = root / f"parkez_{index}.jpg"
            Image.new("RGB", (10, 16), (index, 30, 40)).save(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=(
                        SlideRole.PARKEZ_PROMO
                        if index == 4
                        else (SlideRole.HOOK, SlideRole.TIP1, SlideRole.TIP2)[index - 1]
                    ),
                    text=f"Texto ParkEz {index}",
                    media=MediaCandidate(
                        source_account="fixed" if index == 4 else "alpha",
                        source_id=f"parkez:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                    fixed_asset=index == 4,
                )
            )

        class FakeParkEzService:
            def create_video(self, request):
                return GenerationResult(
                    video_path=None,
                    script_path=root / "script.txt",
                    preview_text="",
                    social_copy=SocialCopy(title="", description="", hashtags=[]),
                    chosen_account="alpha",
                    video_type=VideoType.PARKEZ,
                    language=Language.ES,
                    fallback_accounts=[],
                    slides=slides,
                    separate_slide_text=True,
                )

        class FakeParkEzBot(FakeTelegramBot):
            async def send_message(
                self,
                *,
                chat_id: int,
                text: str,
                reply_markup=None,
            ):
                await super().send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return FakeStatusMessage()

        context = FakeContext()
        context.bot = FakeParkEzBot()
        context.application = FakeApplication(FakeParkEzService())
        update = FakeUpdate()
        update.effective_chat = FakeChat()
        request = VideoRequest(
            chat_id=123,
            user_id=456,
            video_type=VideoType.PARKEZ,
            language=Language.ES,
            account_inputs=["alpha"],
            gender=VideoGender.MALE,
            separate_slide_text=True,
        )

        asyncio.run(_execute_job(update, context, request))

        messages = [text for event, text in context.bot.events if event == "message"]
        assert len(messages) == 7
        assert messages[1].startswith("Carrusel ParkEz listo")
        assert messages[2:6] == [f"Texto ParkEz {index}" for index in range(1, 5)]
        assert context.bot.events[-2] == (
            "album",
            "parkez_1.jpg,parkez_2.jpg,parkez_3.jpg,parkez_4.jpg",
        )
        assert messages[-1] == (
            "¿Quieres otra imagen distinta de @alpha por si alguna no te convence?"
        )
        assert context.user_data["repeat_request"] == {
            "chosen_account": "alpha",
            "requested_accounts": ["alpha"],
            "video_type": VideoType.PARKEZ.value,
            "language": Language.ES.value,
            "video_gender": VideoGender.MALE.value,
            "lowercase_text": False,
            "separate_slide_text": True,
        }
        buttons = context.bot.reply_markup.inline_keyboard[0]
        assert [button.text for button in buttons] == [
            "Aceptar",
            "Pasar cuenta",
            "Cancelar",
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_4_album_reopens_files_and_retries_network_read_errors():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_paths = []
        slides = []
        for index in range(1, 3):
            image_path = root / f"slide_{index:02d}.jpg"
            Image.new("RGB", (10, 16), (index, 20, 30)).save(image_path)
            image_paths.append(image_path)
            slides.append(
                SlidePlan(
                    index=index,
                    role=SlideRole.STORY_MCDONALD,
                    text="",
                    media=MediaCandidate(
                        source_account="ai_story",
                        source_id=f"story:{index}",
                        local_path=image_path,
                        permalink="",
                        caption="",
                        width=10,
                        height=16,
                        created_at="",
                    ),
                )
            )

        class FlakyAlbumBot(FakeTelegramBot):
            def __init__(self):
                super().__init__()
                self.calls = 0

            async def send_media_group(self, *, chat_id: int, media, **kwargs):
                self.calls += 1
                if self.calls <= 3:
                    raise NetworkError("httpx.ReadError")
                return await super().send_media_group(
                    chat_id=chat_id,
                    media=media,
                    **kwargs,
                )

        context = FakeContext()
        context.bot = FlakyAlbumBot()

        with patch("app.bot.asyncio.sleep", new=_fast_sleep):
            asyncio.run(
                _send_slides_text_then_image(
                    context,
                    123,
                    slides,
                    video_type=VideoType.TYPE_4,
                )
            )

        assert context.bot.calls == 4
        assert context.bot.events == [("album", "slide_01.jpg,slide_02.jpg")]
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


def test_type_1_can_send_slide_text_separately_from_image():
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

        asyncio.run(
            _send_slides_text_then_image(
                context,
                123,
                [slide],
                separate_slide_text=True,
            )
        )

        assert context.bot.events == [
            ("message", "Hook text"),
            ("photo", "slide.jpg"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_1_separate_slide_text_splits_month_from_body():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FakeContext()
        slide = SlidePlan(
            index=2,
            role=SlideRole.OCTOBER,
            text="Octubre - 0€\nEmpecé con muchas ganas, pero no conseguí ventas.",
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

        asyncio.run(
            _send_slides_text_then_image(
                context,
                123,
                [slide],
                video_type=VideoType.TYPE_1,
                separate_slide_text=True,
            )
        )

        assert context.bot.events == [
            ("message", "Octubre - 0€"),
            ("message", "Empecé con muchas ganas, pero no conseguí ventas."),
            ("photo", "slide.jpg"),
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_type_2_separate_slide_text_splits_tip_title_from_body():
    root = Path(__file__).resolve().parents[1] / "data" / "_test_tmp" / f"bot-{uuid4().hex}"
    root.mkdir(parents=True)
    try:
        image_path = root / "slide.jpg"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(image_path)
        context = FakeContext()
        slide = SlidePlan(
            index=2,
            role=SlideRole.TIP1,
            text=(
                "1. Revisa el margen real\n"
                "Calcula costes, comisiones y margen antes de lanzar."
            ),
            media=MediaCandidate(
                source_account="tipo2",
                source_id="img",
                local_path=image_path,
                permalink="",
                caption="",
                width=10,
                height=10,
                created_at="",
            ),
        )

        asyncio.run(
            _send_slides_text_then_image(
                context,
                123,
                [slide],
                video_type=VideoType.TYPE_2,
                separate_slide_text=True,
            )
        )

        assert context.bot.events == [
            ("message", "1. Revisa el margen real"),
            ("message", "Calcula costes, comisiones y margen antes de lanzar."),
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


def test_parkez_accept_requests_another_photo_from_the_same_account():
    async def allow(update):
        return True

    captured = {}

    async def capture_extra_image(update, context, request):
        captured["request"] = request

    context = FakeContext()
    context.user_data["repeat_request"] = {
        "chosen_account": "alpha",
        "requested_accounts": ["alpha", "beta"],
        "video_type": VideoType.PARKEZ.value,
        "language": Language.ES.value,
        "video_gender": VideoGender.FEMALE.value,
        "lowercase_text": False,
        "separate_slide_text": True,
    }
    update = FakeRegenerateUpdate(FakeRegenerateQuery(REGENERATE_ACCEPT))

    with patch("app.bot._ensure_allowed", allow), patch(
        "app.bot._execute_extra_image",
        capture_extra_image,
    ):
        asyncio.run(regenerate_choice(update, context))

    request = captured["request"]
    assert request.video_type == VideoType.PARKEZ
    assert request.account_inputs == ["alpha"]
    assert request.gender == VideoGender.FEMALE
    assert request.separate_slide_text is True


def test_skip_account_button_removes_account_file_entry_and_uses_next_account(tmp_path):
    async def allow(update):
        return True

    captured = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    accounts_path = tmp_path / "accounts.txt"
    accounts_path.write_text(
        "@alpha\nhttps://www.instagram.com/beta/\n",
        encoding="utf-8",
    )
    settings = replace(
        get_settings(),
        accounts_file=accounts_path,
        women_accounts_file=tmp_path / "accounts_women.txt",
    )
    service = FakeRegenerateService()
    context = FakeContext()
    context.application = FakeApplication(service)
    context.user_data["repeat_request"] = {
        "chosen_account": "alpha",
        "requested_accounts": ["@alpha", "https://www.instagram.com/beta/"],
        "video_type": "1",
        "language": "es",
        "video_gender": "male",
    }
    query = FakeRegenerateQuery(REGENERATE_SKIP_ACCOUNT)
    update = FakeRegenerateUpdate(query)

    with patch("app.bot._ensure_allowed", allow), patch(
        "app.bot.get_settings",
        return_value=settings,
    ), patch("app.bot._is_owner", return_value=True), patch(
        "app.bot._execute_job",
        capture_execute_job,
    ):
        asyncio.run(regenerate_choice(update, context))

    assert query.answered is True
    assert "Elimine @alpha de accounts.txt" in query.edited_text
    assert (
        accounts_path.read_text(encoding="utf-8")
        == "https://www.instagram.com/beta/\n"
    )
    assert service.excluded_accounts == ["alpha"]
    assert captured["request"].account_inputs == ["https://www.instagram.com/beta/"]
    assert captured["request"].skip_accounts == ["alpha"]
    assert context.user_data["accounts_snapshot"] == ["https://www.instagram.com/beta/"]
    assert "repeat_request" not in context.user_data


def test_authorized_telegram_users_share_access_without_sharing_identity(tmp_path):
    settings = replace(get_settings(), state_dir=tmp_path / "state")

    class AccessUpdate:
        def __init__(self, user_id: int, chat_type: str = "private") -> None:
            self.effective_user = FakeUser()
            self.effective_user.id = user_id
            self.effective_user.username = f"user{user_id}"
            self.effective_chat = FakeChat()
            self.effective_chat.id = user_id * 10
            self.effective_chat.type = chat_type
            self.effective_message = FakeReplyMessage()

    owner_update = AccessUpdate(1)
    with patch("app.bot.get_settings", return_value=settings):
        assert asyncio.run(_ensure_allowed(owner_update))

        store = StateStore(settings.state_dir)
        store.authorize_telegram_user(user_id=2, added_by=1)
        assert asyncio.run(_ensure_allowed(AccessUpdate(2)))

        denied = AccessUpdate(3)
        assert not asyncio.run(_ensure_allowed(denied))
        assert "Tu ID es 3" in denied.effective_message.text

        group = AccessUpdate(2, chat_type="group")
        assert not asyncio.run(_ensure_allowed(group))
        assert "chat privado" in group.effective_message.text


def test_reset_photos_requires_confirmation_and_clears_usage(tmp_path):
    async def allow_admin(update):
        return True

    accounts_file = tmp_path / "accounts.txt"
    women_accounts_file = tmp_path / "accounts_women.txt"
    accounts_file.write_text("@alpha\n", encoding="utf-8")
    women_accounts_file.write_text("@beta\n@alpha\n", encoding="utf-8")
    settings = replace(
        get_settings(),
        state_dir=tmp_path / "state",
        accounts_file=accounts_file,
        women_accounts_file=women_accounts_file,
    )
    store = StateStore(settings.state_dir)
    store.reserve_media(["photo:1", "dhash:1111111111111111"], "job-1")
    service = FakePhotoResetService(store)
    context = FakeContext()
    context.application = FakeApplication(service)
    context.application.bot_data["batch_lock"] = asyncio.Lock()
    service.batch_lock = context.application.bot_data["batch_lock"]
    context.args = []
    update = FakeUpdate()

    with patch("app.bot._ensure_admin", allow_admin), patch(
        "app.bot.get_settings",
        return_value=settings,
    ):
        asyncio.run(reset_photos_command(update, context))
        assert len(store.read_used_media()) == 2
        assert "/reset_fotos confirmar" in update.effective_message.text

        context.args = ["confirmar"]
        asyncio.run(reset_photos_command(update, context))

    assert store.read_used_media() == {}
    assert "Reset completado: 2" in update.effective_message.text
    assert "restauré 3" in update.effective_message.text
    assert (settings.state_dir / "used_media_before_reset.json").exists()
    assert service.batch_lock_was_held
    assert service.account_inputs == ["alpha", "beta"]


def test_reset_photos_refuses_while_batch_is_active(tmp_path):
    async def allow_admin(update):
        return True

    async def run_command() -> tuple[StateStore, FakePhotoResetService, FakeUpdate]:
        settings = replace(get_settings(), state_dir=tmp_path / "state")
        store = StateStore(settings.state_dir)
        store.reserve_media(["photo:1"], "job-1")
        service = FakePhotoResetService(store)
        context = FakeContext()
        context.application = FakeApplication(service)
        context.args = ["confirmar"]
        update = FakeUpdate()
        lock = asyncio.Lock()
        context.application.bot_data["batch_lock"] = lock
        await lock.acquire()
        try:
            with patch("app.bot._ensure_admin", allow_admin), patch(
                "app.bot.get_settings",
                return_value=settings,
            ):
                await reset_photos_command(update, context)
        finally:
            lock.release()
        return store, service, update

    store, service, update = asyncio.run(run_command())

    assert service.calls == 0
    assert store.is_media_used("photo:1")
    assert "Hay un lote en curso" in update.effective_message.text


def test_reset_photos_does_nothing_when_admin_check_fails(tmp_path):
    async def deny_admin(update):
        return False

    settings = replace(get_settings(), state_dir=tmp_path / "state")
    store = StateStore(settings.state_dir)
    store.reserve_media(["photo:1"], "job-1")
    service = FakePhotoResetService(store)
    context = FakeContext()
    context.application = FakeApplication(service)
    context.args = ["confirmar"]

    with patch("app.bot._ensure_admin", deny_admin):
        asyncio.run(reset_photos_command(FakeUpdate(), context))

    assert service.calls == 0
    assert store.is_media_used("photo:1")


def test_non_owner_skip_does_not_mutate_shared_accounts_or_pool(tmp_path):
    async def allow(update):
        return True

    captured = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    accounts_path = tmp_path / "accounts.txt"
    accounts_path.write_text("@alpha\n@beta\n", encoding="utf-8")
    settings = replace(
        get_settings(),
        accounts_file=accounts_path,
        women_accounts_file=tmp_path / "accounts_women.txt",
    )
    service = FakeRegenerateService()
    context = FakeContext()
    context.application = FakeApplication(service)
    context.user_data["repeat_request"] = {
        "chosen_account": "alpha",
        "requested_accounts": ["alpha", "beta"],
        "video_type": "1",
        "language": "es",
        "video_gender": "male",
    }
    update = FakeRegenerateUpdate(FakeRegenerateQuery(REGENERATE_SKIP_ACCOUNT))

    with patch("app.bot._ensure_allowed", allow), patch(
        "app.bot.get_settings",
        return_value=settings,
    ), patch("app.bot._is_owner", return_value=False), patch(
        "app.bot._execute_job",
        capture_execute_job,
    ):
        asyncio.run(regenerate_choice(update, context))

    assert accounts_path.read_text(encoding="utf-8") == "@alpha\n@beta\n"
    assert service.excluded_accounts == []
    assert captured["request"].skip_accounts == ["alpha"]
    assert "pool compartido no se modifica" in update.callback_query.edited_text


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
    assert len(buttons) == 2
    assert buttons[0][0].text == "Video herramientas R2 ES"
    assert buttons[0][0].callback_data == TEMPLATE_VIDEO_CREATE
    assert buttons[0][1].text == "Video tools R2 EN"
    assert buttons[0][1].callback_data == TEMPLATE_VIDEO_CREATE_EN
    assert buttons[1][0].text == "Tipo 4 - Consejos"
    assert buttons[1][0].callback_data == "wizard:type:advice"
    assert buttons[1][1].text == "Tipo 5 - Negocios"
    assert buttons[1][1].callback_data == "wizard:type:5"


def test_create_command_hides_women_and_ai_options():
    async def allow(update):
        return True

    context = FakeContext()
    update = FakeUpdate()
    accounts = {
        VideoGender.MALE: ["alpha"],
        VideoGender.FEMALE: ["beta"],
    }

    with patch("app.bot._ensure_allowed", allow), patch(
        "app.bot._load_accounts_by_gender",
        return_value=accounts,
    ):
        state = asyncio.run(create_command(update, context))

    assert state == GENDER_STATE
    buttons = [
        button
        for row in update.effective_message.reply_markup.inline_keyboard
        for button in row
    ]
    assert any(button.callback_data == "wizard:gender:male" for button in buttons)
    assert all(button.callback_data != "wizard:gender:female" for button in buttons)
    assert all(button.callback_data != "wizard:type:4" for button in buttons)


def test_wizard_gender_offers_advice_without_ai_story():
    context = FakeContext()
    context.user_data["accounts_by_gender"] = {
        VideoGender.MALE.value: ["alpha"],
        VideoGender.FEMALE.value: [],
    }
    query = FakeRegenerateQuery("wizard:gender:male")
    update = FakeRegenerateUpdate(query)

    state = asyncio.run(wizard_gender(update, context))

    assert state != ConversationHandler.END
    buttons = query.reply_markup.inline_keyboard
    assert buttons[1][0].text == "Tipo 4 - Consejos"
    assert buttons[1][0].callback_data == "wizard:type:advice"
    assert buttons[1][1].text == "Tipo 5 - Negocios"
    assert buttons[1][1].callback_data == "wizard:type:5"
    assert all(
        button.callback_data != "wizard:type:4"
        for row in buttons
        for button in row
    )


def test_createp_offers_exactly_woman_and_man():
    async def allow(update):
        return True

    context = FakeContext()
    update = FakeUpdate()
    accounts = {
        VideoGender.MALE: ["alpha"],
        VideoGender.FEMALE: ["beta"],
    }

    with patch("app.bot._ensure_allowed", allow), patch(
        "app.bot._load_accounts_by_gender",
        return_value=accounts,
    ):
        state = asyncio.run(createp_command(update, context))

    assert state == GENDER_STATE
    buttons = update.effective_message.reply_markup.inline_keyboard
    assert [[button.text for button in row] for row in buttons] == [
        ["Mujer", "Hombre"]
    ]
    assert [[button.callback_data for button in row] for row in buttons] == [
        ["parkez:gender:female", "parkez:gender:male"]
    ]


def test_createp_gender_uses_matching_accounts_and_forces_separate_spanish_copy():
    captured: list[VideoRequest] = []

    async def capture_execute_job(update, context, request):
        captured.append(request)

    for gender, account in (
        (VideoGender.FEMALE, "beta"),
        (VideoGender.MALE, "alpha"),
    ):
        context = FakeContext()
        context.user_data["accounts_by_gender"] = {
            VideoGender.MALE.value: ["alpha"],
            VideoGender.FEMALE.value: ["beta"],
        }
        query = FakeRegenerateQuery(f"parkez:gender:{gender.value}")
        update = FakeRegenerateUpdate(query)

        with patch("app.bot._execute_job", capture_execute_job):
            state = asyncio.run(parkez_gender(update, context))

        assert state == ConversationHandler.END
        assert context.user_data == {}
        assert query.answered is True
        assert captured[-1].account_inputs == [account]
        assert captured[-1].gender == gender
        assert captured[-1].video_type == VideoType.PARKEZ
        assert captured[-1].language == Language.ES
        assert captured[-1].separate_slide_text is True


def test_wizard_type_asks_how_to_deliver_slide_text():
    context = FakeContext()
    query = FakeRegenerateQuery("wizard:type:1")
    update = FakeRegenerateUpdate(query)

    state = asyncio.run(wizard_type(update, context))

    assert state == DELIVERY_STATE
    assert context.user_data["video_type"] == "1"
    assert "texto dentro de cada imagen o separado" in query.edited_text
    buttons = query.reply_markup.inline_keyboard[0]
    assert [button.text for button in buttons] == ["Texto en imagen", "Texto separado"]
    assert [button.callback_data for button in buttons] == [
        "wizard:delivery:embedded",
        "wizard:delivery:separate",
    ]


def test_wizard_delivery_stores_separate_text_choice_and_asks_language():
    context = FakeContext()
    query = FakeRegenerateQuery("wizard:delivery:separate")
    update = FakeRegenerateUpdate(query)

    state = asyncio.run(wizard_delivery(update, context))

    assert state == LANGUAGE_STATE
    assert context.user_data["separate_slide_text"] is True
    buttons = query.reply_markup.inline_keyboard[0]
    assert [button.callback_data for button in buttons] == [
        "wizard:lang:es",
        "wizard:lang:en",
    ]


def test_type_4_button_asks_language_then_uses_r2_without_waiting_for_photo():
    captured: dict[str, VideoRequest] = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    context = FakeContext()
    query = FakeRegenerateQuery("wizard:type:4")
    update = FakeRegenerateUpdate(query)

    with patch("app.bot._execute_job", capture_execute_job):
        state = asyncio.run(wizard_type(update, context))

        assert state == LANGUAGE_STATE
        assert "idioma" in query.edited_text
        assert [button.callback_data for button in query.reply_markup.inline_keyboard[0]] == [
            "wizard:storylang:es",
            "wizard:storylang:en",
        ]

        language_query = FakeRegenerateQuery("wizard:storylang:en")
        language_update = FakeRegenerateUpdate(language_query)
        state = asyncio.run(wizard_story_language(language_update, context))

    assert state == ConversationHandler.END
    assert "siguiente imagen de R2" in language_query.edited_text
    assert captured["request"].video_type == VideoType.TYPE_4
    assert captured["request"].language == Language.EN
    assert captured["request"].reference_image_path is None
    assert captured["request"].account_inputs == []
    assert context.user_data == {}


def test_type_5_button_asks_language_and_starts_spanish_r2_carousel():
    captured: dict[str, VideoRequest] = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    context = FakeContext()
    query = FakeRegenerateQuery("wizard:type:5")
    update = FakeRegenerateUpdate(query)

    with patch("app.bot._execute_job", capture_execute_job):
        state = asyncio.run(wizard_type(update, context))

        assert state == LANGUAGE_STATE
        assert "idioma" in query.edited_text
        assert [button.callback_data for button in query.reply_markup.inline_keyboard[0]] == [
            "wizard:type5lang:es",
            "wizard:type5lang:en",
        ]

        language_query = FakeRegenerateQuery("wizard:type5lang:es")
        language_update = FakeRegenerateUpdate(language_query)
        state = asyncio.run(wizard_type_5_language(language_update, context))

    assert state == ConversationHandler.END
    assert "tres imagenes aleatorias" in language_query.edited_text
    assert "imagen fija de Dropradar" in language_query.edited_text
    assert captured["request"].video_type == VideoType.TYPE_5
    assert captured["request"].language == Language.ES
    assert captured["request"].account_inputs == []
    assert captured["request"].separate_slide_text is True
    assert context.user_data == {}


def test_type_5_language_button_starts_english_r2_carousel():
    captured: dict[str, VideoRequest] = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    context = FakeContext()
    context.user_data["video_type"] = VideoType.TYPE_5.value
    context.user_data["separate_slide_text"] = True
    query = FakeRegenerateQuery("wizard:type5lang:en")
    update = FakeRegenerateUpdate(query)

    with patch("app.bot._execute_job", capture_execute_job):
        state = asyncio.run(wizard_type_5_language(update, context))

    assert state == ConversationHandler.END
    assert "three random R2 images" in query.edited_text
    assert "fixed Dropradar image" in query.edited_text
    assert captured["request"].video_type == VideoType.TYPE_5
    assert captured["request"].language == Language.EN
    assert captured["request"].account_inputs == []
    assert captured["request"].separate_slide_text is True
    assert context.user_data == {}


def test_advice_type_4_asks_language_and_needs_no_instagram_accounts():
    captured: dict[str, VideoRequest] = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    context = FakeContext()
    query = FakeRegenerateQuery("wizard:type:advice")
    update = FakeRegenerateUpdate(query)

    with patch("app.bot._execute_job", capture_execute_job):
        state = asyncio.run(wizard_type(update, context))

        assert state == LANGUAGE_STATE
        assert "Tipo 4" in query.edited_text
        assert [
            button.callback_data
            for button in query.reply_markup.inline_keyboard[0]
        ] == [
            "wizard:advicelang:es",
            "wizard:advicelang:en",
        ]

        language_query = FakeRegenerateQuery("wizard:advicelang:en")
        language_update = FakeRegenerateUpdate(language_query)
        state = asyncio.run(wizard_advice_language(language_update, context))

    assert state == ConversationHandler.END
    assert captured["request"].video_type == VideoType.ADVICE
    assert captured["request"].language == Language.EN
    assert captured["request"].account_inputs == []
    assert captured["request"].separate_slide_text is False
    assert context.user_data == {}


def test_story_carousel_command_asks_language_then_waits_for_photo():
    async def allow(update):
        return True

    context = FakeContext()
    update = FakeUpdate()

    with patch("app.bot._ensure_allowed", allow):
        state = asyncio.run(story_carousel_command(update, context))

    assert state == LANGUAGE_STATE
    assert context.user_data["video_type"] == "4"
    assert "idioma" in update.effective_message.text

    query = FakeRegenerateQuery("wizard:storylang:en")
    language_update = FakeRegenerateUpdate(query)
    state = asyncio.run(wizard_story_language(language_update, context))

    assert state == STORY_PHOTO_STATE
    assert context.user_data["language"] == "en"
    assert "foto de referencia" in query.edited_text


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
            (
                "message",
                "Descripcion #dropshipping #ecommerce #shopify #dropradar #capcut",
            ),
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
    assert "Tipo 1 aptas: 0 (0 cuentas con combinación válida)" in text


def test_pool_status_distinguishes_type_1_stock_by_gender():
    text = _format_pool_status(
        {
            "total": 12,
            "raw_total": 20,
            "by_type": {"1": 12, "2": 0, "3": 0},
            "by_account": {},
            "viable_accounts_by_type": {
                "1": ["man", "woman"],
                "2": [],
                "3": [],
            },
            "by_gender": {
                VideoGender.MALE.value: {
                    "by_type": {"1": 6},
                    "viable_accounts_by_type": {"1": ["man"]},
                },
                VideoGender.FEMALE.value: {
                    "by_type": {"1": 6},
                    "viable_accounts_by_type": {"1": ["woman"]},
                },
            },
        }
    )

    assert "Pool de fotos (global)" in text
    assert "Hombres: 6 fotos (1 cuenta capaz de generar ahora)" in text
    assert "Mujeres: 6 fotos (1 cuenta capaz de generar ahora)" in text


def test_type_1_pool_status_filters_accounts_from_instagram_urls():
    filtered = _type_1_pool_status_for_accounts(
        {
            "by_type_by_account": {
                "man": {"1": 7},
                "woman": {"1": 9},
                "old": {"1": 12},
            },
            "viable_accounts_by_type": {
                "1": ["man", "woman", "old"],
            },
        },
        ["https://www.instagram.com/man/?hl=es", "@woman"],
    )

    assert filtered["by_type"] == {"1": 16}
    assert filtered["viable_accounts_by_type"] == {"1": ["man", "woman"]}


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
