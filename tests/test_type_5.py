from app.models import SlideRole
from app.type_5 import TYPE_5_SLIDE_TEXTS, type_5_social_copies


def test_type_5_has_exact_hook_and_requested_business_content():
    assert TYPE_5_SLIDE_TEXTS[SlideRole.HOOK] == (
        "Top negocios para jubilar a tus padres 🫡"
    )
    assert "Trading 2/10 ❌" in TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_TRADING]
    assert "Clipping 4/10 ❌" in TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_CLIPPING]
    ai_text = TYPE_5_SLIDE_TEXTS[SlideRole.TYPE_5_AI_DROPSHIPPING]
    assert "AI + Dropshipping ✅" in ai_text
    assert "Dropradar" in ai_text
    assert "DeepSeek" in ai_text


def test_type_5_provides_six_distinct_titles_and_descriptions():
    copies = type_5_social_copies()

    assert len(copies) == 6
    assert len({copy.title for copy in copies}) == 6
    assert len({copy.description for copy in copies}) == 6
    assert all(copy.hashtags for copy in copies)
