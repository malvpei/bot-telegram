import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

import app.texts as texts_module
from app.models import Language, SlideRole, TYPE_3_ROLES, VideoType
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
    exact_count = 0
    for _ in range(30):
        package = generator.generate(VideoType.TYPE_1, Language.ES)
        hook = package.slides_by_role[SlideRole.HOOK]
        if hook.startswith(("Exactamente cuanto", "Exactamente cuánto")):
            exact_count += 1
        assert len(hook) <= 95
        assert "Dropshipping" in hook
    assert exact_count >= 24


def test_type_1_amounts_are_coherent(state_dir):
    generator = _make_generator(state_dir)
    for _ in range(20):
        package = generator.generate(VideoType.TYPE_1, Language.ES)
        feb_amount = _extract_amount(package.slides_by_role[SlideRole.FEBRUARY])
        march_amount = _extract_amount(package.slides_by_role[SlideRole.MARCH])
        assert feb_amount is not None and march_amount is not None
        # March is the stable-income month, must beat February.
        assert march_amount > feb_amount


def test_type_2_es_has_five_slides_and_no_forbidden_punctuation(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.ES)

    assert len(package.ordered_slides) == 5
    for slide in package.ordered_slides:
        for token in FORBIDDEN_TYPE_2_TOKENS:
            assert token not in slide
    assert "Dropradar" in package.slides_by_role[SlideRole.TIP3]


def test_type_2_tips_are_single_paragraph_and_hooks_are_short(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.ES)

    assert len(package.slides_by_role[SlideRole.HOOK]) <= 85
    for role in (SlideRole.TIP1, SlideRole.TIP2, SlideRole.TIP3, SlideRole.TIP4):
        slide = package.slides_by_role[role]
        assert "\n" not in slide
        assert slide.startswith(f"{role.value[-1]}.")


def test_type_2_en_passes_punctuation_rule(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.EN)

    assert len(package.ordered_slides) == 5
    for slide in package.ordered_slides:
        for token in FORBIDDEN_TYPE_2_TOKENS:
            assert token not in slide
    assert "Dropradar" in package.slides_by_role[SlideRole.TIP3]


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
        assert any(term in hook for term in money_terms)


def test_consecutive_generations_differ(state_dir):
    generator = _make_generator(state_dir)
    first = generator.generate(VideoType.TYPE_1, Language.ES)
    # Persist the previous signature like the service does.
    generator.state.set_last_signature(VideoType.TYPE_1, Language.ES, first.signature)
    generator.state.remember_signature(
        VideoType.TYPE_1, Language.ES, first.signature
    )
    second = generator.generate(VideoType.TYPE_1, Language.ES)
    assert second.signature != first.signature


@pytest.mark.parametrize("video_type", [VideoType.TYPE_1, VideoType.TYPE_2])
def test_type_1_and_2_have_many_script_variants(state_dir, video_type):
    generator = _make_generator(state_dir)
    signatures: set[str] = set()
    for _ in range(12):
        package = generator.generate(video_type, Language.ES)
        generator.state.set_last_signature(video_type, Language.ES, package.signature)
        generator.state.remember_signature(video_type, Language.ES, package.signature)
        signatures.add(package.signature)

    assert len(signatures) >= 10


def test_type_3_has_tool_stack_without_hosting(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.ES)

    assert len(package.ordered_slides) == len(TYPE_3_ROLES)
    full_text = package.plain_text.lower()
    assert "dropshipping" in package.slides_by_role[SlideRole.HOOK].lower()
    assert "hosting" not in full_text
    assert "hostinger" not in full_text
    assert _contains_exactly_one(
        package.slides_by_role[SlideRole.TOOL_PAYMENTS],
        ("paypal", "stripe"),
    )
    assert _contains_exactly_one(
        package.slides_by_role[SlideRole.TOOL_EDITING],
        ("canva", "capcut"),
    )
    assert _contains_exactly_one(
        package.slides_by_role[SlideRole.TOOL_MARKETING],
        ("instagram", "tiktok"),
    )


def test_type_3_can_use_paypal_canva_and_instagram(state_dir, monkeypatch):
    monkeypatch.setattr(texts_module.random, "choice", lambda seq: list(seq)[0])
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.ES)

    assert "paypal" in package.slides_by_role[SlideRole.TOOL_PAYMENTS].lower()
    assert "canva" in package.slides_by_role[SlideRole.TOOL_EDITING].lower()
    assert "instagram" in package.slides_by_role[SlideRole.TOOL_MARKETING].lower()


def test_type_3_can_use_stripe_capcut_and_tiktok(state_dir, monkeypatch):
    monkeypatch.setattr(texts_module.random, "choice", lambda seq: list(seq)[-1])
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.EN)

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
    assert len(package.social_copy.description) >= 220
    if video_type in (VideoType.TYPE_1, VideoType.TYPE_2):
        assert len(package.social_copy.description) >= 340
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


def _extract_amount(text: str) -> int | None:
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _contains_exactly_one(text: str, options: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return sum(option in lowered for option in options) == 1
