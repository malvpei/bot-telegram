from app.advice_cards import (
    ADVICE_BACKGROUNDS,
    ADVICE_EXTERNAL_PHRASES,
    ADVICE_PACKS,
    ADVICE_ROTATION_CYCLE_LENGTH,
    ADVICE_SOCIAL_CYCLE_LENGTH,
    ADVICE_SOCIAL_DESCRIPTIONS,
    ADVICE_SOCIAL_TITLES,
    AdviceBackground,
    advice_selection,
    advice_social_copy,
)
from app.models import Language, SocialCopy


def test_advice_packs_are_bilingual_and_promote_dropradar_winning_products():
    assert len(ADVICE_PACKS[Language.ES]) == 4
    assert len(ADVICE_PACKS[Language.EN]) == 4
    for packs in ADVICE_PACKS.values():
        for tips in packs:
            assert len(tips) == 4
            final_body = tips[-1].body.lower()
            assert "dropradar" in final_body
            assert any(term in final_body for term in ("ganador", "winner", "winning"))


def test_every_type_4_pack_recommends_chatgpt_for_order_operations():
    for language in (Language.ES, Language.EN):
        for tips in ADVICE_PACKS[language]:
            chatgpt_tip = tips[1]
            assert "chatgpt" in f"{chatgpt_tip.title} {chatgpt_tip.body}".lower()
            assert "chatgpt" not in chatgpt_tip.title.lower()
            assert any(
                term in chatgpt_tip.body.lower()
                for term in ("pedido", "orders", "order")
            )


def test_advice_backgrounds_and_scripts_complete_full_rotation():
    assert ADVICE_BACKGROUNDS == (
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.EDITORIAL,
        AdviceBackground.BROWN,
    )
    assert ADVICE_SOCIAL_CYCLE_LENGTH == 360
    assert ADVICE_ROTATION_CYCLE_LENGTH == 360

    selections = [
        advice_selection(phase, Language.ES)
        for phase in range(ADVICE_ROTATION_CYCLE_LENGTH)
    ]
    assert [selection[0] for selection in selections[:10]] == [
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.EDITORIAL,
        AdviceBackground.BROWN,
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.EDITORIAL,
        AdviceBackground.BROWN,
    ]
    assert [selection[2] for selection in selections[:10]] == [
        0,
        1,
        2,
        3,
        0,
        1,
        2,
        3,
        0,
        1,
    ]
    assert advice_selection(360, Language.ES) == advice_selection(0, Language.ES)


def test_editorial_advice_background_adds_a_fifth_dropshipping_tip():
    background, tips, pack_index = advice_selection(3, Language.ES)

    assert background == AdviceBackground.EDITORIAL
    assert pack_index == 3
    assert len(tips) == 5
    assert tips[-2].title == "compara tres ángulos"
    assert "Dropradar" in tips[-1].body


def test_brown_advice_background_adds_a_fifth_dropshipping_tip():
    background, tips, pack_index = advice_selection(4, Language.ES)

    assert background == AdviceBackground.BROWN
    assert pack_index == 0
    assert len(tips) == 5
    assert tips[-2].title == "prueba la oferta antes de escalar"
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

    assert title == "la regla #1 no es perseguir visitas"
    assert title != ADVICE_EXTERNAL_PHRASES[Language.ES]
    assert len(description) >= 1500
    assert "hook" in description.lower()
    assert "Dropradar" in description
    assert hashtags == [
        "#dropshipping",
        "#productosganadores",
        "#ecommerce",
        "#shopify",
        "#dropradar",
    ]


def test_advice_catalog_has_39_unique_matching_social_copy_pairs_per_language():
    for language in (Language.ES, Language.EN):
        assert len(ADVICE_SOCIAL_TITLES[language]) == len(ADVICE_PACKS[language])
        assert len(ADVICE_SOCIAL_DESCRIPTIONS[language]) == len(
            ADVICE_PACKS[language]
        )
        all_titles = []
        all_descriptions = []
        for titles, descriptions in zip(
            ADVICE_SOCIAL_TITLES[language],
            ADVICE_SOCIAL_DESCRIPTIONS[language],
            strict=True,
        ):
            assert len(titles) == len(descriptions)
            all_titles.extend(titles)
            all_descriptions.extend(descriptions)
        assert len(all_titles) == len(set(all_titles)) == 39
        assert len(all_descriptions) == len(set(all_descriptions)) == 39


def test_advice_social_copy_exhausts_each_pack_before_repeating_across_phase_wrap():
    for language in (Language.ES, Language.EN):
        copies_by_pack = [[] for _ in ADVICE_PACKS[language]]
        for phase in range(ADVICE_ROTATION_CYCLE_LENGTH * 2):
            # The persisted service phase resets at the end of the shared cycle.
            saved_phase = phase % ADVICE_ROTATION_CYCLE_LENGTH
            _background, _tips, pack_index = advice_selection(saved_phase, language)
            title, description, _tags = advice_social_copy(
                language, pack_index, rotation_index=saved_phase
            )
            copies_by_pack[pack_index].append((title, description))

        for pack_index in range(len(ADVICE_PACKS[language])):
            expected_pairs = list(
                zip(
                    ADVICE_SOCIAL_TITLES[language][pack_index],
                    ADVICE_SOCIAL_DESCRIPTIONS[language][pack_index],
                    strict=True,
                )
            )
            copies = copies_by_pack[pack_index]
            count = len(expected_pairs)
            assert len(copies) % count == 0
            for start in range(0, len(copies), count):
                assert copies[start : start + count] == expected_pairs


def test_social_copy_keeps_advice_hook_separate_from_title():
    copy = SocialCopy(
        hook=ADVICE_EXTERNAL_PHRASES[Language.ES],
        title="la regla #1 no es perseguir visitas",
        description="Descripción de prueba",
        hashtags=["#dropshipping"],
    )

    assert copy.messages == [
        ADVICE_EXTERNAL_PHRASES[Language.ES],
        "la regla #1 no es perseguir visitas",
        "Descripción de prueba #dropshipping",
    ]
