import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

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


def test_type_2_en_passes_punctuation_rule(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_2, Language.EN)

    assert len(package.ordered_slides) == 5
    for slide in package.ordered_slides:
        for token in FORBIDDEN_TYPE_2_TOKENS:
            assert token not in slide
    assert "Dropradar" in package.slides_by_role[SlideRole.TIP3]


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


def test_type_3_has_tool_stack_without_hosting(state_dir):
    generator = _make_generator(state_dir)
    package = generator.generate(VideoType.TYPE_3, Language.ES)

    assert len(package.ordered_slides) == len(TYPE_3_ROLES)
    full_text = package.plain_text.lower()
    assert "dropshipping" in package.slides_by_role[SlideRole.HOOK].lower()
    assert "hosting" not in full_text
    assert "hostinger" not in full_text
    assert "marketing" in full_text
    assert "tiktok" in full_text


def _extract_amount(text: str) -> int | None:
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None
