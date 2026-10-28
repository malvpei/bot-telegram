from collections import Counter
from itertools import combinations

import pytest

from app.models import TYPE_5_BUSINESS_ROLES, TYPE_5_ROLES, Language, SlideRole
from app.type_5 import (
    TYPE_5_BUSINESS_PAIRS,
    TYPE_5_SLIDE_TEXTS,
    TYPE_5_SLIDE_TEXTS_EN,
    type_5_slide_texts,
    type_5_social_copies,
)


def test_type_5_has_exact_hook_and_requested_business_content():
    assert TYPE_5_SLIDE_TEXTS[SlideRole.HOOK] == (
        "Top negocios para jubilar a tus padres 🫡"
    )
    assert TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_TRADING] == (
        "Traiding 2/10 ❌\n"
        "-Dificil de empezar\n"
        "-Puedes perderlo todo en un momento"
    )
    assert TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_CLIPPING] == (
        "Clipping 4/10 ❌\n"
        "-Mucha competencia\n"
        "-Consume demasiado de tu tiempo por poco"
    )
    assert TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_AI_DROPSHIPPING] == (
        "AI + Dropshipping 10/10 ✅\n"
        "-Infinitamente escalable\n"
        "-Dropradar para productos ganadores y DeepSeek para ideas"
    )


def test_type_5_provides_twelve_distinct_titles_and_descriptions():
    copies = type_5_social_copies(Language.ES)

    assert len(copies) == 12
    assert len({copy.title for copy in copies}) == 12
    assert len({copy.description for copy in copies}) == 12
    assert all(copy.hashtags for copy in copies)


def test_type_5_provides_english_chat_text_and_social_copy():
    texts = type_5_slide_texts(Language.EN)
    copies = type_5_social_copies(Language.EN)

    assert texts == TYPE_5_SLIDE_TEXTS_EN
    assert texts[SlideRole.HOOK] == "Top businesses to retire your parents 🫡"
    assert texts[SlideRole.TYPE_5_TRADING].startswith("Trading 2/10 ❌")
    assert texts[SlideRole.TYPE_5_CLIPPING].startswith("Clipping 4/10 ❌")
    assert "-Low returns" not in texts[SlideRole.TYPE_5_CLIPPING]
    assert texts[SlideRole.TYPE_5_AI_DROPSHIPPING].startswith(
        "AI + Dropshipping 10/10 ✅"
    )
    assert len(copies) == 12
    assert len({copy.title for copy in copies}) == 12
    assert len({copy.description for copy in copies}) == 12
    assert all("#onlinebusiness" in copy.hashtags for copy in copies)


@pytest.mark.parametrize(
    ("role", "spanish", "english"),
    [
        (
            SlideRole.TYPE_5_AMAZON_FBA,
            "Amazon FBA 3/10 ❌\n"
            "-Inversión inicial en stock\n"
            "-Comisiones y costes de almacenamiento",
            "Amazon FBA 3/10 ❌\n"
            "-Upfront investment in inventory\n"
            "-Fees and storage costs",
        ),
        (
            SlideRole.TYPE_5_PRINT_ON_DEMAND,
            "Print on demand 2/10 ❌\n"
            "-Margen limitado por producto\n"
            "-Necesitas vender mucho para escalar",
            "Print on demand 2/10 ❌\n"
            "-Limited margin per product\n"
            "-You need high sales volume to scale",
        ),
        (
            SlideRole.TYPE_5_AFFILIATE_MARKETING,
            "Marketing de afiliados 6/10 🟡\n"
            "-No necesitas gestionar stock\n"
            "-Necesitas audiencia y generar confianza",
            "Affiliate marketing 6/10 🟡\n"
            "-No inventory to manage\n"
            "-You need an audience and trust",
        ),
    ],
)
def test_new_businesses_have_approved_text_and_matching_translation(role, spanish, english):
    assert type_5_slide_texts(Language.ES)[role] == spanish
    assert type_5_slide_texts(Language.EN)[role] == english


def test_business_rotation_covers_all_five_evenly_without_duplicates_per_video():
    assert len(TYPE_5_BUSINESS_PAIRS) == 5
    assert len(TYPE_5_BUSINESS_ROLES) == 5
    assert all(len(set(pair)) == 2 for pair in TYPE_5_BUSINESS_PAIRS)
    appearances = Counter(role for pair in TYPE_5_BUSINESS_PAIRS for role in pair)
    assert appearances == {role: 2 for role in TYPE_5_BUSINESS_ROLES}
    flattened = [role for pair in TYPE_5_BUSINESS_PAIRS for role in pair]
    assert flattened[:5] == list(TYPE_5_BUSINESS_ROLES)
    assert flattened[5:] == list(TYPE_5_BUSINESS_ROLES)
    assert TYPE_5_ROLES[-1] == SlideRole.TYPE_5_AI_DROPSHIPPING
    assert SlideRole.TYPE_5_AI_DROPSHIPPING not in appearances


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("business_roles", list(combinations(TYPE_5_BUSINESS_ROLES, 2)))
def test_every_social_copy_describes_only_the_selected_businesses(language, business_roles):
    names = {
        SlideRole.TYPE_5_TRADING: "Trading",
        SlideRole.TYPE_5_CLIPPING: "Clipping",
        SlideRole.TYPE_5_AMAZON_FBA: "Amazon FBA",
        SlideRole.TYPE_5_PRINT_ON_DEMAND: "Print on demand",
        SlideRole.TYPE_5_AFFILIATE_MARKETING: (
            "Marketing de afiliados" if language == Language.ES else "Affiliate marketing"
        ),
    }
    copies = type_5_social_copies(language, business_roles)

    assert len(copies) == 12
    assert len({copy.title for copy in copies}) == 12
    assert len({copy.description for copy in copies}) == 12
    for copy in copies:
        assert "AI + Dropshipping" in copy.description
        assert "Dropradar" in copy.description
        assert "DeepSeek" in copy.description
        assert "{" not in copy.title + copy.description
        for role, name in names.items():
            if role in business_roles:
                assert name in copy.description
            else:
                assert name.lower() not in (copy.title + copy.description).lower()


@pytest.mark.parametrize("language", list(Language))
def test_business_messages_and_social_copies_are_independent(language):
    texts = type_5_slide_texts(language)
    texts.clear()
    assert len(type_5_slide_texts(language)) == 7
    copies = type_5_social_copies(language, TYPE_5_BUSINESS_PAIRS[1])
    copies[0].hashtags.clear()
    copies[0].title = "changed"
    fresh = type_5_social_copies(language, TYPE_5_BUSINESS_PAIRS[1])
    assert fresh[0].hashtags
    assert fresh[0].title != "changed"


@pytest.mark.parametrize(
    "business_roles",
    [
        (SlideRole.TYPE_5_TRADING, SlideRole.TYPE_5_TRADING),
        (SlideRole.HOOK, SlideRole.TYPE_5_CLIPPING),
        (SlideRole.TYPE_5_TRADING, SlideRole.TYPE_5_AI_DROPSHIPPING),
    ],
)
def test_social_copies_require_two_distinct_rotating_businesses(business_roles):
    with pytest.raises(ValueError, match="two distinct businesses"):
        type_5_social_copies(Language.ES, business_roles)
