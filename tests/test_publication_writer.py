from __future__ import annotations

import json
from dataclasses import replace

import pytest
import requests

from app.config import get_settings
from app.publication_writer import (
    PUBLICATION_WRITER_MODEL,
    PUBLICATION_WRITER_TIMEOUT,
    PUBLICATION_WRITER_URL,
    PublicationWriter,
)


class Response:
    def __init__(self, output=None, *, payload=None, status=200, finish="stop"):
        self.status_code = status
        self.payload = payload if payload is not None else {
            "choices": [{"finish_reason": finish, "message": {"content": output}}],
        }

    def json(self):
        return self.payload


@pytest.fixture
def writer():
    return PublicationWriter(replace(get_settings(), fal_key="test-secret"))


@pytest.fixture
def context():
    return {
        "brand": "parkez", "language": "es", "video_type": "parkez_apps",
        "slides": [
            {"role": "app_store", "text": "Notion: organiza notas y proyectos"},
            {"role": "parkez_promo", "text": "ParkEz: orienta la búsqueda de aparcamiento"},
        ],
    }


def test_writer_sends_only_fact_context_and_recent_history_in_one_bounded_request(writer, context, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response(json.dumps({
            "title": "Una app para tus notas y otra para tu trayecto",
            "description": "Notion organiza tus proyectos. ParkEz te orienta al buscar sitio.",
            "hashtags": ["#ignored"],
        }))

    monkeypatch.setattr("app.publication_writer.requests.post", post)
    history = {
        "titles": [f"Título anterior {index}" for index in range(30)],
        "descriptions": [f"Descripción anterior {index}" for index in range(20)],
        "private_unused": "must-not-be-transmitted",
    }

    result = writer.write(context, history, "short")

    assert result == {
        "title": "Una app para tus notas y otra para tu trayecto",
        "description": "Notion organiza tus proyectos. ParkEz te orienta al buscar sitio.",
    }
    assert len(calls) == 1
    url, request = calls[0]
    assert url == PUBLICATION_WRITER_URL
    assert request["headers"]["Authorization"] == "Key test-secret"
    assert request["timeout"] == PUBLICATION_WRITER_TIMEOUT == 20
    payload = request["json"]
    assert payload["model"] == PUBLICATION_WRITER_MODEL
    assert payload["stream"] is False
    prompt = json.loads(payload["messages"][1]["content"])
    assert prompt["context"] == context
    assert prompt["avoid_recent"]["titles"] == history["titles"][-12:]
    assert prompt["avoid_recent"]["descriptions"] == history["descriptions"][-6:]
    assert "must-not-be-transmitted" not in json.dumps(payload)
    assert prompt["description_style"] == "short"
    assert prompt["description_max_characters"] == 220


@pytest.mark.parametrize("key", ("", "   ", None))
def test_missing_key_never_calls_network(key, context, monkeypatch):
    writer = PublicationWriter(replace(get_settings(), fal_key=key))
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: pytest.fail("No API call without a key"))
    assert writer.write(context, {}, "short") is None


@pytest.mark.parametrize("style", ("unknown", None, []))
def test_invalid_style_uses_local_fallback_without_request(writer, context, style, monkeypatch):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: pytest.fail("No API call for invalid style"))
    assert writer.write(context, {}, style) is None


@pytest.mark.parametrize("style, description, expected", (
    ("none", "Text the model should have omitted", ""),
    ("short", "A" * 220, "A" * 220),
    ("medium", "B" * 550, "B" * 550),
))
def test_description_styles_are_enforced(writer, context, style, description, expected, monkeypatch):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: Response(json.dumps({"title": "Título natural", "description": description})))
    assert writer.write(context, {}, style) == {"title": "Título natural", "description": expected}


@pytest.mark.parametrize("style, description", (("short", "A" * 221), ("medium", "B" * 551), ("short", ""), ("medium", "")))
def test_oversize_or_unrequested_empty_descriptions_are_rejected(writer, context, style, description, monkeypatch):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: Response(json.dumps({"title": "Título natural", "description": description})))
    assert writer.write(context, {}, style) is None


@pytest.mark.parametrize("raw", (
    "", "not json", "[]", "null", '{"title": "Missing description"}',
    '{"title": [], "description": "text"}', '{"title": "text", "description": {}}',
    '{"title": "", "description": "text"}',
    json.dumps({"title": "x" * 121, "description": "text"}),
    json.dumps({"title": "Two\nlines", "description": "text"}),
    json.dumps({"title": "Título #coches", "description": "text"}),
    json.dumps({"title": "Título natural", "description": "Texto #ParkEz"}),
    '```json\n{"title":"unfinished", "description":"text"}',
))
def test_malformed_or_unsuitable_provider_copy_returns_fallback(writer, context, raw, monkeypatch):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: Response(raw))
    assert writer.write(context, {}, "short") is None


def test_fenced_json_and_numbered_title_are_valid(writer, context, monkeypatch):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: Response('```json\n{"title":"El consejo #1 para organizarte", "description":"Una observación útil."}\n```'))
    assert writer.write(context, {}, "short") == {"title": "El consejo #1 para organizarte", "description": "Una observación útil."}


@pytest.mark.parametrize("response", (
    Response("unused", status=401), Response("unused", status=429), Response("unused", status=503),
    Response(payload={"error": "provider details test-secret", "choices": []}),
    Response(payload={"partial": True}), Response(payload={"choices": []}),
    Response("{}", finish="length"), Response("{}", finish="content_filter"),
    Response(payload={"choices": [{"message": {"refusal": "not available", "content": "{}"}}]}),
))
def test_provider_errors_and_truncated_completions_return_fallback(writer, context, response, monkeypatch, caplog):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: response)
    assert writer.write(context, {}, "short") is None
    assert "test-secret" not in caplog.text
    assert "provider details" not in caplog.text


@pytest.mark.parametrize("error", (requests.Timeout("test-secret private payload"), requests.ConnectionError("test-secret private payload"), ValueError("test-secret private payload")))
def test_network_and_parsing_errors_never_leak_credentials_or_retry(writer, context, error, monkeypatch, caplog):
    calls = []

    def post(*args, **kwargs):
        calls.append(True)
        raise error

    monkeypatch.setattr("app.publication_writer.requests.post", post)
    with caplog.at_level("INFO"):
        assert writer.write(context, {}, "short") is None
    assert len(calls) == 1
    assert "test-secret" not in caplog.text
    assert "private payload" not in caplog.text
    assert type(error).__name__ in caplog.text


def test_unsupported_context_uses_fallback_before_request(writer, monkeypatch):
    monkeypatch.setattr("app.publication_writer.requests.post", lambda *args, **kwargs: pytest.fail("Do not serialize unsupported facts"))
    assert writer.write({"not_serializable": object()}, {}, "short") is None
    assert writer.write({"too_large": "x" * 25000}, {}, "short") is None
