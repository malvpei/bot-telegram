from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import lcm

from app.models import Language


class AdviceBackground(str, Enum):
    BLACK = "black"
    WHITE = "white"
    ILLUSTRATED = "illustrated"
    EDITORIAL = "editorial"


@dataclass(frozen=True)
class AdviceTip:
    title: str
    body: str


ADVICE_BACKGROUNDS: tuple[AdviceBackground, ...] = (
    AdviceBackground.BLACK,
    AdviceBackground.WHITE,
    AdviceBackground.ILLUSTRATED,
    AdviceBackground.EDITORIAL,
)

ADVICE_PACKS: dict[Language, tuple[tuple[AdviceTip, ...], ...]] = {
    Language.ES: (
        (
            AdviceTip(
                "no copies el producto, copia el ángulo",
                "dos tiendas pueden vender lo mismo y obtener resultados muy "
                "distintos por cómo explican el problema.",
            ),
            AdviceTip(
                "convierte las dudas en anuncios",
                "las preguntas frecuentes de los clientes pueden darte mejores "
                "guiones que cualquier plantilla viral.",
            ),
            AdviceTip(
                "muestra el producto antes del segundo 2",
                "si tardas demasiado en enseñar qué vendes, muchos se irán sin "
                "entender el anuncio.",
            ),
            AdviceTip(
                "encuentra ganadores antes de lanzar",
                "usa Dropradar para encontrar productos ganadores ya validados y "
                "empezar con una oportunidad mucho más segura.",
            ),
        ),
        (
            AdviceTip(
                "no persigas productos virales",
                "cuando aparecen por todas partes, normalmente ya hay demasiadas "
                "tiendas vendiéndolos.",
            ),
            AdviceTip(
                "lee las reseñas de 2 estrellas",
                "suelen explicar los problemas reales que tu oferta puede solucionar.",
            ),
            AdviceTip(
                "añade un pack bastante más caro",
                "aunque casi nadie lo compre, hará que la opción intermedia parezca "
                "más atractiva.",
            ),
            AdviceTip(
                "deja de elegir productos a ciegas",
                "Dropradar encuentra productos ganadores validados para que empieces "
                "con una oportunidad más segura.",
            ),
        ),
        (
            AdviceTip(
                "busca anuncios antiguos, no solo virales",
                "si una tienda mantiene el mismo anuncio durante semanas, "
                "probablemente está consiguiendo resultados.",
            ),
            AdviceTip(
                "crea packs con nombres distintos",
                "básico, más vendido y completo funcionan mejor que mostrar solo "
                "cantidades y precios.",
            ),
            AdviceTip(
                "lee los comentarios antes de elegir",
                "si muchos preguntan dónde comprarlo, existe interés que aún no se "
                "ha convertido en ventas.",
            ),
            AdviceTip(
                "encuentra productos que ya venden",
                "usa Dropradar para detectar productos ganadores antes de perder "
                "tiempo copiando a otras tiendas.",
            ),
        ),
        (
            AdviceTip(
                "no estudies únicamente anuncios virales",
                "un anuncio activo durante semanas puede ser mejor señal que uno con "
                "visitas durante un solo día.",
            ),
            AdviceTip(
                "convierte preguntas en hooks",
                "si todos preguntan lo mismo, usa esa pregunta exacta al principio "
                "de tu próximo anuncio.",
            ),
            AdviceTip(
                "haz que un pack destaque claramente",
                "una opción más cara puede hacer que tu oferta principal parezca "
                "económica sin cambiar su precio.",
            ),
            AdviceTip(
                "elige un producto ganador",
                "Dropradar te ayuda a encontrar productos ganadores validados antes "
                "de invertir en anuncios.",
            ),
        ),
    ),
    Language.EN: (
        (
            AdviceTip(
                "don't copy the product, copy the angle",
                "two stores can sell the same thing and get very different results "
                "because of how they explain the problem.",
            ),
            AdviceTip(
                "turn customer doubts into ads",
                "frequent questions can give you better scripts than any viral "
                "template.",
            ),
            AdviceTip(
                "show the product before second 2",
                "if you wait too long to reveal what you sell, people leave before "
                "understanding the ad.",
            ),
            AdviceTip(
                "find winners before launching",
                "use Dropradar to find validated winning products and start with a "
                "much safer opportunity.",
            ),
        ),
        (
            AdviceTip(
                "don't chase viral products",
                "when they appear everywhere, there are usually already too many "
                "stores selling them.",
            ),
            AdviceTip(
                "read the 2-star reviews",
                "they often reveal the real problems your offer can solve.",
            ),
            AdviceTip(
                "add a much more expensive bundle",
                "even if almost nobody buys it, your middle option will feel more "
                "attractive.",
            ),
            AdviceTip(
                "stop picking products blindly",
                "Dropradar finds validated winning products so you can start with a "
                "stronger opportunity.",
            ),
        ),
        (
            AdviceTip(
                "study old ads, not only viral ones",
                "if a store keeps the same ad for weeks, it is probably producing "
                "results.",
            ),
            AdviceTip(
                "give your bundles different names",
                "basic, best seller and complete work better than showing only "
                "quantities and prices.",
            ),
            AdviceTip(
                "read comments before choosing",
                "if people keep asking where to buy it, there is interest that has "
                "not become sales yet.",
            ),
            AdviceTip(
                "find products already selling",
                "use Dropradar to spot validated winners before wasting time copying "
                "other stores.",
            ),
        ),
        (
            AdviceTip(
                "don't only study viral ads",
                "an ad running for weeks can be a stronger signal than one getting "
                "views for a single day.",
            ),
            AdviceTip(
                "turn customer questions into hooks",
                "if people keep asking the same thing, open your next ad with that "
                "exact question.",
            ),
            AdviceTip(
                "make one bundle look clearly better",
                "a more expensive option can make your main offer feel cheaper "
                "without changing its price.",
            ),
            AdviceTip(
                "choose a validated winner",
                "Dropradar helps you find validated winning products before you spend "
                "on ads.",
            ),
        ),
    ),
}

# The editorial layout mirrors the five-row reference.  It reuses each
# four-tip pack and inserts one extra practical tip before the Dropradar
# recommendation, so the branded recommendation always closes the list.
ADVICE_EDITORIAL_EXTRA_TIPS: dict[Language, tuple[AdviceTip, ...]] = {
    Language.ES: (
        AdviceTip(
            "prueba la oferta antes de escalar",
            "valida el interés con poco presupuesto antes de aumentar la inversión.",
        ),
        AdviceTip(
            "calcula el margen real",
            "incluye envío, comisiones y devoluciones antes de decidir si merece la pena.",
        ),
        AdviceTip(
            "comprueba al proveedor",
            "pide una muestra y revisa la entrega antes de prometer tiempos al cliente.",
        ),
        AdviceTip(
            "compara tres ángulos",
            "prueba beneficio, problema y demostración para descubrir qué mensaje vende.",
        ),
    ),
    Language.EN: (
        AdviceTip(
            "test the offer before scaling",
            "validate interest with a small budget before increasing your spend.",
        ),
        AdviceTip(
            "calculate the real margin",
            "include shipping, fees and returns before deciding if it is worth testing.",
        ),
        AdviceTip(
            "check the supplier first",
            "order a sample and review delivery before promising times to customers.",
        ),
        AdviceTip(
            "compare three angles",
            "test benefit, problem and demonstration to discover which message sells.",
        ),
    ),
}

ADVICE_EXTERNAL_PHRASES: dict[Language, str] = {
    Language.ES: (
        "un dropshipper millonario me contó la regla número #1 para vender fácilmente"
    ),
    Language.EN: (
        "A millionaire dropshipper told me rule number #1 for selling easily"
    ),
}

ADVICE_SOCIAL_TITLES: dict[Language, tuple[tuple[str, ...], ...]] = {
    Language.ES: (
        (
            "un dropshipper millonario me contó la regla número #1 para vender fácilmente",
            "el producto ganador no se elige mirando solo las visitas",
            "la mayoría busca productos ganadores en el sitio equivocado",
        ),
        (
            "un dropshipper millonario me contó la regla número #1 para vender fácilmente",
            "estas señales te avisan de un producto ganador",
            "el error que hace perder dinero antes de lanzar",
        ),
        (
            "un dropshipper millonario me contó la regla número #1 para vender fácilmente",
            "lo que casi nadie revisa antes de lanzar un producto",
            "un anuncio viral no siempre es un ganador",
        ),
        (
            "un dropshipper millonario me contó la regla número #1 para vender fácilmente",
            "la herramienta que filtra productos por ti",
            "cómo reducir el riesgo al elegir producto",
        ),
    ),
    Language.EN: (
        (
            "A millionaire dropshipper told me rule number #1 for selling easily",
            "winning products are not chosen by views alone",
            "most beginners search for winning products in the wrong place",
        ),
        (
            "A millionaire dropshipper told me rule number #1 for selling easily",
            "these signals reveal a winning product",
            "the mistake that wastes money before launch",
        ),
        (
            "A millionaire dropshipper told me rule number #1 for selling easily",
            "what almost nobody checks before launching",
            "a viral ad is not always a winner",
        ),
        (
            "A millionaire dropshipper told me rule number #1 for selling easily",
            "the tool that filters products for you",
            "how to lower the risk of your next product",
        ),
    ),
}

ADVICE_SOCIAL_DESCRIPTIONS: dict[Language, tuple[tuple[str, ...], ...]] = {
    Language.ES: (
        (
            "4 consejos de dropshipping para detectar mejores oportunidades y encontrar "
            "productos ganadores validados. Usa Dropradar para investigar tu próxima "
            "idea antes de lanzar.",
            "Dos tiendas pueden vender lo mismo y obtener resultados opuestos. Aprende "
            "a elegir el ángulo correcto y encuentra productos ganadores con Dropradar.",
            "Deja de perseguir tendencias al azar. Estos consejos te ayudan a detectar "
            "señales útiles y Dropradar a encontrar productos ganadores validados.",
        ),
        (
            "Elegir producto no debería ser una apuesta. Aplica estos consejos y usa "
            "Dropradar para encontrar productos ganadores validados antes de invertir.",
            "Las dudas de los clientes esconden ideas de anuncios y ofertas. Descubre "
            "cómo usarlas y encuentra una oportunidad más segura con Dropradar.",
            "Antes de lanzar, revisa las señales que otros ignoran. Dropradar te ayuda "
            "a localizar productos ganadores antes de gastar en anuncios.",
        ),
        (
            "Los productos ganadores dejan señales: aprende a reconocerlas en anuncios, "
            "packs y comentarios. Dropradar te ayuda a encontrar oportunidades validadas.",
            "Un pack bien planteado puede cambiar la percepción del precio. Combina estos "
            "consejos con Dropradar para elegir productos con más potencial.",
            "No todo lo viral merece una tienda. Aprende a separar ruido de oportunidad "
            "y usa Dropradar para encontrar productos ganadores.",
        ),
        (
            "Antes de gastar en anuncios, encuentra una oportunidad más segura. Estos "
            "consejos y Dropradar te ayudan a localizar productos ganadores validados.",
            "La selección del producto es el primer filtro de tu negocio. Usa Dropradar "
            "para encontrar ganadores y reduce las pruebas a ciegas.",
            "Guarda estas reglas para tu próximo lanzamiento: elige mejor, prueba antes "
            "y encuentra productos ganadores con Dropradar.",
        ),
    ),
    Language.EN: (
        (
            "4 dropshipping tips to spot better opportunities and find validated winning "
            "products. Use Dropradar to research your next idea before launching.",
            "Two stores can sell the same thing and get opposite results. Learn to choose "
            "the right angle and find winning products with Dropradar.",
            "Stop chasing random trends. These tips help you spot useful signals, while "
            "Dropradar helps you find validated winning products.",
        ),
        (
            "Choosing a product should not be a guess. Use these tips and Dropradar to "
            "find validated winning products before you invest.",
            "Customer doubts hide ideas for ads and offers. Learn to use them and find a "
            "safer opportunity with Dropradar.",
            "Before launching, check the signals other stores ignore. Dropradar helps you "
            "find winning products before you spend on ads.",
        ),
        (
            "Winning products leave signals: learn to spot them in ads, bundles and "
            "comments. Dropradar helps you find validated opportunities.",
            "A well-built bundle can change how customers see the price. Pair these tips "
            "with Dropradar to choose products with more potential.",
            "Not everything viral deserves a store. Separate noise from opportunity and "
            "use Dropradar to find winning products.",
        ),
        (
            "Before spending on ads, start with a safer opportunity. These tips and "
            "Dropradar help you find validated winning products.",
            "Product selection is your business's first filter. Use Dropradar to find "
            "winners and reduce blind testing.",
            "Save these rules for your next launch: choose better, test earlier and find "
            "winning products with Dropradar.",
        ),
    ),
}

ADVICE_SOCIAL_HASHTAGS: dict[Language, tuple[str, ...]] = {
    Language.ES: (
        "#dropshipping",
        "#productosganadores",
        "#ecommerce",
        "#shopify",
        "#dropradar",
    ),
    Language.EN: (
        "#dropshipping",
        "#winningproducts",
        "#ecommerce",
        "#shopify",
        "#dropradar",
    ),
}

ADVICE_VISUAL_CYCLE_LENGTH = (
    len(ADVICE_BACKGROUNDS) * len(ADVICE_PACKS[Language.ES])
)
ADVICE_SOCIAL_CYCLE_LENGTH = (
    len(ADVICE_PACKS[Language.ES])
    * min(
        len(pack_titles)
        for language_titles in ADVICE_SOCIAL_TITLES.values()
        for pack_titles in language_titles
    )
)


def advice_social_copy(
    language: Language,
    pack_index: int,
    rotation_index: int | None = None,
) -> tuple[str, str, list[str]]:
    """Return TikTok-ready title, description and hashtags for an advice card."""
    titles = ADVICE_SOCIAL_TITLES[language]
    descriptions = ADVICE_SOCIAL_DESCRIPTIONS[language]
    hashtags = ADVICE_SOCIAL_HASHTAGS[language]
    pack = max(0, int(pack_index)) % len(titles)
    cycle = 0 if rotation_index is None else max(0, int(rotation_index)) // len(titles)
    variant = cycle % len(titles[pack])
    return (
        titles[pack][variant],
        descriptions[pack][variant],
        list(hashtags),
    )

ADVICE_ILLUSTRATED_TITLES: dict[Language, tuple[str, str]] = {
    Language.ES: (
        "4 reglas para vender más con dropshipping",
        "pequeños detalles que la mayoría de tiendas ignora",
    ),
    Language.EN: (
        "4 rules to sell more with dropshipping",
        "small details most stores overlook",
    ),
}

ADVICE_ROTATION_CYCLE_LENGTH = lcm(
    ADVICE_VISUAL_CYCLE_LENGTH,
    ADVICE_SOCIAL_CYCLE_LENGTH,
)


def advice_selection(
    phase: int,
    language: Language,
) -> tuple[AdviceBackground, tuple[AdviceTip, ...], int]:
    normalized_phase = max(0, int(phase)) % ADVICE_ROTATION_CYCLE_LENGTH
    packs = ADVICE_PACKS[language]
    background_count = len(ADVICE_BACKGROUNDS)
    background = ADVICE_BACKGROUNDS[normalized_phase % background_count]
    # Four backgrounds and four packs would otherwise remain locked together.
    # Shifting the pack after every complete background lap makes every visual
    # template meet every advice pack during the 16-step visual cycle.
    pack_index = (
        normalized_phase + normalized_phase // background_count
    ) % len(packs)
    tips = packs[pack_index]
    if background == AdviceBackground.EDITORIAL:
        tips = (
            *tips[:-1],
            ADVICE_EDITORIAL_EXTRA_TIPS[language][pack_index],
            tips[-1],
        )
    return (
        background,
        tips,
        pack_index,
    )


def format_advice_script(tips: tuple[AdviceTip, ...]) -> str:
    return "\n\n".join(
        f"{index}. {tip.title}\n{tip.body}"
        for index, tip in enumerate(tips, start=1)
    )


def validate_advice_content() -> None:
    expected_pack_count = len(ADVICE_PACKS[Language.ES])
    for language, packs in ADVICE_PACKS.items():
        if len(packs) != expected_pack_count:
            raise ValueError("Los idiomas no tienen el mismo número de guiones tipo 4.")
        editorial_extras = ADVICE_EDITORIAL_EXTRA_TIPS[language]
        if len(editorial_extras) != len(packs):
            raise ValueError(
                f"Faltan consejos para la plantilla editorial en {language.value}."
            )
        social_titles = ADVICE_SOCIAL_TITLES[language]
        social_descriptions = ADVICE_SOCIAL_DESCRIPTIONS[language]
        if len(social_titles) != len(packs) or len(social_descriptions) != len(packs):
            raise ValueError(
                f"Faltan descripciones sociales para los consejos en {language.value}."
            )
        if len(ADVICE_SOCIAL_HASHTAGS[language]) < 3:
            raise ValueError(
                f"Los consejos en {language.value} necesitan hashtags relacionados."
            )
        for pack_titles, pack_descriptions in zip(
            social_titles,
            social_descriptions,
            strict=True,
        ):
            if len(pack_titles) < 3 or len(pack_titles) != len(pack_descriptions):
                raise ValueError(
                    f"Cada pack de consejos en {language.value} necesita títulos y "
                    "descripciones suficientes para rotar."
                )
        for tips in packs:
            if len(tips) != 4:
                raise ValueError("Cada guion tipo 4 debe contener exactamente 4 consejos.")
            final_body = tips[-1].body.lower()
            if "dropradar" not in final_body:
                raise ValueError(
                    f"El cuarto consejo tipo 4 en {language.value} debe nombrar Dropradar."
                )
            if not any(term in final_body for term in ("ganador", "winner", "winning")):
                raise ValueError(
                    f"El cuarto consejo tipo 4 en {language.value} debe presentar "
                    "Dropradar como herramienta de productos ganadores."
                )


validate_advice_content()
