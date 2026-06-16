import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

import app.texts as texts_module
from app.models import (
    Language,
    SlideRole,
    TYPE_3_ROLES,
    TYPE_4_ROLES,
    VideoGender,
    VideoType,
)
from app.state import StateStore
from app.texts import FORBIDDEN_TYPE_2_TOKENS, ScriptGenerator


@pytest.fixture()
def state_dir():
    workspace_tmp = Path(__file__).resolve().parents[1] / "data" / "_test_tmp"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    path = workspace_tmp / f"state-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_generator(state_dir: Path) -> ScriptGenerator:
    return ScriptGenerator(StateStore(state_dir))


def test_type_1_es_has_seven_slides_and_dropradar_in_february(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_1, Language.ES)

    assert len(package.ordered_slides) == 7
    assert "Dropradar" in package.slides_by_role[SlideRole.FEBRUARY]
    # Months in correct narrative order.
    assert package.slides_by_role[SlideRole.OCTOBER].startswith("Octubre")
    assert package.slides_by_role[SlideRole.MARCH].startswith("Marzo")


def test_type_1_hooks_are_short_and_example_like(state_dir):
    generator = _make_generator(state_dir)
    allowed_hooks = {
        "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y por qué casi lo dejo...",
        "Cuanto gané haciendo Dropshipping\nen estos 6 meses y por qué casi lo dejo....",
        "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y porqué casi lo dejo...",
    }
    hooks = set()
    for _ in range(3):
        package = generator.generate(VideoType.TYPE_1, Language.ES)
        generator.state.set_last_text_choice(VideoType.TYPE_1, Language.ES, package.choice_key)
        hook = package.slides_by_role[SlideRole.HOOK]
        assert len(hook) <= 95
        assert len(hook.splitlines()) == 2
        assert hook in allowed_hooks
        hooks.add(hook)
    assert len(hooks) == 3


def test_type_1_es_visible_text_avoids_unapproved_hook_typos(state_dir):
    generator = _make_generator(state_dir)
    allowed_hooks = {
        "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y por qué casi lo dejo...",
        "Cuanto gané haciendo Dropshipping\nen estos 6 meses y por qué casi lo dejo....",
        "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y porqué casi lo dejo...",
    }

    for _ in range(3):
        package = generator.generate(VideoType.TYPE_1, Language.ES)
        generator.state.set_last_text_choice(VideoType.TYPE_1, Language.ES, package.choice_key)
        hook = package.slides_by_role[SlideRole.HOOK]
        visible_text = f"{hook}\n{package.social_copy.title}"

        assert hook in allowed_hooks
        assert "dropsipping" not in visible_text.lower()
        assert "facture" not in visible_text.lower()


def test_type_1_es_rejects_unapproved_exactamente_hook():
    with pytest.raises(RuntimeError, match="hook no aprobado"):
        ScriptGenerator._assert_type_1_rules(
            Language.ES,
            {
                SlideRole.HOOK: (
                    "Exactamente cuánto facturé haciendo Dropshipping en mis primeros 6 meses"
                ),
                SlideRole.FEBRUARY: "Febrero - 800€\nDropradar",
            },
        )


def test_type_1_amounts_are_coherent(state_dir):
    generator = _make_generator(state_dir)
    for _ in range(20):
        package = generator.generate(VideoType.TYPE_1, Language.ES)
        feb_amount = _extract_amount(package.slides_by_role[SlideRole.FEBRUARY])
        march_amount = _extract_amount(package.slides_by_role[SlideRole.MARCH])
        assert feb_amount is not None and march_amount is not None
        # March is the stable-income month, must beat February.
        assert march_amount > feb_amount


def test_type_1_es_uses_fixed_variants_and_alternates(state_dir):
    generator = _make_generator(state_dir)

    first = generator.generate(VideoType.TYPE_1, Language.ES)
    assert first.choice_key == "a"
    assert (
        first.slides_by_role[SlideRole.HOOK]
        == "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y por qué casi lo dejo..."
    )
    assert "Febrero - 800€" in first.slides_by_role[SlideRole.FEBRUARY]
    assert "Marzo - 2700€" in first.slides_by_role[SlideRole.MARCH]

    generator.state.set_last_text_choice(
        VideoType.TYPE_1,
        Language.ES,
        first.choice_key,
    )
    second = generator.generate(VideoType.TYPE_1, Language.ES)
    assert second.choice_key == "b"
    assert (
        second.slides_by_role[SlideRole.HOOK]
        == "Cuanto gané haciendo Dropshipping\nen estos 6 meses y por qué casi lo dejo...."
    )
    assert "Febrero - 680€" in second.slides_by_role[SlideRole.FEBRUARY]
    assert "Marzo - 3100€" in second.slides_by_role[SlideRole.MARCH]

    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.ES, second.choice_key)
    third = generator.generate(VideoType.TYPE_1, Language.ES)
    assert third.choice_key == "c"
    assert (
        third.slides_by_role[SlideRole.HOOK]
        == "Cuanto facturé haciendo Dropshipping\nen mis primeros 6 meses y porqué casi lo dejo..."
    )
    assert "Febrero - 1220€" in third.slides_by_role[SlideRole.FEBRUARY]
    assert "Marzo - 3100€" in third.slides_by_role[SlideRole.MARCH]

    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.ES, third.choice_key)
    assert generator.generate(VideoType.TYPE_1, Language.ES).choice_key == "a"


def test_type_1_es_female_gender_adapts_self_references(state_dir):
    generator = _make_generator(state_dir)

    first = generator.generate(
        VideoType.TYPE_1,
        Language.ES,
        gender=VideoGender.FEMALE,
    )

    expected_hook = (
        "Me dijeron que no iba a ganar\n"
        "nada con el Dropshipping por\n"
        "ser mujer y esto pasó..."
    )
    assert first.slides_by_role[SlideRole.HOOK] == expected_hook
    assert first.ordered_slides[0] == expected_hook
    assert first.plain_text.startswith(expected_hook)
    assert "supermotivada" in first.slides_by_role[SlideRole.OCTOBER]
    assert "supermotivado" not in first.slides_by_role[SlideRole.OCTOBER]
    assert "convencida" in first.social_copy.description
    assert "convencido" not in first.social_copy.description

    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.ES, first.choice_key)
    second = generator.generate(
        VideoType.TYPE_1,
        Language.ES,
        gender=VideoGender.FEMALE,
    )

    march = second.slides_by_role[SlideRole.MARCH]
    assert "No soy millonaria" in march
    assert "no haberme rendido" in march
    assert "millonario" not in march


def test_type_2_es_female_gender_uses_image_hook_in_three_lines(state_dir):
    generator = _make_generator(state_dir)

    package = generator.generate(
        VideoType.TYPE_2,
        Language.ES,
        gender=VideoGender.FEMALE,
    )

    expected_hook = (
        "Con estos 4 tips demostré que las\n"
        "mujeres también podemos tener\n"
        "éxito en el Dropshipping"
    )
    assert package.slides_by_role[SlideRole.HOOK] == expected_hook
    assert package.ordered_slides[0] == expected_hook
    assert package.plain_text.startswith(expected_hook)
    assert len(expected_hook.splitlines()) == 3


def test_type_1_en_uses_fixed_variants_and_alternates(state_dir):
    generator = _make_generator(state_dir)

    first = generator.generate(VideoType.TYPE_1, Language.EN)
    assert first.choice_key == "a"
    assert (
        first.slides_by_role[SlideRole.HOOK]
        == "How much I earned doing Dropshipping\nin my first 6 months and why I almost quit..."
    )
    assert "February - $800" in first.slides_by_role[SlideRole.FEBRUARY]
    assert "March - $2700" in first.slides_by_role[SlideRole.MARCH]

    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.EN, first.choice_key)
    second = generator.generate(VideoType.TYPE_1, Language.EN)
    assert second.choice_key == "b"
    assert (
        second.slides_by_role[SlideRole.HOOK]
        == "How much I made doing Dropshipping\nin my first 6 months and why I almost quit..."
    )
    assert "February - $680" in second.slides_by_role[SlideRole.FEBRUARY]
    assert "March - $3100" in second.slides_by_role[SlideRole.MARCH]

    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.EN, second.choice_key)
    third = generator.generate(VideoType.TYPE_1, Language.EN)
    assert third.choice_key == "c"
    assert (
        third.slides_by_role[SlideRole.HOOK]
        == "Exactly how much I made doing Dropshipping\nin my first 6 months and why I almost quit."
    )
    assert "February - 1220€" in third.slides_by_role[SlideRole.FEBRUARY]
    assert "March - 3100€" in third.slides_by_role[SlideRole.MARCH]

    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.EN, third.choice_key)
    assert generator.generate(VideoType.TYPE_1, Language.EN).choice_key == "a"


def test_type_2_es_has_five_slides_and_no_forbidden_punctuation(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.ES)

    assert len(package.ordered_slides) == 5
    for slide in package.ordered_slides:
        for token in FORBIDDEN_TYPE_2_TOKENS:
            assert token not in slide
    assert "Dropradar" in package.slides_by_role[SlideRole.TIP3]


def test_type_2_tips_separate_title_and_body_and_hooks_are_fixed(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.ES)

    assert package.slides_by_role[SlideRole.HOOK] in {
        "Habría pagado por saber estas 4 cosas\ncuando empecé en Dropshipping",
        "Errores que veo en pequeños Dropshippers\nque están empezando",
        "4 consejos de Dropshipping\nque me habrían ahorrado muchos errores",
    }
    for role in (SlideRole.TIP1, SlideRole.TIP2, SlideRole.TIP3, SlideRole.TIP4):
        slide = package.slides_by_role[role]
        assert slide.startswith(f"{role.value[-1]}.")
        assert "\n" in slide
        title, body = slide.split("\n", 1)
        assert title
        assert body


def test_type_2_es_uses_fixed_variants_and_alternates(state_dir):
    generator = _make_generator(state_dir)

    first = generator.generate(VideoType.TYPE_2, Language.ES)
    assert first.choice_key == "a"
    assert (
        first.slides_by_role[SlideRole.HOOK]
        == "Habría pagado por saber estas 4 cosas\ncuando empecé en Dropshipping"
    )
    assert first.slides_by_role[SlideRole.TIP1].startswith(
        "1. Valida con poco presupuesto\n"
    )

    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.ES, first.choice_key)
    second = generator.generate(VideoType.TYPE_2, Language.ES)
    assert second.choice_key == "b"
    assert (
        second.slides_by_role[SlideRole.HOOK]
        == "Errores que veo en pequeños Dropshippers\nque están empezando"
    )
    assert second.slides_by_role[SlideRole.TIP4].startswith(
        "4. Descuidar el trato con el comprador\n"
    )

    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.ES, second.choice_key)
    third = generator.generate(VideoType.TYPE_2, Language.ES)
    assert third.choice_key == "c"
    assert (
        third.slides_by_role[SlideRole.HOOK]
        == "4 consejos de Dropshipping\nque me habrían ahorrado muchos errores"
    )
    assert third.slides_by_role[SlideRole.TIP1].startswith(
        "1. Protege tu margen\n"
    )
    assert "Dropradar" in third.slides_by_role[SlideRole.TIP3]

    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.ES, third.choice_key)
    assert generator.generate(VideoType.TYPE_2, Language.ES).choice_key == "a"


def test_type_2_en_uses_fixed_variants_and_alternates(state_dir):
    generator = _make_generator(state_dir)

    first = generator.generate(VideoType.TYPE_2, Language.EN)
    assert first.choice_key == "a"
    assert (
        first.slides_by_role[SlideRole.HOOK]
        == "I would have paid to know these 4 things\nwhen I started Dropshipping"
    )
    assert first.slides_by_role[SlideRole.TIP1].startswith(
        "1. Validate with a small budget\n"
    )

    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.EN, first.choice_key)
    second = generator.generate(VideoType.TYPE_2, Language.EN)
    assert second.choice_key == "b"
    assert (
        second.slides_by_role[SlideRole.HOOK]
        == "Mistakes I see small Dropshippers\nmaking when they are starting out"
    )
    assert second.slides_by_role[SlideRole.TIP4].startswith(
        "4. Neglecting the buyer experience\n"
    )

    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.EN, second.choice_key)
    third = generator.generate(VideoType.TYPE_2, Language.EN)
    assert third.choice_key == "c"
    assert (
        third.slides_by_role[SlideRole.HOOK]
        == "4 Dropshipping lessons\nthat would have saved me a lot of mistakes"
    )
    assert third.slides_by_role[SlideRole.TIP1].startswith(
        "1. Protect your margin\n"
    )
    assert "Dropradar" in third.slides_by_role[SlideRole.TIP3]

    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.EN, third.choice_key)
    assert generator.generate(VideoType.TYPE_2, Language.EN).choice_key == "a"


def test_type_2_en_passes_punctuation_rule(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.EN)

    assert len(package.ordered_slides) == 5
    for slide in package.ordered_slides:
        for token in FORBIDDEN_TYPE_2_TOKENS:
            assert token not in slide
    assert "Dropradar" in package.slides_by_role[SlideRole.TIP3]


@pytest.mark.parametrize("video_type", [VideoType.TYPE_1, VideoType.TYPE_2])
@pytest.mark.parametrize("language", [Language.ES, Language.EN])
def test_type_1_and_2_male_hooks_are_exactly_two_lines(
    state_dir,
    video_type,
    language,
):
    generator = _make_generator(state_dir)

    for _ in range(3):
        package = generator.generate(
            video_type,
            language,
            gender=VideoGender.MALE,
        )
        hook = package.slides_by_role[SlideRole.HOOK]

        assert len(hook.splitlines()) == 2
        assert all(line.strip() for line in hook.splitlines())

        generator.state.set_last_text_choice(
            video_type,
            language,
            package.choice_key,
        )


@pytest.mark.parametrize(
    ("video_type", "language", "money_terms"),
    [
        (VideoType.TYPE_1, Language.ES, ("dinero", "€")),
        (VideoType.TYPE_2, Language.ES, ("dinero", "€")),
        (VideoType.TYPE_1, Language.EN, ("money", "$")),
        (VideoType.TYPE_2, Language.EN, ("money", "$")),
    ],
)
def test_type_1_and_2_hooks_mention_money_and_dropshipping(
    state_dir,
    monkeypatch,
    video_type,
    language,
    money_terms,
):
    generator = _make_generator(state_dir)
    for index in range(5):
        monkeypatch.setattr(
            texts_module.random,
            "choice",
            lambda seq, index=index: list(seq)[min(index, len(list(seq)) - 1)],
        )
        package = generator.generate(video_type, language)
        hook = package.slides_by_role[SlideRole.HOOK].lower()
        assert "dropshipping" in hook
        if video_type == VideoType.TYPE_1 and language == Language.ES:
            assert any(term in hook for term in ("gané", "facturé"))
            continue
        if video_type == VideoType.TYPE_1 and language == Language.EN:
            assert any(term in hook for term in ("earned", "made", "revenue"))
            continue
        if video_type == VideoType.TYPE_2:
            normalized_hook = " ".join(hook.split())
            assert normalized_hook in {
                "habría pagado por saber estas 4 cosas cuando empecé en dropshipping",
                "errores que veo en pequeños dropshippers que están empezando",
                "4 consejos de dropshipping que me habrían ahorrado muchos errores",
                "i would have paid to know these 4 things when i started dropshipping",
                "mistakes i see small dropshippers making when they are starting out",
                "4 dropshipping lessons that would have saved me a lot of mistakes",
            }
            continue
        assert any(term in hook for term in money_terms)


def test_consecutive_generations_differ(state_dir):
    generator = _make_generator(state_dir)
    first = generator.generate(VideoType.TYPE_1, Language.ES)
    # Persist the previous signature like the service does.
    generator.state.set_last_signature(VideoType.TYPE_1, Language.ES, first.signature)
    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.ES, first.choice_key)
    generator.state.remember_signature(
        VideoType.TYPE_1, Language.ES, first.signature
    )
    second = generator.generate(VideoType.TYPE_1, Language.ES)
    assert second.signature != first.signature


@pytest.mark.parametrize("video_type", [VideoType.TYPE_1, VideoType.TYPE_2])
def test_type_1_and_2_have_exactly_three_script_variants(state_dir, video_type):
    generator = _make_generator(state_dir)
    signatures: set[str] = set()
    for _ in range(12):
        package = generator.generate(video_type, Language.ES)
        generator.state.set_last_signature(video_type, Language.ES, package.signature)
        generator.state.set_last_text_choice(video_type, Language.ES, package.choice_key)
        generator.state.remember_signature(video_type, Language.ES, package.signature)
        signatures.add(package.signature)

    assert len(signatures) == 3


def test_type_3_has_tool_stack_without_hosting(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.ES)

    assert len(package.ordered_slides) == len(TYPE_3_ROLES)
    full_text = package.plain_text.lower()
    assert "hosting" not in full_text
    assert "hostinger" not in full_text
    assert package.slides_by_role[SlideRole.TOOL_STORE] == (
        "1. Tienda\nConstruye tu tienda por 1€ - Usa Shopify"
    )
    assert package.slides_by_role[SlideRole.TOOL_PRODUCT_SEARCH] == (
        "2. Busqueda de productos\nEncuentra productos ganadores - Usa Dropradar"
    )
    assert package.slides_by_role[SlideRole.TOOL_SCRIPTS] == (
        "3. Guiones\nCrea guiones para tus videos - Usa ChatGPT"
    )
    assert _contains_exactly_one(
        package.slides_by_role[SlideRole.TOOL_PAYMENTS],
        ("paypal", "stripe"),
    )
    assert package.slides_by_role[SlideRole.TOOL_EDITING] == (
        "5. Edicion\nEdita videos con mas calidad - Usa CapCut"
    )
    assert _contains_exactly_one(
        package.slides_by_role[SlideRole.TOOL_MARKETING],
        ("instagram", "tiktok"),
    )


def test_type_4_story_texts_are_exactly_fixed(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(
        VideoType.TYPE_4,
        Language.ES,
        lowercase_text=True,
        gender=VideoGender.FEMALE,
    )

    assert len(package.ordered_slides) == len(TYPE_4_ROLES)
    assert package.ordered_slides[:5] == [
        (
            "Así es como pasé de trabajar en el MacDonald a cumplir mi sueño "
            "de comprarme un Porsche 911 GT3"
        ),
        (
            "Monte mi tienda estuve horas analizando un buen producto y "
            "estudiando creativos"
        ),
        (
            "El primer mes tuve 0 ventas simplemente era un producto que no "
            "causaba interés"
        ),
        (
            "En los siguientes mesese fue peor tuve 0 ventas y probé 3 productos "
            "diferentes ninguno se vendia, estuve a punto de dejarlo para siempre"
        ),
        (
            "Investigando encontré Dropradar me dio un gran producto y empecé "
            "de 0 ese mes tuve mi primera venta"
        ),
    ]
    assert package.ordered_slides[5:] == ["", ""]
    assert package.slides_by_role[SlideRole.STORY_MCDONALD].startswith("Así es")
    assert package.slides_by_role[SlideRole.STORY_DROPRADAR].startswith("Investigando")


def test_type_3_can_use_paypal_and_instagram(state_dir, monkeypatch):
    monkeypatch.setattr(texts_module.random, "choice", lambda seq: list(seq)[0])
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.ES)

    assert package.slides_by_role[SlideRole.HOOK] == "Como hacer dropshipping en 2026"
    assert "paypal" in package.slides_by_role[SlideRole.TOOL_PAYMENTS].lower()
    assert "capcut" in package.slides_by_role[SlideRole.TOOL_EDITING].lower()
    assert "instagram" in package.slides_by_role[SlideRole.TOOL_MARKETING].lower()


def test_type_3_can_use_stripe_and_tiktok(state_dir, monkeypatch):
    monkeypatch.setattr(texts_module.random, "choice", lambda seq: list(seq)[-1])
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.EN)

    assert package.slides_by_role[SlideRole.HOOK] == "How to start in Dropshipping in 2026"
    assert "stripe" in package.slides_by_role[SlideRole.TOOL_PAYMENTS].lower()
    assert "capcut" in package.slides_by_role[SlideRole.TOOL_EDITING].lower()
    assert "tiktok" in package.slides_by_role[SlideRole.TOOL_MARKETING].lower()


@pytest.mark.parametrize(
    ("video_type", "language"),
    [
        (VideoType.TYPE_1, Language.ES),
        (VideoType.TYPE_2, Language.ES),
        (VideoType.TYPE_3, Language.ES),
        (VideoType.TYPE_1, Language.EN),
        (VideoType.TYPE_2, Language.EN),
        (VideoType.TYPE_3, Language.EN),
    ],
)
def test_every_video_type_has_social_copy(state_dir, video_type, language):
    generator = _make_generator(state_dir)
    package = generator.generate(video_type, language)

    assert package.social_copy.title
    assert package.social_copy.description
    assert 500 <= len(package.social_copy.description) <= 3500
    assert len(package.social_copy.hashtags) >= 3
    assert all(tag.startswith("#") for tag in package.social_copy.hashtags)
    assert all(" " not in tag for tag in package.social_copy.hashtags)
    assert package.social_copy.hashtag_line == " ".join(package.social_copy.hashtags)
    assert package.social_copy.messages == [
        package.social_copy.title,
        package.social_copy.description,
        package.social_copy.hashtag_line,
    ]
    assert all("Titulo:" not in message for message in package.social_copy.messages)
    assert all("Descripcion:" not in message for message in package.social_copy.messages)
    assert all("Hashtags:" not in message for message in package.social_copy.messages)
    assert "#dropshipping" in package.social_copy.hashtags


def test_lowercase_option_formats_slides_and_social_copy(state_dir):
    generator = _make_generator(state_dir)
    generator.state.set_last_text_choice(VideoType.TYPE_1, Language.EN, "b")
    package = generator.generate(
        VideoType.TYPE_1,
        Language.EN,
        lowercase_text=True,
    )

    assert package.choice_key == "c"
    assert package.plain_text == package.plain_text.lower()
    assert all(slide == slide.lower() for slide in package.ordered_slides)
    assert all(text == text.lower() for text in package.slides_by_role.values())
    assert package.social_copy.title == package.social_copy.title.lower()
    assert package.social_copy.description == package.social_copy.description.lower()
    assert all(tag == tag.lower() for tag in package.social_copy.hashtags)


def test_lowercase_option_formats_new_type_2_titleless_variant(state_dir):
    generator = _make_generator(state_dir)
    generator.state.set_last_text_choice(VideoType.TYPE_2, Language.EN, "b")

    package = generator.generate(
        VideoType.TYPE_2,
        Language.EN,
        lowercase_text=True,
    )

    assert package.choice_key == "c"
    assert all(slide == slide.lower() for slide in package.ordered_slides)
    assert "\n" in package.slides_by_role[SlideRole.TIP1]
    assert package.slides_by_role[SlideRole.TIP1].startswith("1. protect your margin")


def test_social_hashtags_force_literal_dropshipping():
    hashtags = ScriptGenerator._prepare_social_hashtags(
        ["#dropshipping2026", "#ecommerce", "#shopify", "#dropradar"]
    )

    assert "#dropshipping" in hashtags
    assert "#dropshipping2026" not in hashtags


def test_social_hashtags_shuffle_order(monkeypatch):
    monkeypatch.setattr(texts_module.random, "shuffle", lambda values: values.reverse())

    hashtags = ScriptGenerator._prepare_social_hashtags(
        ["#ecommerce", "#shopify", "#dropradar", "#dropshipping"]
    )

    assert hashtags[0] == "#dropshipping"


@pytest.mark.parametrize("video_type", [VideoType.TYPE_1, VideoType.TYPE_2])
@pytest.mark.parametrize("language", [Language.ES, Language.EN])
def test_type_1_and_2_social_copy_has_exactly_three_defined_variants(
    state_dir,
    video_type,
    language,
):
    generator = _make_generator(state_dir)
    variants = generator._social_copy_variants(video_type, language)

    lengths = [len(description) for _, description, _ in variants.values()]
    assert len(variants) == 3
    assert all(500 <= length <= 3500 for length in lengths)
    assert generator._social_title_variants(video_type, language) == {}

    first_key, first_copy = generator._choose_social_copy_for_text_choice(
        video_type,
        language,
        "a",
    )
    second_key, second_copy = generator._choose_social_copy_for_text_choice(
        video_type,
        language,
        "b",
    )

    assert generator._copy_choice_from_social_key(first_key) == list(variants)[0]
    assert generator._copy_choice_from_social_key(second_key) == list(variants)[1]
    assert second_copy.description != first_copy.description


@pytest.mark.parametrize("language", [Language.ES, Language.EN])
def test_type_3_social_copy_keeps_rotating_descriptions_with_varied_lengths(
    state_dir,
    language,
):
    generator = _make_generator(state_dir)
    variants = generator._social_copy_variants(VideoType.TYPE_3, language)

    lengths = [len(description) for _, description, _ in variants.values()]
    assert len(variants) >= 8
    assert all(500 <= length <= 3500 for length in lengths)
    assert len(set(lengths)) >= 4

    first_key, first_copy = generator._choose_social_copy(VideoType.TYPE_3, language)
    generator.state.set_last_social_choice(
        VideoType.TYPE_3,
        language,
        generator._copy_choice_from_social_key(first_key),
    )
    second_key, second_copy = generator._choose_social_copy(VideoType.TYPE_3, language)

    assert generator._copy_choice_from_social_key(second_key) != generator._copy_choice_from_social_key(first_key)
    assert second_copy.description != first_copy.description


@pytest.mark.parametrize("language", [Language.ES, Language.EN])
def test_type_3_social_copy_has_many_title_variants(state_dir, language):
    generator = _make_generator(state_dir)

    titles = generator._social_title_variants(VideoType.TYPE_3, language)

    assert len(titles) >= 12
    assert len(set(titles.values())) == len(titles)


def _extract_amount(text: str) -> int | None:
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _contains_exactly_one(text: str, options: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return sum(option in lowered for option in options) == 1
