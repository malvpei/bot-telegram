from __future__ import annotations

import hashlib
import random

from app.models import (
    Language,
    ScriptPackage,
    SlideRole,
    SocialCopy,
    VideoGender,
    VideoType,
)
from app.state import StateStore


PARKEZ_MALE_FIXED_IMAGE_NAME = "parkez_male.png"
PARKEZ_FEMALE_FIXED_IMAGE_NAME = "parkez_female.png"

PARKEZ_ROLES: tuple[SlideRole, ...] = (
    SlideRole.HOOK,
    SlideRole.TIP1,
    SlideRole.TIP2,
    SlideRole.PARKEZ_PROMO,
)


_PARKEZ_TEXT_VARIANTS: dict[
    VideoGender,
    tuple[tuple[str, dict[SlideRole, str]], ...],
] = {
    VideoGender.FEMALE: (
        (
            "female-a",
            {
                SlideRole.HOOK: "Cómo bajar el cortisol con 3 sencillos tips 😉",
                SlideRole.TIP1: (
                    "Cuando sientas estrés mastica chicle, esto hace que tu "
                    "cuerpo se relaje inconscientemente."
                ),
                SlideRole.TIP2: (
                    "El agua fría activa tu instinto, tu cuerpo se relaja "
                    "pasado 10 segundos."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Relájate a la hora de aparcar usando aplicaciones como "
                    "ParkEz que te dicen dónde hay sitio."
                ),
            },
        ),
        (
            "female-b",
            {
                SlideRole.HOOK: (
                    "3 trucos sencillos para bajar revoluciones cuando notas "
                    "el estrés ✨"
                ),
                SlideRole.TIP1: (
                    "Prueba el suspiro fisiológico: dos inhalaciones cortas por "
                    "la nariz y una exhalación larga por la boca."
                ),
                SlideRole.TIP2: (
                    "Afloja la mandíbula y baja los hombros; tu cuerpo también "
                    "le manda señales de calma a tu mente."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Evita dar vueltas buscando sitio: ParkEz te orienta hacia "
                    "las calles con más probabilidades de aparcamiento."
                ),
            },
        ),
        (
            "female-c",
            {
                SlideRole.HOOK: (
                    "Si hoy vas a mil, guarda estos 3 tips para volver a la calma 🤍"
                ),
                SlideRole.TIP1: (
                    "Nombra cinco cosas que ves, cuatro que sientes y tres que "
                    "oyes para volver al presente."
                ),
                SlideRole.TIP2: (
                    "Tararea una canción durante unos segundos: alargar la "
                    "exhalación puede ayudarte a respirar más despacio."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Haz que aparcar sea la parte fácil del trayecto con ParkEz "
                    "y sus zonas recomendadas."
                ),
            },
        ),
        (
            "female-d",
            {
                SlideRole.HOOK: (
                    "3 formas rápidas de resetearte cuando el estrés se dispara 😌"
                ),
                SlideRole.TIP1: (
                    "Aprieta todos los músculos durante cinco segundos y suéltalos "
                    "de golpe; notar el contraste ayuda a relajar el cuerpo."
                ),
                SlideRole.TIP2: (
                    "Deja el móvil boca abajo durante un minuto y mira un punto "
                    "lejano para descansar la atención."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Antes de llegar, consulta ParkEz para saber por qué calles "
                    "merece la pena empezar a buscar sitio."
                ),
            },
        ),
    ),
    VideoGender.MALE: (
        (
            "male-a",
            {
                SlideRole.HOOK: "Trucos de vida que deberían ser ilegales 🤫",
                SlideRole.TIP1: (
                    "Si sientes ansiedad, lávate las manos con agua caliente. "
                    "Engañarás a tu cerebro pensando que estás a salvo."
                ),
                SlideRole.TIP2: (
                    "Para cruzar multitudes, mira fijamente hacia tu destino y no "
                    "a la gente. Se apartarán solos."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Quítate el estrés de aparcar, usa aplicaciones como ParkEz "
                    "para encontrar aparcamiento libre en la calle."
                ),
            },
        ),
        (
            "male-b",
            {
                SlideRole.HOOK: "3 trucos cotidianos que parecen hacer trampa 👀",
                SlideRole.TIP1: (
                    "Si necesitas concentrarte, mastica un chicle de un sabor que "
                    "no uses a menudo y conviértelo en tu señal para entrar en modo foco."
                ),
                SlideRole.TIP2: (
                    "Cuando camines entre mucha gente, mira al hueco por el que "
                    "quieres pasar; los demás entenderán mejor tu trayectoria."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Ahorra vueltas innecesarias con ParkEz: consulta primero las "
                    "calles donde es más probable que haya aparcamiento."
                ),
            },
        ),
        (
            "male-c",
            {
                SlideRole.HOOK: (
                    "Trucos simples que te solucionan más de lo que parece 🤫"
                ),
                SlideRole.TIP1: (
                    "Si una canción no sale de tu cabeza, escúchala hasta el final. "
                    "Cerrar la melodía puede ayudar a cortar el bucle."
                ),
                SlideRole.TIP2: (
                    "Cuando necesites recordar algo al salir, deja un objeto fuera "
                    "de lugar junto a la puerta para activar tu memoria."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "No dependas de la suerte al aparcar: ParkEz te muestra por "
                    "dónde conviene empezar a buscar sitio."
                ),
            },
        ),
        (
            "male-d",
            {
                SlideRole.HOOK: "3 trucos para hacerte la vida un poco más fácil 🧠",
                SlideRole.TIP1: (
                    "Si dudas entre dos opciones, lanza una moneda: mientras está "
                    "en el aire suele quedar claro qué resultado esperas."
                ),
                SlideRole.TIP2: (
                    "Para recordar dónde dejaste el coche, fotografía también una "
                    "referencia del lugar y no solo el vehículo."
                ),
                SlideRole.PARKEZ_PROMO: (
                    "Y para encontrar sitio desde el principio, abre ParkEz y ve "
                    "directo a las zonas con mejores probabilidades."
                ),
            },
        ),
    ),
}


def build_parkez_script(
    state: StateStore,
    gender: VideoGender,
    *,
    rng: random.Random | None = None,
) -> ScriptPackage:
    """Choose a coherent ParkEz pack without repeating the previous pack."""
    variants = _PARKEZ_TEXT_VARIANTS[gender]
    previous_choice = state.get_last_text_choice(
        VideoType.PARKEZ,
        Language.ES,
        profile=gender.value,
    )
    available = [variant for variant in variants if variant[0] != previous_choice]
    choice_key, source_texts = (rng or random).choice(available or list(variants))
    slides_by_role = dict(source_texts)
    ordered_slides = [slides_by_role[role] for role in PARKEZ_ROLES]
    signature = hashlib.sha1(
        "|".join([gender.value, *ordered_slides]).encode("utf-8")
    ).hexdigest()
    return ScriptPackage(
        slides_by_role=slides_by_role,
        ordered_slides=ordered_slides,
        signature=signature,
        plain_text="\n\n".join(ordered_slides),
        social_copy=SocialCopy(title="", description="", hashtags=[]),
        choice_key=choice_key,
    )


def parkez_fixed_image_name(gender: VideoGender) -> str:
    if gender == VideoGender.FEMALE:
        return PARKEZ_FEMALE_FIXED_IMAGE_NAME
    return PARKEZ_MALE_FIXED_IMAGE_NAME
