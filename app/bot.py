from __future__ import annotations

import asyncio
import logging
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
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
from app.batches import (
    BATCH_ROTATION_CYCLE_LENGTH,
    DEFAULT_BATCH_SIZE,
    DEFAULT_BATCH_TIMES,
    MAX_BATCH_SIZE,
    BatchItem,
    BatchItemKind,
    build_batch_plan,
    parse_schedule_values,
    schedule_time_to_datetime_time,
)
from app.config import get_settings
from app.models import (
    Language,
    SlideRole,
    VideoGender,
    VideoRequest,
    VideoType,
)
from app.service import VideoCreationService
from app.state import BATCH_SCHEDULE_SCHEMA_VERSION, StateStore


(
    GENDER_STATE,
    TYPE_STATE,
    DELIVERY_STATE,
    LANGUAGE_STATE,
    LOWERCASE_STATE,
    STORY_PHOTO_STATE,
) = range(6)
REGENERATE_ACCEPT = "regen:accept"
REGENERATE_SKIP_ACCOUNT = "regen:skip_account"
REGENERATE_CANCEL = "regen:cancel"
TEMPLATE_VIDEO_CREATE = "template_video:create:es"
TEMPLATE_VIDEO_CREATE_EN = "template_video:create:en"
TEMPLATE_VIDEO_CALLBACK_PATTERN = r"^template_video:create(?::(es|en))?$"

LOGGER = logging.getLogger(__name__)
TELEGRAM_SEND_ATTEMPTS = 6
TELEGRAM_SEND_RETRY_BASE_DELAY = 1.5
TELEGRAM_SEND_RETRY_MAX_DELAY = 30.0
TELEGRAM_CONNECT_TIMEOUT = 30.0
TELEGRAM_READ_TIMEOUT = 60.0
TELEGRAM_WRITE_TIMEOUT = 60.0
TELEGRAM_MEDIA_WRITE_TIMEOUT = 120.0
TELEGRAM_POOL_TIMEOUT = 30.0
TELEGRAM_TEXT_LIMIT = 4096
POOL_SUMMARY_ACCOUNT_DETAIL_LIMIT = 12
POOL_SUMMARY_ERROR_DETAIL_LIMIT = 4
ACCOUNT_AUDIT_DETAIL_LIMIT = 12
BATCH_JOB_NAME_PREFIX = "scheduled-batch:"


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

    application: Application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .media_write_timeout(TELEGRAM_MEDIA_WRITE_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .post_init(_post_init)
        .build()
    )
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
                CallbackQueryHandler(wizard_type, pattern=r"^wizard:type:(?:4|5|advice)$"),
                CallbackQueryHandler(wizard_gender, pattern=r"^wizard:gender:"),
            ],
            TYPE_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(wizard_type, pattern=r"^wizard:type:"),
            ],
            DELIVERY_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(wizard_delivery, pattern=r"^wizard:delivery:"),
            ],
            LANGUAGE_STATE: [
                CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN),
                CallbackQueryHandler(
                    wizard_story_language,
                    pattern=r"^wizard:storylang:",
                ),
                CallbackQueryHandler(
                    wizard_advice_language,
                    pattern=r"^wizard:advicelang:",
                ),
                CallbackQueryHandler(
                    wizard_type_5_language,
                    pattern=r"^wizard:type5lang:",
                ),
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
    application.add_handler(CommandHandler("my_id", my_id_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("add_user", add_user_command))
    application.add_handler(CommandHandler("remove_user", remove_user_command))
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
    application.add_handler(CommandHandler("reset_photos", reset_photos_command))
    application.add_handler(CommandHandler("reset_fotos", reset_photos_command))
    application.add_handler(CommandHandler("template_video", template_video_command))
    application.add_handler(CommandHandler("video_template", template_video_command))
    application.add_handler(CommandHandler("batch", batch_command))
    application.add_handler(CommandHandler("lote", batch_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("programar", schedule_command))
    application.add_handler(CommandHandler("batch_reset", batch_reset_command))
    application.add_handler(wizard_handler)
    application.add_handler(CallbackQueryHandler(template_video_button, pattern=TEMPLATE_VIDEO_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(regenerate_choice, pattern=r"^regen:"))
    application.add_error_handler(error_handler)

    application.run_polling(drop_pending_updates=True)


async def _post_init(application: Application) -> None:
    application.bot_data["batch_lock"] = asyncio.Lock()
    try:
        _replace_scheduled_batch_jobs(application)
        _queue_missed_scheduled_batch(application)
    except Exception:
        LOGGER.exception("Could not restore the saved batch schedule")


async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or user is None:
        return

    values = [str(value).strip() for value in (context.args or []) if str(value).strip()]
    try:
        if len(values) > 1:
            raise ValueError("Uso: /batch [cantidad]")
        count = int(values[0]) if values else DEFAULT_BATCH_SIZE
        if count < 1 or count > MAX_BATCH_SIZE:
            raise ValueError(
                f"La cantidad debe estar entre 1 y {MAX_BATCH_SIZE} videos."
            )
    except ValueError as error:
        await message.reply_text(str(error))
        return

    lock = _batch_lock(context.application)
    queue_line = " Hay otro lote activo; este queda en cola." if lock.locked() else ""
    await message.reply_text(
        f"Lote de {count} videos recibido.{queue_line} Te avisare del progreso aqui."
    )
    context.application.create_task(
        _run_batch(
            context.application,
            chat_id=chat.id,
            user_id=user.id,
            count=count,
            source="manual",
        ),
        update=update,
        name=f"manual-batch-{uuid4().hex[:8]}",
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_admin(update):
        return
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or user is None:
        return

    settings = get_settings()
    store = _batch_store()
    values = [
        piece
        for raw_value in (context.args or [])
        for piece in str(raw_value).split(",")
        if piece.strip()
    ]
    if not values:
        await message.reply_text(_format_batch_schedule_status(store))
        return

    action = values[0].strip().lower()
    if action in {"off", "stop", "disable", "desactivar"}:
        store.disable_batch_schedule()
        _replace_scheduled_batch_jobs(context.application)
        await message.reply_text("Programacion diaria desactivada. La rotacion queda guardada.")
        return

    try:
        count, times = parse_schedule_values(values)
        _load_batch_timezone(settings.batch_timezone)
    except ValueError as error:
        await message.reply_text(
            f"{error}\n\nUso: /schedule 5 08:00 17:00\n"
            "Para apagarla: /schedule off"
        )
        return

    store.write_batch_schedule(
        enabled=True,
        chat_id=chat.id,
        user_id=user.id,
        count=count,
        times=times,
        timezone_name=settings.batch_timezone,
    )
    _replace_scheduled_batch_jobs(context.application)
    await message.reply_text(
        f"Programacion activada: {count} videos listos para las "
        f"{', '.join(times)}, todos los dias ({settings.batch_timezone}).\n"
        f"La preparacion empezara {settings.batch_preparation_lead_minutes} "
        "minutos antes de cada hora objetivo.\n"
        "Puedes crear el siguiente lote ahora con /batch."
    )


async def batch_reset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await _ensure_admin(update):
        return
    lock = _batch_lock(context.application)
    if lock.locked():
        await update.effective_message.reply_text(
            "Hay un lote en curso. Espera a que termine antes de reiniciar la rotacion."
        )
        return
    store = _batch_store()
    store.reset_batch_rotation()
    await update.effective_message.reply_text(
        "Rotacion reiniciada. El siguiente lote volvera al orden inicial: "
        "1 ES, 2 ES, 3 EN, 1 ES y 1 EN. "
        "A partir de ahi, la IA rota con la misma frecuencia en ES y EN; "
        "el video de mujer queda fuera del lote."
    )


async def _scheduled_batch_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data if context.job is not None else {}
    if not isinstance(data, dict):
        LOGGER.error("Scheduled batch has invalid job data: %r", data)
        return
    timezone_name = str(data.get("timezone") or get_settings().batch_timezone)
    timezone = _load_batch_timezone(timezone_name)
    target = _scheduled_target_in_active_window(
        str(data.get("time") or ""),
        timezone,
        lead_minutes=get_settings().batch_preparation_lead_minutes,
    )
    scheduled_slot = (
        _scheduled_batch_slot(target, int(data["chat_id"]))
        if target is not None
        else None
    )
    await _run_batch(
        context.application,
        chat_id=int(data["chat_id"]),
        user_id=int(data["user_id"]),
        count=int(data["count"]),
        source=f"para las {data.get('time', '')}".strip(),
        scheduled_slot=scheduled_slot,
    )


async def _run_batch(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    count: int,
    source: str,
    scheduled_slot: str | None = None,
    recover_running_slot: bool = False,
) -> None:
    lock = _batch_lock(application)
    async with lock:
        service: VideoCreationService = application.bot_data["service"]
        store = service.state
        batch_id = uuid4().hex
        if scheduled_slot and not store.claim_scheduled_batch_slot(
            scheduled_slot,
            batch_id,
            allow_reclaim_running=recover_running_slot,
        ):
            LOGGER.info("Scheduled batch slot %s was already handled", scheduled_slot)
            return
        phase = store.get_batch_rotation_phase(
            cycle_length=BATCH_ROTATION_CYCLE_LENGTH
        )
        plan = build_batch_plan(count, phase)
        accounts_by_gender = _load_accounts_by_gender(get_settings())
        plan_lines = "\n".join(
            f"{item.position}. {item.short_label}" for item in plan
        )
        status_message = await _send_message(
            application,
            chat_id,
            (
                f"Lote {source} iniciado ({count} videos).\n"
                f"Rotacion {phase + 1}/{BATCH_ROTATION_CYCLE_LENGTH}:\n{plan_lines}"
            ),
        )
        store.write_last_batch_run(
            {
                "batch_id": batch_id,
                "status": "running",
                "source": source,
                "chat_id": chat_id,
                "count": count,
                "phase": phase,
                "scheduled_slot": scheduled_slot,
                "plan": [item.short_label for item in plan],
            }
        )
        succeeded = 0
        failures: list[str] = []
        for item in plan:
            try:
                await _edit_batch_status(
                    status_message,
                    f"Lote en curso: preparando {item.position}/{count} "
                    f"({item.short_label}). Completados: {succeeded}.",
                )
                if item.kind == BatchItemKind.TOOLS:
                    await _create_and_send_batch_tools_video(
                        application,
                        chat_id,
                        user_id,
                        item,
                        count,
                    )
                elif item.kind == BatchItemKind.AI:
                    await _create_and_send_batch_generated_video(
                        application,
                        chat_id=chat_id,
                        user_id=user_id,
                        item=item,
                        count=count,
                        accounts=[],
                    )
                else:
                    accounts = accounts_by_gender.get(item.gender, [])
                    if not accounts:
                        account_file = _accounts_path_for_gender(
                            get_settings(),
                            item.gender,
                        )
                        raise ValueError(
                            f"No hay cuentas disponibles en {account_file.name}."
                        )
                    await _create_and_send_batch_generated_video(
                        application,
                        chat_id=chat_id,
                        user_id=user_id,
                        item=item,
                        count=count,
                        accounts=accounts,
                    )
                succeeded += 1
            except Exception as error:
                LOGGER.exception(
                    "Batch %s item %d failed (%s)",
                    batch_id,
                    item.position,
                    item.short_label,
                )
                failures.append(f"{item.position}. {item.short_label}: {error}")
                try:
                    await _send_message(
                        application,
                        chat_id,
                        f"Fallo el video {item.position}/{count} ({item.short_label}): {error}",
                    )
                except TelegramError:
                    LOGGER.exception("Could not report a batch item failure to Telegram")

        final_status = "completed" if not failures else "completed_with_errors"
        if scheduled_slot and not store.finish_scheduled_batch_slot(
            scheduled_slot,
            batch_id=batch_id,
            status=final_status,
        ):
            LOGGER.warning(
                "Batch %s lost ownership of scheduled slot %s; rotation not advanced",
                batch_id,
                scheduled_slot,
            )
            return
        if succeeded:
            next_phase = store.advance_batch_rotation(
                cycle_length=BATCH_ROTATION_CYCLE_LENGTH
            )
        else:
            next_phase = phase
        store.write_last_batch_run(
            {
                "batch_id": batch_id,
                "status": final_status,
                "source": source,
                "chat_id": chat_id,
                "count": count,
                "phase": phase,
                "next_phase": next_phase,
                "scheduled_slot": scheduled_slot,
                "succeeded": succeeded,
                "failed": len(failures),
                "failures": failures,
                "plan": [item.short_label for item in plan],
            }
        )
        summary = (
            f"Lote terminado: {succeeded}/{count} videos enviados. "
            f"Fallos: {len(failures)}."
        )
        if not failures:
            summary += " La rotacion queda preparada para el siguiente lote."
        await _edit_batch_status(status_message, summary)


async def _create_and_send_batch_tools_video(
    application: Application,
    chat_id: int,
    user_id: int,
    item: BatchItem,
    count: int,
) -> None:
    service: VideoCreationService = application.bot_data["service"]
    result = await asyncio.to_thread(
        service.create_template_video,
        None,
        item.language,
        user_id,
        chat_id,
    )
    await _send_message(
        application,
        chat_id,
        f"Lote {item.position}/{count}: video de herramientas {item.language.value.upper()}.",
    )
    if result.queue_restarted:
        await _send_message(
            application,
            chat_id,
            "La cola de videos de herramientas termino y se reinicio desde el principio.",
        )
    await _send_video(application, chat_id, result.video_path)
    for text in result.social_copy.messages:
        await _send_message(application, chat_id, text)


async def _create_and_send_batch_generated_video(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    item: BatchItem,
    count: int,
    accounts: list[str],
) -> None:
    if item.video_type is None:
        raise ValueError("El elemento del lote no tiene tipo de video.")
    request = VideoRequest(
        chat_id=chat_id,
        user_id=user_id,
        video_type=item.video_type,
        language=item.language,
        account_inputs=list(accounts),
        gender=item.gender,
    )
    service: VideoCreationService = application.bot_data["service"]
    result = await asyncio.to_thread(service.create_video, request)
    if result.video_type == VideoType.TYPE_4:
        result_line = (
            f"Lote {item.position}/{count}: historia generada por IA en "
            f"{result.language.value.upper()}.\n"
            f"Referencia elegida: {result.chosen_account}"
        )
    else:
        result_line = (
            f"Lote {item.position}/{count}: tipo {result.video_type.value} "
            f"{result.language.value.upper()}, {_gender_label_plural(item.gender)}.\n"
            f"Cuenta elegida: @{result.chosen_account}"
        )
    await _send_message(application, chat_id, result_line)
    for text in result.social_copy.messages:
        await _send_message(application, chat_id, text)
    await _send_slides_text_then_image(
        application,
        chat_id,
        result.slides,
        video_type=result.video_type,
        separate_slide_text=result.separate_slide_text,
    )
    if result.pool_low_stock:
        await _send_message(
            application,
            chat_id,
            f"Aviso: quedan {result.pool_remaining} fotos disponibles en el pool.",
        )


def _batch_lock(application: Application) -> asyncio.Lock:
    lock = application.bot_data.get("batch_lock")
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        application.bot_data["batch_lock"] = lock
    return lock


def _batch_store() -> StateStore:
    settings = get_settings()
    return StateStore(
        settings.state_dir,
        history_max_per_bucket=settings.history_max_per_bucket,
    )


def _replace_scheduled_batch_jobs(application: Application) -> None:
    job_queue = application.job_queue
    if job_queue is None:
        raise RuntimeError(
            "El planificador no esta instalado. Instala python-telegram-bot[job-queue]."
        )
    for job in job_queue.jobs(rf"^{BATCH_JOB_NAME_PREFIX}"):
        job.schedule_removal()

    store = _batch_store()
    schedule = _migrate_legacy_batch_schedule(store)
    if not schedule.get("enabled"):
        return
    timezone_name = str(schedule.get("timezone") or get_settings().batch_timezone)
    timezone = _load_batch_timezone(timezone_name)
    count = int(schedule.get("count", DEFAULT_BATCH_SIZE))
    chat_id = int(schedule["chat_id"])
    user_id = int(schedule["user_id"])
    times = list(schedule.get("times") or [])
    preparation_lead_minutes = max(
        0,
        get_settings().batch_preparation_lead_minutes,
    )
    for raw_time in times:
        normalized_time = str(raw_time)
        run_time = schedule_time_to_datetime_time(
            normalized_time,
            timezone,
            minute_offset=-preparation_lead_minutes,
        )
        job_queue.run_daily(
            _scheduled_batch_callback,
            time=run_time,
            data={
                "chat_id": chat_id,
                "user_id": user_id,
                "count": count,
                "time": normalized_time,
                "preparation_time": run_time.strftime("%H:%M"),
                "timezone": timezone_name,
            },
            name=f"{BATCH_JOB_NAME_PREFIX}{normalized_time}",
            chat_id=chat_id,
            user_id=user_id,
            job_kwargs={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
        )
    LOGGER.info(
        "Scheduled %d-video batch for %s, starting %d minutes early (%s)",
        count,
        ", ".join(str(value) for value in times),
        preparation_lead_minutes,
        timezone_name,
    )


def _migrate_legacy_batch_schedule(store: StateStore) -> dict[str, Any]:
    schedule = store.read_batch_schedule()
    if not schedule.get("enabled"):
        return schedule
    try:
        schema_version = int(schedule.get("schema_version", 0))
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version >= BATCH_SCHEDULE_SCHEMA_VERSION:
        return schedule

    times = [str(value) for value in schedule.get("times") or []]
    if schema_version < 2 and times == ["08:00", "18:00"]:
        LOGGER.info("Migrating legacy batch schedule from 08:00/18:00 to 08:00/17:00")
        times = list(DEFAULT_BATCH_TIMES)

    count = int(schedule.get("count", DEFAULT_BATCH_SIZE))
    if schema_version < 3 and count == 6:
        LOGGER.info("Migrating scheduled batch size from 6 videos to 5")
        count = DEFAULT_BATCH_SIZE

    return store.write_batch_schedule(
        enabled=True,
        chat_id=int(schedule["chat_id"]),
        user_id=int(schedule["user_id"]),
        count=count,
        times=times,
        timezone_name=str(
            schedule.get("timezone") or get_settings().batch_timezone
        ),
    )


def _scheduled_target_in_active_window(
    raw_time: str,
    timezone: ZoneInfo,
    *,
    lead_minutes: int,
    now: datetime | None = None,
) -> datetime | None:
    target_time = schedule_time_to_datetime_time(raw_time, timezone)
    local_now = (now or datetime.now(timezone)).astimezone(timezone)
    lead = timedelta(minutes=max(0, int(lead_minutes)))
    grace = timedelta(minutes=5)
    for day_offset in (0, 1):
        target = datetime.combine(
            local_now.date() + timedelta(days=day_offset),
            target_time,
        )
        if target - lead <= local_now <= target + grace:
            return target
    return None


def _scheduled_batch_slot(target: datetime, chat_id: int) -> str:
    timezone_name = str(target.tzinfo or get_settings().batch_timezone)
    return (
        f"{target.date().isoformat()}|{target.strftime('%H:%M')}|"
        f"{timezone_name}|{int(chat_id)}"
    )


def _queue_missed_scheduled_batch(
    application: Application,
    *,
    now: datetime | None = None,
) -> bool:
    store = _batch_store()
    schedule = _migrate_legacy_batch_schedule(store)
    if not schedule.get("enabled"):
        return False
    timezone_name = str(schedule.get("timezone") or get_settings().batch_timezone)
    timezone = _load_batch_timezone(timezone_name)
    lead_minutes = get_settings().batch_preparation_lead_minutes
    chat_id = int(schedule["chat_id"])
    queued = False
    for raw_time in schedule.get("times") or []:
        target = _scheduled_target_in_active_window(
            str(raw_time),
            timezone,
            lead_minutes=lead_minutes,
            now=now,
        )
        if target is None:
            continue
        slot = _scheduled_batch_slot(target, chat_id)
        if store.scheduled_batch_slot_is_terminal(slot):
            continue
        LOGGER.warning(
            "Catching up scheduled batch for %s after startup",
            target.isoformat(),
        )
        application.create_task(
            _run_batch(
                application,
                chat_id=chat_id,
                user_id=int(schedule["user_id"]),
                count=int(schedule.get("count", DEFAULT_BATCH_SIZE)),
                source=f"recuperado para las {target.strftime('%H:%M')}",
                scheduled_slot=slot,
                recover_running_slot=True,
            ),
            name=f"scheduled-catchup-{target.strftime('%Y%m%d-%H%M')}",
        )
        queued = True
    return queued


def _load_batch_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"No se reconoce la zona horaria {timezone_name}. "
            "Configura BATCH_TIMEZONE, por ejemplo Europe/Madrid."
        ) from error


def _format_batch_schedule_status(store: StateStore) -> str:
    schedule = _migrate_legacy_batch_schedule(store)
    phase = store.get_batch_rotation_phase(
        cycle_length=BATCH_ROTATION_CYCLE_LENGTH
    )
    last_run = store.read_last_batch_run()
    next_plan = build_batch_plan(
        int(schedule.get("count", DEFAULT_BATCH_SIZE)),
        phase,
    )
    plan_line = ", ".join(item.short_label for item in next_plan)
    if schedule.get("enabled"):
        schedule_line = (
            f"Activa: {schedule.get('count', DEFAULT_BATCH_SIZE)} videos para las "
            f"{', '.join(schedule.get('times') or [])} "
            f"({schedule.get('timezone') or get_settings().batch_timezone})"
        )
    else:
        schedule_line = "Desactivada"
    last_line = "Sin lotes ejecutados"
    if last_run:
        last_line = (
            f"Ultimo lote: {last_run.get('status', '-')} "
            f"({last_run.get('succeeded', 0)}/{last_run.get('count', 0)} enviados)"
        )
    return (
        f"Programacion de lotes\n{schedule_line}\n"
        f"Preparacion: {get_settings().batch_preparation_lead_minutes} minutos antes\n"
        f"Siguiente rotacion: {phase + 1}/{BATCH_ROTATION_CYCLE_LENGTH}\n"
        f"Siguiente lote: {plan_line}\n{last_line}\n\n"
        "Configurar: /schedule 5 08:00 17:00\n"
        "Desactivar: /schedule off\n"
        "Crear ahora: /batch"
    )


async def _edit_batch_status(status_message, text: str) -> None:
    try:
        await status_message.edit_text(text)
    except TelegramError:
        LOGGER.exception("Could not update batch status message")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Este bot genera videos verticales desde las cuentas de Instagram que "
        "hayas dejado en accounts.txt o accounts_women.txt.\n\n"
        "Comandos:\n"
        "/my_id - ver tu ID de Telegram\n"
        "/users, /add_user ID, /remove_user ID - accesos (propietario)\n"
        "/memory - ver si la memoria persiste tras redeploy\n"
        "/sync - descargar la biblioteca local de cuentas de hombres\n"
        "/sync_women - descargar la biblioteca local de cuentas de mujeres\n"
        "/download_pool - precalentar el pool rapido de fotos de hombres\n"
        "/download_pool_women - precalentar el pool rapido de fotos de mujeres\n"
        "/pool - ver stock del pool\n"
        "/audit_accounts - detectar cuentas gastadas/no aptas de hombres\n"
        "/audit_accounts_women - detectar cuentas gastadas/no aptas de mujeres\n"
        "/template_video - coger un video de R2 y aplicar la plantilla fija\n"
        "/story_carousel [es|en] - crear una historia IA desde una foto enviada al bot\n"
        "/batch [cantidad] - crear ahora un lote rotativo (5 por defecto)\n"
        "/schedule 5 08:00 17:00 - programar lotes diarios\n"
        "/schedule off - desactivar la programacion\n"
        "/create — elegir tipo e idioma y generar el video\n"
        "/accounts — ver las cuentas de hombres cargadas\n"
        "/accounts_women — ver las cuentas de mujeres cargadas\n"
        "/cancel — cancelar el wizard actual"
    )
    await update.effective_message.reply_text(
        message,
        reply_markup=_main_menu_markup(),
    )


async def my_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if user is None or update.effective_message is None:
        return
    await update.effective_message.reply_text(
        f"Tu ID de usuario es {user.id}. Chat ID: {chat.id if chat else '-'}"
    )


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_admin(update):
        return
    users = _telegram_state_store().list_telegram_users()
    lines = ["Usuarios autorizados:"]
    for record in users:
        username = str(record.get("username") or "").strip()
        label = f"@{username}" if username else "sin username"
        lines.append(
            f"- {record['user_id']} · {label} · {record.get('role', 'user')}"
        )
    lines.extend(["", "Añadir: /add_user ID", "Eliminar: /remove_user ID"])
    await update.effective_message.reply_text("\n".join(lines))


async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_admin(update):
        return
    try:
        values = list(context.args or [])
        if len(values) != 1:
            raise ValueError
        user_id = int(values[0])
        if user_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        await update.effective_message.reply_text("Uso: /add_user ID_DE_TELEGRAM")
        return
    _telegram_state_store().authorize_telegram_user(
        user_id=user_id,
        added_by=update.effective_user.id,
    )
    await update.effective_message.reply_text(
        f"Usuario {user_id} autorizado. Ya puede abrir el bot en un chat privado."
    )


async def remove_user_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await _ensure_admin(update):
        return
    try:
        values = list(context.args or [])
        if len(values) != 1:
            raise ValueError
        user_id = int(values[0])
    except (TypeError, ValueError):
        await update.effective_message.reply_text("Uso: /remove_user ID_DE_TELEGRAM")
        return
    store = _telegram_state_store()
    if user_id == store.get_owner_user_id():
        await update.effective_message.reply_text(
            "No se puede eliminar al propietario del bot."
        )
        return
    if not store.revoke_telegram_user(user_id):
        await update.effective_message.reply_text(
            f"El usuario {user_id} no estaba autorizado."
        )
        return
    await update.effective_message.reply_text(f"Usuario {user_id} eliminado.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_allowed(update):
        return

    message = (
        "Flujo:\n"
        "1. /create\n"
        "2. elige Hombres o Mujeres\n"
        "3. elige Tipo 1, Tipo 2, Tipo 3, Tipo 4, Tipo 5 o la Historia IA\n"
        "4. elige si quieres texto incrustado en la imagen o separado\n"
        "5. elige Español o English\n"
        "6. elige si quieres textos normales o todo en minúscula\n"
        "7. el bot usa el pool si hay stock o busca dinamicamente si falta\n\n"
        "Tipos:\n"
        "1 = historia de 7 imágenes (slide 6 = tip3_dropradar.jpg, febrero)\n"
        "2 = 4 consejos + hook (slide 3 = tip3_dropradar.jpg, tip3)\n"
        "3 = hook + herramientas para empezar dropshipping en 2026\n"
        "4 = cuatro consejos rotativos sobre fondo negro, blanco o ilustrado\n"
        "5 = comparación de negocios con cuatro fotos tomadas de una cola R2\n"
        "IA = historia vertical de 6 escenas + la foto original, con el texto "
        "compuesto fuera de la IA para que siempre se lea bien\n\n"
        "Las cuentas de hombres se leen de accounts.txt y las de mujeres de "
        "accounts_women.txt (una por línea). Para cambiarlas edita el archivo "
        "y guarda; se releen en cada /create.\n\n"
        "/create usa primero el pool local si hay fotos aptas. "
        "Si no hay stock, busca dinamicamente en las cuentas y guarda "
        "las fotos validas sobrantes para acelerar los siguientes videos. "
        "/download_pool y /download_pool_women quedan como precalentamiento opcional.\n\n"
        "Usa /audit_accounts o /audit_accounts_women para ver que cuentas "
        "estan gastadas, sin cache local o sin suficientes fotos aptas.\n\n"
        "Usa /reset_fotos confirmar para desbloquear todas las fotos ya usadas "
        "sin borrar el pool, las cachés ni el historial de jobs. Solo puede "
        "hacerlo el propietario.\n\n"
        "Usa /template_video [prefijo-r2] para coger un MP4 de R2 y "
        "aplicarle la plantilla fija de herramientas. El MP4 final sale sin audio.\n\n"
        "Usa /batch para crear el lote rotativo ahora. Por ejemplo, "
        "/schedule 5 08:00 17:00 prepara cinco piezas todos los dias con "
        "antelacion para esas horas (Europe/Madrid por defecto). La IA rota "
        "con la misma frecuencia en espanol e ingles; el video de mujer queda "
        "fuera del lote.\n\n"
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
    if not await _ensure_admin(update):
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
    if not await _ensure_admin(update):
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
        f"hasta {settings.pool_refill_max_accounts or 'todas las'} "
        "cuentas por tanda, con "
        f"hasta {settings.pool_refill_max_fresh_accounts or 'todas las'} "
        "cuentas frescas nuevas."
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
    settings = get_settings()
    accounts_by_gender = _load_accounts_by_gender(settings)
    summary = await asyncio.to_thread(service.pool_status)
    summary["by_gender"] = {
        gender.value: _type_1_pool_status_for_accounts(summary, accounts)
        for gender, accounts in accounts_by_gender.items()
        if accounts
    }
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
    user = update.effective_user
    message = update.effective_message
    if message is None or chat is None or user is None:
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
            user.id,
            chat.id,
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
    snapshot = store.memory_snapshot(
        recent_limit=10,
        user_id=update.effective_user.id,
    )
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
        f"Tus jobs guardados: {snapshot['jobs_count']}\n"
        f"Cuentas usadas distintas: {snapshot['unique_chosen_accounts']}\n"
        f"Ultimas cuentas: {recent_line}\n"
        f"Mas repetidas: {top_line}\n\n"
        "Si despues de redeploy fotos/jobs vuelven a 0 o el marker cambia, "
        "falta Persistent Storage montado en /app/data dentro de Coolify."
    )


async def reset_photos_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await _ensure_admin(update):
        return
    message = update.effective_message
    if message is None:
        return

    values = [
        str(value).strip().lower()
        for value in (getattr(context, "args", None) or [])
        if str(value).strip()
    ]
    if values != ["confirmar"]:
        blocked_count = len(_telegram_state_store().read_used_media())
        await message.reply_text(
            "Este reset hará que todas las fotos usadas puedan volver a salir "
            "en vídeos nuevos. No borrará imágenes, pool, cachés, jobs ni "
            "configuración.\n\n"
            f"Marcadores de uso que se desbloquearán: {blocked_count}.\n"
            "Para confirmarlo usa: /reset_fotos confirmar"
        )
        return

    lock = _batch_lock(context.application)
    if lock.locked():
        await message.reply_text(
            "Hay un lote en curso. Espera a que termine antes de reiniciar las fotos."
        )
        return

    try:
        async with lock:
            await message.reply_text(
                "Reiniciando la memoria y reconstruyendo el pool desde la caché local..."
            )
            accounts_by_gender = _load_accounts_by_gender(get_settings())
            normalized_accounts = (
                normalize_account(account)
                for accounts in accounts_by_gender.values()
                for account in accounts
            )
            account_inputs = list(
                dict.fromkeys(
                    account for account in normalized_accounts if account is not None
                )
            )
            service: VideoCreationService | None = context.application.bot_data.get(
                "service"
            )
            if service is not None:
                reset_summary = await asyncio.to_thread(
                    service.reset_photo_usage,
                    account_inputs,
                )
            else:
                reset_summary = {
                    "reset_count": await asyncio.to_thread(
                        _telegram_state_store().reset_used_media
                    ),
                    "restored_count": 0,
                    "cached_candidates": 0,
                    "accounts_with_cache": 0,
                }
    except Exception as error:  # noqa: BLE001
        LOGGER.exception("Photo reset failed")
        await message.reply_text(
            "No pude completar el reinicio de fotos. No se borraron imágenes. "
            f"Motivo: {error}"
        )
        return

    reset_count = int(reset_summary.get("reset_count", 0))
    restored_count = int(reset_summary.get("restored_count", 0))
    cached_candidates = int(reset_summary.get("cached_candidates", 0))
    cached_accounts = int(reset_summary.get("accounts_with_cache", 0))
    backup_line = (
        "Se conservó una copia de seguridad del estado anterior."
        if reset_count
        else "No había marcadores de uso que reiniciar."
    )
    await message.reply_text(
        f"Reset completado: {reset_count} marcadores de uso eliminados. "
        f"Revisé {cached_candidates} fotos locales de {cached_accounts} cuentas "
        f"y restauré {restored_count} que faltaban en el pool. "
        "Todas las fotos cacheadas dejan de estar marcadas como usadas; las "
        f"validaciones de calidad, formato y duplicados siguen activas. {backup_line}"
    )


async def story_carousel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not await _ensure_allowed(update):
        return ConversationHandler.END
    _prepare_story_carousel_state(context, source="upload")
    requested_language = _story_language_from_args(getattr(context, "args", []))
    if requested_language is not None:
        context.user_data["language"] = requested_language.value
        await update.effective_message.reply_text(
            "Mandame la foto de referencia y creo el carrusel IA estilo comic "
            f"en {requested_language.value.upper()}."
        )
        return STORY_PHOTO_STATE
    await update.effective_message.reply_text(
        "Elige el idioma del carrusel IA.",
        reply_markup=_story_language_keyboard(),
    )
    return LANGUAGE_STATE


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
                        "Tipo 4 - Consejos",
                        callback_data="wizard:type:advice",
                    ),
                    InlineKeyboardButton(
                        "Historia IA desde R2",
                        callback_data="wizard:type:4",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Tipo 5 - Negocios",
                        callback_data="wizard:type:5",
                    ),
                ],
            ]
        )
        await update.effective_message.reply_text(
            (
                "Que quieres crear?\n\n"
                "No encontre cuentas cargadas, asi que puedes crear el video "
                "de herramientas R2, el Tipo 4, el Tipo 5 o la historia IA desde R2."
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
                    "Tipo 4 - Consejos",
                    callback_data="wizard:type:advice",
                ),
                InlineKeyboardButton(
                    "Historia IA desde R2",
                    callback_data="wizard:type:4",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Tipo 5 - Negocios",
                    callback_data="wizard:type:5",
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
                    "Tipo 4 - Consejos",
                    callback_data="wizard:type:advice",
                ),
                InlineKeyboardButton(
                    "Historia IA",
                    callback_data="wizard:type:4",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Tipo 5 - Negocios",
                    callback_data="wizard:type:5",
                ),
            ],
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

    if raw_type == VideoType.ADVICE.value:
        context.user_data["separate_slide_text"] = False
        await query.edit_message_text(
            "Perfecto. Elige el idioma del Tipo 4.",
            reply_markup=_advice_language_keyboard(),
        )
        return LANGUAGE_STATE

    if raw_type == VideoType.TYPE_4.value:
        context.user_data["story_source"] = "r2"
        await query.edit_message_text(
            "Perfecto. Elige el idioma de la historia IA.",
            reply_markup=_story_language_keyboard(),
        )
        return LANGUAGE_STATE

    if raw_type == VideoType.TYPE_5.value:
        context.user_data["separate_slide_text"] = True
        await query.edit_message_text(
            "Perfecto. Elige el idioma del Tipo 5.",
            reply_markup=_type_5_language_keyboard(),
        )
        return LANGUAGE_STATE

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Texto en imagen",
                    callback_data="wizard:delivery:embedded",
                ),
                InlineKeyboardButton(
                    "Texto separado",
                    callback_data="wizard:delivery:separate",
                ),
            ]
        ]
    )
    await query.edit_message_text(
        "Perfecto. ¿Quieres el texto dentro de cada imagen o separado como mensaje?",
        reply_markup=keyboard,
    )
    return DELIVERY_STATE


async def wizard_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_delivery = query.data.rsplit(":", maxsplit=1)[-1]
    if raw_delivery not in {"embedded", "separate"}:
        await query.edit_message_text("Opción no reconocida. Lanza /create otra vez.")
        return ConversationHandler.END

    context.user_data["separate_slide_text"] = raw_delivery == "separate"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Español", callback_data="wizard:lang:es"),
                InlineKeyboardButton("English", callback_data="wizard:lang:en"),
            ]
        ]
    )
    await query.edit_message_text(
        "Ahora elige el idioma del texto.",
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


async def wizard_story_language(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()
    raw_lang = query.data.rsplit(":", maxsplit=1)[-1]
    try:
        language = Language(raw_lang)
    except ValueError:
        await query.edit_message_text("Idioma no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END
    context.user_data["language"] = language.value

    if context.user_data.get("story_source") == "upload":
        await query.edit_message_text(
            "Mandame la foto de referencia y creo el carrusel IA estilo comic "
            f"en {language.value.upper()}."
        )
        return STORY_PHOTO_STATE

    raw_gender = context.user_data.get("video_gender", VideoGender.MALE.value)
    try:
        gender = VideoGender(raw_gender)
    except ValueError:
        gender = VideoGender.MALE
    await query.edit_message_text(
        "Perfecto. Cojo la siguiente imagen de R2 y creo el carrusel IA "
        f"en {language.value.upper()}."
    )
    request = VideoRequest(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        video_type=VideoType.TYPE_4,
        language=language,
        account_inputs=[],
        gender=gender,
        lowercase_text=False,
    )
    await _execute_job(update, context, request)
    _clear_wizard_state(context)
    return ConversationHandler.END


async def wizard_advice_language(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()
    raw_lang = query.data.rsplit(":", maxsplit=1)[-1]
    try:
        language = Language(raw_lang)
    except ValueError:
        await query.edit_message_text("Idioma no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END
    context.user_data["language"] = language.value

    raw_gender = context.user_data.get("video_gender", VideoGender.MALE.value)
    try:
        gender = VideoGender(raw_gender)
    except ValueError:
        gender = VideoGender.MALE
    await query.edit_message_text(
        f"Perfecto. Creo el siguiente diseño Tipo 4 en {language.value.upper()}."
    )
    request = VideoRequest(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        video_type=VideoType.ADVICE,
        language=language,
        account_inputs=[],
        gender=gender,
        lowercase_text=False,
        separate_slide_text=False,
    )
    await _execute_job(update, context, request)
    _clear_wizard_state(context)
    return ConversationHandler.END


async def wizard_type_5_language(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()
    raw_lang = query.data.rsplit(":", maxsplit=1)[-1]
    try:
        language = Language(raw_lang)
    except ValueError:
        await query.edit_message_text("Idioma no reconocido. Lanza /create otra vez.")
        return ConversationHandler.END
    context.user_data["language"] = language.value

    raw_gender = context.user_data.get("video_gender", VideoGender.MALE.value)
    try:
        gender = VideoGender(raw_gender)
    except ValueError:
        gender = VideoGender.MALE
    confirmation = (
        "Perfect. I will use three random R2 images and finish with the fixed Dropradar image."
        if language == Language.EN
        else (
            "Perfecto. Cojo tres imagenes aleatorias de R2 y termino con "
            "la imagen fija de Dropradar."
        )
    )
    await query.edit_message_text(confirmation)
    request = VideoRequest(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        video_type=VideoType.TYPE_5,
        language=language,
        account_inputs=[],
        gender=gender,
        lowercase_text=False,
        separate_slide_text=True,
    )
    await _execute_job(update, context, request)
    _clear_wizard_state(context)
    return ConversationHandler.END


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
    separate_slide_text = bool(context.user_data.get("separate_slide_text", False))
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
        separate_slide_text=separate_slide_text,
    )

    lowercase_line = "todo en minúscula" if lowercase_text else "formato normal"
    delivery_line = (
        "texto separado"
        if separate_slide_text
        else "texto dentro de la imagen"
    )
    await query.edit_message_text(
        f"Preparando video de {_gender_label_plural(gender)} tipo "
        f"{video_type.value} en {language.value} "
        f"con {len(accounts)} cuentas ({lowercase_line}, {delivery_line})."
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
        language=Language(context.user_data.get("language", Language.ES.value)),
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
        owner_is_requesting = _is_owner(update)
        if query.data == REGENERATE_SKIP_ACCOUNT and owner_is_requesting:
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
            separate_slide_text=bool(
                repeat_request.get("separate_slide_text", False)
            ),
        )
    except (AccountsFileError, KeyError, ValueError):
        context.user_data.pop("repeat_request", None)
        await query.edit_message_text(
            "No pude recuperar bien la última selección. Lanza /create otra vez."
        )
        return

    if query.data == REGENERATE_SKIP_ACCOUNT:
        if not owner_is_requesting:
            context.user_data.pop("repeat_request", None)
            context.user_data["accounts_snapshot"] = list(request.account_inputs)
            await query.edit_message_text(
                f"Descarto @{chosen_account} solo para tu repetición y busco "
                "otra cuenta. El pool compartido no se modifica."
            )
            await _execute_job(update, context, request)
            return
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
            separate_slide_text=request.separate_slide_text,
        )
        await _execute_extra_image(update, context, extra_request)


async def _execute_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: VideoRequest,
) -> None:
    chat = update.effective_chat
    if request.video_type == VideoType.ADVICE:
        status_text = "Estoy creando el siguiente diseño rotativo del Tipo 4."
    elif request.video_type == VideoType.TYPE_4:
        status_text = (
            "Estoy generando el carrusel IA. Esto puede tardar porque son 6 escenas."
        )
    elif request.video_type == VideoType.TYPE_5:
        status_text = (
            "I am preparing Type 5 with three random R2 images and the fixed Dropradar image."
            if request.language == Language.EN
            else (
                "Estoy preparando el Tipo 5 con tres fotos aleatorias de R2 y la imagen "
                "fija de Dropradar."
            )
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

    if result.video_type == VideoType.ADVICE:
        header = (
            "Tipo 4 listo\n"
            f"Idioma: {result.language.value.upper()}\n"
            "Entrega: 4 consejos en una imagen"
        )
    elif result.video_type == VideoType.TYPE_4:
        source_label = (
            result.chosen_account
            if str(result.chosen_account).startswith("r2:")
            else "foto de referencia"
        )
        header = (
            "Carrusel IA listo\n"
            "Tipo: Historia IA\n"
            f"Fuente: {source_label}\n"
            "Entrega: 6 escenas generadas + foto original"
        )
    elif result.video_type == VideoType.TYPE_5:
        header = (
            "Type 5 ready\n"
            "Language: EN\n"
            "Delivery: 4 clean images + separate text"
            if result.language == Language.EN
            else (
                "Tipo 5 listo\n"
                "Idioma: ES\n"
                "Entrega: 4 imágenes limpias + textos separados"
            )
        )
    else:
        header = (
            f"Cuenta elegida: @{result.chosen_account}\n"
            f"Protagonista: {_gender_label_plural(request.gender)}\n"
            f"Tipo: {result.video_type.value}\n"
            f"Idioma: {result.language.value}"
        )
    if result.language == Language.EN:
        send_status = (
            "Sending images and text separately."
            if result.separate_slide_text
            else "Sending images with their text."
        )
    else:
        send_status = (
            "Enviando imágenes y textos por separado."
            if result.separate_slide_text
            else "Enviando imágenes con su texto."
        )
    await status_message.edit_text(send_status)
    try:
        await _send_message(context, chat.id, header)
        for message in result.social_copy.messages:
            await _send_message(context, chat.id, message)
        await _send_slides_text_then_image(
            context,
            chat.id,
            result.slides,
            video_type=result.video_type,
            separate_slide_text=result.separate_slide_text,
        )
        if result.video_type in {
            VideoType.TYPE_4,
            VideoType.TYPE_5,
            VideoType.ADVICE,
        }:
            return
        context.user_data["repeat_request"] = {
            "chosen_account": result.chosen_account,
            "requested_accounts": request.account_inputs,
            "video_type": result.video_type.value,
            "language": result.language.value,
            "video_gender": request.gender.value,
            "lowercase_text": request.lowercase_text,
            "separate_slide_text": request.separate_slide_text,
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
            "separate_slide_text": request.separate_slide_text,
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


async def _send_photo_album(context, chat_id: int, paths):
    paths = [Path(path) for path in paths]
    if len(paths) < 2:
        if paths:
            return [await _send_photo(context, chat_id, paths[0])]
        return []

    async def send_opened_album(*, chat_id: int, photo_paths):
        # Rebuild every InputMediaPhoto on each retry. PTB consumes file inputs
        # while preparing the multipart request, so reusing them after a broken
        # HTTP connection is unsafe.
        with ExitStack() as stack:
            media = [
                InputMediaPhoto(stack.enter_context(path.open("rb")))
                for path in photo_paths
            ]
            return await context.bot.send_media_group(
                chat_id=chat_id,
                media=media,
                read_timeout=TELEGRAM_READ_TIMEOUT,
                write_timeout=TELEGRAM_MEDIA_WRITE_TIMEOUT,
                connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
                pool_timeout=TELEGRAM_POOL_TIMEOUT,
            )

    return await _telegram_call_with_retries(
        send_opened_album,
        chat_id=chat_id,
        photo_paths=paths,
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
            delay = min(
                TELEGRAM_SEND_RETRY_MAX_DELAY,
                TELEGRAM_SEND_RETRY_BASE_DELAY * (2 ** (attempt - 1)),
            )
            LOGGER.warning(
                "Telegram network error while sending; retrying in %.2fs (%d/%d)",
                delay,
                attempt,
                TELEGRAM_SEND_ATTEMPTS,
                exc_info=True,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Telegram send retry loop finished without a result")


async def _send_slides_text_then_image(
    context,
    chat_id: int,
    slides,
    *,
    video_type: VideoType | None = None,
    separate_slide_text: bool = False,
) -> None:
    slides = list(slides)
    paths = []

    # Keep any deliberately separate copy before the album. Slide copy is
    # otherwise embedded in the rendered images, except for the Type 3 hook,
    # which stays clean and is delivered as Telegram text.
    for slide in slides:
        path = slide.media.local_path
        if not path.exists():
            continue
        paths.append(path)
        if separate_slide_text and slide.text:
            for message in _separate_slide_text_messages(slide, video_type):
                await _send_message(context, chat_id, message)
        elif video_type == VideoType.TYPE_3 and slide.role == SlideRole.HOOK and slide.text:
            await _send_message(context, chat_id, slide.text)

    # Every carousel is delivered as one Telegram media group. The helper
    # falls back to send_photo when only one valid slide exists.
    if paths:
        await _send_photo_album(context, chat_id, paths)


def _separate_slide_text_messages(
    slide: SlidePlan,
    video_type: VideoType | None,
) -> list[str]:
    text = slide.text.strip()
    if not text:
        return []
    if (
        video_type in {VideoType.TYPE_1, VideoType.TYPE_2}
        and slide.role != SlideRole.HOOK
        and "\n" in text
    ):
        title, body = text.split("\n", 1)
        title = title.strip()
        body = body.strip()
        if title.endswith(".") and title[:-1].isdigit() and body:
            return [f"{title} {body}".strip()]
        return [part for part in (title, body) if part]
    return [text]


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


def _story_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Español",
                    callback_data="wizard:storylang:es",
                ),
                InlineKeyboardButton(
                    "English",
                    callback_data="wizard:storylang:en",
                ),
            ]
        ]
    )


def _advice_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Español",
                    callback_data="wizard:advicelang:es",
                ),
                InlineKeyboardButton(
                    "English",
                    callback_data="wizard:advicelang:en",
                ),
            ]
        ]
    )


def _type_5_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Español",
                    callback_data="wizard:type5lang:es",
                ),
                InlineKeyboardButton(
                    "English",
                    callback_data="wizard:type5lang:en",
                ),
            ]
        ]
    )


def _story_language_from_args(args) -> Language | None:
    values = [str(value).strip().lower() for value in (args or []) if str(value).strip()]
    if not values:
        return None
    if values[0] in {"en", "eng", "english", "ingles", "inglés"}:
        return Language.EN
    if values[0] in {"es", "esp", "spanish", "espanol", "español"}:
        return Language.ES
    return None


def _prepare_story_carousel_state(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    source: str = "upload",
) -> None:
    context.user_data["video_type"] = VideoType.TYPE_4.value
    context.user_data["video_gender"] = VideoGender.MALE.value
    context.user_data["accounts_snapshot"] = []
    context.user_data["story_source"] = source


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
    user = update.effective_user
    user_scope = str(user.id) if user is not None else "unknown"
    target_dir = settings.downloads_dir / "_story_references" / user_scope
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
    context.user_data.pop("separate_slide_text", None)
    context.user_data.pop("reference_image_path", None)
    context.user_data.pop("story_source", None)


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


def _type_1_pool_status_for_accounts(
    summary: dict,
    accounts: list[str],
) -> dict[str, object]:
    allowed = {
        normalized
        for account in accounts
        if (normalized := normalize_account(account)) is not None
    }
    by_type_by_account = summary.get("by_type_by_account", {})
    viable = summary.get("viable_accounts_by_type", {}).get("1", [])
    return {
        "by_type": {
            "1": sum(
                int(counts.get("1", 0))
                for account, counts in by_type_by_account.items()
                if account in allowed and isinstance(counts, dict)
            )
        },
        "viable_accounts_by_type": {
            "1": [account for account in viable if account in allowed]
        },
    }


def _format_pool_status(summary: dict) -> str:
    by_type = summary.get("by_type", {})
    by_account = summary.get("by_account", {})
    viable = summary.get("viable_accounts_by_type", {})
    by_gender = summary.get("by_gender", {})
    account_lines = [
        f"@{account}: {count}"
        for account, count in sorted(by_account.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    text = (
        "Pool de fotos (global)\n"
        f"Fotos aptas para planes: {summary.get('total', 0)}\n"
        f"Fotos en disco sin usar: {summary.get('raw_total', summary.get('total', 0))}\n"
        f"Tipo 1 aptas: {by_type.get('1', 0)} "
        f"({_format_viable_account_count(viable.get('1', []))})\n"
        f"Tipo 2 aptas: {by_type.get('2', 0)} "
        f"({_format_viable_account_count(viable.get('2', []))})\n"
        f"Tipo 3 aptas: {by_type.get('3', 0)} "
        f"({_format_viable_account_count(viable.get('3', []))})"
    )
    if by_gender:
        text += "\n\nTipo 1 según protagonista:"
        for gender, label in (
            (VideoGender.MALE.value, "Hombres"),
            (VideoGender.FEMALE.value, "Mujeres"),
        ):
            gender_summary = by_gender.get(gender)
            if not isinstance(gender_summary, dict):
                continue
            gender_by_type = gender_summary.get("by_type", {})
            gender_viable = gender_summary.get("viable_accounts_by_type", {})
            viable_count = len(gender_viable.get("1", []))
            account_label = "cuenta capaz" if viable_count == 1 else "cuentas capaces"
            text += (
                f"\n{label}: {gender_by_type.get('1', 0)} fotos "
                f"({viable_count} {account_label} de generar ahora)"
            )
    if account_lines:
        text += "\n\nPor cuenta con stock:\n" + "\n".join(account_lines)
    return text


def _format_viable_account_count(accounts: object) -> str:
    count = len(accounts) if isinstance(accounts, list) else 0
    label = (
        "cuenta con combinación válida"
        if count == 1
        else "cuentas con combinación válida"
    )
    return f"{count} {label}"


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
            "Cuentas revisadas en esta tanda: "
            f"{summary.get('accounts_checked', 0)}"
            + (
                f"/{summary.get('account_limit')}"
                if summary.get("account_limit")
                else ""
            )
        ),
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
    if summary.get("account_limit_reached"):
        lines.append("")
        lines.append(
            "Pare aqui porque se alcanzo el limite de cuentas por tanda. "
            "Puedes lanzar /download_pool otra vez para precalentar otra tanda."
        )
    elif summary.get("fresh_limit_reached"):
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
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    if user is None:
        if message:
            await message.reply_text("No pude identificar tu cuenta de Telegram.")
        return False

    chat_type = getattr(chat, "type", None)
    if chat_type is not None and str(chat_type).lower() != "private":
        if message:
            await message.reply_text(
                "Por privacidad, usa el bot desde un chat privado. "
                "No genero ni envío fotos en grupos o canales."
            )
        return False

    store = _telegram_state_store()
    username = user.username or user.full_name or ""
    chat_id = chat.id if chat else None
    owner_id = store.get_owner_user_id()

    if owner_id is None:
        if settings.allowed_chat_ids and chat_id not in settings.allowed_chat_ids:
            if message:
                await message.reply_text(
                    f"Este usuario no está autorizado. Tu ID es {user.id}."
                )
            return False
        if store.claim_or_check_owner(
            user_id=user.id,
            chat_id=chat_id,
            username=username,
        ):
            store.touch_telegram_user(
                user_id=user.id,
                chat_id=chat_id,
                username=username,
            )
            return True

    if store.is_telegram_user_authorized(user.id):
        store.touch_telegram_user(
            user_id=user.id,
            chat_id=chat_id,
            username=username,
        )
        return True

    # Existing comma-separated chat IDs remain a bootstrap allow-list.
    if chat_id is not None and chat_id in settings.allowed_chat_ids:
        store.authorize_telegram_user(
            user_id=user.id,
            added_by=owner_id or user.id,
            username=username,
            chat_id=chat_id,
        )
        store.touch_telegram_user(
            user_id=user.id,
            chat_id=chat_id,
            username=username,
        )
        return True

    if message:
        await message.reply_text(
            f"Este usuario no está autorizado. Tu ID es {user.id}. "
            "Pide al propietario que use /add_user con ese ID."
        )
    return False


async def _ensure_admin(update: Update) -> bool:
    if not await _ensure_allowed(update):
        return False
    user = update.effective_user
    if user is not None and _telegram_state_store().get_owner_user_id() == user.id:
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            "Este comando solo puede usarlo el propietario del bot."
        )
    return False


def _telegram_state_store() -> StateStore:
    settings = get_settings()
    return StateStore(
        settings.state_dir,
        history_max_per_bucket=settings.history_max_per_bucket,
    )


def _is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(
        user is not None
        and _telegram_state_store().get_owner_user_id() == user.id
    )


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
