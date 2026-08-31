from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.car_tools import (
    CAR_TOOLS_BACKGROUND_FILES,
    CAR_TOOLS_BODY_LINES,
    CAR_TOOLS_HOOK,
    CAR_TOOLS_ICON_FILES,
    CAR_TOOLS_SLIDE_TEXTS,
    car_tools_slide_texts,
)
from app.car_tools_social import (
    CAR_TOOLS_SOCIAL_COPY_IDS,
    car_tools_social_copies,
)
from app.config import get_settings
from app.models import (
    CAR_TOOLS_ROLES,
    MediaCandidate,
    SlidePlan,
    SlideRole,
    VideoType,
)
from app.render import (
    CAR_TOOLS_BODY_LINE_GAPS,
    CAR_TOOLS_BODY_TOP_RATIOS,
    CAR_TOOLS_TEXT_EDGE_MARGIN,
    CAR_TOOLS_TEXT_BOLD,
    TYPE_3_BODY_FONT_SIZE,
    VideoRenderer,
)


EXPECTED_CAR_TOOLS_TEXTS = {
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

EXPECTED_CAR_TOOLS_BODY_LINES = {
    SlideRole.CAR_TOOL_RADARBOT: (
        "Evita todos los radares, que no te",
        "llegue una multa de sorpresa",
    ),
    SlideRole.CAR_TOOL_PARKEZ: (
        "Te enseña donde habra",
        "aparcamiento en la calle",
    ),
    SlideRole.CAR_TOOL_WAZE: (
        "Encuentra la mejor ruta para",
        "navegar, evita el trafico",
    ),
    SlideRole.CAR_TOOL_GOOGLE_MAPS: (
        "Buena opccion para viajes largos, y",
        "para encontrar cines, restaurantes",
        "ect",
    ),
}

EXPECTED_CAR_TOOLS_ICON_FILES = {
    SlideRole.CAR_TOOL_RADARBOT: "radarbot.png",
    SlideRole.CAR_TOOL_PARKEZ: "parkez.png",
    SlideRole.CAR_TOOL_WAZE: "waze.png",
    SlideRole.CAR_TOOL_GOOGLE_MAPS: "google_maps.png",
}

EXPECTED_CAR_TOOLS_BACKGROUND_FILES = (
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


def _candidate(path: Path, source_id: str) -> MediaCandidate:
    return MediaCandidate(
        source_account="cartools",
        source_id=source_id,
        local_path=path,
        permalink="",
        caption="",
        width=360,
        height=640,
        created_at="fixed",
    )


def test_car_tools_copy_preserves_the_supplied_text_exactly():
    assert list(CAR_TOOLS_ROLES) == [
        SlideRole.CAR_TOOL_RADARBOT,
        SlideRole.CAR_TOOL_PARKEZ,
        SlideRole.CAR_TOOL_WAZE,
        SlideRole.CAR_TOOL_GOOGLE_MAPS,
        SlideRole.CAR_TOOL_R2,
    ]
    assert CAR_TOOLS_SLIDE_TEXTS == EXPECTED_CAR_TOOLS_TEXTS
    assert car_tools_slide_texts() == EXPECTED_CAR_TOOLS_TEXTS
    assert CAR_TOOLS_HOOK == "apps que son lirteralmente obligatorias si tiene coche"


def test_car_tools_has_15_varied_social_copies_with_driving_hashtags():
    copies = car_tools_social_copies()

    assert len(copies) == 15
    assert len(CAR_TOOLS_SOCIAL_COPY_IDS) == 15
    assert len(set(CAR_TOOLS_SOCIAL_COPY_IDS)) == 15
    assert len({copy.title for copy in copies}) == 15
    assert len({copy.description for copy in copies}) == 15

    delivered_description_lengths: list[int] = []
    for copy in copies:
        assert copy.hook == CAR_TOOLS_HOOK
        assert len(copy.messages) == 3
        assert copy.messages[:2] == [CAR_TOOLS_HOOK, copy.title]
        assert copy.messages[2].startswith(copy.description)
        assert 200 <= len(copy.description) <= 2_000
        assert 200 <= len(copy.messages[2]) <= 2_000
        assert "#coches" in copy.hashtags
        assert copy.hashtags
        assert all(
            hashtag.startswith("#") and " " not in hashtag
            for hashtag in copy.hashtags
        )
        for app_name in ("RadarBot", "ParkEz", "Waze", "Google Maps"):
            assert app_name in copy.description
        delivered_description_lengths.append(len(copy.messages[2]))

    assert len(set(delivered_description_lengths)) >= 10
    assert (
        max(delivered_description_lengths) - min(delivered_description_lengths)
        >= 1_000
    )


def test_car_tools_social_copy_factory_returns_independent_hashtag_lists():
    first_batch = car_tools_social_copies()
    second_batch = car_tools_social_copies()

    first_batch[0].hashtags.append("#mutacion")

    assert "#mutacion" not in second_batch[0].hashtags


def test_car_tools_icon_assets_use_stable_names_and_have_visible_alpha():
    assert CAR_TOOLS_ICON_FILES == EXPECTED_CAR_TOOLS_ICON_FILES
    assets_dir = Path(__file__).resolve().parents[1] / "cartools" / "iconos"

    for filename in EXPECTED_CAR_TOOLS_ICON_FILES.values():
        path = assets_dir / filename
        assert path.is_file(), f"Falta el icono fijo de car tools: {path}"
        with Image.open(path) as image:
            alpha = image.convert("RGBA").getchannel("A")
            assert alpha.getbbox() is not None


def test_car_tools_uses_only_the_selected_backgrounds_in_catalog_order():
    assert CAR_TOOLS_BACKGROUND_FILES == EXPECTED_CAR_TOOLS_BACKGROUND_FILES
    assert len(CAR_TOOLS_BACKGROUND_FILES) == 13
    assert len(set(CAR_TOOLS_BACKGROUND_FILES)) == 13
    backgrounds_dir = (
        Path(__file__).resolve().parents[1] / "tipo3" / "fondocolores"
    )

    for filename in EXPECTED_CAR_TOOLS_BACKGROUND_FILES:
        path = backgrounds_dir / filename
        assert path.is_file(), f"Falta el fondo seleccionado de Tools: {path}"
        with Image.open(path) as image:
            image.verify()


def test_car_tools_renderer_resolves_each_role_icon_from_cartools_directory(
    tmp_path,
):
    icons_dir = tmp_path / "cartools" / "iconos"
    icons_dir.mkdir(parents=True)
    background_path = tmp_path / "background.png"
    background_color = (24, 31, 42)
    Image.new("RGB", (360, 640), background_color).save(background_path)

    icon_colors = {
        SlideRole.CAR_TOOL_RADARBOT: (230, 20, 30, 255),
        SlideRole.CAR_TOOL_PARKEZ: (20, 220, 40, 255),
        SlideRole.CAR_TOOL_WAZE: (20, 60, 230, 255),
        SlideRole.CAR_TOOL_GOOGLE_MAPS: (225, 210, 20, 255),
    }
    for role, color in icon_colors.items():
        Image.new("RGBA", (96, 96), color).save(
            icons_dir / EXPECTED_CAR_TOOLS_ICON_FILES[role]
        )

    renderer = VideoRenderer(
        replace(
            get_settings(),
            root_dir=tmp_path,
            width=360,
            height=640,
            fonts_dir=tmp_path / "fonts",
        )
    )

    for index, (role, icon_color) in enumerate(icon_colors.items(), start=1):
        slide = SlidePlan(
            index=index,
            role=role,
            text=EXPECTED_CAR_TOOLS_TEXTS[role],
            media=_candidate(background_path, f"background:{index}"),
            fixed_asset=True,
        )

        rendered = np.asarray(renderer.render_slide_still(slide, VideoType.TOOLS))
        expected_rgb = np.asarray(icon_color[:3])
        matching_icon_pixels = np.all(rendered == expected_rgb, axis=2)

        assert matching_icon_pixels.mean() > 0.01


def test_car_tools_reference_wraps_and_uses_regular_text_weight():
    renderer = VideoRenderer(
        replace(
            get_settings(),
            width=1080,
            height=1920,
        )
    )
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
    font = renderer._load_font(
        size=TYPE_3_BODY_FONT_SIZE,
        bold=CAR_TOOLS_TEXT_BOLD,
    )
    expected_lines = EXPECTED_CAR_TOOLS_BODY_LINES

    assert CAR_TOOLS_BODY_LINES == EXPECTED_CAR_TOOLS_BODY_LINES
    assert [len(lines) for lines in CAR_TOOLS_BODY_LINES.values()] == [2, 2, 2, 3]
    assert CAR_TOOLS_TEXT_BOLD is False

    for role, expected in expected_lines.items():
        _title, body, cta = renderer._split_type_3_tool_text(
            EXPECTED_CAR_TOOLS_TEXTS[role]
        )
        assert " ".join(expected) == " ".join(
            piece for piece in (body, cta) if piece
        )
        for line in expected:
            line_width = renderer._text_size(
                draw,
                line,
                font,
                stroke_width=4,
            )[0]
            assert line_width <= 1080 - CAR_TOOLS_TEXT_EDGE_MARGIN * 2

    assert CAR_TOOLS_BODY_TOP_RATIOS == {
        SlideRole.CAR_TOOL_RADARBOT: 0.315,
        SlideRole.CAR_TOOL_PARKEZ: 0.323,
        SlideRole.CAR_TOOL_WAZE: 0.315,
        SlideRole.CAR_TOOL_GOOGLE_MAPS: 0.324,
    }
    assert CAR_TOOLS_BODY_LINE_GAPS == {
        SlideRole.CAR_TOOL_RADARBOT: 11,
        SlideRole.CAR_TOOL_PARKEZ: 22,
        SlideRole.CAR_TOOL_WAZE: 11,
        SlideRole.CAR_TOOL_GOOGLE_MAPS: 9,
    }


def test_car_tools_r2_slide_is_clean_and_covers_the_canvas(tmp_path):
    source_path = tmp_path / "r2-source.png"
    source_color = (17, 103, 211)
    Image.new("RGB", (500, 500), source_color).save(source_path)
    renderer = VideoRenderer(
        replace(
            get_settings(),
            root_dir=tmp_path,
            width=360,
            height=640,
            fonts_dir=tmp_path / "fonts",
        )
    )
    slide = SlidePlan(
        index=5,
        role=SlideRole.CAR_TOOL_R2,
        text="",
        media=_candidate(source_path, "r2-cartools:example.png"),
        fixed_asset=False,
    )

    rendered = renderer.render_slide_still(slide, VideoType.TOOLS)
    pixels = np.asarray(rendered)

    assert rendered.size == (360, 640)
    assert np.all(pixels == np.asarray(source_color))
