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
    _execute_job,
    _format_account_audit,
    _format_pool_refill_summary,
    _format_pool_status,
    _main_menu_markup,
    regenerate_choice,
    _execute_template_video,
    _send_message,
    _send_slides_text_then_image,
    create_command,
    story_carousel_command,
    wizard_delivery,
    wizard_gender,
    wizard_type,
)
from app.config import get_settings
from app.batches import BatchItem, BatchItemKind
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


class FakeTemplateService:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path

    def create_template_video(self, source=None, language=None):
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
                count=6,
                accounts=[],
            )
        )

        assert service.request is not None
        assert service.request.account_inputs == []
        assert service.request.language == Language.ES
        assert service.request.video_type == VideoType.TYPE_4
        assert service.request.gender == VideoGender.MALE
        assert application.bot.events[0][0] == "message"
        assert "generada por IA en espanol" in application.bot.events[0][1]
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
                count=6,
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
    ), patch("app.bot._execute_job", capture_execute_job):
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
    assert buttons[1][0].text == "Historia IA desde R2"
    assert buttons[1][0].callback_data == "wizard:type:4"


def test_wizard_gender_restores_type_4_story_option():
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
    assert buttons[1][0].text == "Tipo 4 - Historia IA"
    assert buttons[1][0].callback_data == "wizard:type:4"


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


def test_type_4_button_uses_r2_without_waiting_for_photo():
    captured: dict[str, VideoRequest] = {}

    async def capture_execute_job(update, context, request):
        captured["request"] = request

    context = FakeContext()
    query = FakeRegenerateQuery("wizard:type:4")
    update = FakeRegenerateUpdate(query)

    with patch("app.bot._execute_job", capture_execute_job):
        state = asyncio.run(wizard_type(update, context))

    assert state == ConversationHandler.END
    assert "siguiente imagen de R2" in query.edited_text
    assert captured["request"].video_type == VideoType.TYPE_4
    assert captured["request"].language == Language.ES
    assert captured["request"].reference_image_path is None
    assert captured["request"].account_inputs == []
    assert context.user_data == {}


def test_story_carousel_command_waits_for_photo():
    async def allow(update):
        return True

    context = FakeContext()
    update = FakeUpdate()

    with patch("app.bot._ensure_allowed", allow):
        state = asyncio.run(story_carousel_command(update, context))

    assert state == STORY_PHOTO_STATE
    assert context.user_data["video_type"] == "4"
    assert "foto de referencia" in update.effective_message.text


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
