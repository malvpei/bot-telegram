from __future__ import annotations

import hashlib

from app.models import ScriptPackage, SlideRole, SocialCopy
from app.parkez import PARKEZ_ROLES
from app.state import StateStore


PARKEZ_MODE3_HOOK = "Los 3 trucos que nadie te cuenta cuando te sacas el carnet"

# Literal transcription supplied by the user, including the original wording.
# In particular, the speedometer claim is not a verified driving recommendation.
PARKEZ_MODE3_TEXTS = {
    SlideRole.HOOK: PARKEZ_MODE3_HOOK,
    SlideRole.TIP1: (
        "Tu coche siempre te marca menos velocidad a la real, échale cuenta a la "
        "velocidad del GPS para ahórrate multas"
    ),
    SlideRole.TIP2: (
        "Ten cuidado con justo frenar antes de llegar al radar, muchos puntos "
        "tienen radares dobles para pillarte antes de que frenes"
    ),
    SlideRole.PARKEZ_PROMO: (
        "Para no dar vueltas buscando dónde aparcar, usa apps como ParkEz y ve "
        "directamente donde hay aparcamiento"
    ),
}

# Keep IDs stable: the persistent queue can then resume across restarts and edits.
# Social copy stays on the supplied topics without promising immunity from fines
# or guaranteed parking, or repeating the inaccurate speedometer assertion.
_SOCIAL_VARIANTS: tuple[tuple[str, str, str], ...] = (
    (
        "mode3-01",
        "¿Carnet recién sacado? Hay vida después del aprobado 🚗",
        "Velocímetro, GPS, radares y ese último reto: encontrar dónde aparcar. "
        "Tres temas para tus primeros trayectos, con ParkEz para orientar la "
        "búsqueda de sitio. Guarda el carrusel para repasarlo antes de salir.",
    ),
    (
        "mode3-02",
        "Tu primera ruta empieza antes de arrancar 🗺️",
        "No todo es elegir destino. Conocer las indicaciones de velocidad, "
        "respetar los límites y pensar dónde dejar el coche también forma parte "
        "del viaje. Consulta ParkEz antes de ponerte al volante.",
    ),
    (
        "mode3-03",
        "La L puesta y tres cosas que conviene tener presentes",
        "Del cuadro del coche al GPS, de los controles de velocidad al "
        "aparcamiento: este carrusel reúne dudas de los primeros días "
        "conduciendo. ¿Cuál te ha dado más vueltas en la cabeza?",
    ),
    (
        "mode3-04",
        "Aprobar el carnet es el principio, no el final 🔑",
        "Después llegan los trayectos de verdad: entender tu coche, conducir "
        "dentro de los límites y buscar sitio al llegar. ParkEz puede ayudarte "
        "a decidir por dónde empezar esa búsqueda.",
    ),
    (
        "mode3-05",
        "Velocidad, radares y aparcamiento: tu primer checklist",
        "Tres asuntos que aparecen en cuanto empiezas a conducir por tu cuenta. "
        "Revisa la ruta con el coche parado, respeta la señalización y consulta "
        "ParkEz para planificar dónde buscar aparcamiento.",
    ),
    (
        "mode3-06",
        "El viaje no termina al llegar a la dirección 📍",
        "También toca aparcar. Entre las dudas sobre GPS y los controles de "
        "velocidad, no olvides preparar esa última parte del trayecto. "
        "Con ParkEz puedes consultar zonas donde empezar a buscar sitio.",
    ),
    (
        "mode3-07",
        "¿Tu primer coche? Guarda esto antes de salir",
        "Conocer lo que muestra el velocímetro, prestar atención a los límites "
        "y tener una idea de dónde aparcar: pequeños preparativos para una "
        "nueva etapa al volante. El último consejo del carrusel va con ParkEz.",
    ),
    (
        "mode3-08",
        "Tres temas que salen cuando estrenas carnet 🚘",
        "¿Por qué el GPS y el cuadro pueden mostrar cifras distintas? "
        "¿Por qué no conviene esperar al radar para moderar la velocidad? "
        "¿Dónde empiezo a buscar sitio? De eso va este carrusel de ParkEz.",
    ),
    (
        "mode3-09",
        "Menos improvisación en tus primeros trayectos",
        "El destino está claro; prepara también el camino y la llegada. "
        "Aquí hablamos de velocidad, controles y búsqueda de aparcamiento "
        "con ParkEz. El móvil se consulta antes de arrancar o con el coche parado.",
    ),
    (
        "mode3-10",
        "Lo que miras en el coche y lo que preparas antes de llegar",
        "El cuadro, el GPS y las señales merecen tu atención, pero no todo "
        "acaba en la carretera. Añade el aparcamiento a tu planificación "
        "y revisa ParkEz antes de salir. ¿Ya lo haces?",
    ),
    (
        "mode3-11",
        "De la autoescuela a conducir por tu cuenta 🎓",
        "Los primeros recorridos traen preguntas sobre la velocidad, los "
        "radares y dónde dejar el coche. Comparte este carrusel con quien "
        "acaba de aprobar y prepara la llegada con ParkEz.",
    ),
    (
        "mode3-12",
        "Que buscar aparcamiento no sea una sorpresa al final",
        "Antes de salir, piensa en toda la ruta: límites de velocidad, "
        "indicaciones del coche y opciones al llegar. ParkEz te orienta "
        "hacia zonas donde buscar aparcamiento; comprueba siempre las señales.",
    ),
    (
        "mode3-13",
        "¿Acabas de aprobar? Hablemos de tus primeras rutas",
        "No solo importa llevarte las llaves. También conocer el coche, "
        "mantener una velocidad adecuada y preparar dónde aparcar. "
        "Desliza hasta el final para ver el consejo con ParkEz.",
    ),
    (
        "mode3-14",
        "Del velocímetro a encontrar sitio: tres paradas en este carrusel",
        "Empezamos con el cuadro y el GPS, seguimos con los controles de "
        "velocidad y terminamos buscando aparcamiento con ParkEz. "
        "Guárdalo y revisa tus dudas antes de tu próximo trayecto.",
    ),
    (
        "mode3-15",
        "Tu carnet es nuevo; tus trayectos pueden ir preparados ✅",
        "Familiarízate con las indicaciones de tu coche, respeta los límites "
        "durante todo el recorrido y consulta dónde buscar aparcamiento antes "
        "de salir. ParkEz pone el cierre a estos tres temas para nuevos conductores.",
    ),
)

PARKEZ_MODE3_SOCIAL_COPY_IDS = [variant[0] for variant in _SOCIAL_VARIANTS]


def build_parkez_mode3_script(state: StateStore) -> ScriptPackage:
    copy_id, _ = state.peek_next_parkez_mode3_social_copy_id(
        PARKEZ_MODE3_SOCIAL_COPY_IDS
    )
    _, title, description = next(
        variant for variant in _SOCIAL_VARIANTS if variant[0] == copy_id
    )
    texts = dict(PARKEZ_MODE3_TEXTS)
    ordered = [texts[role] for role in PARKEZ_ROLES]
    return ScriptPackage(
        slides_by_role=texts,
        ordered_slides=ordered,
        signature=hashlib.sha1("|".join(ordered).encode("utf-8")).hexdigest(),
        plain_text="\n\n".join(ordered),
        # The hook is delivered once, as the independent HOOK slide message.
        social_copy=SocialCopy(title=title, description=description, hashtags=[]),
        social_choice_key=copy_id,
    )
