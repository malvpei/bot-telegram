from app.advice_cards import (
    ADVICE_BACKGROUNDS,
    ADVICE_EXTERNAL_PHRASES,
    ADVICE_PACKS,
    ADVICE_ROTATION_CYCLE_LENGTH,
    AdviceBackground,
    advice_selection,
)
from app.models import Language


def test_advice_packs_are_bilingual_and_always_finish_with_dropradar():
    assert len(ADVICE_PACKS[Language.ES]) == 4
    assert len(ADVICE_PACKS[Language.EN]) == 4
    for packs in ADVICE_PACKS.values():
        for tips in packs:
            assert len(tips) == 4
            assert "dropradar" in tips[-1].body.lower()


def test_advice_backgrounds_and_scripts_complete_twelve_step_rotation():
    assert ADVICE_BACKGROUNDS == (
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
    )
    assert ADVICE_ROTATION_CYCLE_LENGTH == 12

    selections = [
        advice_selection(phase, Language.ES)
        for phase in range(ADVICE_ROTATION_CYCLE_LENGTH)
    ]
    assert [selection[0] for selection in selections[:6]] == [
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
        AdviceBackground.BLACK,
        AdviceBackground.WHITE,
        AdviceBackground.ILLUSTRATED,
    ]
    assert [selection[2] for selection in selections[:6]] == [0, 1, 2, 3, 0, 1]
    assert advice_selection(12, Language.ES) == advice_selection(0, Language.ES)


def test_advice_external_phrases_match_requested_copy():
    assert ADVICE_EXTERNAL_PHRASES[Language.EN] == (
        "A millionaire dropshipper told me rule number #1 for selling easily"
    )
    assert ADVICE_EXTERNAL_PHRASES[Language.ES] == (
        "un dropshipper millonario me contó la regla número #1 para vender fácilmente"
    )
