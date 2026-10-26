"""Deterministic editorial planning and measurable local render checks.

Technical validation deliberately cannot certify character identity, believable
hands, correct lip-sync or artistic continuity. A separate creative review is
always required before a render is marked ready for delivery.
"""
from __future__ import annotations

import copy
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


STYLE_PATH = Path(__file__).resolve().parents[2] / "assets" / "video_studio" / "style.json"
# quality.py is app/video_studio/quality.py; project root is parents[2].
MODEL_PRICES = {
    "seedance_fast": {"usd_per_second": 0.0216, "min_duration": 2, "max_duration": 12, "integer_duration": True, "duration_allowance": 0.0},
    "h3_turbo": {"usd_per_second": 0.04, "min_duration": 5, "max_duration": 15, "integer_duration": False, "duration_allowance": 0.7},
}
REVIEW_CATEGORIES = ["identity", "hands", "screen", "subtitles", "audio", "continuity"]
ROLE_WORDS = {
    "hook": {"hook", "problem", "failure", "fracaso", "frustrado", "opening", "apertura"},
    "problem": {"problem", "failure", "fracaso", "frustrado", "opening", "apertura"},
    "work": {"work", "working", "trabajo", "fracaso", "failure"},
    "screen": {"screen", "web", "web_reveal", "screen_reveal", "pantalla", "capture", "captura", "real_web", "website", "real_screen", "discovery"},
    "research": {"research", "investigacion", "investigación", "comparison", "comparar"},
    "resolution": {"resolution", "success", "office", "exito", "éxito", "hug", "abrazo", "ending", "family"},
}
ROLE_ACTIONS = {
    "hook": "Show a concise expressive reaction by the adult protagonist that introduces the problem. His mouth is relaxed; narration is off-screen.",
    "problem": "The adult protagonist struggles with an unclear product choice at his desk. Show concern through posture and gaze; narration is off-screen.",
    "work": "The adult protagonist works at a real desk, reviewing notes. Keep the established room and clothing, natural hands, no readable generated interface.",
    "research": "The adult protagonist compares opportunities with focused, purposeful gestures. Keep the laptop physically connected and the room consistent; narration is off-screen.",
    "resolution": "The adult protagonist relaxes with a confident, natural smile after making a considered decision. Finish a complete gesture naturally. No revenue figures or ending brand card.",
}


def default_style() -> dict[str, Any]:
    return json.loads(STYLE_PATH.read_text(encoding="utf-8"))


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} debe ser un número válido.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} debe ser un número válido.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} debe ser un número finito.")
    return result


def _issue(code: str, message: str, severity: str = "error", **details: Any) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, **details}


def _asset_words(asset: dict[str, Any]) -> set[str]:
    values = [str(asset.get(key, "")) for key in ("id", "name", "title", "role", "reference_for")]
    tags = asset.get("tags", [])
    values.extend(tags if isinstance(tags, list) else [str(tags)])
    return set(re.findall(r"[\wáéíóúñ]+", " ".join(map(str, values)).lower()))


def _approved(asset: dict[str, Any]) -> bool:
    return asset.get("approved") is True or asset.get("status") in {"approved", "accepted"}


def _is_video(asset: dict[str, Any]) -> bool:
    return asset.get("media_kind", asset.get("kind", asset.get("type"))) in {"video", "clip", "screen_clip"} or str(asset.get("mime_type", "")).startswith("video/")


def _is_image(asset: dict[str, Any]) -> bool:
    return asset.get("media_kind", asset.get("kind", asset.get("type"))) in {"image", "reference", "character_reference", "scene_reference"} or str(asset.get("mime_type", "")).startswith("image/")


def _asset_bounds(asset: dict[str, Any]) -> tuple[float, float]:
    try:
        start = float(asset.get("usable_in", asset.get("source_in", 0)))
        end = float(asset.get("usable_out", asset.get("source_out", asset.get("duration", 0))))
    except (TypeError, ValueError):
        return 0.0, 0.0
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        return 0.0, 0.0
    return start, end


def _find_video(library: list[dict[str, Any]], role: str, duration: float, used: set[str]) -> dict[str, Any] | None:
    matches = []
    for asset in library:
        if not asset.get("id") or str(asset["id"]) in used or not _approved(asset) or not _is_video(asset):
            continue
        start, end = _asset_bounds(asset)
        if end - start + 0.02 < duration:
            continue
        score = len(_asset_words(asset) & ROLE_WORDS[role])
        if score:
            matches.append((score, str(asset["id"]), asset))
    return sorted(matches, key=lambda item: (-item[0], item[1]))[0][2] if matches else None


def _reference(library: list[dict[str, Any]], role: str) -> str | None:
    images = [asset for asset in library if asset.get("id") and _approved(asset) and _is_image(asset)]
    # A reference is mandatory, but a scene reference is preferred to a head crop.
    if not images:
        return None
    images.sort(key=lambda asset: (-len(_asset_words(asset) & (ROLE_WORDS[role] | {"scene", "protagonist", "character"})), str(asset["id"])))
    return str(images[0]["id"])


def _prompt(role: str, concept: str, style: dict[str, Any]) -> str:
    visual = style.get("visual", {})
    character = style.get("characters", {}).get("protagonist", {}).get("description", "Adult protagonist from the approved reference.")
    return " ".join([
        str(visual.get("medium", "cinematic expressive 3D family animation")) + ".",
        character,
        str(visual.get("lighting", "")),
        str(visual.get("camera", "")),
        ROLE_ACTIONS.get(role, ROLE_ACTIONS["research"]),
        "Narrative context: " + concept[:1500] + ".",
        "Generate the entire integrated scene. Preserve reference identity and style. No readable text or subtitles; the editor adds exact text later.",
        "Avoid: " + str(visual.get("negative_prompt", "")) + ".",
    ])


def build_plan(brief: dict[str, Any], library: list[dict[str, Any]], style: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an editable plan without network calls, new claims or paid work.

    ``library`` entries need id, kind/type, duration, tags and approved/status.
    Optional usable_in/usable_out bounds prevent reusing rejected source tails.
    The returned budget is an estimate; callers must enforce their actual ledger.
    """
    style = copy.deepcopy(style or default_style())
    output = style.get("output", {})
    fps = int(output.get("fps", 24))
    duration = _finite_number(brief.get("duration", 15), "La duración")
    if not output.get("min_duration", 8) <= duration <= output.get("max_duration", 40):
        raise ValueError("La duración debe estar entre 8 y 40 segundos.")
    duration = round(duration * fps) / fps
    budget = _finite_number(brief.get("budget_usd", 2), "El presupuesto")
    if budget <= 0 or budget > 100:
        raise ValueError("El presupuesto debe ser mayor que cero y como máximo 100 USD.")
    model = str(brief.get("model", "seedance_fast"))
    if model not in MODEL_PRICES:
        raise ValueError("Elige un modelo disponible en el estudio.")
    format_name = str(brief.get("format", "demo"))
    if format_name not in {"hook", "demo", "story"}:
        raise ValueError("El formato debe ser hook, demo o story.")
    max_attempts = int(brief.get("max_attempts", 2))
    if max_attempts not in {1, 2, 3}:
        raise ValueError("Se permiten entre una y tres tomas por escena.")
    concept = str(brief.get("concept", "Comparar productos con criterio antes de decidir")).strip()
    scripts = {
        "hook": "Antes elegía a ciegas. Ahora comparo antes de decidir.",
        "demo": "Antes de elegir un producto, comparo demanda, competencia y margen.",
        "story": "Probé sin saber qué buscar. Empecé a comparar demanda, competencia y margen. Ahora elijo con un criterio.",
    }
    script = str(brief.get("script", "")).strip() or scripts[format_name]
    voice_role = str(brief.get("voice_role", "narrator"))
    if voice_role == "protagonist":
        voice_role = "son"
    if voice_role not in style.get("voice", {}).get("roles", ["narrator", "son", "mother"]):
        raise ValueError("Elige una voz de narrador, chico o madre.")

    roles = ["hook", "screen", "resolution"] if duration <= 12 or format_name == "hook" else ["hook", "screen", "research", "resolution"]
    if format_name == "story" and duration >= 18:
        roles = ["problem", "work", "screen", "research", "resolution"]
    # A long hook still uses short shots rather than stretching one generated clip.
    while (duration - float(style.get("screen", {}).get("duration", 1))) / (len(roles) - 1) > MODEL_PRICES[model]["max_duration"]:
        roles.insert(-1, "research")
    screen_frames = round(float(style.get("screen", {}).get("duration", 1)) * fps)
    total_frames = round(duration * fps)
    other_count = len(roles) - 1
    base_frames, remainder = divmod(total_frames - screen_frames, other_count)
    other_index = 0
    cursor_frames = 0
    shots: list[dict[str, Any]] = []
    used: set[str] = set()
    pricing = MODEL_PRICES[model]
    first_take_cost = 0.0
    reserved_video_cost = 0.0
    reuse_library = brief.get("reuse_library", False) is True
    requested_reference = str(brief.get("reference_asset_id", "")).strip()
    explicit_reference = next((asset for asset in library if str(asset.get("id", "")) == requested_reference and _is_image(asset) and _approved(asset)), None)

    for index, role in enumerate(roles):
        frames = screen_frames if role == "screen" else base_frames + (1 if other_index < remainder else 0)
        if role != "screen":
            other_index += 1
        shot_duration = frames / fps
        asset = _find_video(library, role, shot_duration, used) if reuse_library or role == "screen" else None
        shot: dict[str, Any] = {
            "id": f"shot-{index + 1:02d}", "role": role, "duration": shot_duration,
            "timeline_start": cursor_frames / fps, "timeline_end": (cursor_frames + frames) / fps,
            "mode": "library" if asset or role == "screen" else "generate",
            "asset_id": str(asset["id"]) if asset else None,
            "source_in": _asset_bounds(asset)[0] if asset else 0.0,
            "source_out": (_asset_bounds(asset)[0] if asset else 0.0) + shot_duration,
            "prompt": "Use the approved real website composite inside the computer screen, preserving exact text and design." if role == "screen" else _prompt(role, concept, style),
            "reference_asset_id": None if role == "screen" else (str(explicit_reference["id"]) if explicit_reference else (None if requested_reference else _reference(library, role))),
            "dialogue_visible": False, "requires_lipsync_review": False,
            "native_audio": "mute", "transition": "motivated_cut",
        }
        if asset:
            used.add(str(asset["id"]))
            shot["source_duration"] = _asset_bounds(asset)[1]
            # Existing on-camera speech cannot silently pass as a new ElevenLabs lip-sync.
            if asset.get("visible_speech") or asset.get("contains_dialogue"):
                shot["requires_lipsync_review"] = True
        if role == "screen":
            shot["real_web"] = True
            shot["screen_method"] = style.get("screen", {}).get("method")
        if shot["mode"] == "generate":
            billed_duration = max(pricing["min_duration"], shot_duration)
            if pricing["integer_duration"]:
                billed_duration = math.ceil(billed_duration)
            billed_duration = min(pricing["max_duration"], billed_duration)
            shot["generation_duration"] = billed_duration
            shot["model"] = model
            shot["prepare_integrated_scene_image"] = False
            shot["image_preparation_status"] = "approved_reference" if shot["reference_asset_id"] else "missing_reference"
            shot["estimated_cost_usd"] = round(billed_duration * pricing["usd_per_second"], 4)
            first_take_cost += shot["estimated_cost_usd"]
            reserved_video_cost += (billed_duration + pricing["duration_allowance"]) * pricing["usd_per_second"] * max_attempts
        cursor_frames += frames
        shots.append(shot)

    words = len(re.findall(r"\b[\wáéíóúñ]+\b", script, re.UNICODE))
    voice = style.get("voice", {})
    narration_start = float(voice.get("speech_start_padding", 0.35))
    voice_estimate = words / float(voice.get("estimated_words_per_second", 2.7))
    # New scenes require an imported, approved integrated image. No image
    # generation is implemented or silently included in the cost of this plan.
    image_estimate = 0.0
    plan: dict[str, Any] = {
        "title": str(brief.get("title", "Nuevo vídeo de Dropradar")).strip()[:160],
        "concept": concept[:1500], "format": format_name,
        "target_duration": duration, "duration": duration, "fps": fps,
        "width": int(output.get("width", 1080)), "height": int(output.get("height", 1920)),
        "model": model, "style_id": style.get("id"), "style_version": style.get("version"),
        "status": "draft", "shots": shots,
        "technical_preview": brief.get("technical_preview", False) is True,
        "narrations": [{"id": "narration-01", "text": script, "voice_role": voice_role, "start": narration_start, "end": None, "estimated_duration": round(voice_estimate, 3), "mode": "voiceover", "preserve_complete_words": True}],
        "captions": copy.deepcopy(style.get("captions", {})),
        "budget_usd": budget, "max_attempts": max_attempts,
        "estimated_cost_usd": round(first_take_cost + image_estimate, 4),
        "estimated_max_cost_usd": round(reserved_video_cost + image_estimate * max_attempts, 4),
        "cost_estimate": {"video_first_take_usd": round(first_take_cost, 4), "scene_images_usd": round(image_estimate, 4), "image_preparation": "Referencia integrada existente y aprobada; los nuevos escenarios necesitan importar otra referencia aprobada.", "voice": "ElevenLabs: según caracteres, voz y plan; consultar antes de generar", "includes_voice_cost": False, "taxes_included": False, "pricing_date": "2026-10-26", "note": "Estimación de generación de vídeo; no es una autorización de gasto ni garantiza una toma aceptada."},
        "review_checklist": [{"category": category, "passed": None, "note": ""} for category in REVIEW_CATEGORIES],
        "creative_review_required": True, "ready_for_delivery": False,
    }
    plan["issues"] = validate_plan(plan, style)
    return plan


def validate_plan(plan: dict[str, Any], style: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    style = style or default_style()
    issues: list[dict[str, Any]] = []
    try:
        duration = _finite_number(plan.get("duration", plan.get("target_duration")), "La duración")
        fps = _finite_number(plan.get("fps", 24), "Los fotogramas por segundo")
    except ValueError as exc:
        return [_issue("invalid_timing", str(exc))]
    if duration <= 0 or fps <= 0:
        return [_issue("invalid_timing", "La duración y los fotogramas por segundo deben ser positivos.")]
    if not style["output"]["min_duration"] <= duration <= style["output"]["max_duration"]:
        issues.append(_issue("duration_range", "La duración está fuera del intervalo de 8 a 40 segundos."))
    if int(fps) != style["output"]["fps"]:
        issues.append(_issue("fps_mismatch", "El montaje debe conservar los 24 fotogramas por segundo del estilo."))
    shots = plan.get("shots", [])
    if not shots:
        issues.append(_issue("missing_shots", "El vídeo necesita al menos un plano."))
    cursor = 0.0
    screen_count = 0
    for shot in shots:
        shot_id = str(shot.get("id", "plano"))
        try:
            length = _finite_number(shot.get("duration"), "La duración del plano")
            start = _finite_number(shot.get("timeline_start", cursor), "El inicio del plano")
            source_start = _finite_number(shot.get("source_in", 0), "El punto de entrada")
            source_end = _finite_number(shot.get("source_out", source_start + length), "El punto de salida")
        except ValueError as exc:
            issues.append(_issue("invalid_shot_timing", str(exc), shot_id=shot_id))
            continue
        if length <= 0 or source_start < 0 or source_end <= source_start:
            issues.append(_issue("invalid_shot_range", "Un plano tiene un intervalo vacío o negativo.", shot_id=shot_id))
        if abs(start - cursor) > 1 / fps:
            issues.append(_issue("timeline_gap_or_overlap", "Hay un hueco o solapamiento inesperado entre planos.", shot_id=shot_id))
        if abs((source_end - source_start) - length) > 1 / fps:
            issues.append(_issue("source_timing_mismatch", "La duración útil del archivo no coincide con el plano; no se permite congelarlo ni acelerar la voz.", shot_id=shot_id))
        if shot.get("mode") not in {"library", "generate"}:
            issues.append(_issue("invalid_shot_mode", "El plano debe usar biblioteca o generación.", shot_id=shot_id))
        if shot.get("mode") == "library" and not shot.get("asset_id"):
            issues.append(_issue("missing_library_asset", "Falta seleccionar un archivo aprobado de la biblioteca.", shot_id=shot_id))
        if shot.get("source_duration") is not None and source_end > float(shot["source_duration"]) + 1 / fps:
            issues.append(_issue("source_too_short", "El plano pide más vídeo del que contiene su archivo.", shot_id=shot_id))
        if shot.get("mode") == "generate":
            if not shot.get("reference_asset_id"):
                issues.append(_issue("missing_reference", "Falta una referencia aprobada para conservar el personaje y el estilo.", shot_id=shot_id))
            if shot.get("generation_duration", 0) + 1 / fps < length:
                issues.append(_issue("generation_too_short", "La generación solicitada no cubre la duración del plano.", shot_id=shot_id))
        if (shot.get("dialogue_visible") or shot.get("visible_lip_dialogue") or shot.get("requires_lipsync_review")) and shot.get("lipsync_approved") is not True:
            severity = "warning" if plan.get("technical_preview") is True else "error"
            issues.append(_issue("lipsync_review", "La voz visible necesita sincronización labial revisada antes de aprobar este plano.", severity, shot_id=shot_id))
        if shot.get("role") == "screen":
            screen_count += 1
            if shot.get("mode") != "library" or not shot.get("real_web"):
                issues.append(_issue("generated_web_forbidden", "La pantalla debe mostrar una captura real compuesta dentro del ordenador.", shot_id=shot_id))
            if length > style.get("screen", {}).get("max_duration", 1.5) + 1 / fps:
                issues.append(_issue("screen_too_long", "La aparición de la web supera la duración breve del estilo.", shot_id=shot_id))
        cursor += length
    if abs(cursor - duration) > 1 / fps:
        issues.append(_issue("timeline_duration_mismatch", "La suma de los planos no coincide con la duración final."))
    if style.get("screen", {}).get("required") and screen_count != 1:
        issues.append(_issue("screen_count", "Debe aparecer una vez la pantalla real, de forma breve y nítida."))

    voice_style = style.get("voice", {})
    ending_pad = float(voice_style.get("speech_end_padding", 0.45))
    for narration in plan.get("narrations", []):
        text = str(narration.get("text", ""))
        for brand in style.get("content", {}).get("spoken_brand_forbidden", []):
            if re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", text, re.I):
                issues.append(_issue("spoken_brand", "La locución no debe pronunciar Dropradar; la marca aparece en la web."))
        if re.search(r"(?:ingresos|ganancias|beneficios|rentabilidad)\s+(?:están\s+)?garantizad[oa]s?|(?:ganarás|ganarás seguro|te harás rico)", text, re.I):
            issues.append(_issue("guaranteed_income", "El guion contiene una promesa de ingresos garantizados."))
        if re.search(r"(?:\d[\d.,]*\s*(?:€|euros|dólares|USD)|[€$]\s*\d)", text, re.I):
            issues.append(_issue("money_claim_review", "Revisar cualquier cifra monetaria: no presentar una cifra inventada como resultado real.", "warning"))
        try:
            speech_start = _finite_number(narration.get("start", 0), "El inicio de la voz")
            actual_duration = narration.get("duration", narration.get("audio_duration"))
            estimated_duration = _finite_number(actual_duration if actual_duration is not None else narration.get("estimated_duration", 0), "La duración de la voz")
        except ValueError as exc:
            issues.append(_issue("invalid_speech_timing", str(exc)))
            continue
        if speech_start < 0 or estimated_duration < 0:
            issues.append(_issue("invalid_speech_timing", "La locución tiene tiempos negativos."))
        if speech_start + estimated_duration + ending_pad > duration + 1 / fps:
            issues.append(_issue("speech_would_be_cut", "La locución no cabe completa: acorta el texto o alarga el vídeo antes de generar o montar."))
        if actual_duration is None:
            issues.append(_issue("speech_duration_estimated", "La duración de la locución es provisional hasta recibir el audio de ElevenLabs.", "info"))
        if narration.get("end") is not None and float(narration["end"]) + 1 / fps < speech_start + estimated_duration:
            issues.append(_issue("speech_trim_forbidden", "La salida de la locución cortaría parte de la voz."))
    try:
        cost = _finite_number(plan.get("estimated_max_cost_usd", plan.get("estimated_cost_usd", 0)), "El coste")
        budget = _finite_number(plan.get("budget_usd", 0), "El presupuesto")
        if cost > budget:
            issues.append(_issue("budget_exceeded", "La reserva estimada de vídeo e imágenes supera el límite del vídeo."))
    except ValueError as exc:
        issues.append(_issue("invalid_budget", str(exc)))
    captions = plan.get("captions", {})
    if captions.get("outline", 0) or captions.get("shadow", 0):
        issues.append(_issue("caption_style", "Los subtítulos deben ser blancos y no llevar borde ni sombra."))
    if captions.get("max_lines", 2) > 2:
        issues.append(_issue("caption_lines", "Los subtítulos no deben superar dos líneas."))
    return issues


def _ffmpeg_binary(explicit: str | Path | None) -> str:
    if explicit:
        return str(explicit)
    located = shutil.which("ffmpeg")
    if located:
        return located
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("No se encuentra FFmpeg para revisar el archivo.") from exc


def _parse_media_log(log: str) -> dict[str, Any]:
    # Read input header only; output frame rate must not hide an input mismatch.
    input_header = log.split("Output #", 1)[0]
    metadata: dict[str, Any] = {}
    match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", input_header)
    if match:
        metadata["duration"] = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    stream = re.search(r"Stream[^\n]*Video:[^\n]*", input_header)
    if stream:
        dimensions = re.search(r"(?<![\d:])(\d{2,5})x(\d{2,5})(?:[\s,\[]|$)", stream[0])
        if dimensions:
            metadata.update(width=int(dimensions[1]), height=int(dimensions[2]))
        fps = re.search(r"([\d.]+)\s+fps\b", stream[0])
        if fps:
            metadata["fps"] = float(fps[1])
        codec = re.search(r"Video:\s*([^ ,]+)", stream[0])
        if codec:
            metadata["video_codec"] = codec[1]
    metadata["has_audio"] = bool(re.search(r"Stream[^\n]*Audio:", input_header))
    black = []
    for start, end, duration in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", log):
        black.append({"start": float(start), "end": float(end), "duration": float(duration)})
    silence_starts = [float(value) for value in re.findall(r"silence_start:\s*([\d.]+)", log)]
    silence_ends = [(float(end), float(duration)) for end, duration in re.findall(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", log)]
    silence = [{"start": max(0, end - length), "end": end, "duration": length} for end, length in silence_ends]
    if len(silence_starts) > len(silence_ends) and metadata.get("duration") is not None:
        start = silence_starts[-1]
        silence.append({"start": start, "end": metadata["duration"], "duration": max(0, metadata["duration"] - start)})
    metadata["black_intervals"] = black
    metadata["silence_intervals"] = silence
    peaks = re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", log)
    if peaks:
        peak = max(float(value) for value in peaks)
        metadata["audio_peak_dbfs"] = peak if math.isfinite(peak) else None
    return metadata


def validate_render(path: str | Path, plan: dict[str, Any], ffmpeg_path: str | Path | None = None) -> dict[str, Any]:
    """Fully decode a render and flag objective problems, never auto-approve art.

    Black frames and low-level audio are review warnings: they can be intentional
    in a night scene or ending. No automatic identity/lip-sync claim is made.
    """
    file_path = Path(path)
    report: dict[str, Any] = {"technical_passed": False, "ready_for_delivery": False, "review_required": True, "checks": [], "issues": [], "metadata": {}, "creative_checks": [{"category": key, "passed": None} for key in REVIEW_CATEGORIES]}
    if not file_path.is_file() or file_path.stat().st_size < 1024:
        report["issues"].append(_issue("missing_render", "El MP4 no existe o está vacío."))
        return report
    try:
        command = [_ffmpeg_binary(ffmpeg_path), "-hide_banner", "-nostdin", "-i", str(file_path), "-map", "0:v:0", "-map", "0:a:0?", "-vf", "blackdetect=d=0.12:pix_th=0.02", "-af", "silencedetect=n=-50dB:d=0.4,astats=metadata=0:reset=0", "-f", "null", "-"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report["issues"].append(_issue("inspection_unavailable", f"No se pudo completar la revisión técnica: {type(exc).__name__}."))
        return report
    metadata = _parse_media_log(result.stderr)
    metadata["bytes"] = file_path.stat().st_size
    report["metadata"] = metadata
    decode_ok = result.returncode == 0
    report["checks"].append({"name": "full_decode", "passed": decode_ok})
    if not decode_ok:
        report["issues"].append(_issue("decode_error", "El vídeo no se puede decodificar completamente."))
    for key, expected in (("width", plan.get("width", 1080)), ("height", plan.get("height", 1920))):
        passed = metadata.get(key) == expected
        report["checks"].append({"name": key, "passed": passed, "expected": expected, "actual": metadata.get(key)})
        if not passed:
            report["issues"].append(_issue("resolution_mismatch", "La exportación no coincide con la resolución vertical prevista.", dimension=key))
    expected_fps = float(plan.get("fps", 24))
    fps_ok = metadata.get("fps") is not None and abs(metadata["fps"] - expected_fps) <= 0.02
    report["checks"].append({"name": "fps", "passed": fps_ok, "expected": expected_fps, "actual": metadata.get("fps")})
    if not fps_ok:
        report["issues"].append(_issue("fps_mismatch", "La frecuencia de imágenes no coincide con la del montaje."))
    expected_duration = float(plan.get("duration", plan.get("target_duration", 0)))
    actual_duration = metadata.get("duration", 0)
    duration_ok = abs(actual_duration - expected_duration) <= max(0.09, 2 / expected_fps)
    report["checks"].append({"name": "duration", "passed": duration_ok, "expected": expected_duration, "actual": actual_duration})
    if not duration_ok:
        report["issues"].append(_issue("render_duration_mismatch", "La duración del MP4 no coincide con el montaje previsto."))
    if plan.get("narrations") and not metadata.get("has_audio"):
        report["issues"].append(_issue("missing_audio", "El vídeo tiene locución prevista pero no contiene audio."))
    if metadata.get("audio_peak_dbfs") is not None and metadata["audio_peak_dbfs"] >= -0.1:
        report["issues"].append(_issue("audio_peak_review", "El audio se acerca al máximo digital; revisar saturación y reducir el nivel si procede.", "warning"))
    if metadata.get("black_intervals"):
        report["issues"].append(_issue("black_frames_review", "Hay intervalos muy oscuros; comprobar que pertenecen a la escena y no son fotogramas vacíos.", "warning", intervals=metadata["black_intervals"]))
    if metadata.get("silence_intervals"):
        report["issues"].append(_issue("silence_review", "Hay pausas de audio; revisar que sean naturales y no cortes de voz.", "warning", intervals=metadata["silence_intervals"]))
    # Actual timestamps supersede provisional words-per-second estimates.
    for narration in plan.get("narrations", []):
        audio_duration = narration.get("duration", narration.get("audio_duration"))
        start = float(narration.get("start", 0))
        if audio_duration is not None and start + float(audio_duration) > actual_duration + 1 / expected_fps:
            report["issues"].append(_issue("speech_cut_in_render", "El final del vídeo corta la duración real de la locución."))
        alignment = narration.get("alignment", {}) or {}
        ends = alignment.get("character_end_times_seconds", [])
        if ends and start + max(float(value) for value in ends) > actual_duration + 1 / expected_fps:
            report["issues"].append(_issue("word_cut_in_render", "Las marcas de ElevenLabs indican una palabra cortada al final del vídeo."))
    report["technical_passed"] = not any(issue["severity"] == "error" for issue in report["issues"])
    return report
