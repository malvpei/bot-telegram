from __future__ import annotations

from pathlib import Path

from app.advice_cards import AdviceBackground, AdviceTip
from app.car_tools import CAR_TOOLS_ICON_FILES
from app.models import SlideRole, SocialCopy
from app.parkez_advice_social import (
    PARKEZ_ADVICE_SOCIAL_COPY_IDS,
    PARKEZ_ADVICE_SOCIAL_INTROS,
    PARKEZ_ADVICE_SOCIAL_TITLES,
)


PARKEZ_ADVICE_ICON_FILES = {
    "RadarBot": CAR_TOOLS_ICON_FILES[SlideRole.CAR_TOOL_RADARBOT],
    "Waze": CAR_TOOLS_ICON_FILES[SlideRole.CAR_TOOL_WAZE],
    "Google Maps": CAR_TOOLS_ICON_FILES[SlideRole.CAR_TOOL_GOOGLE_MAPS],
    "ParkEz": CAR_TOOLS_ICON_FILES[SlideRole.CAR_TOOL_PARKEZ],
}
PARKEZ_ADVICE_ICON_RELATIVE_PATH = Path("cartools/iconos") / PARKEZ_ADVICE_ICON_FILES["ParkEz"]
PARKEZ_ADVICE_BACKGROUNDS = (AdviceBackground.ILLUSTRATED, AdviceBackground.EDITORIAL)
PARKEZ_ADVICE_DESIGN_IDS = [background.value for background in PARKEZ_ADVICE_BACKGROUNDS]
PARKEZ_ADVICE_HOOKS = {
    "daily": "Apps que te hacen más fácil el día a día con el coche",
    "calm": "Apps para preparar tus trayectos y buscar aparcamiento con más calma",
}
PARKEZ_ADVICE_HOOK_IDS = list(PARKEZ_ADVICE_HOOKS)
PARKEZ_ADVICE_PROMO = AdviceTip(
    "ParkEz",
    "antes de salir, usa ParkEz para orientarte hacia zonas donde buscar sitio. "
    "Al llegar, comprueba que haya una plaza libre y revisa las señales.",
)

# Keep pack, hook and copy IDs stable so existing queues resume after this change.
# Every design explains the same four apps, using Tools' real icon assets.
# Sources for app features and distraction guidance are linked in README.md.
# ParkEz guides the search; it does not reserve or guarantee a parking space.
PARKEZ_ADVICE_PACKS: dict[str, tuple[AdviceTip, ...]] = {
    "apps-01": (
        AdviceTip(
            "RadarBot",
            "te avisa de radares durante el trayecto. Deja los avisos preparados "
            "antes de salir y respeta siempre los límites y las señales.",
        ),
        AdviceTip(
            "Waze",
            "calcula rutas teniendo en cuenta el tráfico. Programa tu hora de "
            "llegada y activa el aviso de salida para organizar el trayecto.",
        ),
        AdviceTip(
            "Google Maps",
            "te ayuda a preparar rutas y localizar lugares. Descarga el mapa de "
            "tu zona antes de salir para navegar en coche si falta cobertura.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
    "driving-01": (
        AdviceTip(
            "RadarBot",
            "recibe avisos de radares y configura las alertas antes de arrancar. "
            "Úsalo como apoyo, no como sustituto de prestar atención a la carretera.",
        ),
        AdviceTip(
            "Waze",
            "te guía con rutas que tienen en cuenta el tráfico y sus incidencias. "
            "Elige el destino con el coche aparcado y sigue las indicaciones de voz.",
        ),
        AdviceTip(
            "Google Maps",
            "busca destinos y prepara la ruta antes de salir. Puedes consultar "
            "lugares como gasolineras o restaurantes para organizar tus paradas.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
    "calm-01": (
        AdviceTip(
            "RadarBot",
            "ofrece avisos de radares para que estés informado durante la ruta. "
            "Mantén una velocidad adecuada todo el camino, no solo al recibir un aviso.",
        ),
        AdviceTip(
            "Waze",
            "programa la hora a la que quieres llegar y recibe un aviso para salir. "
            "Añade también margen para buscar aparcamiento y caminar hasta la puerta.",
        ),
        AdviceTip(
            "Google Maps",
            "guarda los destinos que visitas a menudo y prepara cómo llegar. "
            "Así puedes dejar la ruta elegida antes de arrancar, sin improvisar al volante.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
    "parking-01": (
        AdviceTip(
            "RadarBot",
            "te informa de radares mientras te desplazas. Prepara las alertas antes "
            "de salir y mantén la atención en las señales durante todo el recorrido.",
        ),
        AdviceTip(
            "Waze",
            "te ayuda a elegir la ruta hacia tu destino según el tráfico. "
            "Prepara el recorrido con margen: llegar a la dirección no es lo mismo que aparcar.",
        ),
        AdviceTip(
            "Google Maps",
            "guarda la ubicación del coche al aparcar para encontrarlo al volver. "
            "Si estás en un parking, anota también la planta y la plaza.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
}
PARKEZ_ADVICE_PACK_IDS = list(PARKEZ_ADVICE_PACKS)


def parkez_advice_tips(
    pack_id: str, background: AdviceBackground,
) -> tuple[AdviceTip, ...]:
    if background not in PARKEZ_ADVICE_BACKGROUNDS:
        raise ValueError("Diseño de consejos de ParkEz no disponible.")
    return PARKEZ_ADVICE_PACKS[pack_id]


def parkez_advice_social_copy(
    pack_id: str, background: AdviceBackground = AdviceBackground.ILLUSTRATED,
    *, copy_id: str = PARKEZ_ADVICE_SOCIAL_COPY_IDS[0],
    hook_id: str = PARKEZ_ADVICE_HOOK_IDS[0],
) -> SocialCopy:
    tips = parkez_advice_tips(pack_id, background)
    copy_index = PARKEZ_ADVICE_SOCIAL_COPY_IDS.index(copy_id)
    intro = PARKEZ_ADVICE_SOCIAL_INTROS[copy_index].format(count_word="cuatro")
    points = "\n\n".join(
        f"{index}. {tip.title}: {tip.body}" for index, tip in enumerate(tips, start=1)
    )
    return SocialCopy(
        title=PARKEZ_ADVICE_SOCIAL_TITLES[pack_id][copy_index],
        description=(
            f"{intro}\n\n{points}\n\n"
            "Guárdalo para preparar tu próximo trayecto. Consulta las apps antes "
            "de salir o cuando estés aparcado en un lugar seguro."
        ),
        hashtags=["#ParkEz", "#conduccion", "#appsutiles", "#aparcamiento"],
        hook=PARKEZ_ADVICE_HOOKS[hook_id],
    )
