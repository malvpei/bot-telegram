from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from pathlib import Path

from .providers import ElevenLabsClient, FalClient, ProviderError, SEEDANCE_FAST, H3_MAX_TURBO
from .quality import default_style, validate_plan, validate_render
from .rendering import media_duration, render_plan, ffmpeg
from .store import StudioStore

MODELS = {"seedance_fast": SEEDANCE_FAST, "h3_turbo": H3_MAX_TURBO}
PAID_VOICE_TIERS = {"starter", "creator", "pro", "scale", "business", "enterprise", "growing_business"}


def voice_commercial_ready(status: dict) -> bool:
    return status.get("connected") is True and str(status.get("tier", "")).lower() in PAID_VOICE_TIERS


def approved_budget(job: dict, requested: float) -> float:
    if isinstance(requested, bool):
        raise ValueError("Indica un límite de gasto válido.")
    requested = float(requested)
    if not math.isfinite(requested) or requested <= 0 or requested > float(job["plan"]["budget_usd"]):
        raise ValueError("El límite debe ser positivo y no superar el presupuesto del plan.")
    reserve = float(job["plan"].get("estimated_max_cost_usd", job["plan"].get("estimated_cost_usd", 0)))
    if reserve > requested + 1e-6:
        raise ValueError(f"El margen estimado de vídeo es {reserve:.2f} USD y supera el límite autorizado.")
    return requested


def _voice_settings(style: dict) -> dict:
    voice = style["voice"]
    return {name: voice[name] for name in ("stability", "similarity_boost", "style", "speed", "use_speaker_boost") if name in voice}


def run_generation(store: StudioStore, job_id: str, max_cost_usd: float) -> None:
    """One attempt per shot, persisted before each billable request; no auto-retry."""
    try:
        job = store.job(job_id)
        plan = job["plan"]
        approved_budget(job, max_cost_usd)
        issues = [issue for issue in validate_plan(plan) if issue["severity"] == "error"]
        if issues:
            raise ValueError(issues[0]["message"])
        style = default_style()
        eleven = ElevenLabsClient(store.credential("elevenlabs"))
        account = eleven.status()
        if not voice_commercial_ready(account):
            raise ValueError("ElevenLabs está conectado, pero este plan no tiene verificada la licencia comercial. Las pruebas internas y la biblioteca siguen disponibles.")
        cast = store.settings().get("voice_cast", {})
        narration = plan["narrations"][0]
        voice_id = cast.get(narration["voice_role"])
        if not voice_id:
            raise ValueError("Asigna y revisa una voz para este personaje antes de generar.")
        remaining = account.get("remaining_characters")
        if remaining is None or len(narration["text"]) > remaining:
            raise ValueError("No hay cuota de voz incluida suficiente verificada. No se iniciará consumo adicional.")
        fal = FalClient(store.credential("fal"))
        store.event(job_id, "Creando una locución completa con la voz fija seleccionada.", status="generating_voice", progress=10,
                    authorized_max_cost_usd=max_cost_usd, voice_character_budget=len(narration["text"]))
        voice = eleven.synthesize(narration["text"], voice_id, model_id=style["voice"]["model_id"],
                                  settings=_voice_settings(style), output_dir=store.directory / "cache" / "voices")
        voice_length = media_duration(Path(voice["audio_path"]))
        if voice_length + .45 > plan["duration"]:
            store.update_job(job_id, {"voice": voice})
            raise ValueError(f"La voz completa necesita {voice_length + .45:.1f} s. Amplía el vídeo o acorta el texto antes de generar imágenes; la voz ya está guardada.")
        narration.update({"start": .25, "duration": voice_length, "audio_duration": voice_length,
                          "end": .25 + voice_length, "complete": True})
        store.update_job(job_id, {"voice": voice, "plan": plan})
        sources = []
        directory = store.job_dir(job_id)
        for index, shot in enumerate(plan["shots"]):
            if shot["mode"] == "library":
                asset = store.asset(shot["asset_id"])
                sources.append({"path": asset["path"], "in": shot.get("source_in", 0), "duration": shot["duration"]})
                continue
            reference = store.asset(shot["reference_asset_id"])
            if reference.get("approved") is not True or reference.get("kind") != "image" or "real_screen" in reference.get("tags", []):
                raise ValueError("La animación necesita una referencia integrada aprobada del personaje y su entorno.")
            source = Path(reference["path"])
            mime = "image/png" if source.suffix.lower() == ".png" else "image/jpeg"
            image = f"data:{mime};base64," + base64.b64encode(source.read_bytes()).decode()
            model = MODELS[plan["model"]]
            payload = {"prompt": shot["prompt"], "image_url": image, "duration": shot["generation_duration"]}
            if plan["model"] == "seedance_fast":
                payload.update({"resolution": "720p", "aspect_ratio": "9:16"})
                payload["duration"] = str(int(shot["generation_duration"]))
            else:
                payload["resolution"] = "768P"
            request_hash = hashlib.sha256(json.dumps({"model": model, "payload": payload}, sort_keys=True).encode()).hexdigest()
            current = store.job(job_id)
            requests = current.get("generation_requests", {})
            saved = requests.get(shot["id"])
            if saved and saved.get("hash") != request_hash:
                raise ValueError("La solicitud de este plano cambió. Crea otra producción para conservar el historial y el presupuesto.")
            generated = directory / (shot["id"] + ".mp4")
            if saved and saved.get("state") == "downloaded" and generated.is_file():
                sources.append({"path": str(generated), "duration": shot["duration"]})
                continue
            if saved and not saved.get("request_id"):
                raise ValueError("Hay un envío pendiente de comprobar. No se repetirá automáticamente para evitar cargos duplicados.")
            if not saved:
                rate = .0216 if plan["model"] == "seedance_fast" else .04
                reserve = (float(shot["generation_duration"]) + (.7 if plan["model"] == "h3_turbo" else 0)) * rate
                spent = float(current.get("reserved_cost_usd", 0))
                if spent + reserve > max_cost_usd + 1e-6:
                    raise ValueError("El siguiente plano superaría el límite de gasto.")
                saved = {"hash": request_hash, "model": model, "state": "submitting", "reserved_usd": reserve}
                requests[shot["id"]] = saved
                store.update_job(job_id, {"generation_requests": requests, "reserved_cost_usd": round(spent + reserve, 6)})
                submitted = fal.submit(model, payload)
                saved.update(submitted)
                saved["state"] = "submitted"
                store.update_job(job_id, {"generation_requests": requests})
            store.event(job_id, f"Generando plano {index + 1} de {len(plan['shots'])} con su referencia de estilo.",
                        status="generating_scenes", progress=20 + int(index / len(plan["shots"]) * 45))
            deadline = time.monotonic() + 1200
            while True:
                status = fal.poll(model, saved["request_id"])
                state = str(status.get("status", "")).upper()
                if state == "COMPLETED":
                    break
                if state in ("FAILED", "CANCELLED", "ERROR"):
                    raise ValueError("El proveedor no completó este plano. El historial se conserva para revisarlo.")
                if time.monotonic() >= deadline:
                    raise ValueError("La generación sigue pendiente. Reanuda esta misma producción para consultar su resultado, sin volver a pagar el envío.")
                time.sleep(4)
            result = fal.result(model, saved["request_id"])
            fal.download_video(result, generated)
            saved["state"] = "downloaded"
            saved["path"] = str(generated)
            store.update_job(job_id, {"generation_requests": requests})
            sources.append({"path": str(generated), "duration": shot["duration"]})
        store.event(job_id, "Montando vídeo, voz continua y subtítulos con tiempos reales.", status="rendering", progress=75)
        rendered = render_plan(plan, sources, directory / "render", voice=voice)
        finish_render(store, job_id, plan, rendered, draft=False)
    except (ValueError, ProviderError, OSError) as error:
        store.event(job_id, str(error), status="blocked", progress=0, ready_for_delivery=False)
    except Exception:
        store.event(job_id, "La producción se ha detenido por un error interno. Se conservan los resultados y no se reintenta el consumo automáticamente.", status="error", progress=0, ready_for_delivery=False)


def run_local_preview(store: StudioStore, job_id: str) -> None:
    """Exercise the real renderer with accepted footage; never call it a new ad."""
    try:
        job = store.job(job_id)
        plan = dict(job["plan"])
        duration = float(plan["duration"])
        if duration > 15:
            raise ValueError("El ensayo local usa los 15 segundos disponibles de las escenas aceptadas. Elige 8–15 s o genera planos nuevos.")
        first = min(6.0, (duration - 1) / 2)
        second = duration - first - 1
        if second > 8:
            raise ValueError("La biblioteca de prueba no cubre esta duración sin repetir planos.")
        sources = [{"path": store.asset("scene_success")["path"], "in": .5, "duration": first},
                   {"path": store.asset("screen_reveal")["path"], "in": 0, "duration": 1},
                   {"path": store.asset("scene_family")["path"], "in": 0, "duration": second}]
        plan["technical_preview"] = True
        plan["narrations"] = []
        plan["shots"] = []
        store.event(job_id, "Montando ensayo técnico con escenas existentes, sin voz definitiva ni consumo de API.", status="rendering", progress=20)
        rendered = render_plan(plan, sources, store.job_dir(job_id) / "render_local")
        finish_render(store, job_id, plan, rendered, draft=True)
    except Exception as error:
        store.event(job_id, str(error) if isinstance(error, (ValueError, OSError)) else "El ensayo local no pudo completarse.",
                    status="blocked", progress=0, ready_for_delivery=False)


def finish_render(store: StudioStore, job_id: str, plan: dict, rendered: dict, *, draft: bool) -> None:
    store.event(job_id, "Revisando el archivo completo, sus tiempos y su sonido.", status="checking", progress=90)
    qa = validate_render(Path(rendered["path"]), plan, ffmpeg_path=ffmpeg())
    if draft:
        qa.setdefault("issues", []).append({"severity": "warning", "code": "technical_preview_only",
                                          "message": "Ensayo con material existente y sin locución definitiva. No es un anuncio nuevo terminado."})
    store.update_job(job_id, {"render": rendered, "qa": qa, "technical_preview": draft,
                             "output_path": rendered["path"], "output_url": f"/outputs/{job_id}",
                             "ready_for_delivery": False, "creative_review": None})
    passed = qa.get("technical_passed") is True
    store.event(job_id, "Ensayo técnico disponible para revisar." if draft else
                ("Comprobaciones técnicas superadas. Falta revisar continuidad, gestos, voz y subtítulos." if passed else "El control técnico ha detectado puntos que requieren corrección."),
                status="preview_ready" if draft else ("review_required" if passed else "quality_failed"), progress=100)
