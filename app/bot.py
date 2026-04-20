from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from app.accounts import AccountsFileError, load_accounts
from app.config import get_settings
from app.models import Language, VideoRequest, VideoType
from app.service import VideoCreationService


TYPE_STATE, LANGUAGE_STATE = range(2)

LOGGER = logging.getLogger(__name__)

def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en el archivo .env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    service = VideoCreationService()
    for warning in service.preflight():
        LOGGER.warning("Preflight: %s", warning)

    try:
        accounts = load_accounts(settings.accounts_file)
        LOGGER.info(
            "Loaded %d accounts from %s", len(accounts), settings.accounts_file
        )
    except AccountsFileError as error:
        LOGGER.warning("%s", error)

    application: Application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["service"] = service

    wizard_handler = ConversationHandler(
        entry_points=[
            CommandHandler("create", create_command),
            CommandHandler("wizard", create_command),
        ],
        states={
            TYPE_STATE: [CallbackQueryHandler(wizard_type, pattern=r"^wizard:type:")],
            LANGUAGE_STATE: [CallbackQueryHandler(wizard_language, pattern=r"^wizard:lang:")],
        },
        fallbacks=[CommandHandler("cancel", wizard_cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("accounts", accounts_command))
    application.add_handler(wizard_handler)
    application.add_error_handler(error_handler)

    application.run_polling(drop_pending_updates=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Este bot genera videos verticales desde las cuentas de Instagram que "
        "hayas dejado en accounts.txt.\n\n"
        "Comandos:\n"
        "/create — elegir tipo e idioma y generar el video\n"
        "/accounts — ver las cuentas cargadas\n"
        "/cancel — cancelar el wizard actual"
    )
    await update.effective_message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Flujo:\n"
        "1. /create\n"
        "2. elige Tipo 1, Tipo 2 o Tipo 3\n"
        "3. elige Español o English\n"
        "4. el bot descarga, elige imágenes y envía el video\n\n"
        "Tipos:\n"
        "1 = historia de 7 imágenes (slide 6 = imagen6.png, febrero)\n"
        "2 = 4 consejos + hook (slide 3 = imagen6.png, tip3)\n"
        "3 = hook + herramientas para empezar dropshipping en 2026\n\n"
        "Las cuentas se leen de accounts.txt (una por línea). Para cambiarlas "
        "edita ese archivo y reinicia el bot (o solo guarda, el archivo se "
        "relee en cada /create)."
    )
    await update.effective_message.reply_text(message)


async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    try:
        accounts = load_accounts(settings.accounts_file)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    preview = "\n".join(f"- {entry}" for entry in accounts[:20])
    suffix = "" if len(accounts) <= 20 else f"\n... y {len(accounts) - 20} más"
    await update.effective_message.reply_text(
        f"Cuentas cargadas ({len(accounts)}):\n{preview}{suffix}"
    )


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _ensure_allowed(update):
        return ConversationHandler.END

    settings = get_settings()
    try:
        accounts = load_accounts(settings.accounts_file)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    context.user_data["accounts_snapshot"] = accounts

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Tipo 1", callback_data="wizard:type:1"),
                InlineKeyboardButton("Tipo 2", callback_data="wizard:type:2"),
                InlineKeyboardButton("Tipo 3", callback_data="wizard:type:3"),
            ]
        ]
    )
    await update.effective_message.reply_text(
        f"Tengo {len(accounts)} cuentas cargadas. ¿Qué tipo de video quieres generar?",
        reply_markup=keyboard,
    )
    return TYPE_STATE


async def wizard_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_type = query.data.rsplit(":", maxsplit=1)[-1]
    try:
        VideoType(raw_type)
    except ValueError:
        await query.edit_message_text("Tipo no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END
    context.user_data["video_type"] = raw_type

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Español", callback_data="wizard:lang:es"),
                InlineKeyboardButton("English", callback_data="wizard:lang:en"),
            ]
        ]
    )
    await query.edit_message_text(
        "Perfecto. Ahora elige el idioma del texto.",
        reply_markup=keyboard,
    )
    return LANGUAGE_STATE


async def wizard_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_lang = query.data.rsplit(":", maxsplit=1)[-1]
    try:
        language = Language(raw_lang)
    except ValueError:
        await query.edit_message_text("Idioma no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END

    raw_type = context.user_data.get("video_type")
    accounts = context.user_data.get("accounts_snapshot")
    if not raw_type or not accounts:
        await query.edit_message_text(
            "Perdí el estado del asistente. Lanza /create otra vez."
        )
        return ConversationHandler.END

    try:
        video_type = VideoType(raw_type)
    except ValueError:
        await query.edit_message_text(
            "Tipo no válido. Lanza /create otra vez."
        )
        return ConversationHandler.END

    request = VideoRequest(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        video_type=video_type,
        language=language,
        account_inputs=list(accounts),
    )

    await query.edit_message_text(
        f"Preparando video tipo {video_type.value} en {language.value} "
        f"con {len(accounts)} cuentas."
    )
    await _execute_job(update, context, request)
    context.user_data.clear()
    return ConversationHandler.END


async def wizard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Cancelado.")
    return ConversationHandler.END


async def _execute_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: VideoRequest,
) -> None:
    chat = update.effective_chat
    status_message = await context.bot.send_message(
        chat_id=chat.id,
        text="Estoy descargando cuentas, seleccionando imágenes y montando el video. Esto puede tardar un poco.",
    )
    service: VideoCreationService = context.application.bot_data["service"]

    try:
        result = await asyncio.to_thread(service.create_video, request)
    except Exception as error:
        LOGGER.exception("Video generation failed")
        await status_message.edit_text(f"No pude generar el video.\n\n{error}")
        return

    header = (
        f"Cuenta elegida: @{result.chosen_account}\n"
        f"Tipo: {result.video_type.value}\n"
        f"Idioma: {result.language.value}"
    )
    if result.fallback_accounts:
        fallback_text = ", ".join(f"@{account}" for account in result.fallback_accounts)
        header += f"\nPaisaje fallback: {fallback_text}"

    await status_message.edit_text("Enviando imágenes con su texto.")
    try:
        await context.bot.send_message(chat_id=chat.id, text=header)
        for message in result.social_copy.messages:
            await context.bot.send_message(chat_id=chat.id, text=message)
        await _send_slides_text_then_image(context, chat.id, result.slides)
    except TelegramError as error:
        LOGGER.exception("Telegram refused the send")
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"Telegram rechazó el envío.\nCausa: {error}",
        )


async def _send_slides_text_then_image(context, chat_id: int, slides) -> None:
    # For each slide send the title (first line) as one message, the body as
    # a second message, and then the image. The hook has no title, so it goes
    # in a single message. This keeps title and body visually separated in the
    # Telegram chat, matching the format the user asked for.
    for slide in slides:
        raw = slide.text.strip() if slide.text else ""
        if raw:
            title, body = _split_title_body(raw)
            if title:
                await context.bot.send_message(chat_id=chat_id, text=title)
            if body:
                await context.bot.send_message(chat_id=chat_id, text=body)
        path = slide.media.local_path
        if not path.exists():
            continue
        with path.open("rb") as handle:
            await context.bot.send_photo(chat_id=chat_id, photo=handle)


def _split_title_body(text: str) -> tuple[str, str]:
    parts = text.split("\n", 1)
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].strip()


async def _ensure_allowed(update: Update) -> bool:
    settings = get_settings()
    if not settings.allowed_chat_ids:
        return True
    if update.effective_chat and update.effective_chat.id in settings.allowed_chat_ids:
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            "Este chat no está autorizado para usar el bot."
        )
    return False


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Unhandled bot error", exc_info=context.error)
    if not isinstance(update, Update):
        return
    target = update.effective_message
    if target is None:
        return
    try:
        await target.reply_text(
            "Se produjo un error inesperado mientras procesaba tu petición."
        )
    except TelegramError:
        pass
