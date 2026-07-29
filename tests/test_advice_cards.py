from app.advice_cards import (
    ADVICE_BACKGROUNDS,
    ADVICE_EXTERNAL_PHRASES,
    ADVICE_PACKS,
    ADVICE_ROTATION_CYCLE_LENGTH,
    AdviceBackground,
    advice_selection,
    advice_social_copy,
)
from app.models import Language


def test_advice_packs_are_bilingual_and_promote_dropradar_winning_products():
    assert len(ADVICE_PACKS[Language.ES]) == 4
    assert len(ADVICE_PACKS[Language.EN]) == 4
    for packs in ADVICE_PACKS.values():
        for tips in packs:
            assert len(tips) == 4
            final_body = tips[-1].body.lower()
            assert "dropradar" in final_body
            assert any(term in final_body for term in ("ganador", "winner", "winning"))


def test_advice_backgrounds_and_scripts_complete_full_rotation():
    assert ADVICE_BACKGROUNDS == (
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.EDITORIAL,
    )
    assert ADVICE_ROTATION_CYCLE_LENGTH == 48

    selections = [
        advice_selection(phase, Language.ES)
        for phase in range(ADVICE_ROTATION_CYCLE_LENGTH)
    ]
    assert [selection[0] for selection in selections[:8]] == [
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.EDITORIAL,
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.EDITORIAL,
    ]
    assert [selection[2] for selection in selections[:8]] == [0, 1, 2, 3, 1, 2, 3, 0]
    assert advice_selection(48, Language.ES) == advice_selection(0, Language.ES)


def test_editorial_advice_background_adds_a_fifth_dropshipping_tip():
    background, tips, pack_index = advice_selection(3, Language.ES)

    assert background == AdviceBackground.EDITORIAL
    assert pack_index == 3
    assert len(tips) == 5
    assert tips[-2].title == "compara tres ángulos"
    assert "Dropradar" in tips[-1].body


def test_advice_external_phrases_match_requested_copy():
    assert ADVICE_EXTERNAL_PHRASES[Language.EN] == (
        "A millionaire dropshipper told me rule number #1 for selling easily"
    )
    assert ADVICE_EXTERNAL_PHRASES[Language.ES] == (
        "un dropshipper millonario me contó la regla número #1 para vender fácilmente"
    )


def test_advice_social_copy_has_description_and_related_hashtags():
    title, description, hashtags = advice_social_copy(Language.ES, 0)

    assert title == ADVICE_EXTERNAL_PHRASES[Language.ES]
    assert "Dropradar" in description
    assert "productos ganadores" in description
    assert hashtags == [
        "#dropshipping",
        "#productosganadores",
        "#ecommerce",
        "#shopify",
        "#dropradar",
    ]


def test_advice_social_copy_rotates_three_titles_and_descriptions_per_pack():
    copies = [
        advice_social_copy(Language.EN, 0, rotation_index=phase)
        for phase in (0, 4, 8)
    ]

    assert len({copy[0] for copy in copies}) == 3
    assert len({copy[1] for copy in copies}) == 3
    assert all("Dropradar" in copy[1] for copy in copies)
