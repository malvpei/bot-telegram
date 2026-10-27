import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot_ui import (
    BOT_COMMANDS,
    HELP_TEXT,
    HOME_TEXT,
    TOOLS_TEXT,
    completion_keyboard,
    dropradar_keyboard,
    gograduate_keyboard,
    home_keyboard,
    parkez_keyboard,
    tools_keyboard,
    with_navigation,
)
from app.models import VideoType


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _routes(markup):
    return [button.callback_data for button in _buttons(markup)]


def test_home_exposes_all_three_brands_and_support():
    markup = home_keyboard()

    assert _routes(markup) == ["ui:create", "ui:createp", "ui:g", "ui:tools", "ui:help"]
    assert all(
        any(brand in button.text for button in _buttons(markup))
        for brand in ("Dropradar", "ParkEz", "gograduate.io")
    )


def test_tools_only_offers_status_and_navigation():
    assert set(_routes(tools_keyboard())) == {
        "ui:pool", "ui:memory", "ui:accounts", "ui:schedule",
        "ui:help", "ui:home", "ui:cancel",
    }


def test_dropradar_offers_direct_format_choices_without_gender_step():
    markup = dropradar_keyboard(True)
    labels = {button.callback_data: button.text for button in _buttons(markup)}

    assert labels["wizard:type:1"] == "Tipo 1 · Historia"
    assert labels["wizard:type:2"] == "Tipo 2 · 4 consejos"
    assert labels["wizard:type:3"] == "Tipo 3 · Herramientas"
    assert labels["wizard:type:advice"] == "Tipo 4 · Consejos"
    assert labels["wizard:type:5"] == "Tipo 5 · Negocios"
    assert labels["wizard:type:4"] == "✨ Historia IA · Desde una foto"
    assert "template_video:create:es" in labels
    assert "template_video:create:en" in labels
    assert not any(route.startswith("wizard:gender:") for route in labels)


def test_dropradar_without_accounts_keeps_formats_that_need_no_instagram():
    routes = set(_routes(dropradar_keyboard(False)))

    assert routes == {
        "wizard:type:advice", "wizard:type:5", "wizard:type:4",
        "template_video:create:es", "template_video:create:en",
        "ui:home", "ui:cancel",
    }


def test_parkez_explains_every_format():
    labels = {button.callback_data: button.text for button in _buttons(parkez_keyboard())}

    assert labels["parkez:gender:female"] == "Mujer · Fotos"
    assert labels["parkez:gender:male"] == "Hombre · Fotos"
    assert labels["parkez:tools"] == "Tools · Apps de coche"
    assert labels["parkez:mode3"] == "mode3 · Carnet y trucos"
    assert labels["parkez:advice"] == "Consejos · Recopilatorio"
    assert labels["parkez:apps"] == "Apps iPhone · 5 imágenes"


def test_gograduate_explains_its_format():
    button = gograduate_keyboard().inline_keyboard[0][0]

    assert button.text == "Tipo 1 · Consejos de estudio"
    assert button.callback_data == "gograduate:type:1"


def test_navigation_copies_keyboard_and_replaces_an_existing_footer():
    original = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Contenido", callback_data="wizard:type:1")]]
    )
    original_rows = original.inline_keyboard
    initial = with_navigation(original, back="ui:back:delivery")
    changed = with_navigation(initial, back="ui:back:type")

    assert original.inline_keyboard == original_rows
    assert len(original.inline_keyboard) == 1
    assert len(changed.inline_keyboard) == 2
    assert _routes(changed) == ["wizard:type:1", "ui:back:type", "ui:home", "ui:cancel"]
    assert _routes(initial) == ["wizard:type:1", "ui:back:delivery", "ui:home", "ui:cancel"]
    assert len(changed.inline_keyboard[-1]) == 3


def test_navigation_omits_duplicate_home_and_optional_cancel():
    markup = with_navigation(with_navigation(None), cancel=False)

    assert _routes(markup) == ["ui:home"]
    assert len(markup.inline_keyboard) == 1


@pytest.mark.parametrize("video_type", list(VideoType))
def test_completion_returns_to_the_correct_brand_without_starting_generation(video_type):
    routes = _routes(completion_keyboard(video_type))
    expected = (
        "ui:createp"
        if video_type in {
            VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.PARKEZ_ADVICE,
            VideoType.PARKEZ_APPS, VideoType.TOOLS,
        }
        else "ui:g" if video_type == VideoType.GOGRADUATE_TYPE_1 else "ui:create"
    )

    assert routes == [expected, "ui:home"]
    assert _routes(completion_keyboard(video_type.value)) == routes


def test_all_keyboard_callbacks_fit_telegram_limit_and_have_known_routes():
    known = {
        "ui:create", "ui:createp", "ui:g", "ui:tools", "ui:help", "ui:home", "ui:cancel",
        "ui:pool", "ui:memory", "ui:accounts", "ui:schedule",
        "wizard:type:1", "wizard:type:2", "wizard:type:3", "wizard:type:4", "wizard:type:advice", "wizard:type:5",
        "template_video:create:es", "template_video:create:en",
        "parkez:gender:female", "parkez:gender:male", "parkez:tools", "parkez:mode3",
        "parkez:advice", "parkez:apps", "gograduate:type:1",
    }
    keyboards = [
        home_keyboard(), tools_keyboard(), dropradar_keyboard(True), dropradar_keyboard(False),
        parkez_keyboard(), gograduate_keyboard(),
        *(completion_keyboard(video_type) for video_type in VideoType),
    ]

    for keyboard in keyboards:
        for route in _routes(keyboard):
            assert route in known
            assert 1 <= len(route.encode("utf-8")) <= 64


def test_copy_and_command_menu_fit_telegram_limits_and_explain_reset_safely():
    for text in (HOME_TEXT, HELP_TEXT, TOOLS_TEXT):
        assert 0 < len(text) < 4096
    assert "/reset_fotos confirmar" in HELP_TEXT
    assert "Solo puede hacerlo el propietario" in HELP_TEXT
    assert "sin compresión" in HELP_TEXT
    assert "Historia IA" in HELP_TEXT
    assert ("story_carousel", "Crear una historia IA desde tu foto") in BOT_COMMANDS
    assert 1 <= len(BOT_COMMANDS) <= 100
    assert len({command for command, _ in BOT_COMMANDS}) == len(BOT_COMMANDS)
    for command, description in BOT_COMMANDS:
        assert 1 <= len(command) <= 32
        assert command.replace("_", "").isalnum()
        assert command == command.lower()
        assert 1 <= len(description) <= 256
