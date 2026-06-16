from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.accounts import (
    AccountsFileError,
    load_accounts,
    normalize_account,
    remove_account,
)
from app.config import get_settings
from app.models import (
    Language,
    VideoGender,
    VideoRequest,
    VideoType,
)
from app.service import VideoCreationService
from app.state import StateStore


GENDER_STATE, TYPE_STATE, LANGUAGE_STATE, LOWERCASE_STATE, STORY_PHOTO_STATE = range(5)
REGENERATE_ACCEPT = "regen:accept"
REGENERATE_SKIP_ACCOUNT = "regen:skip_account"
REGENERATE_CANCEL = "regen:cancel"
TEMPLATE_VIDEO_CREATE = "template_video:create:es"
TEMPLATE_VIDEO_CREATE_EN = "template_video:create:en"
TEMPLATE_VIDEO_CALLBACK_PATTERN = r"^template_video:create(?::(es|en))?$"

LOGGER = logging.getLogger(__name__)
TELEGRAM_SEND_ATTEMPTS = 3
TELEGRAM_SEND_RETRY_BASE_DELAY = 1.5
TELEGRAM_TEXT_LIMIT = 4096
POOL_SUMMARY_ACCOUNT_DETAIL_LIMIT = 12
POOL_SUMMARY_ERROR_DETAIL_LIMIT = 4
ACCOUNT_AUDIT_DETAIL_LIMIT = 12


def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en el archivo .env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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
            CommandHandler("story_carousel", story_carousel_command),
        ],
        states={
            GENDER_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(wizard_type, pattern=r"^wizard:type:4$"),
                CallbackQueryHandler(wizard_gender, pattern=r"^wizard:gender:"),
            ],
            TYPE_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(wizard_type, pattern=r"^wizard:type:"),
            ],
            LANGUAGE_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(wizard_language, pattern=r"^wizard:lang:"),
            ],
            LOWERCASE_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(wizard_lowercase, pattern=r"^wizard:lowercase:"),
            ],
            STORY_PHOTO_STATE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, wizard_story_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", wizard_cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("accounts", accounts_command))
    application.add_handler(CommandHandler("accounts_women", accounts_women_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("sync_women", sync_women_command))
    application.add_handler(CommandHandler("download_pool", download_pool_command))
    application.add_handler(
        CommandHandler("download_pool_women", download_pool_women_command)
    )
    application.add_handler(CommandHandler("pool", pool_command))
    application.add_handler(CommandHandler("audit_accounts", audit_accounts_command))
    application.add_handler(
        CommandHandler("audit_accounts_women", audit_accounts_women_command)
    )
    application.add_handler(CommandHandler("memory", memory_command))
    application.add_handler(CommandHandler("template_video", template_video_command))
    application.add_handler(CommandHandler("video_template", template_video_command))
    application.add_handler(wizard_handler)
    application.add_handler(CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(regenerate_choice, pattern=r"^regen:"))
    application.add_error_handler(error_handler)

    application.run_polling(drop_pending_updates=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Este bot genera videos verticales desde las cuentas de Instagram que "
        "hayas dejado en accounts.txt o accounts_women.txt.\n\n"
        "Comandos:\n"
        "/memory - ver si la memoria persiste tras redeploy\n"
        "/sync - descargar la biblioteca local de cuentas de hombres\n"
        "/sync_women - descargar la biblioteca local de cuentas de mujeres\n"
        "/download_pool - precalentar el pool rapido de fotos de hombres\n"
        "/download_pool_women - precalentar el pool rapido de fotos de mujeres\n"
        "/pool - ver stock del pool\n"
        "/audit_accounts - detectar cuentas gastadas/no aptas de hombres\n"
        "/audit_accounts_women - detectar cuentas gastadas/no aptas de mujeres\n"
        "/template_video - coger un video de R2 y aplicar la plantilla fija\n"
        "/story_carousel - crear carrusel IA comic desde una foto enviada por Telegram\n"
        "/create — elegir tipo e idioma y generar el video\n"
        "/accounts — ver las cuentas de hombres cargadas\n"
        "/accounts_women — ver las cuentas de mujeres cargadas\n"
        "/cancel — cancelar el wizard actual"
    )
    await update.effective_message.reply_text(
        message,
        reply_markup=_main_menu_markup(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Flujo:\n"
        "1. /create\n"
        "2. elige Hombres o Mujeres\n"
        "3. elige Tipo 1, Tipo 2, Tipo 3 o Tipo 4\n"
        "4. elige Español o English\n"
        "5. elige si quieres textos normales o todo en minúscula\n"
        "6. el bot usa el pool si hay stock o busca dinamicamente si falta\n\n"
        "Tipos:\n"
        "1 = historia de 7 imágenes (slide 6 = tip3_dropradar.jpg, febrero)\n"
        "2 = 4 consejos + hook (slide 3 = tip3_dropradar.jpg, tip3)\n"
        "3 = hook + herramientas para empezar dropshipping en 2026\n"
        "4 = carrusel IA estilo comic desde una imagen subida a R2 "
        "(6 escenas generadas + foto original)\n\n"
        "Las cuentas de hombres se leen de accounts.txt y las de mujeres de "
        "accounts_women.txt (una por línea). Para cambiarlas edita el archivo "
        "y guarda; se releen en cada /create.\n\n"
        "/create usa primero el pool local si hay fotos aptas. "
        "Si no hay stock, busca dinamicamente en las cuentas y guarda "
        "las fotos validas sobrantes para acelerar los siguientes videos. "
        "/download_pool y /download_pool_women quedan como precalentamiento opcional.\n\n"
        "Usa /audit_accounts o /audit_accounts_women para ver que cuentas "
        "estan gastadas, sin cache local o sin suficientes fotos aptas.\n\n"
        "Usa /template_video [prefijo-r2] para coger un MP4 de R2 y "
        "aplicarle la plantilla fija de herramientas. El MP4 final sale sin audio.\n\n"
        "Usa /memory despues de un redeploy para comprobar que fotos usadas, "
        "jobs y cuentas recientes no vuelven a cero."
    )
    await update.effective_message.reply_text(
        message,
        reply_markup=_main_menu_markup(),
    )


async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _accounts_command_for_gender(update, VideoGender.MALE)


async def accounts_women_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _accounts_command_for_gender(update, VideoGender.FEMALE)


async def _accounts_command_for_gender(
    update: Update,
    gender: VideoGender,
) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    path = _accounts_path_for_gender(settings, gender)
    try:
        accounts = load_accounts(path)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    preview = "\n".join(f"- {entry}" for entry in accounts[:20])
    suffix = "" if len(accounts) <= 20 else f"\n... y {len(accounts) - 20} más"
    await update.effective_message.reply_text(
        f"Cuentas de {_gender_label_plural(gender)} cargadas ({len(accounts)}):\n"
        f"{preview}{suffix}"
    )


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _sync_command_for_gender(update, context, VideoGender.MALE)


async def sync_women_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _sync_command_for_gender(update, context, VideoGender.FEMALE)


async def _sync_command_for_gender(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gender: VideoGender,
) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    path = _accounts_path_for_gender(settings, gender)
    try:
        accounts = load_accounts(path)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    status_message = await update.effective_message.reply_text(
        f"Sincronizando {len(accounts)} cuentas de {_gender_label_plural(gender)}. "
        "Las que ya tengan carpeta local no se descargan de nuevo."
    )
    service: VideoCreationService = context.application.bot_data["service"]
    try:
        summary = await asyncio.to_thread(service.sync_accounts, accounts)
    except Exception as error:
        LOGGER.exception("Account sync failed")
        await status_message.edit_text(f"No pude sincronizar cuentas.\n\n{error}")
        return

    ready = summary["downloaded"]
    errors = summary["errors"]
    ready_lines = [
        f"@{account}: {count} imagenes"
        for account, count in sorted(ready.items())
    ]
    error_lines = [
        f"@{account}: {message}"
        for account, message in sorted(errors.items())
    ]

    text = (
        f"Sincronizacion completada: {len(ready)}/{summary['requested']} cuentas listas.\n"
        f"Carpeta: {settings.downloads_dir}\n\n"
    )
    if ready_lines:
        text += "Listas:\n" + "\n".join(ready_lines[:20])
        if len(ready_lines) > 20:
            text += f"\n... y {len(ready_lines) - 20} mas"
    if error_lines:
        text += "\n\nErrores:\n" + "\n".join(error_lines[:8])
        if len(error_lines) > 8:
            text += f"\n... y {len(error_lines) - 8} mas"
    await status_message.edit_text(text)


async def download_pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _download_pool_command_for_gender(update, context, VideoGender.MALE)


async def download_pool_women_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _download_pool_command_for_gender(update, context, VideoGender.FEMALE)


async def _download_pool_command_for_gender(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gender: VideoGender,
) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    path = _accounts_path_for_gender(settings, gender)
    try:
        accounts = load_accounts(path)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    status_message = await update.effective_message.reply_text(
        f"Rellenando pool de {_gender_label_plural(gender)} hasta "
        f"{settings.pool_target_images} fotos aptas por tipo. "
        "Primero uso cache/local y luego reviso "
        f"hasta {settings.pool_refill_max_fresh_accounts or 'todas las'} "
        "cuentas frescas por tanda."
    )
    service: VideoCreationService = context.application.bot_data["service"]
    try:
        summary = await asyncio.to_thread(service.refill_pool, accounts)
    except Exception as error:
        LOGGER.exception("Pool refill failed")
        await status_message.edit_text(
            _fit_telegram_text(f"No pude rellenar el pool.\n\n{error}")
        )
        return

    await status_message.edit_text(_format_pool_refill_summary(summary))


async def pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return
    service: VideoCreationService = context.application.bot_data["service"]
    summary = await asyncio.to_thread(service.pool_status)
    await update.effective_message.reply_text(_format_pool_status(summary))


async def audit_accounts_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _audit_accounts_command_for_gender(update, context, VideoGender.MALE)


async def audit_accounts_women_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _audit_accounts_command_for_gender(update, context, VideoGender.FEMALE)


async def _audit_accounts_command_for_gender(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gender: VideoGender,
) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    path = _accounts_path_for_gender(settings, gender)
    try:
        accounts = load_accounts(path)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    status_message = await update.effective_message.reply_text(
        f"Revisando memoria local de {len(accounts)} cuentas de "
        f"{_gender_label_plural(gender)}. No hago scraping nuevo."
    )
    service: VideoCreationService = context.application.bot_data["service"]
    try:
        summary = await asyncio.to_thread(service.account_audit, accounts)
    except Exception as error:
        LOGGER.exception("Account audit failed")
        await status_message.edit_text(f"No pude auditar cuentas.\n\n{error}")
        return

    await status_message.edit_text(
        _format_account_audit(summary, _gender_label_plural(gender))
    )


async def template_video_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await _ensure_allowed(update):
        return

    language, raw_source = _parse_template_video_command_args(context.args or [])
    await _execute_template_video(update, context, raw_source, language)


async def template_video_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not await _ensure_allowed(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    language = _template_video_language_from_callback(query.data or "")
    await _execute_template_video(update, context, None, language)
    return ConversationHandler.END


async def _execute_template_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source: str | None,
    language: Language = Language.ES,
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if message is None or chat is None:
        return

    status_message = await message.reply_text(
        "Estoy cogiendo un video de R2 y aplicando la plantilla fija."
    )
    service: VideoCreationService = context.application.bot_data["service"]
    try:
        result = await asyncio.to_thread(
            service.create_template_video,
            source,
            language,
        )
    except Exception as error:
        LOGGER.exception("Template video generation failed")
        await status_message.edit_text(f"No pude generar el video plantilla.\n\n{error}")
        return

    await status_message.edit_text("Video listo. Enviando MP4.")
    try:
        if result.queue_restarted:
            await _send_message(
                context,
                chat.id,
                "Aviso: la cola de videos ha llegado al final y se ha reiniciado desde el principio.",
            )
        await _send_video(context, chat.id, result.video_path)
        for text in result.social_copy.messages:
            await _send_message(context, chat.id, text)
    except TelegramError as error:
        LOGGER.exception("Telegram refused the template video")
        await status_message.edit_text(f"Telegram rechazó el video.\n\n{error}")
        return
    await status_message.edit_text("Listo. Plantilla aplicada, video y textos enviados.")


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    store = StateStore(
        settings.state_dir,
        history_max_per_bucket=settings.history_max_per_bucket,
    )
    marker = store.ensure_persistence_marker()
    snapshot = store.memory_snapshot(recent_limit=10)
    accounts_line = _accounts_status_line(settings, VideoGender.MALE)
    women_accounts_line = _accounts_status_line(settings, VideoGender.FEMALE)

    recent = snapshot["recent_accounts"]
    recent_line = ", ".join(f"@{account}" for account in recent) if recent else "-"
    top_accounts = snapshot["top_accounts"]
    top_line = (
        ", ".join(f"@{account}({count})" for account, count in top_accounts)
        if top_accounts
        else "-"
    )
    marker_status = "nuevo en este arranque" if marker.get("created_now") else "existente"
    marker_id = str(marker.get("install_id") or "-")[:12]
    created_at = marker.get("created_at") or "-"
    cache_line = (
        "permanente"
        if settings.account_cache_ttl_hours <= 0
        else f"{settings.account_cache_ttl_hours}h"
    )
    service: VideoCreationService | None = context.application.bot_data.get("service")
    persistence = service.persistence_status() if service is not None else {}
    if not persistence.get("in_container"):
        storage_line = "local"
    elif persistence.get("is_expected_path") and persistence.get("is_mount"):
        storage_line = "OK (/app/data montado)"
    else:
        storage_line = f"ERROR: {persistence.get('warning') or 'storage no verificado'}"

    await update.effective_message.reply_text(
        "Memoria del bot\n"
        f"DATA_DIR: {settings.data_dir}\n"
        f"State: {snapshot['state_dir']}\n"
        f"Persistent Storage: {storage_line}\n"
        f"Marker: {marker_id} ({marker_status}, creado {created_at})\n"
        f"Cuentas hombres: {accounts_line}\n"
        f"Cuentas mujeres: {women_accounts_line}\n"
        f"Posts con foto por cuenta: {settings.max_posts_per_account}\n"
        f"Cache de cuentas: {cache_line}\n"
        f"Fotos bloqueadas: {snapshot['used_media_count']}\n"
        f"Jobs guardados: {snapshot['jobs_count']}\n"
        f"Cuentas usadas distintas: {snapshot['unique_chosen_accounts']}\n"
        f"Ultimas cuentas: {recent_line}\n"
        f"Mas repetidas: {top_line}\n\n"
        "Si despues de redeploy fotos/jobs vuelven a 0 o el marker cambia, "
        "falta Persistent Storage montado en /app/data dentro de Coolify."
    )


async def story_carousel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not await _ensure_allowed(update):
        return ConversationHandler.END
    _prepare_story_carousel_state(context)
    await update.effective_message.reply_text(
        "Mandame la foto de referencia y creo el carrusel IA estilo comic."
    )
    return STORY_PHOTO_STATE


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _ensure_allowed(update):
        return ConversationHandler.END

    settings = get_settings()
    accounts_by_gender = _load_accounts_by_gender(settings)
    context.user_data["accounts_by_gender"] = {
        gender.value: accounts
        for gender, accounts in accounts_by_gender.items()
    }

    if not any(accounts_by_gender.values()):
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Video herramientas R2 ES",
                        callback_data=TEMPLATE_VIDEO_CREATE,
                    ),
                    InlineKeyboardButton(
                        "Video tools R2 EN",
                        callback_data=TEMPLATE_VIDEO_CREATE_EN,
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Carrusel IA R2",
                        callback_data="wizard:type:4",
                    ),
                ],
            ]
        )
        await update.effective_message.reply_text(
            (
                "Que quieres crear?\n\n"
                "No encontre cuentas cargadas, asi que por ahora estan "
                "disponibles el video de herramientas R2 y el carrusel IA desde R2."
            ),
            reply_markup=keyboard,
        )
        return GENDER_STATE

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Video herramientas R2 ES",
                    callback_data=TEMPLATE_VIDEO_CREATE,
                ),
                InlineKeyboardButton(
                    "Video tools R2 EN",
                    callback_data=TEMPLATE_VIDEO_CREATE_EN,
                ),
            ],
            [
                InlineKeyboardButton(
                    f"Hombres ({len(accounts_by_gender[VideoGender.MALE])})",
                    callback_data="wizard:gender:male",
                ),
                InlineKeyboardButton(
                    f"Mujeres ({len(accounts_by_gender[VideoGender.FEMALE])})",
                    callback_data="wizard:gender:female",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Carrusel IA R2",
                    callback_data="wizard:type:4",
                ),
            ],
        ]
    )
    await update.effective_message.reply_text(
        "Que quieres crear?",
        reply_markup=keyboard,
    )
    return GENDER_STATE


async def wizard_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_gender = query.data.rsplit(":", maxsplit=1)[-1]
    try:
        gender = VideoGender(raw_gender)
    except ValueError:
        await query.edit_message_text("Opción no reconocida. Lanza /create otra vez.")
        return ConversationHandler.END

    accounts_by_gender = context.user_data.get("accounts_by_gender")
    if not isinstance(accounts_by_gender, dict):
        await query.edit_message_text(
            "Perdí las cuentas cargadas. Lanza /create otra vez."
        )
        return ConversationHandler.END

    accounts = list(accounts_by_gender.get(gender.value) or [])
    if not accounts:
        path = _accounts_path_for_gender(get_settings(), gender)
        await query.edit_message_text(
            f"No hay cuentas de {_gender_label_plural(gender)} en {path}. "
            "Añade enlaces, guarda el archivo y lanza /create otra vez."
        )
        return ConversationHandler.END

    context.user_data["video_gender"] = gender.value
    context.user_data["accounts_snapshot"] = accounts

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Tipo 1", callback_data="wizard:type:1"),
                InlineKeyboardButton("Tipo 2", callback_data="wizard:type:2"),
                InlineKeyboardButton("Tipo 3", callback_data="wizard:type:3"),
            ],
            [
                InlineKeyboardButton(
                    "Tipo 4 - Carrusel IA",
                    callback_data="wizard:type:4",
                ),
            ]
        ]
    )
    await query.edit_message_text(
        f"Tengo {len(accounts)} cuentas de {_gender_label_plural(gender)} cargadas. "
        "¿Qué tipo de video quieres generar?",
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

    if raw_type == VideoType.TYPE_4.value:
        raw_gender = context.user_data.get("video_gender", VideoGender.MALE.value)
        try:
            gender = VideoGender(raw_gender)
        except ValueError:
            gender = VideoGender.MALE
        await query.edit_message_text(
            "Perfecto. Cojo la siguiente imagen de R2 y creo el carrusel IA estilo comic."
        )
        request = VideoRequest(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            video_type=VideoType.TYPE_4,
            language=Language.ES,
            account_inputs=[],
            gender=gender,
            lowercase_text=False,
        )
        await _execute_job(update, context, request)
        _clear_wizard_state(context)
        return ConversationHandler.END

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
        Language(raw_lang)
    except ValueError:
        await query.edit_message_text("Idioma no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END
    context.user_data["language"] = raw_lang

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Normal", callback_data="wizard:lowercase:no"),
                InlineKeyboardButton("Todo minúscula", callback_data="wizard:lowercase:yes"),
            ]
        ]
    )
    await query.edit_message_text(
        "¿Quieres mantener mayúsculas normales o mandar todos los textos y títulos en minúscula?",
        reply_markup=keyboard,
    )
    return LOWERCASE_STATE


async def wizard_lowercase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_lowercase = query.data.rsplit(":", maxsplit=1)[-1]
    if raw_lowercase not in {"yes", "no"}:
        await query.edit_message_text("Opción no reconocida. Lanza /create otra vez.")
        return ConversationHandler.END
    lowercase_text = raw_lowercase == "yes"

    raw_lang = context.user_data.get("language")
    if not raw_lang:
        await query.edit_message_text(
            "Perdí el idioma elegido. Lanza /create otra vez."
        )
        return ConversationHandler.END

    try:
        language = Language(raw_lang)
    except ValueError:
        await query.edit_message_text("Idioma no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END

    raw_type = context.user_data.get("video_type")
    raw_gender = context.user_data.get("video_gender", VideoGender.MALE.value)
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
    try:
        gender = VideoGender(raw_gender)
    except ValueError:
        await query.edit_message_text(
            "Protagonista no válido. Lanza /create otra vez."
        )
        return ConversationHandler.END

    request = VideoRequest(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        video_type=video_type,
        language=language,
        account_inputs=list(accounts),
        gender=gender,
        lowercase_text=lowercase_text,
    )

    lowercase_line = "todo en minúscula" if lowercase_text else "formato normal"
    await query.edit_message_text(
        f"Preparando video de {_gender_label_plural(gender)} tipo "
        f"{video_type.value} en {language.value} "
        f"con {len(accounts)} cuentas ({lowercase_line})."
    )
    await _execute_job(update, context, request)
    _clear_wizard_state(context)
    return ConversationHandler.END


async def wizard_story_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not await _ensure_allowed(update):
        return ConversationHandler.END
    message = update.effective_message
    if message is None:
        return STORY_PHOTO_STATE

    try:
        reference_path = await _download_story_reference_photo(update, context)
    except Exception as error:
        LOGGER.exception("Story reference photo download failed")
        await message.reply_text(f"No pude descargar la foto.\n\n{error}")
        return STORY_PHOTO_STATE

    request = VideoRequest(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        video_type=VideoType.TYPE_4,
        language=Language.ES,
        account_inputs=[],
        gender=VideoGender.MALE,
        lowercase_text=False,
        reference_image_path=reference_path,
    )
    await message.reply_text(
        "Foto recibida. Voy a generar las 6 escenas IA y preparar la original como cierre."
    )
    await _execute_job(update, context, request)
    _clear_wizard_state(context)
    return ConversationHandler.END


async def wizard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("Cancelado.")
    return ConversationHandler.END


async def regenerate_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return
    query = update.callback_query
    await query.answer()

    if query.data == REGENERATE_CANCEL:
        context.user_data.pop("repeat_request", None)
        await query.edit_message_text("Perfecto, lo dejo aquí.")
        return

    repeat_request = context.user_data.get("repeat_request")
    if not isinstance(repeat_request, dict):
        await query.edit_message_text(
            "Ya no tengo guardada la última cuenta. Lanza /create otra vez."
        )
        return

    try:
        chosen_account = repeat_request["chosen_account"]
        account_inputs = list(repeat_request.get("requested_accounts") or [])
        if not account_inputs:
            account_inputs = [chosen_account]
        gender = VideoGender(
            repeat_request.get("video_gender", VideoGender.MALE.value)
        )
        removed_from_file = 0
        accounts_path = _accounts_path_for_gender(get_settings(), gender)
        if query.data == REGENERATE_SKIP_ACCOUNT:
            removed_from_file = await asyncio.to_thread(
                remove_account,
                accounts_path,
                chosen_account,
            )
            account_inputs = _remove_account_from_inputs(account_inputs, chosen_account)
            if not account_inputs:
                try:
                    account_inputs = await asyncio.to_thread(
                        load_accounts,
                        accounts_path,
                    )
                except AccountsFileError:
                    account_inputs = []
        request = VideoRequest(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            video_type=VideoType(repeat_request["video_type"]),
            language=Language(repeat_request["language"]),
            account_inputs=account_inputs,
            gender=gender,
            skip_accounts=(
                [chosen_account]
                if query.data == REGENERATE_SKIP_ACCOUNT
                else []
            ),
            lowercase_text=bool(repeat_request.get("lowercase_text", False)),
        )
    except (AccountsFileError, KeyError, ValueError):
        context.user_data.pop("repeat_request", None)
        await query.edit_message_text(
            "No pude recuperar bien la última selección. Lanza /create otra vez."
        )
        return

    if query.data == REGENERATE_SKIP_ACCOUNT:
        service: VideoCreationService = context.application.bot_data["service"]
        removed = await asyncio.to_thread(
            service.exclude_account,
            chosen_account,
        )
        context.user_data.pop("repeat_request", None)
        context.user_data["accounts_snapshot"] = list(request.account_inputs)
        if not request.account_inputs:
            await query.edit_message_text(
                f"Elimine @{chosen_account} de {accounts_path.name} y del pool "
                f"({removed} fotos quitadas). No quedan mas cuentas cargadas."
            )
            return
        file_line = (
            f"Elimine @{chosen_account} de {accounts_path.name}"
            if removed_from_file
            else f"@{chosen_account} ya no estaba en {accounts_path.name}"
        )
        await query.edit_message_text(
            f"{file_line}. Tambien quite sus fotos del pool "
            f"({removed} fotos quitadas) y busco la siguiente cuenta."
        )
        await _execute_job(update, context, request)
    else:
        await query.edit_message_text(
            f"Buscando una imagen distinta de @{repeat_request['chosen_account']}."
        )
        extra_request = VideoRequest(
            chat_id=request.chat_id,
            user_id=request.user_id,
            video_type=request.video_type,
            language=request.language,
            account_inputs=[repeat_request["chosen_account"]],
            gender=request.gender,
            lowercase_text=request.lowercase_text,
        )
        await _execute_extra_image(update, context, extra_request)


async def _execute_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: VideoRequest,
) -> None:
    chat = update.effective_chat
    if request.video_type == VideoType.TYPE_4:
        status_text = (
            "Estoy generando el carrusel IA. Esto puede tardar porque son 6 escenas."
        )
    else:
        status_text = (
            "Estoy seleccionando imagenes. Uso el pool si hay stock; "
            "si no, busco dinamicamente una cuenta viable."
        )
    status_message = await context.bot.send_message(
        chat_id=chat.id,
        text=status_text,
    )
    service: VideoCreationService = context.application.bot_data["service"]

    try:
        result = await asyncio.to_thread(service.create_video, request)
    except Exception as error:
        LOGGER.exception("Video generation failed")
        await status_message.edit_text(f"No pude generar el video.\n\n{error}")
        return

    if result.video_type == VideoType.TYPE_4:
        source_label = (
            result.chosen_account
            if str(result.chosen_account).startswith("r2:")
            else "foto de referencia"
        )
        header = (
            "Carrusel IA listo\n"
            "Tipo: 4\n"
            f"Fuente: {source_label}\n"
            "Entrega: 6 escenas generadas + foto original"
        )
    else:
        header = (
            f"Cuenta elegida: @{result.chosen_account}\n"
            f"Protagonista: {_gender_label_plural(request.gender)}\n"
            f"Tipo: {result.video_type.value}\n"
            f"Idioma: {result.language.value}"
        )
    await status_message.edit_text("Enviando imágenes con su texto.")
    try:
        await _send_message(context, chat.id, header)
        for message in result.social_copy.messages:
            await _send_message(context, chat.id, message)
        await _send_slides_text_then_image(context, chat.id, result.slides)
        if result.video_type == VideoType.TYPE_4:
            return
        context.user_data["repeat_request"] = {
            "chosen_account": result.chosen_account,
            "requested_accounts": request.account_inputs,
            "video_type": result.video_type.value,
            "language": result.language.value,
            "video_gender": request.gender.value,
            "lowercase_text": request.lowercase_text,
        }
        await _ask_for_another_same_account(context, chat.id, result.chosen_account)
        if result.pool_low_stock:
            await _send_message(
                context,
                chat.id,
                (
                    "Aviso: el pool se esta quedando bajo "
                    f"({result.pool_remaining} fotos disponibles). "
                    "Puedes precalentarlo con /download_pool, pero /create "
                    "tambien puede buscar dinamicamente si hace falta."
                ),
            )
    except TelegramError as error:
        LOGGER.exception("Telegram refused the send")
        await _send_message(
            context,
            chat.id,
            text=f"Telegram rechazó el envío.\nCausa: {error}",
        )


async def _execute_extra_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: VideoRequest,
) -> None:
    chat = update.effective_chat
    status_message = await context.bot.send_message(
        chat_id=chat.id,
        text="Estoy buscando una imagen nueva de la misma cuenta.",
    )
    service: VideoCreationService = context.application.bot_data["service"]

    try:
        media = await asyncio.to_thread(service.create_extra_image, request)
    except Exception as error:
        LOGGER.exception("Extra image generation failed")
        await status_message.edit_text(f"No pude sacar otra imagen.\n\n{error}")
        return

    await status_message.edit_text(f"Te mando otra imagen de @{media.source_account}.")
    try:
        await _send_photo(context, chat.id, media.local_path)
        context.user_data["repeat_request"] = {
            "chosen_account": media.source_account,
            "requested_accounts": request.account_inputs,
            "video_type": request.video_type.value,
            "language": request.language.value,
            "video_gender": request.gender.value,
            "lowercase_text": request.lowercase_text,
        }
        await _ask_for_another_same_account(context, chat.id, media.source_account)
    except TelegramError as error:
        LOGGER.exception("Telegram refused the extra image")
        await _send_message(
            context,
            chat.id,
            text=f"Telegram rechazó la imagen.\nCausa: {error}",
        )


async def _send_message(context, chat_id: int, text: str, **kwargs):
    return await _telegram_call_with_retries(
        context.bot.send_message,
        chat_id=chat_id,
        text=text,
        **kwargs,
    )


async def _send_photo(context, chat_id: int, path):
    async def send_opened_photo(*, chat_id: int, photo_path):
        with photo_path.open("rb") as handle:
            return await context.bot.send_photo(chat_id=chat_id, photo=handle)

    return await _telegram_call_with_retries(
        send_opened_photo,
        chat_id=chat_id,
        photo_path=path,
    )


async def _send_video(context, chat_id: int, path):
    async def send_opened_video(*, chat_id: int, video_path):
        with video_path.open("rb") as handle:
            return await context.bot.send_video(
                chat_id=chat_id,
                video=handle,
                supports_streaming=True,
            )

    return await _telegram_call_with_retries(
        send_opened_video,
        chat_id=chat_id,
        video_path=path,
    )


async def _telegram_call_with_retries(call, **kwargs):
    for attempt in range(1, TELEGRAM_SEND_ATTEMPTS + 1):
        try:
            return await call(**kwargs)
        except RetryAfter as error:
            if attempt >= TELEGRAM_SEND_ATTEMPTS:
                raise
            delay = float(error.retry_after) + 0.25
            LOGGER.warning(
                "Telegram rate limit while sending; retrying in %.2fs (%d/%d)",
                delay,
                attempt,
                TELEGRAM_SEND_ATTEMPTS,
            )
            await asyncio.sleep(delay)
        except NetworkError:
            if attempt >= TELEGRAM_SEND_ATTEMPTS:
                raise
            delay = TELEGRAM_SEND_RETRY_BASE_DELAY * attempt
            LOGGER.warning(
                "Telegram network error while sending; retrying in %.2fs (%d/%d)",
                delay,
                attempt,
                TELEGRAM_SEND_ATTEMPTS,
                exc_info=True,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Telegram send retry loop finished without a result")


async def _send_slides_text_then_image(context, chat_id: int, slides) -> None:
    slides = list(slides)

    # Slide copy is embedded in the generated images for every video type.
    for slide in slides:
        path = slide.media.local_path
        if not path.exists():
            continue
        await _send_photo(context, chat_id, path)


async def _ask_for_another_same_account(context, chat_id: int, account: str) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Aceptar", callback_data=REGENERATE_ACCEPT),
                InlineKeyboardButton("Pasar cuenta", callback_data=REGENERATE_SKIP_ACCOUNT),
                InlineKeyboardButton("Cancelar", callback_data=REGENERATE_CANCEL),
            ]
        ]
    )
    await _send_message(
        context,
        chat_id,
        text=(
            f"¿Quieres otra imagen distinta de @{account} por si "
            "alguna no te convence?"
        ),
        reply_markup=keyboard,
    )


def _main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Crear video R2 ES",
                    callback_data=TEMPLATE_VIDEO_CREATE,
                ),
                InlineKeyboardButton(
                    "Create R2 video EN",
                    callback_data=TEMPLATE_VIDEO_CREATE_EN,
                ),
            ],
        ]
    )


def _template_video_language_from_callback(callback_data: str) -> Language:
    parts = callback_data.split(":")
    if parts and parts[-1] == Language.EN.value:
        return Language.EN
    return Language.ES


def _parse_template_video_command_args(args) -> tuple[Language, str | None]:
    values = [str(arg).strip() for arg in args if str(arg).strip()]
    if not values:
        return Language.ES, None
    first = values[0].lower()
    if first in {"en", "eng", "english", "ingles", "inglés"}:
        return Language.EN, " ".join(values[1:]).strip() or None
    if first in {"es", "esp", "spanish", "espanol", "español"}:
        return Language.ES, " ".join(values[1:]).strip() or None
    return Language.ES, " ".join(values).strip() or None


def _prepare_story_carousel_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["video_type"] = VideoType.TYPE_4.value
    context.user_data["language"] = Language.ES.value
    context.user_data["video_gender"] = VideoGender.MALE.value
    context.user_data["accounts_snapshot"] = []


async def _download_story_reference_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> Path:
    message = update.effective_message
    if message is None:
        raise ValueError("No encontre el mensaje con la foto.")

    suffix = ".jpg"
    telegram_file = None
    if message.photo:
        telegram_file = await message.photo[-1].get_file()
    elif message.document and message.document.mime_type:
        if not message.document.mime_type.startswith("image/"):
            raise ValueError("El documento recibido no parece ser una imagen.")
        telegram_file = await message.document.get_file()
        suffix = Path(message.document.file_name or "").suffix or ".jpg"
    if telegram_file is None:
        raise ValueError("Mandame una foto o un documento de imagen.")

    settings = get_settings()
    target_dir = settings.downloads_dir / "_story_references"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"story_reference_{uuid4().hex}{suffix.lower()}"
    await telegram_file.download_to_drive(custom_path=str(target_path))
    return target_path


def _clear_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("accounts_by_gender", None)
    context.user_data.pop("accounts_snapshot", None)
    context.user_data.pop("video_gender", None)
    context.user_data.pop("video_type", None)
    context.user_data.pop("language", None)
    context.user_data.pop("reference_image_path", None)


def _accounts_path_for_gender(settings, gender: VideoGender):
    if gender == VideoGender.FEMALE:
        return settings.women_accounts_file
    return settings.accounts_file


def _gender_label_plural(gender: VideoGender) -> str:
    return "mujeres" if gender == VideoGender.FEMALE else "hombres"


def _load_accounts_by_gender(settings) -> dict[VideoGender, list[str]]:
    accounts_by_gender: dict[VideoGender, list[str]] = {}
    for gender in VideoGender:
        try:
            accounts_by_gender[gender] = load_accounts(
                _accounts_path_for_gender(settings, gender)
            )
        except AccountsFileError:
            accounts_by_gender[gender] = []
    return accounts_by_gender


def _remove_account_from_inputs(account_inputs: list[str], account: str) -> list[str]:
    target = normalize_account(account)
    if not target:
        return list(account_inputs)
    return [item for item in account_inputs if normalize_account(item) != target]


def _accounts_status_line(settings, gender: VideoGender) -> str:
    path = _accounts_path_for_gender(settings, gender)
    try:
        accounts = load_accounts(path)
    except AccountsFileError as error:
        return f"error leyendo {path}: {error}"
    return f"{len(accounts)} desde {path}"


def _format_pool_status(summary: dict) -> str:
    by_type = summary.get("by_type", {})
    by_account = summary.get("by_account", {})
    viable = summary.get("viable_accounts_by_type", {})
    account_lines = [
        f"@{account}: {count}"
        for account, count in sorted(by_account.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    text = (
        "Pool de fotos\n"
        f"Fotos aptas para planes: {summary.get('total', 0)}\n"
        f"Fotos en disco sin usar: {summary.get('raw_total', summary.get('total', 0))}\n"
        f"Tipo 1 aptas: {by_type.get('1', 0)} "
        f"({len(viable.get('1', []))} cuentas con stock minimo)\n"
        f"Tipo 2 aptas: {by_type.get('2', 0)} "
        f"({len(viable.get('2', []))} cuentas con stock minimo)\n"
        f"Tipo 3 aptas: {by_type.get('3', 0)} "
        f"({len(viable.get('3', []))} cuentas con stock minimo)"
    )
    if account_lines:
        text += "\n\nPor cuenta con stock:\n" + "\n".join(account_lines)
    return text


def _format_pool_refill_summary(summary: dict) -> str:
    after = summary.get("after", {})
    added_by_account = summary.get("added_by_account", {})
    errors = summary.get("errors", {})
    skipped = summary.get("skipped_cooldown", [])
    refreshed = summary.get("refreshed_during_cooldown", [])
    ready_by_type = summary.get("ready_by_type", summary.get("viable_after", {}))
    lines = [
        "Pool actualizado",
        f"Objetivo minimo de fotos aptas: {summary.get('target')}",
        f"Antes aptas: {summary.get('before', {}).get('total', 0)}",
        f"Ahora aptas: {after.get('total', 0)}",
        f"En disco sin usar: {after.get('raw_total', after.get('total', 0))}",
        f"Retiradas por usadas/no aptas: {summary.get('pruned', 0)}",
        f"Nuevas guardadas: {summary.get('added', 0)}",
        (
            "Cuentas frescas revisadas: "
            f"{summary.get('fresh_attempts', len(summary.get('scraped', [])))}"
            + (
                f"/{summary.get('fresh_limit')}"
                if summary.get("fresh_limit")
                else ""
            )
        ),
        (
            "Aptas por tipo: "
            f"T1={after.get('by_type', {}).get('1', 0)}, "
            f"T2={after.get('by_type', {}).get('2', 0)}, "
            f"T3={after.get('by_type', {}).get('3', 0)}"
        ),
        (
            "Cuentas con stock minimo: "
            f"T1={len(summary.get('viable_accounts_after', {}).get('1', []))}, "
            f"T2={len(summary.get('viable_accounts_after', {}).get('2', []))}, "
            f"T3={len(summary.get('viable_accounts_after', {}).get('3', []))}"
        ),
        (
            "Stock suficiente por tipo: "
            f"T1={'si' if ready_by_type.get('1') else 'no'}, "
            f"T2={'si' if ready_by_type.get('2') else 'no'}, "
            f"T3={'si' if ready_by_type.get('3') else 'no'}"
        ),
    ]
    if added_by_account:
        added_items = sorted(added_by_account.items())
        lines.append("")
        lines.append("Cuentas revisadas:")
        for account, count in added_items[:POOL_SUMMARY_ACCOUNT_DETAIL_LIMIT]:
            valid = summary.get("valid_by_account", {}).get(account, count)
            type_counts = summary.get("valid_by_type_by_account", {}).get(account, {})
            lines.append(
                f"@{_short_summary_value(account, 48)}: {count} nuevas "
                f"({valid} guardadas; aptas para planes: "
                f"T1={type_counts.get('1', 0)}, "
                f"T2={type_counts.get('2', 0)}, "
                f"T3={type_counts.get('3', 0)})"
            )
        if len(added_items) > POOL_SUMMARY_ACCOUNT_DETAIL_LIMIT:
            lines.append(
                f"... y {len(added_items) - POOL_SUMMARY_ACCOUNT_DETAIL_LIMIT} "
                "cuentas mas"
            )
    if skipped:
        lines.append("")
        lines.append("En cooldown (saltadas sin red para no alargar):")
        lines.extend(
            f"@{_short_summary_value(account, 64)}" for account in skipped[:10]
        )
        if len(skipped) > 10:
            lines.append(f"... y {len(skipped) - 10} cuentas mas")
    if refreshed:
        lines.append("")
        lines.append("Refrescadas aunque estaban en cooldown por falta de stock:")
        lines.extend(
            f"@{_short_summary_value(account, 64)}" for account in refreshed[:10]
        )
        if len(refreshed) > 10:
            lines.append(f"... y {len(refreshed) - 10} cuentas mas")
    if summary.get("fresh_limit_reached"):
        lines.append("")
        lines.append(
            "Paré aqui para que /download_pool no se alargue demasiado. "
            "Puedes lanzarlo otra vez para precalentar otra tanda."
        )
    if errors:
        error_items = sorted(errors.items())
        lines.append("")
        lines.append("Errores:")
        for account, message in error_items[:POOL_SUMMARY_ERROR_DETAIL_LIMIT]:
            lines.append(
                f"@{_short_summary_value(account, 48)}: "
                f"{_short_summary_value(message, 180)}"
            )
        if len(error_items) > POOL_SUMMARY_ERROR_DETAIL_LIMIT:
            lines.append(
                f"... y {len(error_items) - POOL_SUMMARY_ERROR_DETAIL_LIMIT} "
                "errores mas"
            )
    if not summary.get("ready"):
        lines.append("")
        lines.append(
            "Aun no hay stock suficiente para todos los tipos, pero /create "
            "puede buscar dinamicamente si el pool no alcanza. Ejecuta "
            "/download_pool solo cuando quieras precalentar mas fotos."
        )
    return _fit_telegram_text("\n".join(lines))


def _format_account_audit(summary: dict, gender_label: str) -> str:
    rows = list(summary.get("accounts", []))
    counts = summary.get("status_counts", {})
    minimums = summary.get("minimums", {})
    priority = {
        "exhausted": 0,
        "not_viable": 1,
        "missing_cache": 2,
        "excluded": 3,
        "ready": 4,
    }
    labels = {
        "ready": "listas",
        "exhausted": "gastadas",
        "not_viable": "no aptas",
        "missing_cache": "sin cache",
        "excluded": "excluidas",
    }
    ordered = sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("status")), 99),
            -int(row.get("used", 0)),
            str(row.get("account", "")),
        ),
    )
    lines = [
        f"Diagnostico de cuentas de {gender_label}",
        f"Total revisadas: {len(rows)}",
        (
            "Resumen: "
            f"listas={counts.get('ready', 0)}, "
            f"gastadas={counts.get('exhausted', 0)}, "
            f"no aptas={counts.get('not_viable', 0)}, "
            f"sin cache={counts.get('missing_cache', 0)}, "
            f"excluidas={counts.get('excluded', 0)}"
        ),
        (
            "Minimos para poder usar una cuenta: "
            f"T1={minimums.get('1', 6)}, "
            f"T2={minimums.get('2', 4)}, "
            f"T3={minimums.get('3', 1)} fotos aptas sin usar"
        ),
    ]

    actionable = [
        row
        for row in ordered
        if str(row.get("status")) in {"exhausted", "not_viable", "missing_cache", "excluded"}
    ]
    ready = [row for row in ordered if str(row.get("status")) == "ready"]

    if actionable:
        lines.append("")
        lines.append("Para revisar/quitar primero:")
        for row in actionable[:ACCOUNT_AUDIT_DETAIL_LIMIT]:
            lines.append(_format_account_audit_row(row, labels))
        if len(actionable) > ACCOUNT_AUDIT_DETAIL_LIMIT:
            lines.append(f"... y {len(actionable) - ACCOUNT_AUDIT_DETAIL_LIMIT} mas")

    if ready:
        lines.append("")
        lines.append("Con stock util:")
        for row in ready[:ACCOUNT_AUDIT_DETAIL_LIMIT]:
            lines.append(_format_account_audit_row(row, labels))
        if len(ready) > ACCOUNT_AUDIT_DETAIL_LIMIT:
            lines.append(f"... y {len(ready) - ACCOUNT_AUDIT_DETAIL_LIMIT} mas")

    if not actionable and not ready:
        lines.append("")
        lines.append("No encontre cuentas con cache local para auditar.")

    lines.append("")
    lines.append(
        "Sin cache significa que aun no hay fotos locales suficientes para juzgar; "
        "pasa /download_pool antes de borrarlas si quieres verificarlas."
    )
    return _fit_telegram_text("\n".join(lines))


def _format_account_audit_row(row: dict, labels: dict[str, str]) -> str:
    status = str(row.get("status", ""))
    usable = row.get("usable_by_type", {})
    return (
        f"@{_short_summary_value(row.get('account', ''), 34)}: "
        f"{labels.get(status, status)}; "
        f"sin usar={row.get('available', 0)}/{row.get('total', 0)}, "
        f"usadas={row.get('used', 0)}, "
        f"aptas T1={usable.get('1', 0)} "
        f"T2={usable.get('2', 0)} "
        f"T3={usable.get('3', 0)}"
    )


def _short_summary_value(value: object, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _fit_telegram_text(text: str) -> str:
    if len(text) <= TELEGRAM_TEXT_LIMIT:
        return text
    suffix = (
        "\n\n... resumen recortado por el limite de Telegram. "
        "Consulta /pool para ver el stock actual."
    )
    return f"{text[: TELEGRAM_TEXT_LIMIT - len(suffix)].rstrip()}{suffix}"


async def _ensure_allowed(update: Update) -> bool:
    settings = get_settings()
    chat_allowed = (
        not settings.allowed_chat_ids
        or bool(
            update.effective_chat
            and update.effective_chat.id in settings.allowed_chat_ids
        )
    )
    if not chat_allowed:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Este chat no está autorizado para usar el bot."
            )
        return False

    if update.effective_user is None:
        if update.effective_message:
            await update.effective_message.reply_text(
                "No pude identificar tu cuenta de Telegram."
            )
        return False

    store = StateStore(
        settings.state_dir,
        history_max_per_bucket=settings.history_max_per_bucket,
    )
    username = update.effective_user.username or update.effective_user.full_name or ""
    if store.claim_or_check_owner(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        username=username,
    ):
        return True

    if update.effective_message:
        await update.effective_message.reply_text(
            "Este bot ya está vinculado a otra cuenta de Telegram. Usa la misma "
            "cuenta/número en tus dos móviles."
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
