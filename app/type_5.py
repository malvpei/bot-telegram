from __future__ import annotations

from app.models import Language, SlideRole, SocialCopy


TYPE_5_SLIDE_TEXTS: dict[SlideRole, str] = {
    SlideRole.HOOK: "Top negocios para jubilar a tus padres 🫡",
    SlideRole.TYPE_5_TRADING: (
        "Traiding 2/10 ❌\n"
        "-Dificil de empezar\n"
        "-Puedes perderlo todo en un momento"
    ),
    SlideRole.TYPE_5_CLIPPING: (
        "Clipping 4/10 ❌\n"
        "-Mucha competencia\n"
        "-Consume demasiado de tu tiempo por poco"
    ),
    SlideRole.TYPE_5_AI_DROPSHIPPING: (
        "AI + Dropshipping 10/10 ✅\n"
        "-Infinitamente escalable\n"
        "-Dropradar para productos ganadores y DeepSeek para ideas"
    ),
}

TYPE_5_SLIDE_TEXTS_EN: dict[SlideRole, str] = {
    SlideRole.HOOK: "Top businesses to retire your parents 🫡",
    SlideRole.TYPE_5_TRADING: (
        "Trading 2/10 ❌\n"
        "-Hard to get started\n"
        "-You can lose everything in an instant"
    ),
    SlideRole.TYPE_5_CLIPPING: (
        "Clipping 4/10 ❌\n"
        "-Too much competition\n"
        "-Takes too much time for too little reward"
    ),
    SlideRole.TYPE_5_AI_DROPSHIPPING: (
        "AI + Dropshipping 10/10 ✅\n"
        "-Infinitely scalable\n"
        "-Dropradar for winning products and DeepSeek for ideas"
    ),
}

TYPE_5_SLIDE_TEXTS_BY_LANGUAGE: dict[Language, dict[SlideRole, str]] = {
    Language.ES: TYPE_5_SLIDE_TEXTS,
    Language.EN: TYPE_5_SLIDE_TEXTS_EN,
}


_TYPE_5_HASHTAGS = [
    "#negociosonline",
    "#dropshipping",
    "#inteligenciaartificial",
    "#ecommerce",
    "#dropradar",
]

_TYPE_5_HASHTAGS_EN = [
    "#onlinebusiness",
    "#dropshipping",
    "#artificialintelligence",
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
    SocialCopy(
        title="Tres modelos de negocio y tres resultados muy diferentes",
        description=(
            "Comparar negocios online exige mirar algo más que sus promesas. Trading, "
            "clipping y AI + Dropshipping cambian mucho en riesgo, tiempo necesario y "
            "posibilidad de crecer. La mejor elección depende de cuánto puedes invertir, "
            "qué habilidades quieres desarrollar y qué sistema quieres construir."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="El negocio online que elegiría para construir a largo plazo",
        description=(
            "No basta con encontrar una forma de ganar dinero: conviene pensar si puede "
            "mantenerse y escalar con el tiempo. Mientras algunos modelos concentran riesgo "
            "o consumen demasiadas horas, AI + Dropshipping permite apoyarse en Dropradar "
            "para investigar productos y en DeepSeek para desarrollar ideas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="Cómo comparar negocios online antes de elegir uno",
        description=(
            "Pon cada opción frente a los mismos criterios: dificultad para empezar, riesgo "
            "de pérdida, retorno por hora y capacidad de escalar. Así resulta más sencillo "
            "entender por qué trading, clipping y AI + Dropshipping no ofrecen el mismo "
            "punto de partida ni requieren el mismo tipo de trabajo."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="Riesgo, tiempo y escalabilidad en tres negocios digitales",
        description=(
            "Cada modelo tiene una limitación diferente. El trading puede exponer tu capital, "
            "el clipping suele exigir mucho volumen de trabajo y AI + Dropshipping busca "
            "convertir la investigación y la creación de ideas en un proceso que puedas "
            "repetir, medir y mejorar con el tiempo."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="Qué cambia realmente entre trading, clipping y dropshipping",
        description=(
            "Aunque los tres se presentan como negocios online, su funcionamiento es muy "
            "distinto. Uno depende de gestionar riesgo financiero, otro de producir contenido "
            "constantemente y el tercero de validar productos, preparar ofertas y usar "
            "herramientas para acelerar la investigación y las ideas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
    SocialCopy(
        title="La opción más escalable no siempre es la más evidente",
        description=(
            "Antes de seguir una tendencia, revisa cuánto depende el resultado de tu tiempo y "
            "cuánto puede convertirse en un sistema. Dropradar ayuda a localizar productos con "
            "señales interesantes y DeepSeek puede servir para explorar enfoques creativos, "
            "mientras tú decides qué probar y cómo medirlo."
        ),
        hashtags=list(_TYPE_5_HASHTAGS),
    ),
)


TYPE_5_SOCIAL_COPIES_EN: tuple[SocialCopy, ...] = (
    SocialCopy(
        title="Three online businesses compared honestly",
        description=(
            "Trading, clipping, and AI-powered dropshipping can look similar from "
            "the outside, but they demand very different levels of risk, time, and "
            "scalability. This comparison gives you a practical starting point for "
            "deciding which model fits you best."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Which online business makes sense for a beginner",
        description=(
            "Before choosing an opportunity, compare how much capital you could lose, "
            "how many hours you must trade for results, and whether the system can grow "
            "without always depending on you. Trading, clipping, and AI + Dropshipping "
            "answer those three questions very differently."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Trading, clipping, or AI + Dropshipping",
        description=(
            "Not every digital business offers the same balance of difficulty, return, "
            "and scalability. Trading concentrates risk, clipping often depends on volume "
            "and time, while AI-powered dropshipping can create a more repeatable process "
            "for researching products and developing ideas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Selling your time versus building a system",
        description=(
            "A business can generate income and still be difficult to sustain. The key is "
            "whether every result requires more of your hours or whether the work can become "
            "a system. Tools such as Dropradar and DeepSeek can reduce research time and help "
            "you test ideas faster."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Compare these three things before starting online",
        description=(
            "Measure the risk of losing capital, the likely return for every hour invested, "
            "and how easily results can grow without multiplying your workload. Using those "
            "criteria helps you look past quick promises and choose a model with a more "
            "reasonable foundation."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Not every online business scales the same way",
        description=(
            "A popular idea is not automatically the right one for you. Trading can punish "
            "mistakes quickly, clipping competes for attention in a crowded market, and AI + "
            "Dropshipping lets you use data and ideas to validate opportunities before "
            "committing more budget."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Three business models with very different outcomes",
        description=(
            "Comparing online businesses means looking beyond their promises. Trading, "
            "clipping, and AI + Dropshipping differ greatly in risk, time requirements, and "
            "room to grow. The best choice depends on what you can invest, which skills you "
            "want to build, and what kind of system you want to create."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="The online business I would build for the long term",
        description=(
            "Finding a way to make money is not enough; it should also be sustainable and "
            "scalable. While some models concentrate risk or consume too many hours, AI + "
            "Dropshipping can use Dropradar for product research and DeepSeek for developing "
            "new angles and ideas."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="How to compare online businesses before choosing one",
        description=(
            "Judge every option by the same criteria: difficulty to start, risk of loss, "
            "return per hour, and ability to scale. This makes it easier to understand why "
            "trading, clipping, and AI + Dropshipping do not offer the same starting point "
            "or require the same kind of work."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="Risk, time, and scalability in digital business",
        description=(
            "Each model has a different limitation. Trading can expose your capital, clipping "
            "usually demands a high volume of work, and AI + Dropshipping aims to turn product "
            "research and idea generation into a process you can repeat, measure, and improve."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="What changes between trading, clipping, and dropshipping",
        description=(
            "Although all three are presented as online businesses, they work very differently. "
            "One depends on managing financial risk, another on producing content constantly, "
            "and the third on validating products, preparing offers, and using tools to speed "
            "up research and ideation."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
    SocialCopy(
        title="The most scalable option is not always the obvious one",
        description=(
            "Before following a trend, check how much the outcome depends on your time and how "
            "much of the work can become a system. Dropradar can help identify products with "
            "interesting signals, while DeepSeek can help explore creative angles for the ideas "
            "you decide to test."
        ),
        hashtags=list(_TYPE_5_HASHTAGS_EN),
    ),
)

TYPE_5_SOCIAL_COPIES_BY_LANGUAGE: dict[Language, tuple[SocialCopy, ...]] = {
    Language.ES: TYPE_5_SOCIAL_COPIES,
    Language.EN: TYPE_5_SOCIAL_COPIES_EN,
}


def type_5_slide_texts(language: Language) -> dict[SlideRole, str]:
    """Return the four separate chat messages for the requested language."""
    return dict(TYPE_5_SLIDE_TEXTS_BY_LANGUAGE[language])


def type_5_social_copies(language: Language = Language.ES) -> list[SocialCopy]:
    """Return independent copies so callers can safely format or reorder them."""
    return [
        SocialCopy(
            title=copy.title,
            description=copy.description,
            hashtags=list(copy.hashtags),
            hook=copy.hook,
        )
        for copy in TYPE_5_SOCIAL_COPIES_BY_LANGUAGE[language]
    ]
