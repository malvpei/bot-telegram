from __future__ import annotations

from app.models import TYPE_5_BUSINESS_ROLES, Language, SlideRole, SocialCopy


# Advancing two positions per video gives each business two appearances per cycle.
TYPE_5_BUSINESS_PAIRS: tuple[tuple[SlideRole, SlideRole], ...] = tuple(
    (
        TYPE_5_BUSINESS_ROLES[(index * 2) % len(TYPE_5_BUSINESS_ROLES)],
        TYPE_5_BUSINESS_ROLES[(index * 2 + 1) % len(TYPE_5_BUSINESS_ROLES)],
    )
    for index in range(len(TYPE_5_BUSINESS_ROLES))
)

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
    SlideRole.TYPE_5_AMAZON_FBA: (
        "Amazon FBA 3/10 ❌\n"
        "-Inversión inicial en stock\n"
        "-Comisiones y costes de almacenamiento"
    ),
    SlideRole.TYPE_5_PRINT_ON_DEMAND: (
        "Print on demand 2/10 ❌\n"
        "-Margen limitado por producto\n"
        "-Necesitas vender mucho para escalar"
    ),
    SlideRole.TYPE_5_AFFILIATE_MARKETING: (
        "Marketing de afiliados 6/10 🟡\n"
        "-No necesitas gestionar stock\n"
        "-Necesitas audiencia y generar confianza"
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
    SlideRole.TYPE_5_AMAZON_FBA: (
        "Amazon FBA 3/10 ❌\n"
        "-Upfront investment in inventory\n"
        "-Fees and storage costs"
    ),
    SlideRole.TYPE_5_PRINT_ON_DEMAND: (
        "Print on demand 2/10 ❌\n"
        "-Limited margin per product\n"
        "-You need high sales volume to scale"
    ),
    SlideRole.TYPE_5_AFFILIATE_MARKETING: (
        "Affiliate marketing 6/10 🟡\n"
        "-No inventory to manage\n"
        "-You need an audience and trust"
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

_TYPE_5_BUSINESS_NAMES: dict[Language, dict[SlideRole, str]] = {
    Language.ES: {
        SlideRole.TYPE_5_TRADING: "Trading",
        SlideRole.TYPE_5_CLIPPING: "Clipping",
        SlideRole.TYPE_5_AMAZON_FBA: "Amazon FBA",
        SlideRole.TYPE_5_PRINT_ON_DEMAND: "Print on demand",
        SlideRole.TYPE_5_AFFILIATE_MARKETING: "Marketing de afiliados",
    },
    Language.EN: {
        SlideRole.TYPE_5_TRADING: "Trading",
        SlideRole.TYPE_5_CLIPPING: "Clipping",
        SlideRole.TYPE_5_AMAZON_FBA: "Amazon FBA",
        SlideRole.TYPE_5_PRINT_ON_DEMAND: "Print on demand",
        SlideRole.TYPE_5_AFFILIATE_MARKETING: "Affiliate marketing",
    },
}

_TYPE_5_BUSINESS_SUMMARIES: dict[Language, dict[SlideRole, str]] = {
    Language.ES: {
        SlideRole.TYPE_5_TRADING: (
            "Trading exige aprender a gestionar el riesgo y puede exponer tu capital."
        ),
        SlideRole.TYPE_5_CLIPPING: (
            "Clipping compite por atención y puede requerir muchas horas de edición."
        ),
        SlideRole.TYPE_5_AMAZON_FBA: (
            "Amazon FBA requiere inversión inicial en stock y asumir comisiones "
            "y costes de almacenamiento."
        ),
        SlideRole.TYPE_5_PRINT_ON_DEMAND: (
            "Print on demand tiene un margen limitado por producto y necesita "
            "volumen de ventas para escalar."
        ),
        SlideRole.TYPE_5_AFFILIATE_MARKETING: (
            "Marketing de afiliados permite empezar sin gestionar stock, pero "
            "necesitas audiencia y generar confianza."
        ),
    },
    Language.EN: {
        SlideRole.TYPE_5_TRADING: (
            "Trading requires learning to manage risk and can expose your capital."
        ),
        SlideRole.TYPE_5_CLIPPING: (
            "Clipping competes for attention and can require many hours of editing."
        ),
        SlideRole.TYPE_5_AMAZON_FBA: (
            "Amazon FBA requires upfront investment in inventory, plus fees "
            "and storage costs."
        ),
        SlideRole.TYPE_5_PRINT_ON_DEMAND: (
            "Print on demand has a limited margin per product and needs "
            "high sales volume to scale."
        ),
        SlideRole.TYPE_5_AFFILIATE_MARKETING: (
            "Affiliate marketing lets you start without managing inventory, "
            "but you need an audience and trust."
        ),
    },
}

# Each description uses only the two businesses actually shown in the carousel.
_TYPE_5_SOCIAL_TEMPLATES: dict[Language, tuple[tuple[str, str], ...]] = {
    Language.ES: (
        (
            "Tres negocios online comparados sin venderte humo",
            "Comparamos {businesses} para entender sus diferencias en riesgo, tiempo "
            "y capacidad para escalar. {comparison}",
        ),
        (
            "Qué negocio online elegir si empiezas desde cero",
            "Antes de elegir entre {businesses}, piensa cuánto puedes invertir y qué "
            "habilidades quieres desarrollar. {comparison}",
        ),
        (
            "{first}, {second} o AI + Dropshipping",
            "Cada modelo pide un punto de partida diferente. Esta vez ponemos frente "
            "a frente {businesses}. {comparison}",
        ),
        (
            "La diferencia entre vender tu tiempo y construir un sistema",
            "Mira cuánto depende cada resultado de tus horas y qué trabajo puedes "
            "convertir en un proceso al comparar {businesses}. {comparison}",
        ),
        (
            "Antes de empezar un negocio online, compara estas tres cosas",
            "Capital necesario, tiempo disponible y facilidad para crecer: aplica "
            "los mismos criterios a {businesses}. {comparison}",
        ),
        (
            "No todos los negocios online escalan de la misma manera",
            "La popularidad de una idea no indica si encaja contigo. Revisa qué "
            "requieren {businesses} antes de elegir. {comparison}",
        ),
        (
            "Tres modelos de negocio y tres resultados muy diferentes",
            "{businesses} implican tareas y necesidades distintas. Tu elección "
            "depende de tus recursos y del sistema que quieras construir. {comparison}",
        ),
        (
            "El negocio online que elegiría para construir a largo plazo",
            "Piensa en cómo sostener el trabajo con el tiempo al valorar "
            "{businesses}. {comparison}",
        ),
        (
            "Cómo comparar negocios online antes de elegir uno",
            "Pon {businesses} frente a los mismos criterios: dificultad para empezar, "
            "inversión y capacidad para crecer. {comparison}",
        ),
        (
            "Riesgo, tiempo y escalabilidad en tres negocios digitales",
            "Cada modelo tiene una limitación diferente. Así se comparan "
            "{businesses} en este vídeo. {comparison}",
        ),
        (
            "Qué cambia realmente entre {first}, {second} y AI + Dropshipping",
            "Aunque {businesses} se presentan como negocios online, el trabajo "
            "diario de cada uno es distinto. {comparison}",
        ),
        (
            "La opción más escalable no siempre es la más evidente",
            "Antes de seguir una tendencia, revisa qué puedes repetir y mejorar "
            "en cada modelo. Hoy: {businesses}. {comparison}",
        ),
    ),
    Language.EN: (
        (
            "Three online businesses compared honestly",
            "We compare {businesses} to understand their differences in risk, time, "
            "and room to grow. {comparison}",
        ),
        (
            "Which online business makes sense for a beginner",
            "Before choosing between {businesses}, consider what you can invest "
            "and which skills you want to build. {comparison}",
        ),
        (
            "{first}, {second}, or AI + Dropshipping",
            "Each model has a different starting point. This time we compare "
            "{businesses}. {comparison}",
        ),
        (
            "Selling your time versus building a system",
            "Check how much each result depends on your hours and which tasks "
            "can become a process when comparing {businesses}. {comparison}",
        ),
        (
            "Compare these three things before starting online",
            "Required capital, available time, and room to grow: apply the same "
            "criteria to {businesses}. {comparison}",
        ),
        (
            "Not every online business scales the same way",
            "A popular idea is not automatically right for you. Check what "
            "{businesses} require before choosing. {comparison}",
        ),
        (
            "Three business models with very different outcomes",
            "{businesses} involve different tasks and needs. Your choice depends "
            "on your resources and the system you want to build. {comparison}",
        ),
        (
            "The online business I would build for the long term",
            "Think about how to sustain the work over time when evaluating "
            "{businesses}. {comparison}",
        ),
        (
            "How to compare online businesses before choosing one",
            "Judge {businesses} by the same criteria: difficulty to start, "
            "investment, and ability to grow. {comparison}",
        ),
        (
            "Risk, time, and scalability in digital business",
            "Each model has a different limitation. Here is how {businesses} "
            "compare in this video. {comparison}",
        ),
        (
            "What changes between {first}, {second}, and AI + Dropshipping",
            "Although {businesses} are all presented as online businesses, "
            "their daily work is different. {comparison}",
        ),
        (
            "The most scalable option is not always the obvious one",
            "Before following a trend, check what you can repeat and improve "
            "in each model. Today: {businesses}. {comparison}",
        ),
    ),
}


def type_5_slide_texts(language: Language) -> dict[SlideRole, str]:
    """Return localized texts for the hook, all five businesses, and the close."""
    return dict(TYPE_5_SLIDE_TEXTS_BY_LANGUAGE[language])


def type_5_social_copies(
    language: Language = Language.ES,
    business_roles: tuple[SlideRole, SlideRole] | None = None,
) -> list[SocialCopy]:
    """Build independent copies describing only the selected business pair."""
    selected = TYPE_5_BUSINESS_PAIRS[0] if business_roles is None else business_roles
    if (
        len(selected) != 2
        or selected[0] == selected[1]
        or any(role not in TYPE_5_BUSINESS_ROLES for role in selected)
    ):
        raise ValueError("Type 5 requires two distinct businesses from its rotation.")
    first, second = (_TYPE_5_BUSINESS_NAMES[language][role] for role in selected)
    if language == Language.EN:
        businesses = f"{first}, {second}, and AI + Dropshipping"
        closing_summary = (
            "AI + Dropshipping uses Dropradar for product research and DeepSeek "
            "to develop ideas."
        )
        hashtags = _TYPE_5_HASHTAGS_EN
    else:
        businesses = f"{first}, {second} y AI + Dropshipping"
        closing_summary = (
            "AI + Dropshipping se apoya en Dropradar para investigar productos "
            "y en DeepSeek para desarrollar ideas."
        )
        hashtags = _TYPE_5_HASHTAGS
    context = {
        "first": first,
        "second": second,
        "businesses": businesses,
        "comparison": " ".join(
            [*(_TYPE_5_BUSINESS_SUMMARIES[language][role] for role in selected), closing_summary]
        ),
    }
    return [
        SocialCopy(
            title=title.format(**context),
            description=description.format(**context),
            hashtags=list(hashtags),
        )
        for title, description in _TYPE_5_SOCIAL_TEMPLATES[language]
    ]


TYPE_5_SOCIAL_COPIES: tuple[SocialCopy, ...] = tuple(type_5_social_copies(Language.ES))
TYPE_5_SOCIAL_COPIES_EN: tuple[SocialCopy, ...] = tuple(type_5_social_copies(Language.EN))
TYPE_5_SOCIAL_COPIES_BY_LANGUAGE: dict[Language, tuple[SocialCopy, ...]] = {
    Language.ES: TYPE_5_SOCIAL_COPIES,
    Language.EN: TYPE_5_SOCIAL_COPIES_EN,
}
