from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.models import SocialCopy


@dataclass(frozen=True)
class ParkEzApp:
    """An App Store-style card and its separate, on-photo explanation."""

    key: str
    title: str
    subtitle: str
    description: str
    action: str = "Get"
    purchase_note: str = ""
    icon_file: str = ""

    @property
    def name(self) -> str:
        return _APP_NAMES[self.key]


# Reference copy is deliberately literal, including the requested hook spelling.
# These are display labels from the supplied screenshots, not live store data.
PARKEZ_APPS_HOOKS: tuple[str, ...] = (
    "Si tu iphone no tienes esta apps, estas perdiendo el tiempo",
    "Apps que tu iphone  necesita para llevarte al siguiente nivel",
    "Las apps que literamente ponen la vida en modo facil",
)

ROTATING_APPS: tuple[ParkEzApp, ...] = (
    ParkEzApp(
        key="notion",
        title="Notion: notes, tasks, AI",
        subtitle="Notion Labs, Incorporated",
        description=(
            "Te permite controlar tu tiempo y tus proyectos de una manera que "
            "ninguna app iguala"
        ),
        action="cloud",
        icon_file="notion.png",
    ),
    ParkEzApp(
        key="claude",
        title="Claude by Anthropic",
        subtitle="Anthropic PBC",
        description=(
            "Un gran poder conlleva una gran responsabilidad y esta app te da "
            "el poder de hacer lo que quieras"
        ),
        action="Update",
        icon_file="claude.png",
    ),
    ParkEzApp(
        key="waze",
        title="Waze Navigation & Live Traffic",
        subtitle="Traffic alerts while you drive",
        description="Si conoces Google Maps, esta app es su evolución",
        icon_file="waze.png",
    ),
    ParkEzApp(
        key="mathway",
        title="Mathway",
        subtitle="Chegg, Inc.",
        description=(
            "Si tienes algún problema matemático que no sepas resolver, "
            "hazle una foto y lo tienes"
        ),
        purchase_note="In-App Purchases",
        icon_file="mathway.png",
    ),
    ParkEzApp(
        key="screenzen",
        title="ScreenZen- Screen Time Control",
        subtitle="Bloquea apps, limita pantalla",
        description=(
            "Te ayuda a dejar de abrir redes por inercia poniendo pausas y "
            "límites para que recuperes el control de tu tiempo"
        ),
        action="Obtener",
        purchase_note="Compras dentro de la app",
        icon_file="screenzen.png",
    ),
    ParkEzApp(
        key="fintonic",
        title="Fintonic | Ahorra y finánciate",
        subtitle="Control de gastos y préstamos",
        description=(
            "Te muestra en qué se va tu dinero y agrupa tus gastos para que no "
            "llegues a fin de mes sin saber qué ha pasado"
        ),
        action="Obtener",
        icon_file="fintonic.png",
    ),
)

PARKEZ_APP = ParkEzApp(
    key="parkez",
    title="ParkEz",
    subtitle="Encuentra dónde aparcar",
    description=(
        "Te orienta hacia las calles con más probabilidades de aparcar para "
        "que sepas por dónde empezar a buscar sitio"
    ),
    action="Obtener",
    icon_file="parkez.png",
)

APP_BY_KEY: dict[str, ParkEzApp] = {
    app.key: app for app in (*ROTATING_APPS, PARKEZ_APP)
}
_APP_NAMES = {
    "notion": "Notion",
    "claude": "Claude",
    "waze": "Waze",
    "mathway": "Mathway",
    "screenzen": "ScreenZen",
    "fintonic": "Fintonic",
    "parkez": "ParkEz",
}

# Features for new explanations were checked against primary sources:
# https://screenzen.co/
# https://www.fintonic.com/es-ES/alertas/
# https://apps.apple.com/dk/app/parkez/id6799709478
# In particular, ParkEz estimates probability; it does not guarantee a space.
_SOCIAL_SUMMARIES: dict[str, str] = {
    "notion": "organiza tus notas, tareas y proyectos en un mismo sitio.",
    "claude": "un asistente de IA para trabajar con ideas, preguntas y textos.",
    "waze": "prepara tus rutas teniendo en cuenta el tráfico.",
    "mathway": "consulta problemas matemáticos a partir de una foto.",
    "screenzen": "pon pausas y límites a las apps que te distraen.",
    "fintonic": "consulta tus cuentas y revisa tus gastos por categorías.",
    "parkez": "compara calles con más probabilidades de aparcar antes de llegar.",
}

# Every variant describes the actual three rotating apps and the fixed ParkEz
# card. General-purpose intros never imply an absent app is in this carousel.
_SOCIAL_VARIANTS: tuple[tuple[str, str, str], ...] = (
    (
        "4 apps para que tu iPhone te sea más útil",
        "Tu móvil puede servir para algo más que hacer scroll. Estas son las cuatro apps de este carrusel:",
        "Guárdalas y empieza por la que resuelva algo que haces cada día.",
    ),
    (
        "Tu próxima carpeta de apps útiles empieza aquí",
        "No necesitas instalarlo todo: elige las herramientas que encajan contigo. Hoy te enseño:",
        "¿Cuál añadirías primero a tu pantalla de inicio?",
    ),
    (
        "Menos vueltas, más herramientas: 4 apps para tu día",
        "Cuatro usos concretos para aprovechar mejor tu iPhone, incluido preparar dónde buscar aparcamiento:",
        "Prueba una, intégrala en tu rutina y después decide si necesitas las demás.",
    ),
    (
        "Estas apps merecen un hueco en tu iPhone",
        "Una app tiene sentido cuando sabes para qué abrirla. Aquí tienes la selección de hoy:",
        "Guarda este carrusel para consultarlo cuando necesites una de estas funciones.",
    ),
    (
        "4 apps que puedes usar fuera del scroll infinito",
        "El móvil también puede ayudarte con tareas reales. En este carrusel aparecen:",
        "Quédate con la que más encaje con tu día a día.",
    ),
    (
        "Apps con una misión: hacerte más práctica la rutina",
        "Cada herramienta de esta selección tiene un uso distinto. Estas son las cuatro protagonistas:",
        "Guárdalo: conocer el uso de una app importa más que acumular iconos.",
    ),
    (
        "Lo útil de tu iPhone no acaba en las apps de siempre",
        "Si quieres ampliar tu caja de herramientas, empieza por estos usos concretos:",
        "¿Cuál te vendría mejor esta semana?",
    ),
    (
        "4 herramientas para abrir el móvil con un propósito",
        "Antes de abrir una app, piensa qué necesitas resolver. Esta es la selección que te propongo:",
        "Guarda la lista y vuelve a ella cuando tengas una tarea concreta.",
    ),
    (
        "Tu iPhone puede hacer más: descubre estas 4 apps",
        "No todas las apps sirven para lo mismo. En las imágenes de hoy te enseño estas cuatro:",
        "Empieza por la que encaje mejor con lo que necesitas ahora.",
    ),
    (
        "Una carpeta útil: 3 apps nuevas para ti y ParkEz",
        "Esta selección reúne tres herramientas rotativas y ParkEz para preparar la búsqueda de sitio:",
        "Compártelo con alguien que disfrute descubriendo apps prácticas.",
    ),
    (
        "4 apps, 4 usos que merece la pena conocer",
        "Lo importante no es cuántas apps tienes, sino qué puedes hacer con ellas. Estas son las de hoy:",
        "Guárdalas y elige la que tenga un uso real en tu rutina.",
    ),
    (
        "Del iPhone a la vida real: apps que sí tienen un uso",
        "La selección de este carrusel incluye estas cuatro herramientas y sus funciones:",
        "¿Conocías todas o has descubierto alguna?",
    ),
    (
        "Dale un uso más práctico a tu pantalla de inicio",
        "Si vas a añadir un icono, que sea para algo que necesites. Estas son las apps del carrusel:",
        "No hace falta probarlas todas a la vez: empieza por una.",
    ),
    (
        "4 apps para tener a mano cuando las necesites",
        "Algunas herramientas se agradecen justo cuando aparece una tarea. Hoy te muestro:",
        "Guarda este post para recuperar los nombres sin tener que buscarlos después.",
    ),
    (
        "No más apps por instalar: elige estas por su función",
        "Esta lista no va de llenar tu móvil. Va de conocer qué aporta cada una de estas cuatro apps:",
        "¿Qué función te resulta más útil ahora mismo?",
    ),
    (
        "Apps para el día a día, con ParkEz en la selección",
        "Cuatro herramientas que puedes consultar según lo que necesites. En este carrusel salen:",
        "Guarda la selección y úsala como una lista de ideas, no de tareas pendientes.",
    ),
    (
        "4 iconos que pueden tener sentido en tu iPhone",
        "Una pantalla de inicio útil se construye con funciones que realmente usas. Estas son las de hoy:",
        "Prueba la que más encaje contigo y cuéntame qué tal.",
    ),
    (
        "Tu selección de apps prácticas para hoy",
        "Aquí tienes cuatro nombres y una explicación de lo que puedes hacer con cada uno:",
        "Envíale el carrusel a quien siempre te pregunta por apps útiles.",
    ),
    (
        "El móvil como herramienta: 4 apps que explorar",
        "Además de entretenerte, tu iPhone puede ayudarte con cosas concretas. La selección de hoy es:",
        "Guárdalo para descubrirlas con calma cuando las necesites.",
    ),
    (
        "4 apps que quizá le faltan a tu iPhone",
        "Puede que ya conozcas alguna, pero cada una tiene una función diferente. Estas son las del vídeo:",
        "¿Cuál guardarías y cuál ya usas?",
    ),
)

PARKEZ_APPS_SOCIAL_VARIANT_COUNT = len(_SOCIAL_VARIANTS)
PARKEZ_APPS_SOCIAL_COPY_IDS: tuple[str, ...] = tuple(
    str(index) for index in range(PARKEZ_APPS_SOCIAL_VARIANT_COUNT)
)


def build_parkez_apps_social_copy(
    hook: str, apps: Sequence[ParkEzApp], variant_index: int,
) -> SocialCopy:
    """Build copy for the three selected apps, preserving ParkEz's slide order."""
    selected = tuple(apps)
    keys = tuple(app.key for app in selected)
    rotating_keys = {app.key for app in ROTATING_APPS}
    if len(selected) != 3 or len(set(keys)) != 3 or not set(keys) <= rotating_keys:
        raise ValueError("El carrusel de apps necesita tres aplicaciones distintas además de ParkEz.")
    if any(APP_BY_KEY[app.key] != app for app in selected):
        raise ValueError("La aplicación no coincide con el catálogo de Apps iPhone.")

    title, intro, closing = _SOCIAL_VARIANTS[
        variant_index % PARKEZ_APPS_SOCIAL_VARIANT_COUNT
    ]
    # Hook -> app -> app -> ParkEz -> app: four app rows, five images in total.
    displayed = (selected[0], selected[1], PARKEZ_APP, selected[2])
    points = "\n\n".join(
        f"{index}. {app.name}: {_SOCIAL_SUMMARIES[app.key]}"
        for index, app in enumerate(displayed, start=1)
    )
    return SocialCopy(
        title=title,
        description=(
            f"{intro}\n\n{points}\n\n{closing}\n\n"
            "ParkEz ofrece estimaciones, no garantiza una plaza libre. "
            "Consulta las apps con el coche aparcado y revisa las señales al aparcar."
        ),
        hashtags=["#ParkEz", "#appsutiles", "#iPhone", "#aparcamiento"],
        hook=hook,
    )
