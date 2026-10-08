from __future__ import annotations

from pathlib import Path

from app.advice_cards import AdviceBackground, AdviceTip
from app.gograduate_social import (
    GOGRADUATE_SOCIAL_COPY_IDS,
    GOGRADUATE_SOCIAL_INTROS,
    GOGRADUATE_SOCIAL_TITLES,
)
from app.models import SocialCopy


GOGRADUATE_ICON_RELATIVE_PATH = Path("assets/gograduate.png")
GOGRADUATE_HOOKS = {
    "oxford": (
        "Un amigo que entro en Oxford me dio el consejo numero #1 "
        "para aprobar cualquier examen"
    ),
    "biomedicina": (
        "Un amigo que se graduo en biomedicina con matricula de honor "
        "me dio el consejo numero #1 para aprobar cualquier examen"
    ),
}
GOGRADUATE_HOOK_IDS = list(GOGRADUATE_HOOKS)
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
    *, copy_id: str = GOGRADUATE_SOCIAL_COPY_IDS[0], hook_id: str = GOGRADUATE_HOOK_IDS[0],
) -> SocialCopy:
    tips = gograduate_tips(pack_id, background)
    count_word = "cuatro" if len(tips) == 4 else "cinco"
    copy_index = GOGRADUATE_SOCIAL_COPY_IDS.index(copy_id)
    intro = GOGRADUATE_SOCIAL_INTROS[copy_index].format(count_word=count_word)
    points = "\n\n".join(
        f"{index}. {tip.title}: {tip.body}" for index, tip in enumerate(tips, start=1)
    )
    return SocialCopy(
        title=GOGRADUATE_SOCIAL_TITLES[pack_id][copy_index],
        description=(
            f"{intro}\n\n{points}\n\n"
            "Guarda estos consejos para tu próximo repaso y prepara tus apuntes con GoGraduate."
        ),
        hashtags=["#estudiantes", "#estudio", "#examenes", "#gograduate"],
        hook=GOGRADUATE_HOOKS[hook_id],
    )
