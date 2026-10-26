"""Server-side media providers for the local video studio.

No credentials are persisted by this module. Billable POSTs are never retried.
The caller is responsible for reserving a budget before invoking generation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from filelock import FileLock


ELEVENLABS_BASE = "https://api.elevenlabs.io"
FAL_QUEUE_BASE = "https://queue.fal.run"
SEEDANCE_FAST = "fal-ai/bytedance/seedance/v1/pro/fast/image-to-video"
H3_MAX_TURBO = "minimax/h3-max-turbo/image-to-video"
GPT_IMAGE_EDIT = "openai/gpt-image-2/edit"
ALLOWED_FAL_MODELS = frozenset({SEEDANCE_FAST, H3_MAX_TURBO, GPT_IMAGE_EDIT})
ALLOWED_TTS_MODELS = frozenset(
    {"eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_v3"}
)
PUBLISHED_IMAGE_PRICING = {
    "model": GPT_IMAGE_EDIT,
    "currency": "USD",
    "unit": "million_tokens",
    "input_text": 5.0,
    "cached_input_text": 1.25,
    "output_text": 10.0,
    "input_image": 8.0,
    "cached_input_image": 2.0,
    "output_image": 30.0,
    "source_url": "https://fal.ai/models/openai/gpt-image-2/edit",
    "checked_date": "2026-10-26",
    "fixed_per_image_price": None,
    "note": "El coste depende de los tokens de entrada y salida y de la calidad; no es una tarifa plana por imagen.",
}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MAX_MEDIA_BYTES = 256 * 1024 * 1024
_MAX_AUDIO_BYTES = 32 * 1024 * 1024
_DEFAULT_VOICE_SETTINGS = {
    "stability": 0.65,
    "similarity_boost": 0.8,
    "style": 0.15,
    "use_speaker_boost": True,
    "speed": 1.0,
}


class ProviderError(RuntimeError):
    """An intentionally sanitized error suitable for a local UI."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        status_code: int | None = None,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown


class MissingCredential(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Falta conectar {provider}.", code="missing_credential", status_code=None
        )


def _credential(value: str, provider: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissingCredential(provider)
    value = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ProviderError("La credencial no tiene un formato válido.", code="invalid_credential")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ProviderError(f"El identificador de {label} no es válido.", code="invalid_input")
    return value


def _finite(value: Any, lower: float, upper: float, name: str) -> float:
    if isinstance(value, bool):
        raise ProviderError(f"El valor de {name} no es válido.", code="invalid_input")
    try:
        numeric = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ProviderError(f"El valor de {name} no es válido.", code="invalid_input") from None
    if not math.isfinite(numeric) or not lower <= numeric <= upper:
        raise ProviderError(f"El valor de {name} está fuera de rango.", code="invalid_input")
    return numeric


def _safe_https(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 16000:
        return False
    try:
        p = urlsplit(value)
        return (
            p.scheme == "https"
            and bool(p.hostname)
            and not p.username
            and not p.password
            and p.port in (None, 443)
            and not p.fragment
            and not any(ord(c) < 32 or c == "\\" for c in value)
        )
    except ValueError:
        return False


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _http_error(code: int, provider: str, billable: bool) -> ProviderError:
    messages = {
        400: "La solicitud no es válida.",
        401: "La conexión ha caducado o la credencial no es válida.",
        402: "No hay saldo disponible o el proveedor requiere un plan habilitado.",
        403: "La cuenta no tiene permiso para esta operación.",
        404: "No se ha encontrado el recurso solicitado.",
        405: "El proveedor no admite esta operación.",
        422: "El proveedor ha rechazado los parámetros de la solicitud.",
        429: "Se ha alcanzado el límite de solicitudes del proveedor.",
    }
    unknown = billable and code >= 500
    return ProviderError(
        f"{provider}: {messages.get(code, 'El proveedor no pudo completar la solicitud.')}"
        + (" Revisa el resultado antes de volver a generar." if unknown else ""),
        code=f"http_{code}",
        status_code=code,
        outcome_unknown=unknown,
    )


class _APIClient:
    provider = "Proveedor"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self._api_key = _credential(api_key, self.provider)
        self._session = session if session is not None else requests.Session()

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        billable = method == "POST"
        try:
            response = self._session.request(
                method,
                url,
                timeout=(10, 180 if billable else 30),
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException:
            raise ProviderError(
                f"No se pudo completar la conexión con {self.provider}."
                + (" El resultado es desconocido; no se repetirá la generación automáticamente." if billable else ""),
                code="network_error",
                outcome_unknown=billable,
            ) from None
        if 300 <= response.status_code < 400:
            raise ProviderError(
                "El proveedor devolvió una redirección inesperada.",
                code="unexpected_redirect",
                status_code=response.status_code,
                outcome_unknown=billable,
            )
        if not 200 <= response.status_code < 300:
            raise _http_error(response.status_code, self.provider, billable)
        return response

    def _json_request(self, method: str, url: str, **kwargs: Any) -> tuple[dict, Any]:
        response = self._request(method, url, **kwargs)
        try:
            value = response.json()
        except (ValueError, TypeError):
            raise ProviderError(
                "El proveedor no devolvió una respuesta válida.",
                code="invalid_response",
                outcome_unknown=method == "POST",
            ) from None
        if not isinstance(value, dict):
            raise ProviderError("El proveedor no devolvió una respuesta válida.", code="invalid_response", outcome_unknown=method == "POST")
        return value, response


class ElevenLabsClient(_APIClient):
    provider = "ElevenLabs"

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key, "Accept": "application/json"}

    def status(self) -> dict:
        """Check the connection without generating speech or changing a plan."""
        value, _ = self._json_request("GET", f"{ELEVENLABS_BASE}/v1/user/subscription", headers=self._headers())
        result: dict[str, Any] = {"provider": "elevenlabs", "connected": True}
        for key in ("tier", "status", "currency", "billing_period"):
            if isinstance(value.get(key), str):
                result[key] = value[key][:80]
        for key in ("character_count", "character_limit", "next_character_count_reset_unix"):
            if isinstance(value.get(key), int) and not isinstance(value[key], bool):
                result[key] = value[key]
        if "character_count" in result and "character_limit" in result:
            result["remaining_characters"] = max(0, result["character_limit"] - result["character_count"])
        return result

    def voices(self) -> list[dict]:
        """Return a bounded, sanitized catalogue; never verification recordings."""
        output: dict[str, dict] = {}
        seen_tokens: set[str] = set()
        token = None
        for _ in range(20):
            params: dict[str, Any] = {"page_size": 100, "include_total_count": "false"}
            if token:
                params["next_page_token"] = token
            try:
                value, _ = self._json_request("GET", f"{ELEVENLABS_BASE}/v2/voices", headers=self._headers(), params=params)
            except ProviderError as error:
                if error.status_code not in (404, 405) or output:
                    raise
                value, _ = self._json_request("GET", f"{ELEVENLABS_BASE}/v1/voices", headers=self._headers())
                value["has_more"] = False
            rows = value.get("voices")
            if not isinstance(rows, list):
                raise ProviderError("No se pudo leer el catálogo de voces.", code="invalid_response")
            for raw in rows:
                if not isinstance(raw, dict) or not isinstance(raw.get("voice_id"), str) or not _IDENTIFIER.fullmatch(raw["voice_id"]):
                    continue
                row = {
                    "voice_id": raw["voice_id"],
                    "name": str(raw.get("name") or "Voz sin nombre")[:200],
                    "category": str(raw.get("category") or "")[:80],
                    "description": str(raw.get("description") or "")[:600],
                    "labels": {str(k)[:60]: str(v)[:160] for k, v in (raw.get("labels") or {}).items() if isinstance(v, (str, int, float, bool))} if isinstance(raw.get("labels"), dict) else {},
                    "preview_url": raw.get("preview_url") if _safe_https(raw.get("preview_url")) else None,
                    "verified_languages": [],
                }
                for lang in raw.get("verified_languages") or []:
                    if isinstance(lang, dict):
                        row["verified_languages"].append({k: str(lang[k])[:100] for k in ("language", "locale", "accent", "model_id") if isinstance(lang.get(k), str)})
                output[row["voice_id"]] = row
            if not value.get("has_more"):
                return list(output.values())
            token = value.get("next_page_token")
            if not isinstance(token, str) or not token or token in seen_tokens:
                raise ProviderError("El catálogo de voces devolvió una paginación inválida.", code="invalid_response")
            seen_tokens.add(token)
        raise ProviderError("El catálogo es demasiado grande para cargarlo de una vez.", code="catalogue_limit")

    def shared_voices(
        self,
        language: str = "es",
        accent: str | None = None,
        *,
        locale: str | None = "es-ES",
        gender: str | None = None,
        age: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        """Search public voice previews without adding a voice or generating.

        A public preview is not proof that the connected account may synthesize
        it. ElevenLabs requires a paid plan for Voice Library API access.
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ProviderError("El límite del catálogo debe estar entre 1 y 100.", code="invalid_input")
        params: dict[str, Any] = {
            "page_size": min(100, limit),
            "page": 0,
            "sort": "usage_character_count_1y",
            "include_custom_rates": "false",
            "include_live_moderated": "false",
        }
        for key, value in (("language", language), ("locale", locale), ("accent", accent), ("gender", gender), ("age", age)):
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value) > 80 or any(ord(c) < 32 for c in value):
                    raise ProviderError("El filtro de voces no es válido.", code="invalid_input")
                params[key] = value.strip()
        output: dict[str, dict] = {}
        for page in range(5):
            params["page"] = page
            value, _ = self._json_request("GET", f"{ELEVENLABS_BASE}/v1/shared-voices", headers=self._headers(), params=dict(params))
            rows = value.get("voices")
            if not isinstance(rows, list):
                raise ProviderError("No se pudo leer la biblioteca de voces.", code="invalid_response")
            for raw in rows:
                if not isinstance(raw, dict) or not isinstance(raw.get("voice_id"), str) or not _IDENTIFIER.fullmatch(raw["voice_id"]):
                    continue
                labels = {key: str(raw[key])[:160] for key in ("language", "locale", "accent", "gender", "age", "use_case", "descriptive") if isinstance(raw.get(key), str)}
                verified = []
                for lang in raw.get("verified_languages") or []:
                    if isinstance(lang, dict):
                        verified.append({key: str(lang[key])[:100] for key in ("language", "locale", "accent", "model_id") if isinstance(lang.get(key), str)})
                output[raw["voice_id"]] = {
                    "voice_id": raw["voice_id"],
                    "name": str(raw.get("name") or "Voz sin nombre")[:200],
                    "description": str(raw.get("description") or "")[:600],
                    "category": str(raw.get("category") or "")[:80],
                    "labels": labels,
                    "verified_languages": verified,
                    "preview_url": raw.get("preview_url") if _safe_https(raw.get("preview_url")) else None,
                    "source": "voice_library",
                    "requires_paid_api_access": True,
                    "added_to_account": False,
                }
                if len(output) >= limit:
                    return list(output.values())
            if not value.get("has_more"):
                return list(output.values())
        return list(output.values())

    def synthesize(
        self,
        text: str,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
        settings: dict | None = None,
        output_dir: Path | str = ".",
        seed: int | None = 42,
    ) -> dict:
        """Create cached MP3 speech and character alignment; one POST at most.

        ``duration`` is the last aligned character end, not a media-container
        measurement. The renderer must measure the MP3 and preserve its tail.
        """
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise ProviderError("La locución debe contener entre 1 y 5000 caracteres.", code="invalid_input")
        voice_id = _identifier(voice_id, "voz")
        if model_id not in ALLOWED_TTS_MODELS:
            raise ProviderError("Ese modelo de voz no está configurado en el estudio.", code="unsupported_model")
        voice_settings = dict(_DEFAULT_VOICE_SETTINGS)
        if settings is not None:
            if not isinstance(settings, dict) or set(settings) - set(voice_settings):
                raise ProviderError("Los ajustes de voz no son válidos.", code="invalid_input")
            voice_settings.update(settings)
        for key in ("stability", "similarity_boost", "style"):
            voice_settings[key] = _finite(voice_settings[key], 0, 1, key)
        voice_settings["speed"] = _finite(voice_settings["speed"], 0.7, 1.2, "velocidad")
        if not isinstance(voice_settings["use_speaker_boost"], bool):
            raise ProviderError("El ajuste de voz no es válido.", code="invalid_input")
        body: dict[str, Any] = {"text": text.strip(), "model_id": model_id, "voice_settings": voice_settings}
        if seed is not None:
            if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 4294967295:
                raise ProviderError("La semilla de voz no es válida.", code="invalid_input")
            body["seed"] = seed
        if model_id != "eleven_multilingual_v2":
            body["language_code"] = "es"
        fingerprint = {"provider": "elevenlabs", "voice_id": voice_id, "output_format": "mp3_44100_128", "body": body, "cache_version": 1}
        cache_key = hashlib.sha256(_json_bytes(fingerprint)).hexdigest()
        directory = Path(output_dir).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        audio_path = directory / f"{cache_key}.mp3"
        alignment_path = directory / f"{cache_key}.alignment.json"
        state_path = directory / f"{cache_key}.request.json"
        with FileLock(str(directory / f"{cache_key}.lock"), timeout=240):
            previous = {}
            if state_path.exists():
                try:
                    previous = json.loads(state_path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    raise ProviderError("No se pudo verificar la caché de la locución.", code="cache_invalid") from None
                if previous.get("status") == "completed":
                    if not audio_path.is_file() or not alignment_path.is_file() or hashlib.sha256(audio_path.read_bytes()).hexdigest() != previous.get("audio_sha256"):
                        raise ProviderError("La locución guardada está incompleta; revísala antes de regenerar.", code="cache_invalid")
                    return {**previous["result"], "cached": True}
                if previous.get("status") in ("in_flight", "unknown_outcome"):
                    raise ProviderError("Esta locución tiene una petición pendiente de comprobar. No se enviará otra para evitar un cobro duplicado.", code="unknown_outcome", outcome_unknown=True)
            _atomic_write(state_path, _json_bytes({"status": "in_flight", "cache_key": cache_key}))
            try:
                value, response = self._json_request("POST", f"{ELEVENLABS_BASE}/v1/text-to-speech/{voice_id}/with-timestamps", headers=self._headers(), params={"output_format": "mp3_44100_128"}, json=body)
                encoded = value.get("audio_base64")
                if not isinstance(encoded, str) or len(encoded) > _MAX_AUDIO_BYTES * 4 // 3 + 8:
                    raise ProviderError("ElevenLabs no devolvió un audio válido.", code="invalid_audio", outcome_unknown=True)
                try:
                    audio_bytes = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    raise ProviderError("ElevenLabs no devolvió un audio válido.", code="invalid_audio", outcome_unknown=True) from None
                if len(audio_bytes) < 10 or len(audio_bytes) > _MAX_AUDIO_BYTES or not (audio_bytes.startswith(b"ID3") or (audio_bytes[0] == 255 and audio_bytes[1] & 224 == 224)):
                    raise ProviderError("ElevenLabs no devolvió un MP3 reconocible.", code="invalid_audio", outcome_unknown=True)
                alignment = self._alignment(value.get("alignment"))
                normalized = self._alignment(value.get("normalized_alignment")) if value.get("normalized_alignment") else alignment
                _atomic_write(audio_path, audio_bytes)
                _atomic_write(alignment_path, _json_bytes({"alignment": alignment, "normalized_alignment": normalized, "text": body["text"]}))
                request_id = response.headers.get("request-id") or response.headers.get("x-request-id")
                request_id = request_id if isinstance(request_id, str) and _IDENTIFIER.fullmatch(request_id) else None
                result = {"audio_path": str(audio_path), "alignment_path": str(alignment_path), "duration": max(normalized["character_end_times_seconds"]), "duration_source": "character_alignment", "character_count": len(body["text"]), "request_id": request_id, "cache_key": cache_key, "cached": False, "model_id": model_id, "voice_id": voice_id}
                _atomic_write(state_path, _json_bytes({"status": "completed", "cache_key": cache_key, "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(), "result": result}))
                return result
            except ProviderError as error:
                _atomic_write(state_path, _json_bytes({"status": "unknown_outcome" if error.outcome_unknown else "failed", "cache_key": cache_key, "error_code": error.code}))
                raise
            except (OSError, ValueError, TypeError, KeyError):
                _atomic_write(state_path, _json_bytes({"status": "unknown_outcome", "cache_key": cache_key, "error_code": "local_processing_error"}))
                raise ProviderError("Se recibió la locución, pero no se pudo guardar correctamente. Revisa el resultado antes de regenerar.", code="local_processing_error", outcome_unknown=True) from None

    @staticmethod
    def _alignment(value: Any) -> dict:
        if not isinstance(value, dict):
            raise ProviderError("La locución no incluye tiempos verificables.", code="invalid_alignment", outcome_unknown=True)
        names = ("characters", "character_start_times_seconds", "character_end_times_seconds")
        values = [value.get(name) for name in names]
        if not all(isinstance(v, list) for v in values) or not values[0] or len({len(v) for v in values}) != 1:
            raise ProviderError("Los tiempos de la locución están incompletos.", code="invalid_alignment", outcome_unknown=True)
        if any(not isinstance(c, str) for c in values[0]):
            raise ProviderError("Los tiempos de la locución no son válidos.", code="invalid_alignment", outcome_unknown=True)
        start, end = values[1], values[2]
        try:
            for i, (a, b) in enumerate(zip(start, end)):
                if isinstance(a, bool) or isinstance(b, bool) or not math.isfinite(a) or not math.isfinite(b) or a < 0 or b < a or b > 3600 or (i and a < start[i-1]) or (i and b < end[i-1]):
                    raise ValueError
        except (TypeError, ValueError):
            raise ProviderError("Los tiempos de la locución no son válidos.", code="invalid_alignment", outcome_unknown=True) from None
        return {key: value[key] for key in names}


class FalClient(_APIClient):
    provider = "fal"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._api_key}", "Accept": "application/json"}

    def pricing(self, model: str) -> dict:
        """Read the account's published rate without submitting an inference.

        A price per token/second is not a total generation quote. The caller
        must check the returned unit rather than treating it as per image.
        Missing rates and permissions are errors, never a zero-price fallback.
        """
        self._model(model)
        value, _ = self._json_request(
            "GET", "https://api.fal.ai/v1/models/pricing",
            headers=self._headers(), params={"endpoint_id": model},
        )
        rows = value.get("prices")
        if not isinstance(rows, list):
            raise ProviderError("No se pudo verificar la tarifa de este generador.", code="pricing_unavailable")
        prices = []
        for row in rows:
            if not isinstance(row, dict) or row.get("endpoint_id") != model:
                continue
            try:
                rate = _finite(row.get("unit_price"), 0, 1e9, "tarifa")
            except ProviderError:
                continue
            if not isinstance(row.get("unit"), str) or not row["unit"] or not isinstance(row.get("currency"), str):
                continue
            prices.append({"endpoint_id": model, "unit_price": rate, "unit": row["unit"][:120], "currency": row["currency"][:12]})
        if not prices:
            raise ProviderError("El proveedor no ha devuelto una tarifa verificable para este generador.", code="pricing_unavailable")
        return {"available": True, "model": model, "prices": prices, "source_url": "https://fal.ai/docs/documentation/model-apis/pricing", "checked_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def _model(model: str) -> str:
        if model not in ALLOWED_FAL_MODELS:
            raise ProviderError("Ese generador no está configurado en el estudio.", code="unsupported_model")
        return model

    @classmethod
    def _request_url(cls, model: str, request_id: str, suffix: str = "") -> str:
        cls._model(model)
        _identifier(request_id, "petición")
        owner_app = "/".join(model.split("/")[:2])
        return f"{FAL_QUEUE_BASE}/{owner_app}/requests/{request_id}{suffix}"

    @classmethod
    def _queue_url(cls, url: Any, model: str, request_id: str, suffix: str = "") -> str:
        expected = cls._request_url(model, request_id, suffix)
        if url is None:
            return expected
        if not _safe_https(url) or url != expected:
            raise ProviderError("fal devolvió una dirección de seguimiento inesperada.", code="invalid_response", outcome_unknown=True)
        return url

    @staticmethod
    def _file_input(value: Any) -> None:
        if isinstance(value, str) and value.startswith("data:"):
            if not re.match(r"^data:(image/(png|jpeg|webp)|audio/(mpeg|wav));base64,", value) or len(value) > 32 * 1024 * 1024:
                raise ProviderError("La referencia multimedia no es válida.", code="invalid_input")
            return
        if not _safe_https(value):
            raise ProviderError("La referencia debe ser una imagen HTTPS o una imagen incrustada.", code="invalid_input")

    def submit(self, model: str, payload: dict) -> dict:
        self._model(model)
        if not isinstance(payload, dict) or not isinstance(payload.get("prompt"), str) or not payload["prompt"].strip() or len(payload["prompt"]) > 20000:
            raise ProviderError("Falta una descripción válida de la escena.", code="invalid_input")
        payload = dict(payload)
        if payload.get("enable_safety_checker") is False:
            raise ProviderError("El estudio conserva los filtros del proveedor.", code="invalid_input")
        if model == GPT_IMAGE_EDIT:
            images = payload.get("image_urls")
            if not isinstance(images, list) or not 1 <= len(images) <= 16 or payload.get("num_images", 1) != 1:
                raise ProviderError("Cada petición debe crear una imagen a partir de sus referencias.", code="invalid_input")
            for image in images:
                self._file_input(image)
        else:
            self._file_input(payload.get("image_url"))
            if payload.get("end_image_url"):
                self._file_input(payload["end_image_url"])
            if payload.get("target_audio_url"):
                self._file_input(payload["target_audio_url"])
            duration = _finite(payload.get("duration", 5), 2 if model == SEEDANCE_FAST else 5, 12 if model == SEEDANCE_FAST else 15, "duración")
            if model == SEEDANCE_FAST:
                if not duration.is_integer():
                    raise ProviderError("Seedance necesita una duración entera.", code="invalid_input")
                payload["duration"] = str(int(duration))
                if payload.get("aspect_ratio", "9:16") != "9:16":
                    raise ProviderError("El estudio genera vídeo vertical 9:16.", code="invalid_input")
                payload["aspect_ratio"] = "9:16"
                if payload.get("resolution", "720p") not in ("480p", "720p", "1080p"):
                    raise ProviderError("La resolución no es válida.", code="invalid_input")
            else:
                payload["duration"] = duration
                payload["resolution"] = str(payload.get("resolution", "768P")).upper()
                if payload["resolution"] not in ("480P", "768P", "1080P"):
                    raise ProviderError("La resolución no es válida.", code="invalid_input")
        value, _ = self._json_request("POST", f"{FAL_QUEUE_BASE}/{model}", headers=self._headers(), json=payload)
        try:
            request_id = _identifier(value.get("request_id"), "petición")
        except ProviderError:
            raise ProviderError("fal no devolvió un identificador de generación verificable.", code="invalid_response", outcome_unknown=True) from None
        return {"request_id": request_id, "status_url": self._queue_url(value.get("status_url"), model, request_id, "/status"), "response_url": self._queue_url(value.get("response_url"), model, request_id), "model": model}

    def poll(self, model: str, request_id: str) -> dict:
        value, _ = self._json_request("GET", self._request_url(model, request_id, "/status"), headers=self._headers())
        status = value.get("status")
        if status not in ("IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"):
            raise ProviderError("fal devolvió un estado desconocido.", code="invalid_response")
        result = {"status": status, "request_id": request_id}
        if isinstance(value.get("queue_position"), int):
            result["queue_position"] = value["queue_position"]
        return result

    def result(self, model: str, request_id: str) -> dict:
        value, _ = self._json_request("GET", self._request_url(model, request_id), headers=self._headers())
        if not isinstance(value.get("video"), dict) and not isinstance(value.get("images"), list):
            raise ProviderError("fal no devolvió el vídeo o la imagen esperados.", code="missing_output")
        return {key: value[key] for key in ("video", "images", "seed", "has_nsfw_concepts") if key in value}

    @staticmethod
    def _media_url(value: Any) -> str:
        if not _safe_https(value):
            raise ProviderError("La dirección del recurso generado no es válida.", code="invalid_media_url")
        p = urlsplit(value)
        host = p.hostname or ""
        if not (host in ("fal.media", "fal.run", "fal.ai", "storage.googleapis.com") or host.endswith((".fal.media", ".fal.run", ".fal.ai"))):
            raise ProviderError("El recurso generado está en un dominio que el estudio no reconoce.", code="untrusted_media_url")
        return value

    def _download(self, item: dict, destination: Path | str, media_type: str) -> dict:
        if not isinstance(item, dict):
            raise ProviderError("No se ha encontrado el recurso generado.", code="missing_output")
        url = self._media_url(item.get("url"))
        destination = Path(destination).resolve()
        if destination.exists():
            raise ProviderError("Ya existe un archivo en el destino; se conserva el original.", code="destination_exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = None
        for _ in range(4):
            try:
                # Keys are deliberately supplied per API call, never as session
                # defaults. CDN calls receive no Authorization or xi-api-key.
                response = self._session.request("GET", url, headers={"Accept": f"{media_type}/*"}, timeout=(10, 120), allow_redirects=False, stream=True)
            except requests.RequestException:
                raise ProviderError("No se pudo descargar el recurso generado.", code="download_error") from None
            if 300 <= response.status_code < 400:
                location = response.headers.get("Location") or response.headers.get("location")
                response.close()
                if not isinstance(location, str):
                    raise ProviderError("La descarga devolvió una redirección inválida.", code="invalid_media_url")
                url = self._media_url(urljoin(url, location))
                continue
            break
        else:
            raise ProviderError("La descarga devolvió demasiadas redirecciones.", code="download_error")
        if not 200 <= response.status_code < 300:
            response.close()
            raise _http_error(response.status_code, "fal", False)
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type and not content_type.startswith(f"{media_type}/") and content_type not in ("application/octet-stream", "binary/octet-stream"):
            response.close()
            raise ProviderError("La descarga no contiene el tipo de archivo esperado.", code="invalid_media")
        limit = _MAX_MEDIA_BYTES if media_type == "video" else _MAX_AUDIO_BYTES
        try:
            length = int(response.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            length = 0
        if length > limit:
            response.close()
            raise ProviderError("El archivo generado supera el tamaño permitido.", code="media_too_large")
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        total = 0
        digest = hashlib.sha256()
        prefix = b""
        try:
            with os.fdopen(fd, "wb") as stream:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise ProviderError("El archivo generado supera el tamaño permitido.", code="media_too_large")
                    if len(prefix) < 64:
                        prefix += chunk[:64-len(prefix)]
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            valid = b"ftyp" in prefix[:32] if media_type == "video" else prefix.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP")
            if total == 0 or not valid:
                raise ProviderError("El archivo descargado no tiene un formato reconocible.", code="invalid_media")
            # link is atomic and refuses an existing destination, including a
            # file created by another worker after the initial existence check.
            os.link(temporary, destination)
            return {"path": str(destination), "bytes": total, "sha256": digest.hexdigest(), "content_type": content_type, "source_url": url}
        except requests.RequestException:
            raise ProviderError("La descarga se interrumpió; se conserva la generación en el proveedor.", code="download_error") from None
        except OSError:
            raise ProviderError("No se pudo guardar el recurso; revisa el destino sin volver a generarlo.", code="save_error") from None
        finally:
            response.close()
            if os.path.exists(temporary):
                os.unlink(temporary)

    def download_video(self, result: dict, destination: Path | str) -> dict:
        return self._download(result.get("video"), destination, "video")

    def download_image(self, result: dict, destination: Path | str) -> dict:
        images = result.get("images")
        if not isinstance(images, list) or not images:
            raise ProviderError("fal no devolvió una imagen.", code="missing_output")
        return self._download(images[0], destination, "image")
