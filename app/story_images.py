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
    "Style target: simple flat 2D social-media cartoon panel like a clean Spanish "
    "TikTok story illustration, not anime, not manga, not semi-realistic, not 3D, "
    "not photorealistic. Use thick smooth black outlines, flat color fills, very "
    "limited cel shading, low-detail simplified faces with simple eyes, simple "
    "nose and simple mouth, rounded youthful features, minimal texture, clean "
    "geometry and a limited muted palette. Avoid realistic facial anatomy, "
    "painted skin, photographic lighting, glossy rendering, complex shadows, "
    "muscular heroic body proportions and detailed cinematic backgrounds."
)
NO_OVERLAY_TEXT_DIRECTIVE = (
    "Do not add captions, speech bubbles, subtitles, watermarks or TikTok UI. "
    "Leave clean empty space near the top for an external text card."
)
SINGLE_SCENE_DIRECTIVE = (
    "HARD RULE: the whole image is one single full-page illustration from one "
    "camera shot. Do not create a comic strip. Do not create panels. Do not use "
    "split-screen, stacked frames, horizontal dividers, repeated rooms, repeated "
    "characters, before/after layout, montage, collage or multiple moments. "
    "Only one protagonist and one laptop maximum."
)
BEDROOM_CONTINUITY_DIRECTIVE = (
    "Bedroom continuity: use the same small bedroom as a single real room across "
    "these scenes: plain light gray walls, wooden desk, realistic desk lamp, "
    "small shelf with books, Porsche 911 GT3 poster taped on the left wall, piggy "
    "bank labeled GT3 FUND, notebook and pen, same desk position and same layout. "
    "The protagonist is normal human size, seated on a chair at the desk, never "
    "standing on the desk, never miniature, never separated from the laptop."
)
LAPTOP_COMPOSITION_DIRECTIVE = (
    "Laptop composition for desk scenes: copy the believable layout of a simple "
    "cartoon side-view desk illustration. The laptop sits on the desk in the left "
    "foreground, opened at a normal 100 to 110 degree angle. The keyboard base is "
    "flat on the desk. The hinge is one straight horizontal line. The screen is "
    "one upright rectangle, slightly tilted back, with parallel vertical edges, "
    "facing both the viewer and the protagonist. The protagonist sits to the "
    "right of the laptop in profile or three-quarter profile, eyes aimed at the "
    "screen, with hands aligned to the keyboard or trackpad. The laptop must not "
    "be twisted, folded toward the wrong direction, floating, detached, vertical "
    "on its keyboard edge, or shown from an impossible perspective."
)
REFERENCE_IDENTITY_DIRECTIVE = (
    "Use the person in the reference photo as the identity reference: preserve "
    "the same young male protagonist, hair color, face shape, build and overall "
    "look across all scenes, adapted to the cartoon comic style. No sunglasses "
    "unless explicitly requested; eyes should be visible in indoor scenes."
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
            "McDonald's-style work clothes: black short-sleeve polo uniform with "
            "small yellow M-style logo, red visor or cap, name tag, black or red "
            "apron, no luxury shirt, no GT3 text, no sunglasses, eyes visible. "
            "Composition like a single vertical cartoon frame inside the kitchen: "
            "he stands in the center foreground holding a burger with both hands, "
            "sad/tired expression, industrial fryers, grill, fries and burgers "
            "around him, coworkers and customers only small in the far background."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_BUILDING_STORE,
        prompt=(
            "Scene 2: same bedroom. The protagonist sits on the chair at the "
            "wooden desk, leaning forward, looking directly at the laptop screen, "
            "focused and determined while building a dropshipping store. Use the "
            "laptop composition rule so both the protagonist and the screen are "
            "visible naturally. On the laptop screen show a clean store builder "
            "dashboard with product cards, a small green progress chart and simple "
            "order widgets. Include notebooks, desk lamp, GT3 FUND piggy bank and "
            "the Porsche poster."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_FIRST_FAILURE,
        prompt=(
            "Scene 3: same bedroom and same desk. The protagonist is normal size, "
            "seated in the chair, sad and discouraged, looking at the laptop "
            "screen because he has no sales. Use the laptop composition rule so "
            "the screen and his sad face are both visible in one believable shot. "
            "On the laptop screen show a minimal clean ecommerce dashboard with "
            "one simple red downward line chart, a visible zero-sales feeling, "
            "and no readable brand names."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_DEEP_FAILURE,
        prompt=(
            "Scene 4: same bedroom and same desk, several months later at night. "
            "The protagonist sits in the chair using the laptop, very sad and "
            "almost crying, one hand on his face and one hand near the keyboard "
            "or trackpad, looking at the laptop screen. Use the laptop composition "
            "rule; do not make separate panels. Blue dark room lighting, laptop "
            "glow, slightly messy desk. The laptop screen is visible at a realistic "
            "angle and shows a clean ecommerce analytics dashboard with tidy cards, "
            "red KPI numbers, a red downward chart and a red arrow, clearly "
            "communicating the store is going badly."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_DROPRADAR,
        prompt=(
            "Scene 5: same bedroom and same desk, turning point. The protagonist "
            "sits in the chair using the laptop, concentrated and serious, looking "
            "at the screen. Use the laptop composition rule; both his face/profile "
            "and the screen must be visible in one believable shot. On the laptop "
            "screen clearly show Dropradar on a clean white interface: the word "
            "Dropradar large in green and black, product research dashboard cards, "
            "clean data rows, product metrics and a green rising chart."
        ),
    ),
    StoryScene(
        role=SlideRole.STORY_SUCCESS_COMIC,
        prompt=(
            "Scene 6: transform the reference photo itself into the same clean "
            "cartoon comic illustration style. Preserve the original photo "
            "composition closely: one outdoor road scene only, the young man next "
            "to the black Porsche 911 GT3, mountains, trees and dramatic cloudy sky. "
            "Do not show a bedroom, laptop, desk, lamp or poster. Do not create "
            "multiple panels. The protagonist is happy and proud, as if he achieved "
            "his dream. No text inside the image."
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

        prompt = self._build_prompt(scene)
        submit_payload = {
            "prompt": prompt,
            "image_url": self._image_data_uri(reference_image_path),
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

        prompt = self._build_prompt(scene)
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

    def _build_prompt(self, scene: StoryScene) -> str:
        directives = [
            STORY_STYLE,
            REFERENCE_IDENTITY_DIRECTIVE,
            SINGLE_SCENE_DIRECTIVE,
            NO_OVERLAY_TEXT_DIRECTIVE,
        ]
        if scene.role in {
            SlideRole.STORY_BUILDING_STORE,
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
        directives.extend(
            (
                scene.prompt,
                (
                    "Final hard constraints: one single scene, one camera angle, "
                    "one normal-size protagonist, no sunglasses indoors, no collage, "
                    "no panels, no horizontal separators, no duplicated room, no "
                    "duplicated protagonist."
                ),
            )
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
