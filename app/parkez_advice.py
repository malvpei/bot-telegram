from __future__ import annotations

from pathlib import Path

from app.advice_cards import AdviceBackground, AdviceTip
from app.models import SocialCopy
from app.parkez_advice_social import (
    PARKEZ_ADVICE_SOCIAL_COPY_IDS,
    PARKEZ_ADVICE_SOCIAL_INTROS,
    PARKEZ_ADVICE_SOCIAL_TITLES,
)


PARKEZ_ADVICE_ICON_RELATIVE_PATH = Path("cartools/iconos/parkez.png")
PARKEZ_ADVICE_BACKGROUNDS = (AdviceBackground.ILLUSTRATED, AdviceBackground.EDITORIAL)
PARKEZ_ADVICE_DESIGN_IDS = [background.value for background in PARKEZ_ADVICE_BACKGROUNDS]
PARKEZ_ADVICE_HOOKS = {
    "daily": "Los trucos que hacen más fácil tu día a día con el coche",
    "calm": "Apps y hábitos para conducir con menos líos y aparcar con más calma",
}
PARKEZ_ADVICE_HOOK_IDS = list(PARKEZ_ADVICE_HOOKS)
PARKEZ_ADVICE_PROMO = AdviceTip(
    "Planifica dónde aparcar con ParkEz",
    "antes de salir, usa ParkEz para orientarte hacia zonas donde buscar sitio. "
    "Al llegar, comprueba que haya una plaza libre y revisa las señales.",
)

# Sources for app features and distraction guidance are linked in README.md.
# ParkEz guides the search; it does not reserve or guarantee a parking space.
PARKEZ_ADVICE_PACKS: dict[str, tuple[AdviceTip, ...]] = {
    "apps-01": (
        AdviceTip(
            "Programa la salida con Waze",
            "indica cuándo quieres llegar y activa el aviso de salida. "
            "Añade margen para aparcar y caminar: la ruta no es todo el trayecto.",
        ),
        AdviceTip(
            "Descarga el mapa antes de salir",
            "guarda la zona en Google Maps para navegar en coche si falta cobertura. "
            "Sin conexión no tendrás tráfico en directo ni rutas alternativas.",
        ),
        AdviceTip(
            "Guarda dónde has dejado el coche",
            "al aparcar, guarda la ubicación en Google Maps. Si estás en un parking, "
            "apunta también la planta y la plaza en una nota.",
        ),
        AdviceTip(
            "Prepara un recordatorio de vuelta",
            "si tu estacionamiento tiene un horario, anótalo y crea una alarma "
            "con margen. Comprueba el límite en las señales o en tu ticket.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
    "driving-01": (
        AdviceTip(
            "Prepara todo antes de arrancar",
            "ajusta asiento y espejos, elige la ruta y deja lista la música. "
            "Si necesitas cambiar algo en el móvil, aparca en un lugar seguro.",
        ),
        AdviceTip(
            "Una salida perdida no es una urgencia",
            "si te pasas un desvío, sigue hasta poder cambiar la ruta con seguridad. "
            "Es mejor llegar un poco después que hacer una maniobra brusca.",
        ),
        AdviceTip(
            "Deja espacio para reaccionar",
            "no te pegues al coche de delante. Aumenta la separación si llueve "
            "o ves peor: ese margen te permite anticiparte sin frenar de golpe.",
        ),
        AdviceTip(
            "Descansa antes de estar agotado",
            "planifica paradas en viajes largos. Si aparece sueño o cansancio, "
            "detente en un lugar seguro; una ventana abierta no sustituye el descanso.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
    "calm-01": (
        AdviceTip(
            "Calcula el tiempo hasta la puerta",
            "suma al trayecto el tiempo de buscar sitio y caminar. Salir con "
            "ese margen evita que cada semáforo parezca un retraso inesperado.",
        ),
        AdviceTip(
            "Decide tu plan B antes de salir",
            "elige otra zona donde aparcar o un parking de pago como alternativa. "
            "No dependas de encontrar sitio justo delante del destino.",
        ),
        AdviceTip(
            "Quita los avisos que no necesitas",
            "configura No molestar antes de arrancar y prepara el navegador. "
            "Los mensajes pueden esperar a que estés aparcado en un lugar seguro.",
        ),
        AdviceTip(
            "No improvises con el móvil al volante",
            "si necesitas revisar una dirección o avisar de un retraso, busca "
            "un lugar seguro para aparcar. Después retoma el trayecto.",
        ),
        PARKEZ_ADVICE_PROMO,
    ),
    "parking-01": (
        AdviceTip(
            "Mira más allá de la puerta",
            "antes de salir, compara zonas a pocos minutos a pie del destino. "
            "Una pequeña caminata puede ser mejor que dar vueltas a la misma manzana.",
        ),
        AdviceTip(
            "Una plaza libre no siempre es válida",
            "antes de dejar el coche, comprueba señales, horarios y reservas. "
            "Que un hueco esté vacío no significa que puedas estacionar allí.",
        ),
        AdviceTip(
            "Guarda el punto de regreso",
            "marca en Google Maps dónde has aparcado antes de alejarte. "
            "Añade una nota con la entrada o la planta si el lugar es grande.",
        ),
        AdviceTip(
            "Ten una alternativa preparada",
            "decide antes de salir qué otra zona o parking puedes usar. "
            "Si el primer sitio está lleno, tendrás otra opción ya pensada.",
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
    tips = PARKEZ_ADVICE_PACKS[pack_id]
    if background == AdviceBackground.ILLUSTRATED:
        return tips[:3] + tips[-1:]
    return tips


def parkez_advice_social_copy(
    pack_id: str, background: AdviceBackground = AdviceBackground.ILLUSTRATED,
    *, copy_id: str = PARKEZ_ADVICE_SOCIAL_COPY_IDS[0],
    hook_id: str = PARKEZ_ADVICE_HOOK_IDS[0],
) -> SocialCopy:
    tips = parkez_advice_tips(pack_id, background)
    copy_index = PARKEZ_ADVICE_SOCIAL_COPY_IDS.index(copy_id)
    count_word = "cuatro" if len(tips) == 4 else "cinco"
    intro = PARKEZ_ADVICE_SOCIAL_INTROS[copy_index].format(count_word=count_word)
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
