from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.config import get_settings
from app.story_images import STORY_SCENES, StoryCarouselImageGenerator


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: dict | None = None,
        content: bytes = b"",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (72, 128), (20, 120, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_story_generator_uses_fal_queue_and_downloads_result(tmp_path, monkeypatch):
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (72, 128), (10, 20, 30)).save(reference)
    output = tmp_path / "story.png"
    settings = replace(
        get_settings(),
        image_provider="fal",
        fal_key="fal-secret",
        fal_model="fal-ai/flux-pro/kontext",
        fal_image_aspect_ratio="9:16",
        fal_output_format="png",
        fal_poll_interval_seconds=0.1,
        fal_request_timeout_seconds=5.0,
    )
    posts: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        posts.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse(
            payload={
                "request_id": "req_1",
                "status_url": "https://queue.fal.run/status/req_1",
                "response_url": "https://queue.fal.run/result/req_1",
            }
        )

    def fake_get(url, *, headers=None, timeout):
        if url.endswith("/status/req_1"):
            return FakeResponse(
                payload={
                    "status": "COMPLETED",
                    "response_url": "https://queue.fal.run/result/req_1",
                }
            )
        if url.endswith("/result/req_1"):
            return FakeResponse(
                payload={
                    "images": [
                        {
                            "url": "https://fal.media/output.png",
                            "width": 72,
                            "height": 128,
                            "content_type": "image/png",
                        }
                    ]
                }
            )
        if url == "https://fal.media/output.png":
            return FakeResponse(content=_png_bytes())
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("app.story_images.requests.post", fake_post)
    monkeypatch.setattr("app.story_images.requests.get", fake_get)

    StoryCarouselImageGenerator(settings)._generate_scene(reference, STORY_SCENES[0], output)

    assert output.exists()
    assert Image.open(output).size == (72, 128)
    assert posts[0]["url"] == "https://queue.fal.run/fal-ai/flux-pro/kontext"
    assert posts[0]["headers"]["Authorization"] == "Key fal-secret"
    assert posts[0]["json"]["image_url"].startswith("data:image/jpeg;base64,")
    assert posts[0]["json"]["aspect_ratio"] == "9:16"
    assert posts[0]["json"]["output_format"] == "png"
    assert posts[0]["json"]["num_images"] == 1
    assert "Dropradar" not in posts[0]["json"]["prompt"]


def test_story_generator_requires_fal_key(tmp_path):
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (72, 128), (10, 20, 30)).save(reference)
    settings = replace(get_settings(), image_provider="fal", fal_key="")

    with pytest.raises(RuntimeError, match="FAL_KEY"):
        StoryCarouselImageGenerator(settings)._generate_scene(
            reference,
            STORY_SCENES[0],
            tmp_path / "story.png",
        )
