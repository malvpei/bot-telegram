from __future__ import annotations

import base64
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from app.config import Settings
from app.models import MediaCandidate, SlideRole


OPENAI_IMAGES_EDIT_URL = "https://api.openai.com/v1/images/edits"
FAL_QUEUE_BASE_URL = "https://queue.fal.run"
STORY_IMAGE_SOURCE_ACCOUNT = "ai_story"
STORY_STYLE = (
    "clean vertical 2D comic/caricature illustration like a simple social-media "
    "webcomic, bold black outlines, flat soft colors, simple shading, expressive "
    "faces, less realistic and more cartoon, polished but not photorealistic"
)
NO_OVERLAY_TEXT_DIRECTIVE = (
    "Do not add captions, speech bubbles, subtitles, watermarks or TikTok UI. "
    "Leave clean empty space near the top for an external text card."
)
SINGLE_SCENE_DIRECTIVE = (
    "Create exactly ONE single continuous scene in the image. No split-screen, "
    "no comic panels, no repeated character, no before/after layout, no stacked "
    "frames, no duplicated laptop, no duplicated room."
)
BEDROOM_CONTINUITY_DIRECTIVE = (
    "For bedroom scenes use the exact same small bedroom across the sequence: "
    "plain light gray walls, wooden desk, realistic desk lamp, small shelf with "
    "books, Porsche 911 GT3 poster taped on the left wall, piggy bank labeled "
    "GT3 FUND, same desk position and same overall layout."
)
REFERENCE_IDENTITY_DIRECTIVE = (
    "Use the person in the reference photo as the identity reference: preserve "
    "the same young male protagonist, hair color, face shape, build and overall "
    "look across all scenes, adapted to the comic style."
)


@dataclass(frozen=True)
class StoryScene:
    role: SlideRole
    prompt: str


STORY_SCENES: tuple[StoryScene, ...] = (
    StoryScene(
        role=SlideRole.STORY_MCDONALD,
        prompt=(
            "Scene 1: the same protagonist is working sadly in a busy fast-food "
            "restaurant kitchen inspired by McDonald's. He must wear clear "
            "McDonald's-style work clothes: black polo uniform, red visor or cap, "
            "red apron, small yellow M-style badge/name tag, no sunglasses. He is "
            "holding a burger, tired posture, industrial fryers, burgers and fries "
            "around him, coworkers and customers only in the far background, "
            "feeling depressed and stuck."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_BUILDING_STORE,
        prompt=(
            "Scene 2: same bedroom. The protagonist sits at the wooden desk, "
            "leaning forward and looking directly at his laptop, focused and "
            "determined while building a dropshipping store. Camera angle shows "
            "mostly the plain back of the laptop, with no data, no charts and no "
            "dashboard visible on the laptop exterior. Include notebooks, desk "
            "lamp, GT3 FUND piggy bank and the Porsche poster."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_FIRST_FAILURE,
        prompt=(
            "Scene 3: same bedroom and same desk. The store is failing. Use a "
            "single coherent camera angle where both the protagonist and the open "
            "laptop screen are visible. The laptop must have a realistic hinge and "
            "realistic orientation toward the protagonist; he is looking at the "
            "screen with one hand on his face, discouraged. On the laptop screen "
            "show a minimal clean ecommerce dashboard with one simple red downward "
            "line chart and zero-sales mood, no readable brand names."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_DEEP_FAILURE,
        prompt=(
            "Scene 4: same bedroom and same desk, several months later at night. "
            "Single coherent scene only. The protagonist is more sad and desperate, "
            "close to giving up, crying with both hands near his face. Blue dark "
            "room lighting, laptop glow, slightly messy desk. The laptop screen is "
            "visible at a realistic angle and shows a cleaner, more developed "
            "ecommerce analytics dashboard with tidy cards, red KPI numbers, a red "
            "downward chart and a red arrow, clearly communicating the store is "
            "going badly, no readable brand names."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_DROPRADAR,
        prompt=(
            "Scene 5: same bedroom and same desk, turning point. Single coherent "
            "scene only. The protagonist is concentrated and serious, studying the "
            "laptop, not celebrating yet. The laptop orientation is realistic toward "
            "him while still letting the viewer see the screen. The screen must have "
            "a clean white background, clearly show the word Dropradar in green and "
            "black, attractive product research dashboard cards, clean data rows "
            "and a green rising sales chart. Keep the interface bright, white and "
            "modern."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_SUCCESS_COMIC,
        prompt=(
            "Scene 6: transform the reference photo itself into the same clean "
            "comic/caricature illustration style. Preserve the original composition closely: "
            "the young man next to the black Porsche 911 GT3 on the road, mountains, "
            "trees and dramatic cloudy sky. The protagonist is happy and proud, "
            "as if he achieved his dream. Single scene only. No text."
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
        generated: list[MediaCandidate] = []
        for index, scene in enumerate(STORY_SCENES, start=1):
            output_path = scenes_dir / f"story_{index:02d}_{scene.role.value}.png"
            self._generate_scene(reference_image_path, scene, output_path)
            generated.append(
                self._candidate_for_path(
                    output_path,
                    source_id=f"story_ai:{index}:{scene.role.value}",
                    caption=scene.prompt,
                )
            )
        return generated

    def _generate_scene(
        self,
        reference_image_path: Path,
        scene: StoryScene,
        output_path: Path,
    ) -> None:
        provider = self.settings.image_provider.lower()
        if provider == "fal":
            self._generate_scene_fal(reference_image_path, scene, output_path)
            return
        if provider == "openai":
            self._generate_scene_openai(reference_image_path, scene, output_path)
            return
        raise RuntimeError(
            f"IMAGE_PROVIDER={self.settings.image_provider!r} no esta soportado. "
            "Usa 'fal' u 'openai'."
        )

    def _generate_scene_fal(
        self,
        reference_image_path: Path,
        scene: StoryScene,
        output_path: Path,
    ) -> None:
        if not self.settings.fal_key:
            raise RuntimeError(
                "Falta FAL_KEY. Configuralo para usar el carrusel IA tipo 4 con fal.ai."
            )

        prompt = self._build_prompt(scene.prompt)
        submit_payload = {
            "prompt": prompt,
            "image_url": self._image_data_uri(reference_image_path),
            "num_images": 1,
            "aspect_ratio": self.settings.fal_image_aspect_ratio,
            "output_format": self.settings.fal_output_format,
            "guidance_scale": self.settings.fal_guidance_scale,
            "safety_tolerance": self.settings.fal_safety_tolerance,
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
        output_path.write_bytes(image_response.content)

    def _generate_scene_openai(
        self,
        reference_image_path: Path,
        scene: StoryScene,
        output_path: Path,
    ) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError(
                "Falta OPENAI_API_KEY. Configuralo para usar el carrusel IA tipo 4."
            )

        prompt = self._build_prompt(scene.prompt)
        mime_type = mimetypes.guess_type(reference_image_path.name)[0] or "image/jpeg"
        with reference_image_path.open("rb") as image_handle:
            files = [
                (
                    "image[]",
                    (reference_image_path.name, image_handle, mime_type),
                )
            ]
            data = {
                "model": self.settings.openai_image_model,
                "prompt": prompt,
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

        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(
                f"OpenAI Images devolvio una respuesta no JSON: {response.text[:400]}"
            ) from error
        if response.status_code >= 400:
            message = (
                payload.get("error", {}).get("message")
                if isinstance(payload, dict)
                else ""
            )
            raise RuntimeError(
                f"OpenAI Images fallo ({response.status_code}): "
                f"{message or response.text[:400]}"
            )

        image_base64 = (
            payload.get("data", [{}])[0].get("b64_json")
            if isinstance(payload, dict)
            else None
        )
        if not image_base64:
            raise RuntimeError("OpenAI Images no devolvio b64_json para la escena.")
        output_path.write_bytes(base64.b64decode(image_base64))

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

    def _image_data_uri(self, image_path: Path) -> str:
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

    def _build_prompt(self, scene_prompt: str) -> str:
        return "\n".join(
            (
                STORY_STYLE,
                REFERENCE_IDENTITY_DIRECTIVE,
                SINGLE_SCENE_DIRECTIVE,
                BEDROOM_CONTINUITY_DIRECTIVE,
                NO_OVERLAY_TEXT_DIRECTIVE,
                scene_prompt,
                (
                    "Generate a vertical carousel image with strong storytelling, "
                    "consistent character design and clean readable visual elements."
                ),
            )
        )

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
