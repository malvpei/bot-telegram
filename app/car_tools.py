from __future__ import annotations

from app.models import CAR_TOOLS_ROLES, SlideRole


# Curated from catalog numbers 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 15, 16 and 17.
# Keep the exact filenames and order: this tuple is also the Tools rotation.
CAR_TOOLS_BACKGROUND_FILES: tuple[str, ...] = (
    "Abstract Boho Blurred Background.jpg",
    (
        "Abstract Luxury Gradient Blue Background. Smooth Dark Blue with Black "
        "Vignette Studio Banner. (1).jpg"
    ),
    (
        "Abstract Luxury Gradient Blue Background. Smooth Dark Blue with Black "
        "Vignette Studio Banner..jpg"
    ),
    (
        "Abstract Smooth Orange Background Layout Design,Studio,Room, Web Template "
        ",Business Report with Smooth Circle Gradient Color.jpg"
    ),
    "Artistic Blurry Colorful Wallpaper Background.jpg",
    (
        "Backdrop Purple Background Room Studio with Pink Gradient Spotlight "
        "Backdrop Blurred Light.jpg"
    ),
    "Black Background with White Spotlight.jpg",
    "color-gradiente-verde_179286-43.jpg",
    "Gemini_Generated_Image_82pvb782pvb782pv.png",
    "Gemini_Generated_Image_ejsejcejsejcejse.png",
    "Gemini_Generated_Image_vyx9odvyx9odvyx9.png",
    "Gemini_Generated_Image_y25n3hy25n3hy25n.png",
    "istockphoto-1328691808-612x612.jpg",
)


CAR_TOOLS_ICON_FILES: dict[SlideRole, str] = {
    SlideRole.CAR_TOOL_RADARBOT: "radarbot.png",
    SlideRole.CAR_TOOL_PARKEZ: "parkez.png",
    SlideRole.CAR_TOOL_WAZE: "waze.png",
    SlideRole.CAR_TOOL_GOOGLE_MAPS: "google_maps.png",
}


# These strings intentionally preserve the spelling shown in the supplied
# reference images. They are product copy, not prose to normalize or correct.
CAR_TOOLS_SLIDE_TEXTS: dict[SlideRole, str] = {
    SlideRole.CAR_TOOL_RADARBOT: (
        "1. RadarBot\n"
        "Evita todos los radares, que no te llegue una multa de sorpresa"
    ),
    SlideRole.CAR_TOOL_PARKEZ: (
        "2. ParkEz\n"
        "Te enseña donde habra aparcamiento en la calle"
    ),
    SlideRole.CAR_TOOL_WAZE: (
        "3. Waze\n"
        "Encuentra la mejor ruta para navegar, evita el trafico"
    ),
    SlideRole.CAR_TOOL_GOOGLE_MAPS: (
        "4. Google maps\n"
        "Buena opccion para viajes largos, y para encontrar cines, "
        "restaurantes ect"
    ),
    SlideRole.CAR_TOOL_R2: "",
}


def car_tools_slide_texts() -> dict[SlideRole, str]:
    """Return the fixed five-slide copy in carousel order."""
    return {role: CAR_TOOLS_SLIDE_TEXTS[role] for role in CAR_TOOLS_ROLES}
