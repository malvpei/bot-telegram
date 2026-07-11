from __future__ import annotations

import base64
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event, Lock

import pytest
from PIL import Image, ImageDraw

from app.config import get_settings
from app.story_images import (
    STORY_SCENES,
    StoryCarouselImageGenerator,
    StoryImageReview,
)


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


def _save_valid_story_image(path: Path, seed: int = 0) -> None:
    image = Image.new("RGB", (720, 1280), (28 + seed, 54, 76))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 719, 360), fill=(180, 205, 220))
    draw.rectangle((80, 470, 640, 1180), fill=(62, 118 + seed, 92))
    draw.ellipse((230, 560, 490, 820), fill=(228, 176, 128))
    image.save(path, format="PNG")


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


def test_fal_gpt_image_2_uses_multiple_references_and_medium_quality(
    tmp_path,
    monkeypatch,
):
    original = tmp_path / "original.jpg"
    continuity = tmp_path / "continuity.png"
    Image.new("RGB", (720, 1280), (10, 20, 30)).save(original)
    _save_valid_story_image(continuity, 2)
    output = tmp_path / "story.png"
    settings = replace(
        get_settings(),
        image_provider="fal",
        fal_key="fal-secret",
        fal_model="openai/gpt-image-2/edit",
        fal_image_size="864x1536",
        fal_image_quality="medium",
        fal_output_format="png",
        fal_poll_interval_seconds=0.1,
        fal_request_timeout_seconds=5.0,
    )
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            payload={
                "status_url": "https://queue.fal.run/status/gpt_1",
                "response_url": "https://queue.fal.run/result/gpt_1",
            }
        )

    def fake_get(url, *, headers=None, timeout):
        if url.endswith("/status/gpt_1"):
            return FakeResponse(
                payload={
                    "status": "COMPLETED",
                    "response_url": "https://queue.fal.run/result/gpt_1",
                }
            )
        if url.endswith("/result/gpt_1"):
            return FakeResponse(
                payload={"images": [{"url": "https://fal.media/gpt.png"}]}
            )
        if url == "https://fal.media/gpt.png":
            return FakeResponse(content=_png_bytes())
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("app.story_images.requests.post", fake_post)
    monkeypatch.setattr("app.story_images.requests.get", fake_get)

    StoryCarouselImageGenerator(settings)._generate_scene(
        [original, continuity],
        STORY_SCENES[2],
        output,
    )

    payload = captured["json"]
    assert captured["url"] == (
        "https://queue.fal.run/openai/gpt-image-2/edit"
    )
    assert len(payload["image_urls"]) == 2
    assert payload["image_size"] == {"width": 864, "height": 1536}
    assert payload["quality"] == "medium"
    assert payload["output_format"] == "png"
    assert "aspect_ratio" not in payload
    assert "INPUT ORDER" in payload["prompt"]


def test_openai_scene_uses_identity_and_continuity_references(tmp_path, monkeypatch):
    original = tmp_path / "original.jpg"
    continuity = tmp_path / "continuity.png"
    Image.new("RGB", (720, 1280), (10, 20, 30)).save(original)
    _save_valid_story_image(continuity, 2)
    output = tmp_path / "story.png"
    settings = replace(
        get_settings(),
        image_provider="openai",
        openai_api_key="openai-secret",
        openai_image_model="gpt-image-2",
        openai_image_size="864x1536",
        openai_image_quality="medium",
        story_review_enabled=False,
    )
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, data, files, timeout):
        captured.update(
            url=url,
            headers=headers,
            data=data,
            filenames=[item[1][0] for item in files],
            timeout=timeout,
        )
        return FakeResponse(
            payload={
                "data": [
                    {"b64_json": base64.b64encode(_png_bytes()).decode("ascii")}
                ]
            }
        )

    monkeypatch.setattr("app.story_images.requests.post", fake_post)

    StoryCarouselImageGenerator(settings)._generate_scene(
        [original, continuity],
        STORY_SCENES[2],
        output,
    )

    assert output.exists()
    assert captured["url"] == "https://api.openai.com/v1/images/edits"
    assert captured["filenames"] == ["original.jpg", "continuity.png"]
    assert captured["data"]["size"] == "864x1536"
    assert captured["data"]["quality"] == "medium"
    assert "INPUT ORDER" in captured["data"]["prompt"]


def test_semantic_reviewer_uses_strict_json_and_minimum_score(tmp_path, monkeypatch):
    reference = tmp_path / "reference.jpg"
    candidate = tmp_path / "candidate.png"
    _save_valid_story_image(reference, 1)
    _save_valid_story_image(candidate, 2)
    settings = replace(
        get_settings(),
        openai_api_key="review-secret",
        story_review_enabled=True,
        story_review_model="gpt-5.4-nano",
        story_review_min_score=8,
    )
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            payload={
                "choices": [
                    {
                        "message": {
                            "content": json_module.dumps(
                                {
                                    "accepted": True,
                                    "score": 7,
                                    "issues": ["minor identity drift"],
                                    "retry_instruction": "Match the face more closely.",
                                }
                            )
                        }
                    }
                ]
            }
        )

    # Keep the request body's `json` name while retaining access to the module.
    json_module = json
    monkeypatch.setattr("app.story_images.requests.post", fake_post)

    review = StoryCarouselImageGenerator(settings)._review_generated_scene(
        reference,
        reference,
        candidate,
        STORY_SCENES[0],
    )

    assert review is not None
    assert review.accepted is False
    assert review.score == 7
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["response_format"]["type"] == "json_schema"


def test_semantic_reviewer_falls_back_to_existing_fal_key(tmp_path, monkeypatch):
    reference = tmp_path / "reference.jpg"
    candidate = tmp_path / "candidate.png"
    _save_valid_story_image(reference, 1)
    _save_valid_story_image(candidate, 2)
    settings = replace(
        get_settings(),
        openai_api_key="",
        fal_key="fal-review-key",
        story_review_enabled=True,
        story_review_fal_model="google/gemini-2.5-flash",
        story_review_min_score=8,
        fal_poll_interval_seconds=0.1,
        fal_request_timeout_seconds=5.0,
    )
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            payload={
                "status_url": "https://queue.fal.run/status/review_1",
                "response_url": "https://queue.fal.run/result/review_1",
            }
        )

    def fake_get(url, *, headers=None, timeout):
        if url.endswith("/status/review_1"):
            return FakeResponse(
                payload={
                    "status": "COMPLETED",
                    "response_url": "https://queue.fal.run/result/review_1",
                }
            )
        if url.endswith("/result/review_1"):
            return FakeResponse(
                payload={
                    "output": (
                        "```json\n"
                        '{"accepted":true,"score":9,"issues":[], '
                        '"retry_instruction":""}\n'
                        "```"
                    )
                }
            )
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("app.story_images.requests.post", fake_post)
    monkeypatch.setattr("app.story_images.requests.get", fake_get)

    review = StoryCarouselImageGenerator(settings)._review_generated_scene(
        reference,
        reference,
        candidate,
        STORY_SCENES[0],
    )

    assert review == StoryImageReview(True, 9, (), "")
    assert captured["url"] == (
        "https://queue.fal.run/openrouter/router/vision"
    )
    assert captured["headers"]["Authorization"] == "Key fal-review-key"
    assert captured["json"]["model"] == "google/gemini-2.5-flash"
    assert len(captured["json"]["image_urls"]) == 2


def test_story_scenes_are_generated_with_bounded_parallelism(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        image_provider="fal",
        fal_model="fal-ai/flux-pro/kontext",
        story_image_workers=3,
        story_review_enabled=False,
    )
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (90, 120), (20, 40, 60)).save(reference)
    branch_barrier = Barrier(2, timeout=3)
    counter_lock = Lock()
    active = 0
    max_active = 0
    calls: list[tuple[object, list[str]]] = []

    def fake_generate_with_gate(original, inputs, scene, output_path):
        nonlocal active, max_active
        calls.append((scene.role, [Path(path).name for path in inputs]))
        if scene is STORY_SCENES[0]:
            _save_valid_story_image(output_path, 1)
            return
        with counter_lock:
            active += 1
            max_active = max(max_active, active)
        if scene in {STORY_SCENES[1], STORY_SCENES[5]}:
            branch_barrier.wait()
        _save_valid_story_image(output_path, STORY_SCENES.index(scene) + 1)
        with counter_lock:
            active -= 1

    monkeypatch.setattr(
        generator,
        "_generate_scene_with_quality_gate",
        fake_generate_with_gate,
    )

    slides = generator.generate_slides(reference, tmp_path / "job")

    assert max_active == 2
    assert [slide.source_id for slide in slides] == [
        f"story_ai:{index}:{scene.role.value}"
        for index, scene in enumerate(STORY_SCENES, start=1)
    ]
    inputs_by_role = {role: inputs for role, inputs in calls}
    assert inputs_by_role[STORY_SCENES[0].role] == ["reference.jpg"]
    assert inputs_by_role[STORY_SCENES[1].role] == [
        "story_01_story_mcdonald.png"
    ]
    assert inputs_by_role[STORY_SCENES[2].role] == [
        "story_02_story_building_store.png"
    ]
    assert inputs_by_role[STORY_SCENES[5].role] == ["reference.jpg"]


def test_multi_reference_story_reuses_one_bedroom_anchor(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        image_provider="fal",
        fal_model="openai/gpt-image-2/edit",
        story_image_workers=2,
        story_review_enabled=False,
    )
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (720, 1280), (20, 40, 60)).save(reference)
    calls: list[tuple[object, list[str]]] = []
    calls_lock = Lock()

    def fake_generate_with_gate(original, inputs, scene, output_path):
        with calls_lock:
            calls.append((scene.role, [Path(path).name for path in inputs]))
        _save_valid_story_image(output_path, STORY_SCENES.index(scene) + 1)

    monkeypatch.setattr(
        generator,
        "_generate_scene_with_quality_gate",
        fake_generate_with_gate,
    )

    generator.generate_slides(reference, tmp_path / "job")

    inputs_by_role = {role: inputs for role, inputs in calls}
    assert inputs_by_role[STORY_SCENES[0].role] == ["reference.jpg"]
    assert inputs_by_role[STORY_SCENES[1].role] == [
        "reference.jpg",
        "story_01_story_mcdonald.png",
    ]
    for scene in STORY_SCENES[2:5]:
        assert inputs_by_role[scene.role] == [
            "reference.jpg",
            "story_02_story_building_store.png",
        ]
    assert inputs_by_role[STORY_SCENES[5].role] == [
        "reference.jpg",
        "story_01_story_mcdonald.png",
    ]


def test_story_generator_waits_for_started_requests_after_an_error(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        image_provider="fal",
        fal_model="fal-ai/flux-pro/kontext",
        story_image_workers=2,
        story_review_enabled=False,
    )
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (90, 120), (20, 40, 60)).save(reference)
    second_started = Event()
    second_finished = Event()

    def fake_generate_with_gate(original, inputs, scene, output_path):
        if scene is STORY_SCENES[0]:
            _save_valid_story_image(output_path, 1)
            return
        if scene is STORY_SCENES[1]:
            assert second_started.wait(timeout=1)
            raise RuntimeError("provider failed")
        if scene is STORY_SCENES[5]:
            second_started.set()
            Event().wait(0.1)
            _save_valid_story_image(output_path, 6)
            second_finished.set()

    monkeypatch.setattr(
        generator,
        "_generate_scene_with_quality_gate",
        fake_generate_with_gate,
    )

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
        assert "one single full-page vertical 9:16 illustration" in prompt
        assert "simple flat 2D social-media cartoon illustration" in prompt
        assert "not anime, not manga, not semi-realistic" in prompt
        assert "Do not create panels" in prompt
        assert "no horizontal separators" in prompt
        assert "Do not add any readable text" in prompt
        assert "Dropradar" not in prompt
    assert "fast-food restaurant kitchen" in prompts[STORY_SCENES[0].role]
    assert "No luxury shirt" in prompts[STORY_SCENES[0].role]
    assert "Bedroom base" in prompts[STORY_SCENES[1].role]
    assert "hinge is one straight horizontal line" in prompts[STORY_SCENES[1].role]
    assert "must not be twisted" in prompts[STORY_SCENES[1].role]
    assert "Bedroom continuity" in prompts[STORY_SCENES[2].role]
    assert "preserve the previous bedroom, camera and desk exactly" in prompts[
        STORY_SCENES[2].role
    ]
    assert "external compositor" in prompts[STORY_SCENES[4].role]
    assert "Bedroom continuity" not in prompts[STORY_SCENES[0].role]
    assert "Bedroom continuity" not in prompts[STORY_SCENES[1].role]
    assert "Bedroom continuity" not in prompts[STORY_SCENES[5].role]
    assert "Do not show a bedroom" in prompts[STORY_SCENES[5].role]


def test_quality_gate_retries_only_the_rejected_scene(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        story_image_max_attempts=2,
        story_review_enabled=True,
        openai_api_key="review-key",
    )
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (720, 1280), (30, 60, 90)).save(reference)
    output = tmp_path / "accepted.png"
    feedback: list[str] = []
    review_calls = 0

    def fake_generate(inputs, scene, attempt_path, *, retry_feedback=""):
        feedback.append(retry_feedback)
        _save_valid_story_image(attempt_path, len(feedback))

    def fake_review(*args, **kwargs):
        nonlocal review_calls
        review_calls += 1
        if review_calls == 1:
            return StoryImageReview(
                accepted=False,
                score=5,
                issues=("the laptop is folded backwards",),
                retry_instruction="Fix the laptop geometry and keep one scene.",
            )
        return StoryImageReview(True, 9, (), "")

    monkeypatch.setattr(generator, "_generate_scene", fake_generate)
    monkeypatch.setattr(generator, "_review_generated_scene", fake_review)

    generator._generate_scene_with_quality_gate(
        reference,
        [reference],
        STORY_SCENES[1],
        output,
    )

    assert output.exists()
    assert review_calls == 2
    assert feedback == ["", "Fix the laptop geometry and keep one scene."]


def test_quality_gate_refuses_to_deliver_repeated_bad_scene(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        story_image_max_attempts=2,
        story_review_enabled=True,
        openai_api_key="review-key",
    )
    generator = StoryCarouselImageGenerator(settings)
    reference = tmp_path / "reference.jpg"
    Image.new("RGB", (720, 1280), (30, 60, 90)).save(reference)
    output = tmp_path / "rejected.png"

    def fake_generate(inputs, scene, attempt_path, *, retry_feedback=""):
        _save_valid_story_image(attempt_path, 1)

    monkeypatch.setattr(generator, "_generate_scene", fake_generate)
    monkeypatch.setattr(
        generator,
        "_review_generated_scene",
        lambda *args, **kwargs: StoryImageReview(
            False,
            4,
            ("two protagonists and a split screen",),
            "Use one protagonist in one full-page scene.",
        ),
    )

    with pytest.raises(RuntimeError, match="no alcanzo la calidad minima"):
        generator._generate_scene_with_quality_gate(
            reference,
            [reference],
            STORY_SCENES[0],
            output,
        )

    assert not output.exists()


def test_local_quality_gate_rejects_wrong_aspect_ratio(tmp_path):
    generator = StoryCarouselImageGenerator(get_settings())
    landscape = tmp_path / "landscape.png"
    Image.new("RGB", (1280, 800), (20, 80, 120)).save(landscape)

    issue = generator._validate_generated_image(landscape)

    assert issue is not None
    assert "formato no vertical" in issue
