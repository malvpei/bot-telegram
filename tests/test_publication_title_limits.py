"""The published title has one character budget across every delivery path."""

import pytest

from app.models import SocialCopy
from app.publication_limits import MAX_PUBLICATION_TITLE_LENGTH, limit_publication_title


@pytest.mark.parametrize("title, expected", (
    ("", ""),
    ("Una idea para repasar mejor", "Una idea para repasar mejor"),
    ("á" * 90, "á" * 90),
    ("x" * 91, "x" * 90),
    ("a" * 84 + " " + "b" * 5 + " fin", "a" * 84 + " " + "b" * 5),
    ("\tRepasa\t\t tus\napuntes\u00a0con cafe\u0301   ", "Repasa tus apuntes con café"),
    ("e\u0301" * 90, "é" * 90),
))
def test_title_budget_normalizes_unicode_and_preserves_the_exact_boundary(title, expected):
    assert MAX_PUBLICATION_TITLE_LENGTH == 90
    assert limit_publication_title(title) == expected


def test_long_title_ends_on_a_complete_word():
    title = "Organiza tus apuntes y revisa lo que todavía te cuesta antes de preparar el siguiente examen"

    limited = limit_publication_title(title)

    assert 0 < len(limited) <= 90
    assert limited != title
    assert title.startswith(limited + " ")


def test_legacy_copy_is_bounded_without_changing_the_hook_description_or_hashtags():
    title = "Una idea para preparar tus aplicaciones antes de salir de casa y organizar la llegada al destino"
    hook = "Hook literal " + "largo " * 25
    description = "Una descripción con su propio espacio. " * 20
    hashtags = ["#coches", "#ParkEz"]

    copy = SocialCopy(title=title, description=description, hashtags=hashtags, hook=hook)

    assert 0 < len(copy.title) <= 90
    assert copy.hook == hook
    assert copy.description == description
    assert copy.hashtags == hashtags
    assert copy.messages == [hook, copy.title, description.strip() + " #coches #ParkEz"]


def test_message_delivery_bounds_a_title_replaced_after_copy_creation():
    copy = SocialCopy(title="Título inicial", description="Texto de publicación.", hashtags=[], hook="Hook literal")
    copy.title = "apuntes " * 20

    messages = copy.messages

    assert messages[0] == "Hook literal"
    assert 0 < len(messages[1]) <= 90
    assert messages[1].split() == ["apuntes"] * len(messages[1].split())
    assert messages[2] == "Texto de publicación."
