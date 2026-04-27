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
from app.state import StateStore


TYPE_STATE, LANGUAGE_STATE = range(2)
REGENERATE_ACCEPT = "regen:accept"
REGENERATE_SKIP_ACCOUNT = "regen:skip_account"
REGENERATE_CANCEL = "regen:cancel"

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
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("download_pool", download_pool_command))
    application.add_handler(CommandHandler("pool", pool_command))
    application.add_handler(CommandHandler("memory", memory_command))
    application.add_handler(wizard_handler)
    application.add_handler(CallbackQueryHandler(regenerate_choice, pattern=r"^regen:"))
    application.add_error_handler(error_handler)

    application.run_polling(drop_pending_updates=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Este bot genera videos verticales desde las cuentas de Instagram que "
        "hayas dejado en accounts.txt.\n\n"
        "Comandos:\n"
        "/memory - ver si la memoria persiste tras redeploy\n"
        "/sync - descargar la biblioteca local de cuentas\n"
        "/download_pool - rellenar el pool rapido de fotos\n"
        "/pool - ver stock del pool\n"
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
        "4. el bot elige imágenes ya guardadas y envía el video\n\n"
        "Tipos:\n"
        "1 = historia de 7 imágenes (slide 6 = imagen6.png, febrero)\n"
        "2 = 4 consejos + hook (slide 3 = imagen6.png, tip3)\n"
        "3 = hook + herramientas para empezar dropshipping en 2026\n\n"
        "Las cuentas se leen de accounts.txt (una por línea). Para cambiarlas "
        "edita ese archivo y reinicia el bot (o solo guarda, el archivo se "
        "relee en cada /create).\n\n"
        "Usa /download_pool para precargar un lote de fotos aptas. "
        "Despues /create elige desde ese pool local sin descargar en caliente.\n\n"
        "Usa /memory despues de un redeploy para comprobar que fotos usadas, "
        "jobs y cuentas recientes no vuelven a cero."
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


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    try:
        accounts = load_accounts(settings.accounts_file)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    status_message = await update.effective_message.reply_text(
        f"Sincronizando {len(accounts)} cuentas. Las que ya tengan carpeta local no se descargan de nuevo."
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
    if not await _ensure_allowed(update):
        return

    settings = get_settings()
    try:
        accounts = load_accounts(settings.accounts_file)
    except AccountsFileError as error:
        await update.effective_message.reply_text(str(error))
        return

    status_message = await update.effective_message.reply_text(
        f"Rellenando pool hasta {settings.pool_target_images} fotos disponibles. "
        "Voy cuenta por cuenta y pongo cooldown despues de revisar cada una."
    )
    service: VideoCreationService = context.application.bot_data["service"]
    try:
        summary = await asyncio.to_thread(service.refill_pool, accounts)
    except Exception as error:
        LOGGER.exception("Pool refill failed")
        await status_message.edit_text(f"No pude rellenar el pool.\n\n{error}")
        return

    await status_message.edit_text(_format_pool_refill_summary(summary))


async def pool_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return
    service: VideoCreationService = context.application.bot_data["service"]
    summary = await asyncio.to_thread(service.pool_status)
    await update.effective_message.reply_text(_format_pool_status(summary))


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
    try:
        accounts = load_accounts(settings.accounts_file)
        accounts_line = f"{len(accounts)} desde {settings.accounts_file}"
    except AccountsFileError as error:
        accounts_line = f"error leyendo {settings.accounts_file}: {error}"

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
        f"Cuentas cargadas: {accounts_line}\n"
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
        account_inputs = list(repeat_request.get("requested_accounts") or [])
        if not account_inputs:
            account_inputs = [repeat_request["chosen_account"]]
        request = VideoRequest(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            video_type=VideoType(repeat_request["video_type"]),
            language=Language(repeat_request["language"]),
            account_inputs=account_inputs,
            skip_accounts=(
                [repeat_request["chosen_account"]]
                if query.data == REGENERATE_SKIP_ACCOUNT
                else []
            ),
        )
    except (KeyError, ValueError):
        context.user_data.pop("repeat_request", None)
        await query.edit_message_text(
            "No pude recuperar bien la última selección. Lanza /create otra vez."
        )
        return

    if query.data == REGENERATE_SKIP_ACCOUNT:
        await query.edit_message_text(
            f"Paso @{repeat_request['chosen_account']} y busco la siguiente cuenta del pool."
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
        )
        await _execute_extra_image(update, context, extra_request)


async def _execute_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: VideoRequest,
) -> None:
    chat = update.effective_chat
    status_message = await context.bot.send_message(
        chat_id=chat.id,
        text="Estoy seleccionando imágenes de la biblioteca local y montando el video. Esto puede tardar un poco.",
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
        context.user_data["repeat_request"] = {
            "chosen_account": result.chosen_account,
            "requested_accounts": request.account_inputs,
            "video_type": result.video_type.value,
            "language": result.language.value,
        }
        await _ask_for_another_same_account(context, chat.id, result.chosen_account)
        if result.pool_low_stock:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "Aviso: el pool se esta quedando bajo "
                    f"({result.pool_remaining} fotos aptas para tipo {result.video_type.value}). "
                    "Ejecuta /download_pool cuando quieras rellenarlo."
                ),
            )
    except TelegramError as error:
        LOGGER.exception("Telegram refused the send")
        await context.bot.send_message(
            chat_id=chat.id,
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
        with media.local_path.open("rb") as handle:
            await context.bot.send_photo(chat_id=chat.id, photo=handle)
        context.user_data["repeat_request"] = {
            "chosen_account": media.source_account,
            "requested_accounts": request.account_inputs,
            "video_type": request.video_type.value,
            "language": request.language.value,
        }
        await _ask_for_another_same_account(context, chat.id, media.source_account)
    except TelegramError as error:
        LOGGER.exception("Telegram refused the extra image")
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"Telegram rechazó la imagen.\nCausa: {error}",
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
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"¿Quieres otra imagen distinta de @{account} por si "
            "alguna no te convence?"
        ),
        reply_markup=keyboard,
    )


def _split_title_body(text: str) -> tuple[str, str]:
    parts = text.split("\n", 1)
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].strip()


def _clear_wizard_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("accounts_snapshot", None)
    context.user_data.pop("video_type", None)


def _format_pool_status(summary: dict) -> str:
    by_type = summary.get("by_type", {})
    by_account = summary.get("by_account", {})
    account_lines = [
        f"@{account}: {count}"
        for account, count in sorted(by_account.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    text = (
        "Pool de fotos\n"
        f"Total disponible: {summary.get('total', 0)}\n"
        f"Tipo 1: {by_type.get('1', 0)}\n"
        f"Tipo 2: {by_type.get('2', 0)}\n"
        f"Tipo 3: {by_type.get('3', 0)}"
    )
    if account_lines:
        text += "\n\nPor cuenta:\n" + "\n".join(account_lines)
    return text


def _format_pool_refill_summary(summary: dict) -> str:
    after = summary.get("after", {})
    added_by_account = summary.get("added_by_account", {})
    errors = summary.get("errors", {})
    skipped = summary.get("skipped_cooldown", [])
    lines = [
        "Pool actualizado",
        f"Objetivo minimo: {summary.get('target')}",
        f"Antes: {summary.get('before', {}).get('total', 0)}",
        f"Ahora: {after.get('total', 0)}",
        f"Nuevas: {summary.get('added', 0)}",
        (
            "Por tipo: "
            f"T1={after.get('by_type', {}).get('1', 0)}, "
            f"T2={after.get('by_type', {}).get('2', 0)}, "
            f"T3={after.get('by_type', {}).get('3', 0)}"
        ),
        (
            "Planes viables: "
            f"T1={'si' if summary.get('viable_after', {}).get('1') else 'no'}, "
            f"T2={'si' if summary.get('viable_after', {}).get('2') else 'no'}, "
            f"T3={'si' if summary.get('viable_after', {}).get('3') else 'no'}"
        ),
        (
            "Cuentas listas: "
            f"T1={len(summary.get('viable_accounts_after', {}).get('1', []))}, "
            f"T2={len(summary.get('viable_accounts_after', {}).get('2', []))}, "
            f"T3={len(summary.get('viable_accounts_after', {}).get('3', []))}"
        ),
    ]
    if added_by_account:
        lines.append("")
        lines.append("Cuentas revisadas:")
        for account, count in sorted(added_by_account.items()):
            valid = summary.get("valid_by_account", {}).get(account, count)
            type_counts = summary.get("valid_by_type_by_account", {}).get(account, {})
            lines.append(
                f"@{account}: {count} nuevas ({valid} aptas; "
                f"T1={type_counts.get('1', 0)}, "
                f"T2={type_counts.get('2', 0)}, "
                f"T3={type_counts.get('3', 0)})"
            )
    if skipped:
        lines.append("")
        lines.append("En cooldown:")
        lines.extend(f"@{account}" for account in skipped[:10])
    if errors:
        lines.append("")
        lines.append("Errores:")
        for account, message in sorted(errors.items())[:8]:
            lines.append(f"@{account}: {message}")
    if not summary.get("ready"):
        lines.append("")
        lines.append(
            "Aun no hay planes viables para todos los tipos. Ejecuta /download_pool "
            "otra vez cuando haya cuentas fuera de cooldown o revisa /pool."
        )
    return "\n".join(lines)


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
