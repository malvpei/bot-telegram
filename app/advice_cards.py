from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import lcm

from app.models import Language


class AdviceBackground(str, Enum):
    BLACK = "black"
    WHITE = "white"
    ILLUSTRATED = "illustrated"


@dataclass(frozen=True)
class AdviceTip:
    title: str
    body: str


ADVICE_BACKGROUNDS: tuple[AdviceBackground, ...] = (
    AdviceBackground.BLACK,
    AdviceBackground.WHITE,
    AdviceBackground.ILLUSTRATED,
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

ADVICE_EXTERNAL_PHRASES: dict[Language, str] = {
    Language.ES: (
        "un dropshipper millonario me contó la regla número #1 para vender fácilmente"
    ),
    Language.EN: (
        "A millionaire dropshipper told me rule number #1 for selling easily"
    ),
}

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
    len(ADVICE_BACKGROUNDS),
    *(len(packs) for packs in ADVICE_PACKS.values()),
)


def advice_selection(
    phase: int,
    language: Language,
) -> tuple[AdviceBackground, tuple[AdviceTip, ...], int]:
    normalized_phase = max(0, int(phase)) % ADVICE_ROTATION_CYCLE_LENGTH
    packs = ADVICE_PACKS[language]
    return (
        ADVICE_BACKGROUNDS[normalized_phase % len(ADVICE_BACKGROUNDS)],
        packs[normalized_phase % len(packs)],
        normalized_phase % len(packs),
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
