from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

import requests
from PIL import Image, ImageOps, ImageStat

from app.config import Settings
from app.models import MediaCandidate, SlideRole


LOGGER = logging.getLogger(__name__)
OPENAI_IMAGES_EDIT_URL = "https://api.openai.com/v1/images/edits"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
FAL_QUEUE_BASE_URL = "https://queue.fal.run"
FAL_VISION_REVIEW_MODEL = "openrouter/router/vision"
STORY_IMAGE_SOURCE_ACCOUNT = "ai_story"
MIN_STORY_IMAGE_WIDTH = 512
MIN_STORY_IMAGE_HEIGHT = 768

STORY_STYLE = (
    "Style target: simple flat 2D social-media cartoon illustration like a clean "
    "Spanish TikTok story, not anime, not manga, not semi-realistic, not 3D and "
    "not photorealistic. Use thick smooth black outlines, flat color fills, very "
    "limited cel shading, low-detail simplified faces with simple visible eyes, "
    "rounded youthful features, minimal texture, clean geometry and a limited "
    "muted palette. Avoid realistic facial anatomy, painted skin, photographic "
    "lighting, glossy rendering, complex shadows, muscular heroic proportions "
    "and detailed cinematic backgrounds. Keep this exact drawing style across "
    "the complete story."
)
NO_OVERLAY_TEXT_DIRECTIVE = (
    "Do not add any readable text, letters, numbers, captions, speech bubbles, "
    "subtitles, labels, brand names, watermarks or social-media UI anywhere in "
    "the illustration. Do not add unrelated company logos to clothes or devices. "
    "Use simple abstract interface shapes instead. An external "
    "compositor will add all exact wording later. Keep the upper 32 percent calm "
    "and uncluttered for that external caption, without putting the protagonist's "
    "face, hands or important objects there."
)
SINGLE_SCENE_DIRECTIVE = (
    "HARD RULE: the whole image is one single full-page vertical 9:16 illustration "
    "from one camera shot. Do not create a comic strip. Do not create panels. Do "
    "not use split-screen, stacked frames, horizontal dividers, repeated rooms, "
    "repeated characters, before/after layout, montage, collage or multiple "
    "moments. Show only one foreground protagonist. Show a laptop only in scenes "
    "that explicitly request one; all other scenes must contain no laptop."
)
BEDROOM_BASE_DIRECTIVE = (
    "Bedroom base: establish one small believable bedroom with a wooden desk, "
    "chair, desk lamp, small book shelf, sports-car poster without readable text, "
    "plain light-gray walls, piggy bank without a label, notebook and pen. Keep "
    "the room simple and make these positions the canonical layout for later scenes."
)
BEDROOM_CONTINUITY_DIRECTIVE = (
    "Bedroom continuity: preserve the exact same small bedroom, camera side, "
    "wooden desk, chair, desk lamp, small book shelf, sports-car poster without "
    "readable text, plain light-gray walls, piggy bank without a label, notebook, "
    "pen and object positions from the previous bedroom scene. This is the same "
    "real room at a later moment, not a new interpretation. The protagonist is "
    "normal human size, seated on the chair at the desk, never standing on the "
    "desk, never miniature and never separated from the laptop."
)
LAPTOP_COMPOSITION_DIRECTIVE = (
    "Laptop composition for desk scenes: keep a believable side or three-quarter "
    "desk view. The laptop sits on the desk in the left foreground, open at a "
    "normal 100 to 110 degree angle. Its keyboard base is flat on the desk, its "
    "hinge is one straight horizontal line and its screen is one upright rectangle "
    "with parallel edges, facing both viewer and protagonist. The protagonist sits "
    "to the right, looking at the screen, with hands aligned to the keyboard or "
    "trackpad. The laptop must not be twisted, reversed, floating, detached, folded "
    "the wrong way or standing vertically on its keyboard edge."
)
REFERENCE_IDENTITY_DIRECTIVE = (
    "Identity and continuity rule: preserve the same young male protagonist, hair "
    "color, face shape, build, age and overall recognizable look from the input "
    "reference. When two inputs are supplied, input 1 is the original identity "
    "reference and input 2 is the continuity/style reference from this same story. "
    "Keep the identity from input 1 and the drawing style, room geometry, clothing "
    "design and camera logic from input 2. No sunglasses indoors; eyes must be "
    "visible. Do not add a second foreground version of him."
)


@dataclass(frozen=True)
class StoryScene:
    role: SlideRole
    prompt: str
    review_criteria: str


@dataclass(frozen=True)
class StoryImageReview:
    accepted: bool
    score: int
    issues: tuple[str, ...]
    retry_instruction: str


STORY_SCENES: tuple[StoryScene, ...] = (
    StoryScene(
        role=SlideRole.STORY_MCDONALD,
        prompt=(
            "Scene 1: transform the reference person into the protagonist working "
            "sadly in one busy fast-food restaurant kitchen. He wears a black "
            "short-sleeve polo uniform with a tiny abstract yellow arch icon, red "
            "visor, name-tag shape with no letters and black or red apron. No luxury "
            "shirt, car clothing or sunglasses. He stands centered in the lower "
            "half holding one finished burger with both hands, tired expression. "
            "Show industrial fryers, grill, fries and burgers; coworkers may appear "
            "only as small indistinct background silhouettes. Do not show a laptop, "
            "desk, bedroom or car in this restaurant scene."
        ),
        review_criteria=(
            "One tired fast-food worker in a restaurant kitchen, holding one burger "
            "with believable hands, wearing the requested black/red uniform."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_BUILDING_STORE,
        prompt=(
            "Scene 2: move the same protagonist and exact cartoon style into the "
            "small bedroom described below. He sits on the chair at the wooden desk, "
            "leaning forward and looking directly at the laptop, focused and "
            "determined while building an online store. Replace every part of the "
            "restaurant uniform with a plain dark charcoal crew-neck t-shirt and "
            "dark casual trousers: no polo collar, no apron, no visor and no yellow "
            "arch icon. On the screen use only clean "
            "abstract product-card rectangles, a small green progress chart shape "
            "and simple order widgets with no readable characters. Include notebook, "
            "desk lamp, piggy bank and sports-car poster."
        ),
        review_criteria=(
            "Same recognizable protagonist in one small bedroom, naturally seated "
            "at a physically correct laptop, focused on an online-store dashboard."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_FIRST_FAILURE,
        prompt=(
            "Scene 3: preserve the previous bedroom, camera and desk exactly. Change "
            "only the story moment: the protagonist is sad and discouraged because "
            "he has no sales, with slumped shoulders, visibly disappointed eyes and "
            "a downturned mouth, seated and looking at the same laptop. On its screen "
            "use a minimal ecommerce dashboard made of blank cards and one simple "
            "red downward line ending at an empty result, with no readable text or "
            "numbers. Keep both his sad face and the screen naturally visible."
        ),
        review_criteria=(
            "Same room and protagonist as the prior bedroom scene; clear sadness, "
            "correct seated pose, one valid laptop and an obviously failing dashboard."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_DEEP_FAILURE,
        prompt=(
            "Scene 4: preserve the same bedroom, desk, camera and protagonist, now "
            "several months later at night. He sits using the laptop, almost crying, "
            "hunched forward with one clearly visible tear, one hand covering part "
            "of his face and the other near the keyboard or trackpad. Use "
            "dark blue room lighting, laptop glow and a slightly messier desk. The "
            "screen shows tidy blank analytics cards and a red downward chart with "
            "no readable letters or numbers. One scene only."
        ),
        review_criteria=(
            "Same bedroom continuity at night; one distressed protagonist with a "
            "believable hand-to-face pose and a geometrically correct failing laptop."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_DROPRADAR,
        prompt=(
            "Scene 5: preserve the same bedroom, desk, camera and protagonist for the "
            "turning point. He sits concentrated and serious, looking at the laptop. "
            "His posture is upright and hopeful, visibly different from the prior "
            "failure scene. "
            "The screen shows a polished white-and-green product-research dashboard "
            "with blank product cards, clean data-row shapes, metric blocks, a small "
            "radar-like green icon and one green rising chart. No brand name or other "
            "readable text; the external compositor will add the exact brand name."
        ),
        review_criteria=(
            "Same bedroom continuity; focused protagonist, valid laptop, and a clean "
            "green product-research dashboard that clearly signals improvement."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_SUCCESS_COMIC,
        prompt=(
            "Scene 6: transform the original reference photo into the exact same flat "
            "cartoon style used by this story. Preserve the photo composition closely: "
            "one outdoor road scene, the same young man beside one black Porsche 911 "
            "GT3-style sports car, mountains, trees and dramatic cloudy sky. Do not "
            "show a bedroom, laptop, desk, restaurant, lamp or poster. The protagonist "
            "is happy and proud. No text inside the image."
        ),
        review_criteria=(
            "One proud recognizable protagonist beside one well-formed black sports "
            "car outdoors, matching the reference composition and the story's 2D style."
        ),
    ),
)


class StoryCarouselImageGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_slides(
        self,
        reference_image_path: Path,
        job_dir: Path,
    ) -> list[MediaCandidate]:
        scenes_dir = job_dir / "story_ai_sources"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        scene_outputs = [
            (
                index,
                scene,
                scenes_dir / f"story_{index:02d}_{scene.role.value}.png",
            )
            for index, scene in enumerate(STORY_SCENES, start=1)
        ]

        # The first generated panel becomes the shared cartoon identity/style anchor.
        _first_index, first_scene, first_output = scene_outputs[0]
        self._generate_scene_with_quality_gate(
            reference_image_path,
            [reference_image_path],
            first_scene,
            first_output,
        )

        if self._supports_multiple_reference_images():
            # Establish the bedroom once. Later bedroom moments all reference
            # this approved anchor so the room stays stable while the action and
            # emotion can still change substantially.
            _index, bedroom_scene, bedroom_output = scene_outputs[1]
            self._generate_scene_with_quality_gate(
                reference_image_path,
                [reference_image_path, first_output],
                bedroom_scene,
                bedroom_output,
            )
            tasks = [
                ([reference_image_path, bedroom_output], scene, output_path)
                for _index, scene, output_path in scene_outputs[2:5]
            ]
            _index, success_scene, success_output = scene_outputs[5]
            tasks.append(
                (
                    [reference_image_path, first_output],
                    success_scene,
                    success_output,
                )
            )
            self._run_scene_tasks(reference_image_path, tasks)
        else:
            # Legacy single-reference models can only preserve continuity by
            # editing the previous panel. Keep this path as a compatibility fallback.
            def generate_bedroom_story() -> None:
                continuity_path = first_output
                for _index, scene, output_path in scene_outputs[1:5]:
                    inputs = self._generation_inputs(
                        reference_image_path,
                        continuity_path,
                    )
                    self._generate_scene_with_quality_gate(
                        reference_image_path,
                        inputs,
                        scene,
                        output_path,
                    )
                    continuity_path = output_path

            def generate_success_scene() -> None:
                _index, scene, output_path = scene_outputs[5]
                self._generate_scene_with_quality_gate(
                    reference_image_path,
                    [reference_image_path],
                    scene,
                    output_path,
                )

            workers = max(1, min(2, int(self.settings.story_image_workers or 1)))
            if workers == 1:
                generate_bedroom_story()
                generate_success_scene()
            else:
                with ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix="story-image",
                ) as executor:
                    futures: list[Future[None]] = [
                        executor.submit(generate_bedroom_story),
                        executor.submit(generate_success_scene),
                    ]
                    self._wait_for_futures(futures)

        generated: list[MediaCandidate] = []
        for index, scene, output_path in scene_outputs:
            generated.append(
                self._candidate_for_path(
                    output_path,
                    source_id=f"story_ai:{index}:{scene.role.value}",
                    caption=scene.prompt,
                )
            )
        return generated

    def _generation_inputs(
        self,
        original_reference: Path,
        continuity_reference: Path,
    ) -> list[Path]:
        if self._supports_multiple_reference_images():
            return [original_reference, continuity_reference]
        return [continuity_reference]

    def _run_scene_tasks(
        self,
        original_reference: Path,
        tasks: Sequence[tuple[list[Path], StoryScene, Path]],
    ) -> None:
        workers = max(
            1,
            min(len(tasks), int(self.settings.story_image_workers or 1)),
        )
        if workers == 1:
            for inputs, scene, output_path in tasks:
                self._generate_scene_with_quality_gate(
                    original_reference,
                    inputs,
                    scene,
                    output_path,
                )
            return

        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="story-image",
        ) as executor:
            futures = [
                executor.submit(
                    self._generate_scene_with_quality_gate,
                    original_reference,
                    inputs,
                    scene,
                    output_path,
                )
                for inputs, scene, output_path in tasks
            ]
            self._wait_for_futures(futures)

    @staticmethod
    def _wait_for_futures(futures: Sequence[Future[None]]) -> None:
        first_error: Exception | None = None
        for future in futures:
            try:
                future.result()
            except Exception as error:  # wait for every already-started request
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def _supports_multiple_reference_images(self) -> bool:
        provider = self.settings.image_provider.lower()
        if provider == "openai":
            return True
        if provider != "fal":
            return False
        model = self.settings.fal_model.strip("/").lower()
        return model in {
            "openai/gpt-image-2/edit",
            "fal-ai/qwen-image-2/edit",
            "fal-ai/qwen-image-2/pro/edit",
        }

    def _is_fal_gpt_image_2(self) -> bool:
        return (
            self.settings.image_provider.lower() == "fal"
            and self.settings.fal_model.strip("/").lower()
            == "openai/gpt-image-2/edit"
        )

    def _generate_scene_with_quality_gate(
        self,
        original_reference: Path,
        generation_inputs: Sequence[Path],
        scene: StoryScene,
        output_path: Path,
    ) -> None:
        max_attempts = max(1, min(4, int(self.settings.story_image_max_attempts)))
        retry_feedback = ""
        last_issue = "la imagen no supero el control de calidad"

        for attempt in range(1, max_attempts + 1):
            attempt_path = output_path.with_name(
                f"{output_path.stem}.attempt_{attempt}{output_path.suffix}"
            )
            try:
                self._generate_scene(
                    list(generation_inputs),
                    scene,
                    attempt_path,
                    retry_feedback=retry_feedback,
                )
                local_issue = self._validate_generated_image(attempt_path)
                if local_issue:
                    last_issue = local_issue
                    retry_feedback = (
                        "Return a valid, detailed 9:16 portrait image. Fix this "
                        f"technical defect: {local_issue}"
                    )
                    review = None
                else:
                    review = self._review_generated_scene(
                        original_reference,
                        generation_inputs[-1],
                        attempt_path,
                        scene,
                    )
                    if review is None or review.accepted:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(attempt_path, output_path)
                        return
                    issue_text = "; ".join(review.issues).strip()
                    last_issue = issue_text or (
                        f"puntuacion visual {review.score}/10, minimo "
                        f"{self.settings.story_review_min_score}/10"
                    )
                    retry_feedback = review.retry_instruction.strip() or last_issue
            except Exception as error:
                last_issue = str(error)
                if attempt >= max_attempts:
                    raise
                retry_feedback = (
                    "The previous request failed or returned an unusable image. "
                    "Follow every constraint literally and return one clean portrait "
                    f"illustration. Provider feedback: {last_issue}"
                )
            finally:
                if attempt_path.exists():
                    try:
                        attempt_path.unlink()
                    except OSError:
                        pass

            if attempt < max_attempts:
                LOGGER.warning(
                    "Story scene %s rejected on attempt %d/%d: %s",
                    scene.role.value,
                    attempt,
                    max_attempts,
                    last_issue,
                )

        raise RuntimeError(
            f"La escena {scene.role.value} no alcanzo la calidad minima tras "
            f"{max_attempts} intentos: {last_issue}"
        )

    def _generate_scene(
        self,
        reference_image_paths: Path | Sequence[Path],
        scene: StoryScene,
        output_path: Path,
        *,
        retry_feedback: str = "",
    ) -> None:
        paths = self._normalise_reference_paths(reference_image_paths)
        provider = self.settings.image_provider.lower()
        if provider == "fal":
            self._generate_scene_fal(
                paths,
                scene,
                output_path,
                retry_feedback=retry_feedback,
            )
            return
        if provider == "openai":
            self._generate_scene_openai(
                paths,
                scene,
                output_path,
                retry_feedback=retry_feedback,
            )
            return
        raise RuntimeError(
            f"IMAGE_PROVIDER={self.settings.image_provider!r} no esta soportado. "
            "Usa 'fal' u 'openai'."
        )

    @staticmethod
    def _normalise_reference_paths(
        reference_image_paths: Path | Sequence[Path],
    ) -> list[Path]:
        if isinstance(reference_image_paths, Path):
            paths = [reference_image_paths]
        else:
            paths = [Path(path) for path in reference_image_paths]
        if not paths:
            raise ValueError("La escena necesita al menos una imagen de referencia.")
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"No encuentro la referencia visual: {path}")
        return paths

    def _generate_scene_fal(
        self,
        reference_image_paths: Sequence[Path],
        scene: StoryScene,
        output_path: Path,
        *,
        retry_feedback: str = "",
    ) -> None:
        if not self.settings.fal_key:
            raise RuntimeError(
                "Falta FAL_KEY. Configuralo para usar el carrusel IA tipo 4 con fal.ai."
            )

        prompt = self._build_prompt(
            scene,
            retry_feedback=retry_feedback,
            input_count=len(reference_image_paths),
        )
        if self._is_fal_gpt_image_2():
            submit_payload = {
                "prompt": prompt,
                "image_urls": [
                    self._image_data_uri(path) for path in reference_image_paths
                ],
                "image_size": self._fal_image_size(),
                "quality": self.settings.fal_image_quality,
                "num_images": 1,
                "output_format": self.settings.fal_output_format,
                "sync_mode": False,
            }
        elif self._supports_multiple_reference_images():
            submit_payload = {
                "prompt": prompt,
                "image_urls": [
                    self._image_data_uri(path) for path in reference_image_paths
                ],
                "num_images": 1,
                "output_format": self.settings.fal_output_format,
                "enhance_prompt": False,
            }
        else:
            submit_payload = {
                "prompt": prompt,
                "image_url": self._image_data_uri(reference_image_paths[-1]),
                "num_images": 1,
                "aspect_ratio": self.settings.fal_image_aspect_ratio,
                "output_format": self.settings.fal_output_format,
                "guidance_scale": self.settings.fal_guidance_scale,
                "safety_tolerance": self.settings.fal_safety_tolerance,
                "enhance_prompt": False,
            }
        submit_url = f"{FAL_QUEUE_BASE_URL}/{self.settings.fal_model.strip('/')}"
        response = requests.post(
            submit_url,
            headers=self._fal_headers(),
            json=submit_payload,
            timeout=self.settings.fal_request_timeout_seconds,
        )
        payload = self._json_response(response, "fal.ai")
        if response.status_code >= 400:
            raise RuntimeError(
                f"fal.ai fallo ({response.status_code}): "
                f"{self._response_message(payload, response)}"
            )

        result_payload = self._wait_for_fal_result(payload)
        images = result_payload.get("images") if isinstance(result_payload, dict) else None
        image_url = (
            images[0].get("url")
            if images and isinstance(images[0], dict)
            else None
        )
        if not image_url:
            raise RuntimeError("fal.ai no devolvio una URL de imagen para la escena.")

        image_response = requests.get(
            image_url,
            timeout=self.settings.fal_request_timeout_seconds,
        )
        if image_response.status_code >= 400:
            raise RuntimeError(
                f"No pude descargar la imagen de fal.ai ({image_response.status_code}): "
                f"{image_response.text[:400]}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_response.content)

    def _fal_image_size(self) -> dict[str, int] | str:
        raw_size = self.settings.fal_image_size.strip().lower()
        try:
            width_text, height_text = raw_size.split("x", maxsplit=1)
            width = int(width_text)
            height = int(height_text)
        except (TypeError, ValueError):
            return "auto"
        if width <= 0 or height <= 0:
            return "auto"
        return {"width": width, "height": height}

    def _generate_scene_openai(
        self,
        reference_image_paths: Sequence[Path],
        scene: StoryScene,
        output_path: Path,
        *,
        retry_feedback: str = "",
    ) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError(
                "Falta OPENAI_API_KEY. Configuralo para usar el carrusel IA tipo 4."
            )

        with ExitStack() as stack:
            files = []
            for path in reference_image_paths:
                mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
                image_handle = stack.enter_context(path.open("rb"))
                files.append(("image[]", (path.name, image_handle, mime_type)))
            data = {
                "model": self.settings.openai_image_model,
                "prompt": self._build_prompt(
                    scene,
                    retry_feedback=retry_feedback,
                    input_count=len(reference_image_paths),
                ),
                "size": self.settings.openai_image_size,
                "quality": self.settings.openai_image_quality,
                "output_format": "png",
                "background": "opaque",
                "n": "1",
            }
            response = requests.post(
                OPENAI_IMAGES_EDIT_URL,
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                data=data,
                files=files,
                timeout=self.settings.openai_request_timeout_seconds,
            )

        payload = self._json_response(response, "OpenAI Images")
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI Images fallo ({response.status_code}): "
                f"{self._response_message(payload, response)}"
            )

        image_base64 = (
            payload.get("data", [{}])[0].get("b64_json")
            if isinstance(payload, dict)
            else None
        )
        if not image_base64:
            raise RuntimeError("OpenAI Images no devolvio b64_json para la escena.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            output_path.write_bytes(base64.b64decode(image_base64, validate=True))
        except (ValueError, TypeError) as error:
            raise RuntimeError("OpenAI Images devolvio una imagen base64 invalida.") from error

    def _validate_generated_image(self, image_path: Path) -> str | None:
        try:
            with Image.open(image_path) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (OSError, ValueError) as error:
            return f"archivo de imagen invalido: {error}"

        width, height = image.size
        if width < MIN_STORY_IMAGE_WIDTH or height < MIN_STORY_IMAGE_HEIGHT:
            return (
                f"resolucion insuficiente ({width}x{height}); minimo "
                f"{MIN_STORY_IMAGE_WIDTH}x{MIN_STORY_IMAGE_HEIGHT}"
            )
        portrait_ratio = height / max(1, width)
        if not 1.45 <= portrait_ratio <= 1.95:
            return f"formato no vertical 9:16 ({width}x{height})"

        grayscale = image.convert("L").resize((128, 128), Image.Resampling.BILINEAR)
        extrema = grayscale.getextrema()
        contrast = float(ImageStat.Stat(grayscale).stddev[0])
        if extrema[1] - extrema[0] < 18 or contrast < 7.0:
            return "imagen vacia, casi uniforme o sin contraste suficiente"

        # Normalize every provider response to a real PNG. Some providers can
        # return JPEG bytes even when the requested filename ends in .png.
        image.save(image_path, format="PNG", optimize=True)
        return None

    def _review_generated_scene(
        self,
        original_reference: Path,
        continuity_reference: Path,
        candidate_path: Path,
        scene: StoryScene,
    ) -> StoryImageReview | None:
        if not self.settings.story_review_enabled:
            return None
        if self.settings.openai_api_key:
            return self._review_generated_scene_openai(
                original_reference,
                continuity_reference,
                candidate_path,
                scene,
            )
        if self.settings.fal_key:
            return self._review_generated_scene_fal(
                original_reference,
                continuity_reference,
                candidate_path,
                scene,
            )
        LOGGER.info(
            "Story semantic review skipped for %s: no OpenAI or fal.ai key",
            scene.role.value,
        )
        return None

    def _review_generated_scene_openai(
        self,
        original_reference: Path,
        continuity_reference: Path,
        candidate_path: Path,
        scene: StoryScene,
    ) -> StoryImageReview | None:
        image_paths = self._review_image_paths(
            original_reference,
            continuity_reference,
            candidate_path,
        )
        content: list[dict[str, Any]] = [
            {"type": "text", "text": self._review_prompt(scene)}
        ]
        for index, path in enumerate(image_paths):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._review_image_data_uri(path),
                        "detail": "high" if index == len(image_paths) - 1 else "low",
                    },
                }
            )

        schema = self._review_json_schema()
        try:
            response = requests.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.story_review_model,
                    "messages": [{"role": "user", "content": content}],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "story_image_review",
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    "max_completion_tokens": 500,
                },
                timeout=self.settings.openai_request_timeout_seconds,
            )
            payload = self._json_response(response, "revisor visual OpenAI")
            if response.status_code >= 400:
                raise RuntimeError(
                    f"revisor visual OpenAI fallo ({response.status_code}): "
                    f"{self._response_message(payload, response)}"
                )
            raw_content = payload.get("choices", [{}])[0].get("message", {}).get("content")
            return self._parse_story_review(raw_content)
        except (
            IndexError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            requests.RequestException,
        ) as error:
            LOGGER.warning(
                "Story semantic review unavailable for %s via OpenAI: %s",
                scene.role.value,
                error,
            )
            return None

    def _review_generated_scene_fal(
        self,
        original_reference: Path,
        continuity_reference: Path,
        candidate_path: Path,
        scene: StoryScene,
    ) -> StoryImageReview | None:
        image_paths = self._review_image_paths(
            original_reference,
            continuity_reference,
            candidate_path,
        )
        try:
            response = requests.post(
                f"{FAL_QUEUE_BASE_URL}/{FAL_VISION_REVIEW_MODEL}",
                headers=self._fal_headers(),
                json={
                    "image_urls": [
                        self._review_image_data_uri(path) for path in image_paths
                    ],
                    "prompt": self._review_prompt(scene),
                    "system_prompt": (
                        "Return only one valid JSON object matching the requested "
                        "fields. Do not use markdown fences or add commentary."
                    ),
                    "model": self.settings.story_review_fal_model,
                    "reasoning": False,
                    "temperature": 0,
                    "max_tokens": 500,
                },
                timeout=self.settings.fal_request_timeout_seconds,
            )
            payload = self._json_response(response, "revisor visual fal.ai")
            if response.status_code >= 400:
                raise RuntimeError(
                    f"revisor visual fal.ai fallo ({response.status_code}): "
                    f"{self._response_message(payload, response)}"
                )
            result = self._wait_for_fal_result(payload)
            return self._parse_story_review(result.get("output"))
        except (
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            requests.RequestException,
        ) as error:
            LOGGER.warning(
                "Story semantic review unavailable for %s via fal.ai: %s",
                scene.role.value,
                error,
            )
            return None

    @staticmethod
    def _review_image_paths(
        original_reference: Path,
        continuity_reference: Path,
        candidate_path: Path,
    ) -> list[Path]:
        paths = [original_reference]
        if continuity_reference.resolve() != original_reference.resolve():
            paths.append(continuity_reference)
        paths.append(candidate_path)
        return paths

    @staticmethod
    def _review_json_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "accepted": {"type": "boolean"},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                },
                "retry_instruction": {"type": "string"},
            },
            "required": ["accepted", "score", "issues", "retry_instruction"],
            "additionalProperties": False,
        }

    def _parse_story_review(self, raw_content: Any) -> StoryImageReview:
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise ValueError("el revisor visual no devolvio texto JSON")
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        if not cleaned.startswith("{") or not cleaned.endswith("}"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("el revisor visual devolvio JSON invalido")
            cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("el revisor visual devolvio una estructura inesperada")
        score = max(0, min(10, int(parsed.get("score", 0))))
        raw_issues = parsed.get("issues", [])
        issues = (
            tuple(
                str(issue).strip()
                for issue in raw_issues
                if str(issue).strip()
            )
            if isinstance(raw_issues, list)
            else (str(raw_issues).strip(),)
        )
        accepted = bool(parsed.get("accepted")) and score >= int(
            self.settings.story_review_min_score
        )
        return StoryImageReview(
            accepted=accepted,
            score=score,
            issues=issues,
            retry_instruction=str(parsed.get("retry_instruction") or "").strip(),
        )

    def _review_prompt(self, scene: StoryScene) -> str:
        return (
            "You are the strict visual quality gate for a vertical social-media "
            "story. Image 1 is the original identity/photo reference. If three "
            "images are present, image 2 is the previous continuity/style image. "
            "The final image is the candidate to grade. Reject the candidate if it "
            "has a collage, panels, duplicated foreground protagonist, malformed "
            "face/hands, impossible laptop or car geometry, unreadable fake text, "
            "important content in the upper caption-safe area, wrong setting/action/"
            "emotion, weak identity continuity, or a style mismatch. Small background "
            "people are allowed only in the fast-food scene. Be demanding but do not "
            "reject harmless minor cartoon simplification.\n\n"
            f"Scene requirement: {scene.review_criteria}\n"
            f"Full generation brief: {scene.prompt}\n\n"
            "Set accepted=true only for a clean publishable result scoring at least "
            f"{self.settings.story_review_min_score}/10. retry_instruction must be a "
            "short concrete English correction prompt for the image generator. "
            "Return one JSON object with exactly: accepted (boolean), score "
            "(integer 0-10), issues (array of at most four short strings), and "
            "retry_instruction (string)."
        )

    @staticmethod
    def _review_image_data_uri(image_path: Path) -> str:
        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((640, 960), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=84, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def _wait_for_fal_result(self, submit_payload: dict[str, Any]) -> dict[str, Any]:
        response_url = str(submit_payload.get("response_url") or "")
        status_url = str(submit_payload.get("status_url") or "")
        if not response_url:
            raise RuntimeError(
                "fal.ai no devolvio response_url para consultar el resultado."
            )
        if not status_url:
            return self._fetch_fal_json(response_url, "resultado fal.ai")

        deadline = time.monotonic() + self.settings.fal_request_timeout_seconds
        while time.monotonic() < deadline:
            status_payload = self._fetch_fal_json(status_url, "estado fal.ai")
            status = str(status_payload.get("status") or "").upper()
            if status == "COMPLETED":
                return self._fetch_fal_json(
                    str(status_payload.get("response_url") or response_url),
                    "resultado fal.ai",
                )
            if status in {"FAILED", "ERROR", "CANCELED", "CANCELLED"}:
                raise RuntimeError(
                    f"fal.ai no pudo generar la escena: "
                    f"{status_payload.get('error') or status_payload}"
                )
            time.sleep(max(0.1, self.settings.fal_poll_interval_seconds))
        raise RuntimeError("fal.ai tardo demasiado en generar la escena.")

    def _fetch_fal_json(self, url: str, label: str) -> dict[str, Any]:
        response = requests.get(
            url,
            headers=self._fal_headers(),
            timeout=self.settings.fal_request_timeout_seconds,
        )
        payload = self._json_response(response, label)
        if response.status_code >= 400:
            raise RuntimeError(
                f"{label} fallo ({response.status_code}): "
                f"{self._response_message(payload, response)}"
            )
        return payload

    def _fal_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Key {self.settings.fal_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _image_data_uri(image_path: Path) -> str:
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{image_base64}"

    @staticmethod
    def _json_response(response: requests.Response, label: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(
                f"{label} devolvio una respuesta no JSON: {response.text[:400]}"
            ) from error
        if not isinstance(payload, dict):
            raise RuntimeError(f"{label} devolvio una respuesta JSON inesperada.")
        return payload

    @staticmethod
    def _response_message(payload: dict[str, Any], response: requests.Response) -> str:
        detail = payload.get("detail")
        if detail:
            return str(detail)
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
        return response.text[:400]

    def _build_prompt(
        self,
        scene: StoryScene,
        *,
        retry_feedback: str = "",
        input_count: int = 1,
    ) -> str:
        directives = [
            STORY_STYLE,
            REFERENCE_IDENTITY_DIRECTIVE,
            SINGLE_SCENE_DIRECTIVE,
            NO_OVERLAY_TEXT_DIRECTIVE,
        ]
        if input_count > 1:
            directives.append(
                "INPUT ORDER: input 1 is the original photo for identity and, when "
                "relevant, composition. Input 2 is the approved cartoon continuity "
                "anchor. Never blend them into two people or two frames."
            )
        if scene.role == SlideRole.STORY_BUILDING_STORE:
            directives.extend(
                (
                    BEDROOM_BASE_DIRECTIVE,
                    LAPTOP_COMPOSITION_DIRECTIVE,
                )
            )
        elif scene.role in {
            SlideRole.STORY_FIRST_FAILURE,
            SlideRole.STORY_DEEP_FAILURE,
            SlideRole.STORY_DROPRADAR,
        }:
            directives.extend(
                (
                    BEDROOM_CONTINUITY_DIRECTIVE,
                    LAPTOP_COMPOSITION_DIRECTIVE,
                )
            )
        directives.append(scene.prompt)
        if retry_feedback:
            directives.append(
                "QUALITY REVIEW OF THE PREVIOUS ATTEMPT: " + retry_feedback
            )
        directives.append(
            "Final hard constraints: one single vertical scene, one camera angle, "
            "one normal-size foreground protagonist, no sunglasses indoors, no "
            "collage, no panels, no horizontal separators, no duplicated room, no "
            "duplicated protagonist, no fake text, clean caption-safe upper area."
        )
        return "\n".join(directives)

    def _candidate_for_path(
        self,
        path: Path,
        *,
        source_id: str,
        caption: str,
    ) -> MediaCandidate:
        with Image.open(path) as image:
            width, height = image.size
        return MediaCandidate(
            source_account=STORY_IMAGE_SOURCE_ACCOUNT,
            source_id=source_id,
            local_path=path,
            permalink=f"{self.settings.image_provider}://{source_id}",
            caption=caption,
            width=width,
            height=height,
            created_at="generated",
        )
