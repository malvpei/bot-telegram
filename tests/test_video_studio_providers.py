from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import requests

from app.video_studio.providers import (
    ElevenLabsClient,
    FalClient,
    GPT_IMAGE_EDIT,
    H3_MAX_TURBO,
    MissingCredential,
    ProviderError,
    SEEDANCE_FAST,
)


class Reply:
    def __init__(self, data=None, status=200, headers=None, content=b""):
        self.data = data
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.closed = False

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def speech_reply():
    alignment = {"characters": ["H", "o", "l", "a"], "character_start_times_seconds": [0, .1, .2, .3], "character_end_times_seconds": [.1, .2, .3, .5]}
    return Reply({"audio_base64": base64.b64encode(b"ID3" + b"\0" * 64).decode(), "alignment": alignment, "normalized_alignment": alignment}, headers={"request-id": "speech-123"})


def test_missing_credential_never_calls_network():
    with pytest.raises(MissingCredential):
        ElevenLabsClient("")
    with pytest.raises(MissingCredential):
        FalClient(" ")


def test_subscription_is_read_only_and_returns_no_billing_identity():
    session = Session(Reply({"tier": "starter", "status": "active", "character_count": 100, "character_limit": 1000, "email": "private@example.com", "next_invoice": {"amount": 50}}))
    result = ElevenLabsClient("secret", session).status()
    assert result["remaining_characters"] == 900
    assert "email" not in result and "next_invoice" not in result
    method, url, kwargs = session.calls[0]
    assert method == "GET" and url.endswith("/v1/user/subscription")
    assert kwargs["headers"]["xi-api-key"] == "secret"
    assert kwargs["allow_redirects"] is False


def test_voices_paginate_and_strip_verification_recordings():
    session = Session(
        Reply({"voices": [{"voice_id": "a1", "name": "Ana", "samples": [{"private": True}], "labels": {"language": "es"}}], "has_more": True, "next_page_token": "next"}),
        Reply({"voices": [{"voice_id": "b2", "name": "Pablo", "preview_url": "javascript:alert(1)"}], "has_more": False}),
    )
    result = ElevenLabsClient("secret", session).voices()
    assert [v["voice_id"] for v in result] == ["a1", "b2"]
    assert "samples" not in result[0]
    assert result[1]["preview_url"] is None
    assert session.calls[1][2]["params"]["next_page_token"] == "next"


def test_voices_v1_fallback_only_when_v2_unavailable():
    session = Session(Reply({}, status=404), Reply({"voices": [{"voice_id": "v1", "name": "Voz"}]}))
    assert ElevenLabsClient("secret", session).voices()[0]["voice_id"] == "v1"
    assert session.calls[1][1].endswith("/v1/voices")
    denied = Session(Reply({}, status=403))
    with pytest.raises(ProviderError) as error:
        ElevenLabsClient("secret", denied).voices()
    assert error.value.status_code == 403 and len(denied.calls) == 1


def test_shared_voices_filters_spain_and_never_implies_account_access():
    session = Session(Reply({"voices": [{"voice_id": "spain1", "name": "Pablo", "language": "es", "accent": "peninsular", "gender": "male", "age": "young", "public_owner_id": "owner", "email": "private@example.com", "preview_url": "https://storage.googleapis.com/eleven-public-prod/sample.mp3", "free_users_allowed": True}], "has_more": False}))
    result = ElevenLabsClient("secret", session).shared_voices(gender="male", age="young")
    assert result[0]["source"] == "voice_library"
    assert result[0]["added_to_account"] is False
    assert result[0]["requires_paid_api_access"] is True
    assert result[0]["labels"]["accent"] == "peninsular"
    assert "email" not in result[0] and "public_owner_id" not in result[0]
    method, url, kwargs = session.calls[0]
    assert method == "GET" and url.endswith("/v1/shared-voices")
    assert kwargs["params"]["locale"] == "es-ES"
    assert kwargs["params"]["language"] == "es"
    assert kwargs["params"]["include_custom_rates"] == "false"


def test_shared_voices_paginates_without_copying_any_voice():
    session = Session(Reply({"voices": [{"voice_id": "a", "name": "Uno"}], "has_more": True}), Reply({"voices": [{"voice_id": "b", "name": "Dos"}], "has_more": False}))
    result = ElevenLabsClient("secret", session).shared_voices(limit=2)
    assert len(result) == 2
    assert all(method == "GET" for method, _, _ in session.calls)
    assert [call[2]["params"]["page"] for call in session.calls] == [0, 1]


def test_speech_with_timestamps_cached_without_second_billable_post(tmp_path):
    session = Session(speech_reply())
    client = ElevenLabsClient("very-secret-key", session)
    first = client.synthesize("Hola", "speaker1", output_dir=tmp_path)
    second = client.synthesize("Hola", "speaker1", output_dir=tmp_path)
    assert first["cached"] is False and second["cached"] is True
    assert first["duration"] == .5 and first["duration_source"] == "character_alignment"
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "POST" and url.endswith("/speaker1/with-timestamps")
    assert kwargs["params"]["output_format"] == "mp3_44100_128"
    assert "language_code" not in kwargs["json"]
    for path in tmp_path.iterdir():
        assert b"very-secret-key" not in path.read_bytes()
    assert json.loads(Path(first["alignment_path"]).read_text())["alignment"]["characters"] == list("Hola")


def test_speech_timeout_does_not_retry_or_duplicate_on_next_run(tmp_path):
    session = Session(requests.Timeout("contains secret-key and sensitive request"))
    client = ElevenLabsClient("secret-key", session)
    with pytest.raises(ProviderError) as first:
        client.synthesize("Hola", "speaker1", output_dir=tmp_path)
    assert first.value.outcome_unknown and "secret-key" not in str(first.value)
    with pytest.raises(ProviderError) as second:
        client.synthesize("Hola", "speaker1", output_dir=tmp_path)
    assert second.value.code == "unknown_outcome"
    assert len(session.calls) == 1


def test_malformed_paid_response_requires_review_before_repeating(tmp_path):
    reply = speech_reply()
    reply.data["alignment"]["character_end_times_seconds"][2] = -1
    session = Session(reply)
    client = ElevenLabsClient("secret", session)
    with pytest.raises(ProviderError) as error:
        client.synthesize("Hola", "speaker1", output_dir=tmp_path)
    assert error.value.code == "invalid_alignment"
    with pytest.raises(ProviderError) as repeated:
        client.synthesize("Hola", "speaker1", output_dir=tmp_path)
    assert repeated.value.code == "unknown_outcome" and len(session.calls) == 1


def test_voice_setting_change_creates_distinct_cache_and_spanish_flash(tmp_path):
    session = Session(speech_reply(), speech_reply())
    client = ElevenLabsClient("secret", session)
    first = client.synthesize("Hola", "speaker1", model_id="eleven_flash_v2_5", output_dir=tmp_path)
    second = client.synthesize("Hola", "speaker1", model_id="eleven_flash_v2_5", settings={"stability": .8}, output_dir=tmp_path)
    assert first["cache_key"] != second["cache_key"]
    assert session.calls[0][2]["json"]["language_code"] == "es"


@pytest.mark.parametrize("settings", [{"speed": float("nan")}, {"stability": 2}, {"use_speaker_boost": "yes"}, {"unexpected": True}])
def test_invalid_speech_configuration_fails_before_charge(tmp_path, settings):
    session = Session()
    with pytest.raises(ProviderError):
        ElevenLabsClient("secret", session).synthesize("Hola", "speaker1", settings=settings, output_dir=tmp_path)
    assert session.calls == []


def test_api_redirect_never_follows_with_credentials():
    session = Session(Reply({}, status=302, headers={"Location": "https://evil.example/"}))
    with pytest.raises(ProviderError) as error:
        ElevenLabsClient("secret", session).status()
    assert error.value.code == "unexpected_redirect"
    assert len(session.calls) == 1 and session.calls[0][2]["allow_redirects"] is False


def test_fal_queue_owner_app_routes_survive_new_client():
    session = Session(Reply({"request_id": "r123", "status_url": "https://queue.fal.run/fal-ai/bytedance/requests/r123/status", "response_url": "https://queue.fal.run/fal-ai/bytedance/requests/r123"}))
    info = FalClient("secret", session).submit(SEEDANCE_FAST, {"prompt": "A complete scene", "image_url": "https://v3.fal.media/ref.png", "duration": 5})
    assert info["request_id"] == "r123"
    assert session.calls[0][2]["json"]["duration"] == "5"
    polling = Session(Reply({"status": "IN_PROGRESS", "logs": [{"secret": True}]}), Reply({"video": {"url": "https://v3.fal.media/result.mp4"}, "expanded_prompt": "large-private-input"}))
    client = FalClient("secret", polling)
    assert client.poll(SEEDANCE_FAST, "r123") == {"status": "IN_PROGRESS", "request_id": "r123"}
    assert "expanded_prompt" not in client.result(SEEDANCE_FAST, "r123")
    assert polling.calls[0][1] == "https://queue.fal.run/fal-ai/bytedance/requests/r123/status"


def test_fal_rejects_model_injection_and_foreign_tracking_url():
    empty = Session()
    with pytest.raises(ProviderError):
        FalClient("secret", empty).submit("https://evil.example/model", {"prompt": "x"})
    assert not empty.calls
    session = Session(Reply({"request_id": "r123", "status_url": "https://evil.example/status"}))
    with pytest.raises(ProviderError) as error:
        FalClient("secret", session).submit(H3_MAX_TURBO, {"prompt": "x", "image_url": "https://v3.fal.media/ref.png"})
    assert error.value.outcome_unknown
    assert len(session.calls) == 1


def test_h3_normalizes_documented_resolution_and_image_edit_preserves_refs():
    session = Session(Reply({"request_id": "a"}), Reply({"request_id": "b"}))
    client = FalClient("secret", session)
    client.submit(H3_MAX_TURBO, {"prompt": "x", "image_url": "data:image/png;base64,AAAA", "resolution": "768p", "duration": 6})
    client.submit(GPT_IMAGE_EDIT, {"prompt": "An integrated whole scene", "image_urls": ["data:image/png;base64,AAAA", "https://v3.fal.media/ref2.png"], "quality": "medium"})
    assert session.calls[0][2]["json"]["resolution"] == "768P"
    assert len(session.calls[1][2]["json"]["image_urls"]) == 2


def test_fal_pricing_is_read_only_and_preserves_billing_unit():
    session = Session(Reply({"prices": [{"endpoint_id": GPT_IMAGE_EDIT, "unit_price": 30, "unit": "million_output_image_tokens", "currency": "USD"}], "has_more": False}))
    result = FalClient("secret", session).pricing(GPT_IMAGE_EDIT)
    assert result["prices"][0]["unit"] == "million_output_image_tokens"
    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["params"] == {"endpoint_id": GPT_IMAGE_EDIT}


def test_missing_price_is_not_assumed_free():
    session = Session(Reply({"prices": []}))
    with pytest.raises(ProviderError) as error:
        FalClient("secret", session).pricing(H3_MAX_TURBO)
    assert error.value.code == "pricing_unavailable"


def test_media_download_omits_auth_and_checks_magic(tmp_path):
    data = b"\0\0\0\x18ftypisom" + b"\0" * 100
    session = Session(Reply(content=data, headers={"Content-Type": "video/mp4"}))
    destination = tmp_path / "shot.mp4"
    result = FalClient("secret", session).download_video({"video": {"url": "https://v3b.fal.media/files/shot.mp4"}}, destination)
    assert destination.read_bytes() == data and result["bytes"] == len(data)
    assert "Authorization" not in session.calls[0][2]["headers"]
    assert "xi-api-key" not in session.calls[0][2]["headers"]
    assert session.calls[0][2]["allow_redirects"] is False


@pytest.mark.parametrize("url", ["https://localhost/result.mp4", "https://127.0.0.1/result.mp4", "http://v3.fal.media/result.mp4", "https://fal.media.evil.example/result.mp4", "https://user:secret@v3.fal.media/result.mp4"])
def test_media_destination_is_restricted_before_network(tmp_path, url):
    session = Session()
    with pytest.raises(ProviderError):
        FalClient("secret", session).download_video({"video": {"url": url}}, tmp_path / "shot.mp4")
    assert session.calls == []


def test_media_redirect_to_internal_address_is_rejected(tmp_path):
    session = Session(Reply(status=302, headers={"Location": "https://127.0.0.1/secrets"}))
    with pytest.raises(ProviderError):
        FalClient("secret", session).download_video({"video": {"url": "https://v3.fal.media/result.mp4"}}, tmp_path / "shot.mp4")
    assert len(session.calls) == 1
    assert not (tmp_path / "shot.mp4").exists()


def test_invalid_media_never_becomes_final_file(tmp_path):
    session = Session(Reply(content=b"<html>error</html>", headers={"Content-Type": "application/octet-stream"}))
    with pytest.raises(ProviderError) as error:
        FalClient("secret", session).download_video({"video": {"url": "https://v3.fal.media/result.mp4"}}, tmp_path / "shot.mp4")
    assert error.value.code == "invalid_media"
    assert not list(tmp_path.iterdir())


def test_original_download_destination_is_not_overwritten(tmp_path):
    original = tmp_path / "shot.mp4"
    original.write_bytes(b"original")
    session = Session()
    with pytest.raises(ProviderError) as error:
        FalClient("secret", session).download_video({"video": {"url": "https://v3.fal.media/result.mp4"}}, original)
    assert error.value.code == "destination_exists"
    assert original.read_bytes() == b"original" and not session.calls
