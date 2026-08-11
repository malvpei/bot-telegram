from __future__ import annotations

from app.models import SlideRole, SocialCopy


TYPE_5_SLIDE_TEXTS: dict[SlideRole, str] = {
    SlideRole.HOOK: "Top negocios para jubilar a tus padres 🫡",
    SlideRole.TYPE_5_TRADING: (
        "Trading 2/10 ❌\n"
        "• Difícil de empezar\n"
        "• Puedes perderlo todo en un momento"
    ),
    SlideRole.TYPE_5_CLIPPING: (
        "Clipping 4/10 ❌\n"
        "• Mucha competencia\n"
        "• Poco retorno\n"
        "• Consume demasiado de tu tiempo por poco"
    ),
    SlideRole.TYPE_5_AI_DROPSHIPPING: (
        "AI + Dropshipping ✅\n"
        "• Infinitamente escalable\n"
        "• Dropradar para productos ganadores y DeepSeek para ideas"
    ),
}


_TYPE_5_HASHTAGS = [
    "#negociosonline",
    "#dropshipping",
    "#inteligenciaartificial",
    "#ecommerce",
    "#dropradar",
]


TYPE_5_SOCIAL_COPIES: tuple[SocialCopy, ...] = (
    SocialCopy(
        title="Tres negocios online comparados sin venderte humo",
        description=(
            "Trading, clipping y dropshipping con inteligencia artificial pueden "
            "parecer caminos similares desde fuera, pero exigen niveles muy distintos "
            "de riesgo, tiempo y capacidad para escalar. Esta comparación sirve como "
            "punto de partida para decidir qué modelo encaja mejor contigo."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="Qué negocio online elegir si empiezas desde cero",
        description=(
            "Antes de elegir una oportunidad, compara cuánto capital puedes perder, "
            "cuántas horas tendrás que intercambiar por resultados y si el sistema puede "
            "crecer sin depender siempre de ti. Trading, clipping y AI + Dropshipping "
            "responden de forma muy diferente a esas tres preguntas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="Trading, clipping o AI + Dropshipping",
        description=(
            "No todos los negocios digitales ofrecen la misma relación entre dificultad, "
            "retorno y escalabilidad. Trading concentra mucho riesgo, clipping suele "
            "depender de volumen y tiempo, y el dropshipping apoyado en IA permite crear "
            "un proceso más repetible para investigar productos e ideas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="La diferencia entre vender tu tiempo y construir un sistema",
        description=(
            "Un modelo puede generar ingresos y aun así ser difícil de sostener. La clave "
            "está en observar si cada resultado necesita más horas tuyas o si puedes "
            "convertir el trabajo en un sistema. Herramientas como Dropradar y DeepSeek "
            "pueden reducir parte de la investigación y acelerar las pruebas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="Antes de empezar un negocio online, compara estas tres cosas",
        description=(
            "Mide el riesgo de perder capital, el retorno probable por cada hora invertida "
            "y la facilidad para aumentar resultados sin multiplicar tu carga de trabajo. "
            "Aplicar esos criterios ayuda a mirar más allá de las promesas rápidas y a "
            "elegir un modelo con una base más razonable."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="No todos los negocios online escalan de la misma manera",
        description=(
            "La popularidad de una idea no indica si es adecuada para ti. Trading puede "
            "castigar los errores con rapidez, clipping compite por atención en un mercado "
            "saturado y AI + Dropshipping permite apoyarse en datos e ideas para validar "
            "antes de dedicar más presupuesto."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
)


def type_5_social_copies() -> list[SocialCopy]:
    """Return independent copies so callers can safely format or reorder them."""
    return [
        SocialCopy(
            title=copy.title,
            description=copy.description,
            hashtags=list(copy.hashtags),
            hook=copy.hook,
        )
        for copy in TYPE_5_SOCIAL_COPIES
    ]
