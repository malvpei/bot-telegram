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
        "Te indica donde habra aparcamiento gratuito libre cerca de tu destino, "
        "evitando calles con el aparcamiento lleno"
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

# These short uses and alternative explanations stay within the same functions
# as the original summaries. Only names and uses from the selected apps enter
# the additional templates; the literal on-photo descriptions remain separate.
_SOCIAL_USES: dict[str, str] = {
    "notion": "ordenar notas y proyectos",
    "claude": "trabajar ideas y textos con IA",
    "waze": "preparar rutas según el tráfico",
    "mathway": "consultar ejercicios con una foto",
    "screenzen": "poner límites al tiempo en apps",
    "fintonic": "revisar gastos por categorías",
}

_SOCIAL_SUMMARY_VARIANTS: dict[str, tuple[str, ...]] = {
    "notion": (
        "reúne tus notas, tareas y proyectos para tenerlos a mano.",
        "si tienes notas y tareas dispersas, puedes organizarlas junto a tus proyectos.",
        "úsala cuando quieras ordenar las notas, tareas y proyectos de la semana.",
        "un mismo sitio para consultar tus notas y seguir las tareas de tus proyectos.",
    ),
    "claude": (
        "trabaja tus ideas, preguntas y textos con un asistente de IA.",
        "cuando quieras desarrollar una idea o trabajar un texto, puedes consultarlo con su IA.",
        "plantea tus preguntas y trabaja sobre tus textos con ayuda de la IA.",
        "un asistente de IA al que acudir con una pregunta, una idea o un texto.",
    ),
    "waze": (
        "consulta el tráfico para preparar tu ruta antes de salir.",
        "antes de ponerte en marcha, revisa una ruta que tenga en cuenta el tráfico.",
        "úsala al preparar un trayecto y consultar cómo está el tráfico.",
        "ten en cuenta el tráfico cuando decidas qué ruta seguir.",
    ),
    "mathway": (
        "consulta un problema matemático a partir de una foto del ejercicio.",
        "cuando un ejercicio se te atasque, usa una foto para consultar el problema.",
        "lleva tu duda matemática a la app con una foto del ejercicio.",
        "tenla a mano para consultar esos problemas matemáticos que tienes en una foto.",
    ),
    "screenzen": (
        "añade pausas y límites a las apps que abres por inercia.",
        "si una app te distrae, pon una pausa y un límite al tiempo que le dedicas.",
        "úsala para marcar límites y hacer una pausa antes de abrir apps que te distraen.",
        "configura pausas y límites para controlar el tiempo que pasas en las apps.",
    ),
    "fintonic": (
        "consulta tus cuentas y mira cómo se reparten tus gastos por categorías.",
        "cuando quieras revisar en qué gastas, consulta tus cuentas y las categorías de gasto.",
        "úsala para repasar tus cuentas y los gastos agrupados por categorías.",
        "ten a mano tus cuentas y una vista de tus gastos por categorías.",
    ),
    "parkez": (
        "revisa las calles con más probabilidades de aparcar antes de llegar al destino.",
        "prepara la búsqueda de aparcamiento comparando las probabilidades de distintas calles.",
        "consulta qué calles ofrecen más probabilidades de encontrar aparcamiento.",
        "antes de salir, compara calles para decidir dónde empezar a buscar aparcamiento.",
    ),
}

# Every variant describes the actual three rotating apps and the fixed ParkEz
# card. General-purpose intros never imply an absent app is in this carousel.
_ORIGINAL_SOCIAL_VARIANTS: tuple[tuple[str, str, str], ...] = (
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

_SOCIAL_VARIANTS: tuple[tuple[str, str, str], ...] = _ORIGINAL_SOCIAL_VARIANTS + (
    (
        "{app1}, {app2}, ParkEz y {app3}: tu nueva carpeta útil",
        "Pon nombre a lo que necesitas: {app1} para {use1}, {app2} para {use2} y {app3} para {use3}. ParkEz completa la selección con la búsqueda de aparcamiento. Así encaja cada una:",
        "Guarda los cuatro nombres y empieza por la función que vayas a usar esta semana.",
    ),
    (
        "{app1}: una app para {use1} que puedes tener a mano",
        "Si hoy necesitas {use1}, empieza mirando {app1}. En las siguientes imágenes también aparecen {app2}, ParkEz y {app3}, cada una con un uso diferente:",
        "¿Te encaja más {app1} o alguna de las otras tres? Guarda el carrusel para compararlas con calma.",
    ),
    (
        "{app2} y ParkEz: dos usos que conviene conocer",
        "Hay momentos para {use2} y momentos para preparar dónde buscar aparcamiento. Para esas dos tareas, aquí aparecen {app2} y ParkEz. La lista se completa con {app1} y {app3}:",
        "Piensa en tu próxima semana: ¿en qué momento abrirías cada una?",
    ),
    (
        "{app3}: de icono instalado a herramienta del día a día",
        "{app3} tiene un uso concreto: {use3}. Para entender el resto del carrusel, mira también qué aportan {app1}, {app2} y ParkEz:",
        "Guárdalo y vuelve a la app que corresponda cuando aparezca esa tarea.",
    ),
    (
        "De {app1} a ParkEz: 4 apps, cuatro necesidades",
        "Esta selección empieza con {app1}, sigue con {app2}, pasa por ParkEz y termina con {app3}. Antes de añadirlas al iPhone, relaciona cada nombre con su función:",
        "¿Cuál de estas necesidades se repite más en tu rutina? Esa puede ser tu primera app para probar.",
    ),
    (
        "¿Ya usas {app2}? Mira estas 4 apps para tu iPhone",
        "Quizá hayas abierto {app2} para {use2}. En este carrusel comparte sitio con {app1}, ParkEz y {app3}; aquí tienes un motivo para consultar cada una:",
        "Cuéntame cuál ya usas y guarda el nombre de la que te falte por explorar.",
    ),
    (
        "{app1} y {app3}: así encajan en una carpeta con ParkEz",
        "Entre {use1} con {app1} y {use3} con {app3} hay dos usos muy distintos. Añade {app2} y la búsqueda de aparcamiento con ParkEz, y esta es la carpeta del carrusel:",
        "No necesitas abrirlas todas hoy. Guarda la selección para el momento de cada tarea.",
    ),
    (
        "Para {use2}, empieza por {app2}",
        "La segunda app del carrusel es {app2}, una opción para {use2}. Si buscas otros usos para tu iPhone, también puedes conocer {app1}, ParkEz y {app3}:",
        "Guarda este post si quieres recordar qué app consultar para cada cosa.",
    ),
    (
        "¿Qué abrirías primero: {app1}, {app2} o {app3}?",
        "La respuesta depende de lo que necesites hacer. {app1}, {app2} y {app3} cubren sus propios usos; ParkEz añade la preparación de la búsqueda de aparcamiento. Elige con esta lista:",
        "Dime con cuál empezarías y para qué la usarías.",
    ),
    (
        "ParkEz, {app1} y compañía: apps con un momento de uso",
        "Antes de buscar sitio puedes consultar ParkEz. Para {use1}, tienes {app1}. {app2} y {app3} tienen otros momentos de uso que puedes encontrar en la selección completa:",
        "Asocia cada app a una situación de tu día y guarda las que te resulten prácticas.",
    ),
    (
        "{app3} para {use3}: descubre la selección completa",
        "El carrusel termina con {app3}, que puedes usar para {use3}. Antes aparecen {app1}, {app2} y ParkEz. Estas son sus funciones, en el mismo orden que las imágenes:",
        "¿Llegaste por {app3} y te quedaste con otra? Guarda la que más encaje contigo.",
    ),
    (
        "Un motivo para abrir {app1} y otros tres para tu iPhone",
        "Abre {app1} cuando quieras {use1}. Para las otras tareas del carrusel, mira los usos de {app2}, ParkEz y {app3}:",
        "Guarda esta pequeña guía para volver al nombre que necesitas sin repasar todos tus iconos.",
    ),
    (
        "{app1} y {app2}: dos nombres que guardar junto a ParkEz",
        "{app1} sirve para {use1}; {app2}, para {use2}. ParkEz y {app3} completan las cuatro herramientas que ves aquí. Te dejo el uso de cada una:",
        "Compártelo con alguien que necesite una de estas funciones y dile cuál le puede servir.",
    ),
    (
        "Tu iPhone, {app2} y una tarea concreta por resolver",
        "Si tu tarea es {use2}, fíjate en {app2}. Si hoy necesitas otra cosa, revisa también {app1}, ParkEz y {app3}, que son las otras apps de las imágenes:",
        "Elige por lo que necesitas hacer hoy y guarda las demás para después.",
    ),
    (
        "4 apps para consultar a tiempo: de {app1} a {app3}",
        "{app1} cuando quieras {use1}, {app2} para {use2}, ParkEz antes de buscar aparcamiento y {app3} para {use3}. Aquí tienes algo más de contexto para cada momento:",
        "¿Cuál te habría venido bien ayer? Guarda el carrusel para tenerla presente la próxima vez.",
    ),
    (
        "¿Para qué sirve {app3}? Una selección con usos concretos",
        "{app3} te permite {use3}. En este carrusel también hay sitio para {app1}, {app2} y ParkEz. Relaciona los cuatro nombres con estas tareas:",
        "Guarda el post y cuéntame qué uso te resulta más interesante.",
    ),
    (
        "De {use1} con {app1} a buscar sitio con ParkEz",
        "El iPhone puede acompañarte en tareas distintas: {app1} para {use1}, {app2} para {use2} y {app3} para {use3}. ParkEz añade información para preparar la búsqueda de aparcamiento:",
        "Quédate con la función que más uses y guarda los otros nombres para cuando los necesites.",
    ),
    (
        "{app2}, {app3} y ParkEz: nombres para tu próxima lista",
        "Si estás pensando qué apps explorar, apunta {app2} y {app3} por sus usos para {use2} y {use3}. La primera imagen de app es {app1}, y ParkEz también forma parte de la lista:",
        "Guárdalo como recordatorio y prueba la que responda a una necesidad que tengas ahora.",
    ),
    (
        "Una tarea, una app: {app1}, {app2}, ParkEz y {app3}",
        "¿Qué necesitas hacer? Para {use1} puedes consultar {app1}; para {use2}, {app2}; para {use3}, {app3}. Estas son las cuatro herramientas de las imágenes, incluida ParkEz:",
        "Vuelve a esta lista cuando tengas clara la tarea y quieras recordar el nombre de la app.",
    ),
    (
        "{app1}, {app2} y {app3}: descubre cuándo te pueden servir",
        "Si guardas los nombres, guarda también sus usos. {app1}, {app2} y {app3} aparecen en este carrusel junto a ParkEz; así puedes decidir cuándo abrir cada una:",
        "¿Con qué app te quedas para tu rutina? Guarda el carrusel y empieza por esa.",
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

    index = variant_index % PARKEZ_APPS_SOCIAL_VARIANT_COUNT
    title, intro, closing = _SOCIAL_VARIANTS[index]
    fields = {
        field: value
        for position, app in enumerate(selected, start=1)
        for field, value in (
            (f"app{position}", app.name),
            (f"use{position}", _SOCIAL_USES[app.key]),
        )
    }
    title, intro, closing = (
        text.format_map(fields) for text in (title, intro, closing)
    )
    # Hook -> app -> app -> ParkEz -> app: four app rows, five images in total.
    displayed = (selected[0], selected[1], PARKEZ_APP, selected[2])
    additional_index = index - len(_ORIGINAL_SOCIAL_VARIANTS)

    def summary(app: ParkEzApp, position: int) -> str:
        if additional_index < 0:
            return _SOCIAL_SUMMARIES[app.key]
        variants = _SOCIAL_SUMMARY_VARIANTS[app.key]
        return variants[(additional_index + position - 1) % len(variants)]

    points = "\n\n".join(
        f"{position}. {app.name}: {summary(app, position)}"
        for position, app in enumerate(displayed, start=1)
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
