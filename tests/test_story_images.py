from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event, Lock

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
    assert posts[0]["json"]["enhance_prompt"] is False
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


def test_story_scenes_are_generated_with_bounded_parallelism(tmp_path, monkeypatch):
    settings = replace(get_settings(), story_image_workers=3)
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (90, 120), (20, 40, 60)).save(reference)
    barrier = Barrier(3, timeout=3)
    counter_lock = Lock()
    active = 0
    max_active = 0

    def fake_generate(reference_path, scene, output_path):
        nonlocal active, max_active
        index = int(output_path.name.split("_")[1])
        with counter_lock:
            active += 1
            max_active = max(max_active, active)
        if index <= 3:
            barrier.wait()
        Image.new("RGB", (90, 120), (index * 20, 40, 60)).save(output_path)
        with counter_lock:
            active -= 1

    monkeypatch.setattr(generator, "_generate_scene", fake_generate)

    slides = generator.generate_slides(reference, tmp_path / "job")

    assert max_active == 3
    assert [slide.source_id for slide in slides] == [
        f"story_ai:{index}:{scene.role.value}"
        for index, scene in enumerate(STORY_SCENES, start=1)
    ]


def test_story_generator_waits_for_started_requests_after_an_error(tmp_path, monkeypatch):
    settings = replace(get_settings(), story_image_workers=2)
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (90, 120), (20, 40, 60)).save(reference)
    second_started = Event()
    second_finished = Event()

    def fake_generate(reference_path, scene, output_path):
        index = int(output_path.name.split("_")[1])
        if index == 1:
            assert second_started.wait(timeout=1)
            raise RuntimeError("provider failed")
        if index == 2:
            second_started.set()
            Event().wait(0.1)
            second_finished.set()

    monkeypatch.setattr(generator, "_generate_scene", fake_generate)

    with pytest.raises(RuntimeError, match="provider failed"):
        generator.generate_slides(reference, tmp_path / "job")

    assert second_finished.is_set()


def test_story_prompts_lock_single_scene_style_and_bedroom_continuity():
    settings = get_settings()
    generator = StoryCarouselImageGenerator(settings)
    prompts = {
        scene.role: generator._build_prompt(scene)
        for scene in STORY_SCENES
    }

    for prompt in prompts.values():
        assert "one single full-page illustration" in prompt
        assert "simple flat 2D social-media cartoon panel" in prompt
        assert "not anime, not manga, not semi-realistic" in prompt
        assert "Do not create panels" in prompt
        assert "no horizontal separators" in prompt
    assert "McDonald's-style work clothes" in prompts[STORY_SCENES[0].role]
    assert "no sunglasses, eyes visible" in prompts[STORY_SCENES[0].role]
    assert "Use the laptop composition rule" in prompts[STORY_SCENES[1].role]
    assert "hinge is one straight horizontal line" in prompts[STORY_SCENES[1].role]
    assert "must not be twisted" in prompts[STORY_SCENES[1].role]
    assert "same bedroom and same desk" in prompts[STORY_SCENES[2].role]
    assert "normal size, seated in the chair" in prompts[STORY_SCENES[2].role]
    assert "word Dropradar large in green and black" in prompts[STORY_SCENES[4].role]
    assert "Bedroom continuity" not in prompts[STORY_SCENES[0].role]
    assert "Bedroom continuity" not in prompts[STORY_SCENES[5].role]
    assert "Do not show a bedroom" in prompts[STORY_SCENES[5].role]
