from __future__ import annotations

from pathlib import Path

from app.advice_cards import AdviceBackground, AdviceTip
from app.models import SocialCopy


GOGRADUATE_ICON_RELATIVE_PATH = Path("assets/gograduate.png")
GOGRADUATE_HOOK = "{count} trucos para estudiantes que no te cuentan en clase"
GOGRADUATE_BACKGROUNDS = (AdviceBackground.ILLUSTRATED, AdviceBackground.EDITORIAL)
GOGRADUATE_DESIGN_IDS = [background.value for background in GOGRADUATE_BACKGROUNDS]
GOGRADUATE_PROMO = AdviceTip(
    title="Usa GoGraduate como tu profesor",
    body=(
        "usa tu propio profesor que aprende de tus errores, te dice y resume la "
        "información más importante y analiza tus apuntes para que el aprobado "
        "esté garantizado"
    ),
)

# Practical applications of retrieval practice, spaced review and interleaving.
# The promotion closes each pack; the illustrated design omits the fourth tip.
GOGRADUATE_PACKS: dict[str, tuple[AdviceTip, ...]] = {
    "students-01": (
        AdviceTip(
            "Recuerda antes de releer",
            "cierra los apuntes y escribe lo que recuerdas. Después comprueba "
            "qué falta: reconocer una frase no es lo mismo que saber explicarla.",
        ),
        AdviceTip(
            "Reparte tus repasos",
            "vuelve a las preguntas al día siguiente y unos días después. "
            "Repasa más lo que fallas que lo que ya respondes sin ayuda.",
        ),
        AdviceTip(
            "Mezcla tipos de ejercicios",
            "alterna problemas que necesiten métodos distintos. Antes de "
            "resolverlos, decide cuál usar y explica por qué encaja.",
        ),
        AdviceTip(
            "Lleva una lista de errores",
            "anota qué confundiste y cómo detectarlo. En el siguiente repaso, "
            "intenta corregir esos fallos sin mirar la solución.",
        ),
        GOGRADUATE_PROMO,
    ),
    "students-02": (
        AdviceTip(
            "Convierte títulos en preguntas",
            "en vez de copiar cada apartado, conviértelo en una pregunta. "
            "Responde sin mirar y usa tus apuntes para comprobar la respuesta.",
        ),
        AdviceTip(
            "Inténtalo antes de ver la solución",
            "escribe un primer intento, aunque dudes. Al corregir, identifica "
            "el paso exacto donde cambió tu razonamiento.",
        ),
        AdviceTip(
            "No repases siempre lo fácil",
            "separa lo que respondes solo de lo que necesita pistas. Vuelve "
            "más a tus dudas y comprueba después lo que ya dominabas.",
        ),
        AdviceTip(
            "Contrasta conceptos parecidos",
            "escribe qué tienen en común y qué los distingue. Crea una "
            "pregunta donde tengas que elegir entre ellos y justificarlo.",
        ),
        GOGRADUATE_PROMO,
    ),
    "students-03": (
        AdviceTip(
            "Empieza con una hoja en blanco",
            "antes de abrir el tema, apunta sus ideas principales de memoria. "
            "Lo que no sale te indica por dónde empezar a repasar.",
        ),
        AdviceTip(
            "Corrige explicando el porqué",
            "no cambies solo la respuesta equivocada. Escribe por qué era "
            "incorrecta y qué pista te ayudará a evitar el mismo fallo.",
        ),
        AdviceTip(
            "Vuelve al tema días después",
            "deja una pequeña prueba para otro día. Intenta responder antes "
            "de releer: así compruebas qué puedes recuperar sin pistas.",
        ),
        AdviceTip(
            "Ensaya sin ayudas",
            "mezcla preguntas de varios temas y responde sin apuntes. "
            "Después revisa si el problema fue el contenido o entender la pregunta.",
        ),
        GOGRADUATE_PROMO,
    ),
    "students-04": (
        AdviceTip(
            "Cambia la forma de la pregunta",
            "si solo recuerdas la frase del apunte, prueba con un ejemplo "
            "distinto. Comprueba si puedes usar la idea, no solo repetirla.",
        ),
        AdviceTip(
            "Separa las pistas de las respuestas",
            "en tus tarjetas deja una pregunta delante y la explicación "
            "detrás. No descubras la respuesta hasta hacer tu propio intento.",
        ),
        AdviceTip(
            "Decide el método antes de calcular",
            "mezcla ejercicios ya practicados. Escribe primero qué estrategia "
            "necesitas y solo después realiza los pasos.",
        ),
        AdviceTip(
            "Recupera los fallos del último repaso",
            "empieza la siguiente sesión con dos preguntas que fallaste. "
            "Si vuelves a atascarte, revisa la explicación y prueba más tarde.",
        ),
        GOGRADUATE_PROMO,
    ),
}

GOGRADUATE_PACK_IDS = list(GOGRADUATE_PACKS)
_SOCIAL_COPY = {
    "students-01": (
        "Estudiar más no siempre es estudiar mejor",
        "Recordar sin mirar, repartir los repasos y mezclar ejercicios"
        "{error_habit}: hábitos para tus próximas sesiones. "
        "El último consejo es usar GoGraduate como tu propio profesor con tus apuntes.",
    ),
    "students-02": (
        "Deja de copiar apuntes y empieza a hacerte preguntas",
        "Transforma los apartados en preguntas, intenta responder antes de "
        "corregir y detecta qué conceptos estás confundiendo. Guarda estos "
        "{count_word} consejos para estudiantes y prepara tus apuntes con GoGraduate.",
    ),
    "students-03": (
        "La hoja en blanco también sirve para estudiar",
        "¿Qué recuerdas antes de abrir los apuntes? Prueba a recuperarlo, "
        "explica tus errores y compruébalo otra vez días después. {count_title} "
        "consejos de estudio con GoGraduate como cierre.",
    ),
    "students-04": (
        "Si cambia la pregunta, ¿sigues sabiendo la respuesta?",
        "Practica con ejemplos diferentes, esconde las respuestas y decide "
        "qué método necesitas antes de resolver. {last_step}",
    ),
}


def gograduate_tips(
    pack_id: str, background: AdviceBackground,
) -> tuple[AdviceTip, ...]:
    if background not in GOGRADUATE_BACKGROUNDS:
        raise ValueError("Diseño de GoGraduate no disponible.")
    tips = GOGRADUATE_PACKS[pack_id]
    if background == AdviceBackground.ILLUSTRATED:
        return tips[:3] + tips[-1:]
    return tips


def gograduate_social_copy(
    pack_id: str, background: AdviceBackground = AdviceBackground.ILLUSTRATED,
) -> SocialCopy:
    count = len(gograduate_tips(pack_id, background))
    count_word = "cuatro" if count == 4 else "cinco"
    title, description = _SOCIAL_COPY[pack_id]
    return SocialCopy(
        title=title,
        description=description.format(
            count_word=count_word,
            count_title=count_word.capitalize(),
            error_habit=" y aprender de los errores" if count == 5 else "",
            last_step=(
                "Vuelve a los errores del último repaso y usa GoGraduate con tus apuntes."
                if count == 5 else "Usa GoGraduate con tus apuntes."
            ),
        ),
        hashtags=["#estudiantes", "#estudio", "#examenes", "#gograduate"],
        hook=GOGRADUATE_HOOK.format(count=count),
    )
