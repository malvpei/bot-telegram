"""Telegram copy and keyboards, without conversation or service side effects."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import VideoType


HOME_TEXT = (
    "¿Qué quieres crear?\n\n"
    "Elige una marca para ver sus formatos. Te guiaré hasta recibir las imágenes "
    "y los textos listos para publicar.\n\n"
    "Usa los botones para avanzar y vuelve a Inicio cuando quieras."
)

HELP_TEXT = (
    "Crear contenido en tres pasos\n\n"
    "1. Elige Dropradar, ParkEz o gograduate.io en Inicio.\n"
    "2. Escoge el formato y las opciones que aparezcan.\n"
    "3. Recibe el contenido y usa Crear otro para seguir.\n\n"
    "Dropradar: historias, consejos y herramientas de dropshipping. Historia IA "
    "crea seis escenas desde una foto y termina con la original. También "
    "incluye videos R2 con plantilla, en español o inglés.\n"
    "ParkEz: carruseles de fotos, apps y consejos de conducción.\n"
    "gograduate.io: consejos para estudiantes.\n\n"
    "Las fotos se eligen del banco disponible. Según el formato, el texto va "
    "dentro de las imágenes o en mensajes separados. Las imágenes se envían "
    "como archivos, sin compresión. Los videos R2 se entregan en MP4.\n\n"
    "Atrás cambia la selección anterior; Inicio abre las marcas; Cancelar "
    "descarta la selección. Una generación ya iniciada sigue hasta terminar.\n\n"
    "Comandos avanzados\n"
    "/menu — abrir Inicio\n"
    "/pool, /memory — consultar el estado\n"
    "/accounts, /accounts_women — ver cuentas\n"
    "/batch [cantidad] — crear un lote (5 por defecto)\n"
    "/schedule — consultar la programación (propietario)\n"
    "/my_id — ver tu ID\n"
    "/users, /add_user ID, /remove_user ID — accesos (propietario)\n"
    "/sync, /sync_women — actualizar la biblioteca (propietario)\n"
    "/download_pool, /download_pool_women — rellenar el pool (propietario)\n\n"
    "/story_carousel [es|en] — crear una historia IA desde una foto\n"
    "/audit_accounts, /audit_accounts_women — revisar la biblioteca\n"
    "/template_video [es|en] — crear un MP4 R2 con plantilla\n\n"
    "Usa /reset_fotos confirmar para desbloquear todas las fotos ya usadas "
    "sin borrar el pool, las cachés ni el historial de jobs. Solo puede "
    "hacerlo el propietario."
)

TOOLS_TEXT = (
    "Estado y herramientas\n\n"
    "Consulta las fotos disponibles, la memoria, las cuentas y la programación. "
    "Estos botones solo muestran información.\n\n"
    "En Ayuda encontrarás los comandos avanzados. Usa /my_id para ver tu ID; "
    "el propietario gestiona los accesos con /users."
)

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Abrir el menú de marcas"),
    ("menu", "Volver a Inicio"),
    ("create", "Crear contenido de Dropradar"),
    ("story_carousel", "Crear una historia IA desde tu foto"),
    ("createp", "Crear contenido de ParkEz"),
    ("g", "Crear contenido de gograduate.io"),
    ("pool", "Consultar las fotos disponibles"),
    ("batch", "Crear un lote de contenido"),
    ("schedule", "Consultar o configurar lotes (propietario)"),
    ("my_id", "Ver tu ID de Telegram"),
    ("memory", "Consultar la memoria del bot"),
    ("help", "Ver ayuda y comandos avanzados"),
    ("cancel", "Cancelar la selección actual"),
)

_BACK_LABEL = "⬅️ Atrás"
_HOME_LABEL = "🏠 Inicio"
_CANCEL_LABEL = "✖️ Cancelar"
_NAVIGATION_LABELS = {_BACK_LABEL, _HOME_LABEL, _CANCEL_LABEL}


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Dropradar", callback_data="ui:create")],
            [InlineKeyboardButton("🚗 ParkEz", callback_data="ui:createp")],
            [InlineKeyboardButton("🎓 gograduate.io", callback_data="ui:g")],
            [
                InlineKeyboardButton("⚙️ Estado y herramientas", callback_data="ui:tools"),
                InlineKeyboardButton("❓ Ayuda", callback_data="ui:help"),
            ],
        ]
    )


def tools_keyboard() -> InlineKeyboardMarkup:
    return with_navigation(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📷 Fotos disponibles", callback_data="ui:pool"),
                    InlineKeyboardButton("💾 Memoria", callback_data="ui:memory"),
                ],
                [
                    InlineKeyboardButton("👥 Cuentas", callback_data="ui:accounts"),
                    InlineKeyboardButton("🕒 Programación", callback_data="ui:schedule"),
                ],
                [InlineKeyboardButton("❓ Ayuda", callback_data="ui:help")],
            ]
        )
    )


def dropradar_keyboard(has_accounts: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_accounts:
        rows.extend(
            [
                [InlineKeyboardButton("Tipo 1 · Historia", callback_data="wizard:type:1")],
                [InlineKeyboardButton("Tipo 2 · 4 consejos", callback_data="wizard:type:2")],
                [InlineKeyboardButton("Tipo 3 · Herramientas", callback_data="wizard:type:3")],
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton("Tipo 4 · Consejos", callback_data="wizard:type:advice")],
            [InlineKeyboardButton("Tipo 5 · Negocios", callback_data="wizard:type:5")],
            [InlineKeyboardButton("✨ Historia IA · Desde una foto", callback_data="wizard:type:4")],
            [
                InlineKeyboardButton("🎬 Video R2 · Español", callback_data="template_video:create:es"),
                InlineKeyboardButton("🎬 Video R2 · English", callback_data="template_video:create:en"),
            ],
        ]
    )
    return with_navigation(InlineKeyboardMarkup(rows))


def parkez_keyboard() -> InlineKeyboardMarkup:
    return with_navigation(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Mujer · Fotos", callback_data="parkez:gender:female"),
                    InlineKeyboardButton("Hombre · Fotos", callback_data="parkez:gender:male"),
                ],
                [InlineKeyboardButton("Tools · Apps de coche", callback_data="parkez:tools")],
                [InlineKeyboardButton("mode3 · Carnet y trucos", callback_data="parkez:mode3")],
                [InlineKeyboardButton("Consejos · Recopilatorio", callback_data="parkez:advice")],
                [InlineKeyboardButton("Apps iPhone · 5 imágenes", callback_data="parkez:apps")],
            ]
        )
    )


def gograduate_keyboard() -> InlineKeyboardMarkup:
    return with_navigation(
        InlineKeyboardMarkup(
            [[InlineKeyboardButton("Tipo 1 · Consejos de estudio", callback_data="gograduate:type:1")]]
        )
    )


def with_navigation(
    markup: InlineKeyboardMarkup | None,
    *,
    back: str = "ui:home",
    cancel: bool = True,
) -> InlineKeyboardMarkup:
    """Copy a keyboard and replace its navigation footer, if one is present."""
    rows = [
        list(row)
        for row in (markup.inline_keyboard if markup is not None else ())
        if not _is_navigation_row(row)
    ]
    footer = []
    if back != "ui:home":
        footer.append(InlineKeyboardButton(_BACK_LABEL, callback_data=back))
    footer.append(InlineKeyboardButton(_HOME_LABEL, callback_data="ui:home"))
    if cancel:
        footer.append(InlineKeyboardButton(_CANCEL_LABEL, callback_data="ui:cancel"))
    rows.append(footer)
    return InlineKeyboardMarkup(rows)


def completion_keyboard(video_type: VideoType | str) -> InlineKeyboardMarkup:
    """Offer another selection in the same brand after a completed delivery."""
    if video_type in {
        VideoType.PARKEZ,
        VideoType.PARKEZ_MODE3,
        VideoType.PARKEZ_ADVICE,
        VideoType.PARKEZ_APPS,
        VideoType.TOOLS,
    }:
        brand = "ParkEz"
        callback = "ui:createp"
    elif video_type == VideoType.GOGRADUATE_TYPE_1:
        brand = "gograduate.io"
        callback = "ui:g"
    else:
        brand = "Dropradar"
        callback = "ui:create"
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(f"➕ Crear otro · {brand}", callback_data=callback),
            InlineKeyboardButton(_HOME_LABEL, callback_data="ui:home"),
        ]]
    )


def _is_navigation_row(row: tuple[InlineKeyboardButton, ...]) -> bool:
    return bool(row) and all(button.text in _NAVIGATION_LABELS for button in row)
