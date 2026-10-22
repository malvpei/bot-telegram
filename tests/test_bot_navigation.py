import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram import MenuButtonCommands, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from app import bot
from app.models import VideoGender, VideoType


STATES = (
    bot.GENDER_STATE,
    bot.TYPE_STATE,
    bot.DELIVERY_STATE,
    bot.LANGUAGE_STATE,
    bot.LOWERCASE_STATE,
    bot.STORY_PHOTO_STATE,
    bot.GOGRADUATE_STATE,
)
BRANDS = {"ui:create", "ui:createp", "ui:g"}
WIZARD_SELECTION = {
    "creation_brand": "dropradar",
    "accounts_by_gender": {"male": ["old"], "female": ["old-woman"]},
    "accounts_snapshot": ["old"],
    "video_gender": "male",
    "video_type": "2",
    "language": "en",
    "separate_slide_text": True,
    "reference_image_path": "old-reference.jpg",
    "story_source": "reference",
    "repeat_request": {"chosen_account": "old"},
}


def _update(*, data=None, command=None, telegram_bot=None):
    telegram_bot = telegram_bot or SimpleNamespace(
        username="test_bot",
        answer_callback_query=AsyncMock(return_value=True),
        edit_message_text=AsyncMock(),
        send_message=AsyncMock(),
    )
    message = {
        "message_id": 10,
        "date": 1,
        "chat": {"id": 123, "type": "private"},
        "from": {"id": 456, "is_bot": False, "first_name": "Tester"},
        "text": command or "Elige una opción",
    }
    if command:
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(command.split()[0])}]
        payload = {"update_id": 1, "message": message}
    else:
        payload = {
            "update_id": 1,
            "callback_query": {
                "id": "callback-1",
                "from": message["from"],
                "message": message,
                "chat_instance": "private-chat",
                "data": data,
            },
        }
    update = Update.de_json(payload, telegram_bot)
    application = SimpleNamespace(bot=telegram_bot, bot_data={"service": Mock()})
    context = SimpleNamespace(bot=telegram_bot, application=application, user_data={}, args=[])
    return update, context


def _last_response(context):
    edits = context.bot.edit_message_text.await_args_list
    replies = context.bot.send_message.await_args_list
    assert edits or replies
    return (edits or replies)[-1].kwargs


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }


@pytest.fixture
def authorized(monkeypatch):
    store = Mock()
    store.get_owner_user_id.return_value = 456
    store.is_telegram_user_authorized.return_value = True
    monkeypatch.setattr(bot, "_telegram_state_store", lambda: store)
    monkeypatch.setattr(bot, "_load_accounts_by_gender", lambda settings: {
        VideoGender.MALE: ["alpha", "beta"],
        VideoGender.FEMALE: ["woman"],
    })
    return store


def test_start_shows_short_home_and_discards_previous_selection(authorized):
    update, context = _update(command="/start")
    context.user_data.update(WIZARD_SELECTION, unrelated="keep")

    state = asyncio.run(bot.start(update, context))

    assert state == ConversationHandler.END
    assert context.user_data == {"unrelated": "keep"}
    response = _last_response(context)
    assert len(response["text"]) < 500
    assert BRANDS | {"ui:tools", "ui:help"} == _callbacks(response["reply_markup"])
    assert "/sync" not in response["text"]


@pytest.mark.parametrize("route", ["ui:home", "ui:cancel"])
def test_home_and_cancel_clear_only_creation_selection(route, authorized):
    update, context = _update(data=route)
    context.user_data.update(WIZARD_SELECTION, unrelated="keep")

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == ConversationHandler.END
    assert context.user_data == {"unrelated": "keep"}
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()


@pytest.mark.parametrize(
    ("route", "expected_state"),
    [("ui:create", bot.TYPE_STATE), ("ui:createp", bot.GENDER_STATE), ("ui:g", bot.GOGRADUATE_STATE)],
)
def test_brand_navigation_replaces_old_creation_selection(route, expected_state, authorized):
    update, context = _update(data=route)
    context.user_data.update(WIZARD_SELECTION, unrelated="keep")

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == expected_state
    assert context.user_data["unrelated"] == "keep"
    assert not ({"video_type", "language", "reference_image_path", "story_source", "repeat_request"} & context.user_data.keys())
    if route == "ui:create":
        assert context.user_data["creation_brand"] == "dropradar"
        assert context.user_data["accounts_snapshot"] == ["alpha", "beta"]
        assert context.user_data["video_gender"] == "male"
    elif route == "ui:createp":
        assert context.user_data["creation_brand"] == "parkez"
        assert context.user_data["accounts_by_gender"] == {"male": ["alpha", "beta"], "female": ["woman"]}
    else:
        assert context.user_data == {"creation_brand": "gograduate", "unrelated": "keep"}
    assert "ui:home" in _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()


@pytest.mark.parametrize("route", ["ui:tools", "ui:help"])
def test_informational_menus_preserve_creation_selection(route, authorized):
    update, context = _update(data=route)
    context.user_data.update(WIZARD_SELECTION, unrelated="keep")
    before = dict(context.user_data)

    asyncio.run(bot.navigation_callback(update, context))

    assert context.user_data == before
    assert "ui:home" in _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()
    if route == "ui:tools":
        assert {"ui:pool", "ui:memory", "ui:accounts", "ui:schedule"} <= _callbacks(_last_response(context)["reply_markup"])


def test_schedule_button_only_reads_status_even_with_stale_command_arguments(authorized, monkeypatch):
    update, context = _update(data="ui:schedule")
    context.args = ["off"]
    context.user_data.update(WIZARD_SELECTION)
    before = dict(context.user_data)
    schedule_store = Mock()
    monkeypatch.setattr(bot, "_batch_store", lambda: schedule_store)
    formatter = Mock(return_value="Programación vigente")
    monkeypatch.setattr(bot, "_format_batch_schedule_status", formatter)

    asyncio.run(bot.navigation_callback(update, context))

    assert context.user_data == before
    assert context.args == ["off"]
    formatter.assert_called_once_with(schedule_store, read_only=True)
    assert "Programación vigente" in _last_response(context)["text"]
    schedule_store.disable_batch_schedule.assert_not_called()
    schedule_store.write_batch_schedule.assert_not_called()
    assert "ui:home" in _callbacks(_last_response(context)["reply_markup"])


def test_schedule_menu_does_not_migrate_a_saved_legacy_schedule(authorized, monkeypatch, tmp_path):
    from app.state import StateStore

    store = StateStore(tmp_path / "state")
    schedule_path = store.state_dir / "batch_schedule.json"
    store._write_json(schedule_path, {
        "schema_version": 1, "enabled": True, "count": 5,
        "times": ["09:00"], "timezone": "Europe/Madrid",
        "chat_id": 123, "user_id": 456,
    })
    before = schedule_path.read_bytes()
    monkeypatch.setattr(bot, "_batch_store", lambda: store)
    update, context = _update(data="ui:schedule")

    asyncio.run(bot.navigation_callback(update, context))

    assert schedule_path.read_bytes() == before
    assert "09:00" in _last_response(context)["text"]


def test_memory_menu_reads_counts_without_initializing_or_resetting_memory(authorized):
    authorized.memory_snapshot.return_value = {"used_media_count": 42, "jobs_count": 7}
    update, context = _update(data="ui:memory")

    asyncio.run(bot.navigation_callback(update, context))

    text = _last_response(context)["text"]
    assert "42" in text and "7" in text
    authorized.ensure_persistence_marker.assert_not_called()
    authorized.reset_used_media.assert_not_called()


def test_schedule_button_preserves_owner_only_access(authorized, monkeypatch):
    authorized.get_owner_user_id.return_value = 999
    update, context = _update(data="ui:schedule")
    context.user_data.update(WIZARD_SELECTION)
    before = dict(context.user_data)
    formatter = Mock()
    monkeypatch.setattr(bot, "_format_batch_schedule_status", formatter)

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == ConversationHandler.END
    assert context.user_data == before
    assert "propietario" in _last_response(context)["text"]
    context.bot.answer_callback_query.assert_awaited()
    formatter.assert_not_called()


@pytest.mark.parametrize("route", ["ui:home", "ui:create", "ui:createp", "ui:g", "ui:tools", "ui:pool", "ui:memory", "ui:accounts", "ui:schedule", "ui:help", "ui:cancel"])
def test_navigation_rechecks_authorization_before_any_action(route, authorized, monkeypatch):
    authorized.is_telegram_user_authorized.return_value = False
    authorized.get_owner_user_id.return_value = 999
    settings = SimpleNamespace(allowed_chat_ids=[])
    monkeypatch.setattr(bot, "get_settings", lambda: settings)
    update, context = _update(data=route)
    context.user_data.update(WIZARD_SELECTION)
    before = dict(context.user_data)
    execute = AsyncMock()
    monkeypatch.setattr(bot, "_execute_job", execute)

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == ConversationHandler.END
    assert context.user_data == before
    context.bot.answer_callback_query.assert_awaited()
    assert "autorizado" in _last_response(context)["text"]
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("initial_state", "data"),
    [
        (bot.GENDER_STATE, "parkez:gender:female"),
        (bot.GENDER_STATE, "parkez:tools"),
        (bot.GENDER_STATE, "parkez:mode3"),
        (bot.GENDER_STATE, "parkez:advice"),
        (bot.GENDER_STATE, "parkez:apps"),
        (bot.TYPE_STATE, "wizard:type:1"),
        (bot.TYPE_STATE, "template_video:create:es"),
        (bot.DELIVERY_STATE, "wizard:delivery:separate"),
        (bot.LANGUAGE_STATE, "wizard:lang:es"),
        (bot.LANGUAGE_STATE, "wizard:storylang:es"),
        (bot.LANGUAGE_STATE, "wizard:advicelang:es"),
        (bot.LANGUAGE_STATE, "wizard:type5lang:es"),
        (bot.LOWERCASE_STATE, "wizard:lowercase:no"),
        (bot.GOGRADUATE_STATE, "gograduate:type:1"),
    ],
)
def test_registered_creation_callbacks_recheck_revoked_access(initial_state, data, authorized, monkeypatch):
    authorized.is_telegram_user_authorized.return_value = False
    authorized.get_owner_user_id.return_value = 999
    monkeypatch.setattr(bot, "get_settings", lambda: SimpleNamespace(allowed_chat_ids=[]))
    update, context = _update(data=data)
    context.user_data.update(WIZARD_SELECTION)
    before = dict(context.user_data)
    execute = AsyncMock()
    monkeypatch.setattr(bot, "_execute_job", execute)
    handler = bot._build_wizard_handler()
    key = (123, 456)
    handler._conversations[key] = initial_state
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert key not in handler._conversations
    assert context.user_data == before
    context.bot.answer_callback_query.assert_awaited()
    assert "autorizado" in _last_response(context)["text"]
    execute.assert_not_awaited()


@pytest.mark.parametrize("route", ["ui:unknown", "ui:back:type", "ui:back:delivery", "ui:back:language"])
def test_unknown_or_stale_navigation_recovers_home(route, authorized):
    update, context = _update(data=route)

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == ConversationHandler.END
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()


@pytest.mark.parametrize("data", ["wizard:lang:es", "parkez:tools", "gograduate:type:1", "regen:expired", "obsolete:button"])
def test_global_stale_callback_recovers_home_without_generation(data, authorized, monkeypatch):
    update, context = _update(data=data)
    execute = AsyncMock()
    monkeypatch.setattr(bot, "_execute_job", execute)

    state = asyncio.run(bot.stale_callback(update, context))

    assert state == ConversationHandler.END
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()
    execute.assert_not_awaited()


def test_stale_creation_button_in_other_brand_recovers_home(authorized, monkeypatch):
    update, context = _update(data="wizard:lang:es")
    context.user_data.update(WIZARD_SELECTION)
    execute = AsyncMock()
    monkeypatch.setattr(bot, "_execute_job", execute)
    handler = bot._build_wizard_handler()
    key = (123, 456)
    handler._conversations[key] = bot.GOGRADUATE_STATE
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert key not in handler._conversations
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("brand_route", "expected_brand", "old_data"),
    [
        ("ui:create", "dropradar", "parkez:tools"),
        ("ui:createp", "parkez", "wizard:type:advice"),
    ],
)
def test_shared_gender_state_rejects_previous_brand_buttons(brand_route, expected_brand, old_data, authorized, monkeypatch):
    monkeypatch.setattr(bot, "_load_accounts_by_gender", lambda settings: {VideoGender.MALE: [], VideoGender.FEMALE: []})
    execute = AsyncMock()
    monkeypatch.setattr(bot, "_execute_job", execute)
    update, context = _update(data=brand_route)
    context.user_data["unrelated"] = "keep"
    handler = bot._build_wizard_handler()
    key = (123, 456)
    check_result = handler.check_update(update)
    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))
    assert handler._conversations[key] == bot.GENDER_STATE
    assert context.user_data["creation_brand"] == expected_brand
    stale_update, _ = _update(data=old_data, telegram_bot=context.bot)
    stale_result = handler.check_update(stale_update)

    assert stale_result is not None
    asyncio.run(handler.handle_update(stale_update, context.application, stale_result, context))

    assert key not in handler._conversations
    assert context.user_data == {"unrelated": "keep"}
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("selected_type", "old_data", "initial_state"),
    [
        (VideoType.TYPE_5, "wizard:advicelang:en", bot.LANGUAGE_STATE),
        (VideoType.TYPE_2, "wizard:type5lang:en", bot.LANGUAGE_STATE),
        (VideoType.ADVICE, "wizard:storylang:en", bot.LANGUAGE_STATE),
        (VideoType.TYPE_5, "wizard:lang:en", bot.LANGUAGE_STATE),
        (VideoType.ADVICE, "wizard:delivery:separate", bot.DELIVERY_STATE),
        (VideoType.TYPE_5, "wizard:lowercase:no", bot.LOWERCASE_STATE),
    ],
)
def test_shared_steps_reject_buttons_for_another_content_type(selected_type, old_data, initial_state, authorized, monkeypatch):
    update, context = _update(data=old_data)
    context.user_data.update(WIZARD_SELECTION, video_type=selected_type.value, unrelated="keep")
    execute = AsyncMock()
    monkeypatch.setattr(bot, "_execute_job", execute)
    handler = bot._build_wizard_handler()
    key = (123, 456)
    handler._conversations[key] = initial_state
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert key not in handler._conversations
    assert context.user_data == {"unrelated": "keep"}
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])
    context.bot.answer_callback_query.assert_awaited()
    execute.assert_not_awaited()


def test_back_to_type_keeps_loaded_accounts_and_offers_all_five_types(authorized, monkeypatch):
    update, context = _update(data="ui:back:type")
    context.user_data.update(WIZARD_SELECTION)
    reload_accounts = Mock(side_effect=AssertionError("Back should reuse loaded accounts"))
    monkeypatch.setattr(bot, "_load_accounts_by_gender", reload_accounts)

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == bot.TYPE_STATE
    assert context.user_data["accounts_snapshot"] == ["old"]
    assert context.user_data["video_gender"] == "male"
    assert context.user_data["accounts_by_gender"] == WIZARD_SELECTION["accounts_by_gender"]
    assert {"wizard:type:1", "wizard:type:2", "wizard:type:3", "wizard:type:advice", "wizard:type:5"} <= _callbacks(_last_response(context)["reply_markup"])
    reload_accounts.assert_not_called()


def test_back_to_delivery_preserves_type_and_accounts(authorized):
    update, context = _update(data="ui:back:delivery")
    context.user_data.update(WIZARD_SELECTION)

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == bot.DELIVERY_STATE
    assert context.user_data["video_type"] == "2"
    assert context.user_data["accounts_snapshot"] == ["old"]
    assert {"wizard:delivery:embedded", "wizard:delivery:separate", "ui:back:type", "ui:home", "ui:cancel"} <= _callbacks(_last_response(context)["reply_markup"])


@pytest.mark.parametrize(
    ("video_type", "callback_prefix"),
    [(VideoType.TYPE_1, "wizard:lang:"), (VideoType.ADVICE, "wizard:advicelang:"), (VideoType.TYPE_4, "wizard:storylang:"), (VideoType.TYPE_5, "wizard:type5lang:")],
)
def test_back_to_language_uses_selected_content_language_callbacks(video_type, callback_prefix, authorized):
    update, context = _update(data="ui:back:language")
    context.user_data.update(WIZARD_SELECTION, video_type=video_type.value)

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == bot.LANGUAGE_STATE
    assert context.user_data["video_type"] == video_type.value
    assert context.user_data["accounts_snapshot"] == ["old"]
    assert {f"{callback_prefix}es", f"{callback_prefix}en", "ui:home", "ui:cancel"} <= _callbacks(_last_response(context)["reply_markup"])


def test_navigation_handles_callback_without_effective_message(authorized):
    query = SimpleNamespace(data="ui:create", answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(
        callback_query=query,
        effective_message=None,
        effective_chat=SimpleNamespace(id=123, type="private"),
        effective_user=SimpleNamespace(id=456, username="tester", full_name="Tester"),
    )
    _, context = _update(data="ui:create")

    state = asyncio.run(bot.navigation_callback(update, context))

    assert state == bot.TYPE_STATE
    query.answer.assert_awaited()
    query.edit_message_text.assert_awaited()
    assert context.user_data["accounts_snapshot"] == ["alpha", "beta"]


@pytest.mark.parametrize(
    ("initial_state", "data", "expected_state", "back"),
    [
        (bot.TYPE_STATE, "wizard:type:1", bot.DELIVERY_STATE, "ui:back:type"),
        (bot.DELIVERY_STATE, "wizard:delivery:separate", bot.LANGUAGE_STATE, "ui:back:delivery"),
        (bot.LANGUAGE_STATE, "wizard:lang:es", bot.LOWERCASE_STATE, "ui:back:language"),
        (bot.TYPE_STATE, "wizard:type:advice", bot.LANGUAGE_STATE, "ui:back:type"),
        (bot.TYPE_STATE, "wizard:type:5", bot.LANGUAGE_STATE, "ui:back:type"),
    ],
)
def test_creation_steps_keep_back_home_and_cancel_navigation(initial_state, data, expected_state, back, authorized):
    update, context = _update(data=data)
    context.user_data.update(WIZARD_SELECTION)
    handler = bot._build_wizard_handler()
    key = (123, 456)
    handler._conversations[key] = initial_state
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert handler._conversations[key] == expected_state
    assert {back, "ui:home", "ui:cancel"} <= _callbacks(_last_response(context)["reply_markup"])


def test_story_command_with_language_keeps_upload_navigation(authorized):
    update, context = _update(command="/story_carousel en")
    handler = bot._build_wizard_handler()
    key = (123, 456)
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert handler._conversations[key] == bot.STORY_PHOTO_STATE
    assert context.user_data["creation_brand"] == "dropradar"
    assert context.user_data["language"] == "en"
    assert {"ui:back:language", "ui:home", "ui:cancel"} <= _callbacks(_last_response(context)["reply_markup"])


def test_conversation_has_reentrant_commands_and_navigation_fallback():
    handler = bot._build_wizard_handler()

    assert handler.allow_reentry is True
    commands = set().union(*(entry.commands for entry in handler.entry_points if isinstance(entry, CommandHandler)))
    assert {"start", "menu", "help", "create", "createp", "g", "wizard", "story_carousel"} <= commands
    assert any(isinstance(entry, CallbackQueryHandler) and entry.callback is bot.navigation_callback for entry in handler.entry_points)
    assert any(isinstance(entry, CallbackQueryHandler) and entry.callback is bot.navigation_callback for entry in handler.fallbacks)
    assert any(isinstance(entry, CommandHandler) and "cancel" in entry.commands for entry in handler.fallbacks)


@pytest.mark.parametrize("initial_state", [None, *STATES])
@pytest.mark.parametrize(
    ("route", "expected_state"),
    [("ui:create", bot.TYPE_STATE), ("ui:createp", bot.GENDER_STATE), ("ui:g", bot.GOGRADUATE_STATE)],
)
def test_real_conversation_routes_each_brand_from_every_creation_state(initial_state, route, expected_state, authorized):
    update, context = _update(data=route)
    context.user_data.update(WIZARD_SELECTION)
    handler = bot._build_wizard_handler()
    key = (123, 456)
    if initial_state is not None:
        handler._conversations[key] = initial_state
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert handler._conversations[key] == expected_state
    assert "repeat_request" not in context.user_data
    assert "video_type" not in context.user_data
    context.bot.answer_callback_query.assert_awaited()
    if route == "ui:create":
        assert "wizard:type:1" in _callbacks(_last_response(context)["reply_markup"])
    elif route == "ui:createp":
        assert "parkez:tools" in _callbacks(_last_response(context)["reply_markup"])
    else:
        assert "gograduate:type:1" in _callbacks(_last_response(context)["reply_markup"])


@pytest.mark.parametrize("initial_state", STATES)
def test_real_conversation_start_reentry_leaves_creation_from_every_state(initial_state, authorized):
    update, context = _update(command="/start")
    context.user_data.update(WIZARD_SELECTION)
    handler = bot._build_wizard_handler()
    key = (123, 456)
    handler._conversations[key] = initial_state
    check_result = handler.check_update(update)

    assert check_result is not None
    asyncio.run(handler.handle_update(update, context.application, check_result, context))

    assert key not in handler._conversations
    assert context.user_data == {}
    assert BRANDS <= _callbacks(_last_response(context)["reply_markup"])


def test_post_init_registers_native_commands_and_restores_schedule(monkeypatch):
    application = SimpleNamespace(bot_data={}, bot=SimpleNamespace(set_my_commands=AsyncMock(), set_chat_menu_button=AsyncMock()))
    restore = Mock()
    missed = Mock()
    monkeypatch.setattr(bot, "_replace_scheduled_batch_jobs", restore)
    monkeypatch.setattr(bot, "_queue_missed_scheduled_batch", missed)

    asyncio.run(bot._post_init(application))

    assert isinstance(application.bot_data["batch_lock"], asyncio.Lock)
    application.bot.set_my_commands.assert_awaited_once()
    call = application.bot.set_my_commands.await_args
    commands = call.args[0] if call.args else call.kwargs["commands"]
    assert {"start", "create", "createp", "g", "help"} <= {command.command for command in commands}
    assert len(commands) <= 12
    application.bot.set_chat_menu_button.assert_awaited_once()
    assert isinstance(application.bot.set_chat_menu_button.await_args.kwargs["menu_button"], MenuButtonCommands)
    restore.assert_called_once_with(application)
    missed.assert_called_once_with(application)


@pytest.mark.parametrize("failing_method", ["set_my_commands", "set_chat_menu_button"])
def test_native_command_registration_failure_does_not_prevent_schedule_restore(failing_method, monkeypatch):
    telegram_bot = SimpleNamespace(set_my_commands=AsyncMock(), set_chat_menu_button=AsyncMock())
    getattr(telegram_bot, failing_method).side_effect = TelegramError("Telegram unavailable")
    application = SimpleNamespace(bot_data={}, bot=telegram_bot)
    restore = Mock()
    missed = Mock()
    monkeypatch.setattr(bot, "_replace_scheduled_batch_jobs", restore)
    monkeypatch.setattr(bot, "_queue_missed_scheduled_batch", missed)

    asyncio.run(bot._post_init(application))

    restore.assert_called_once_with(application)
    missed.assert_called_once_with(application)
