from app.models import Language, SlideRole
from app.type_5 import (
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
        "-Poco retorno\n"
        "-Consume demasiado de tu tiempo por poco"
    )
    assert TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_AI_DROPSHIPPING] == (
        "AI + Dropshipping ✅\n"
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
    assert texts[SlideRole.HOOK] == "Top businesses to retire your parents"
    assert texts[SlideRole.TYPE_5_TRADING].startswith("Trading 2/10 ❌")
    assert texts[SlideRole.TYPE_5_CLIPPING].startswith("Clipping 4/10 ❌")
    assert texts[SlideRole.TYPE_5_AI_DROPSHIPPING].startswith(
        "AI + Dropshipping ✅"
    )
    assert len(copies) == 12
    assert len({copy.title for copy in copies}) == 12
    assert len({copy.description for copy in copies}) == 12
    assert all("#onlinebusiness" in copy.hashtags for copy in copies)
