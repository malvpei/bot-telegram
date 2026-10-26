from __future__ import annotations

import argparse
import hashlib
import math
import secrets
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file
from PIL import Image

from .pipeline import approved_budget, run_generation, run_local_preview, voice_commercial_ready
from .providers import ElevenLabsClient, FalClient, ProviderError, SEEDANCE_FAST
from .quality import REVIEW_CATEGORIES, build_plan, default_style, validate_plan
from .store import DATA, ROOT, StudioStore, now, seed_library

ACTIVE = {"queued", "generating_voice", "generating_scenes", "rendering", "checking"}


def create_app(directory: Path | str = DATA, *, seed: bool = True) -> Flask:
    static = Path(__file__).parent / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    app.config.update(MAX_CONTENT_LENGTH=20 * 1024 * 1024, JSON_SORT_KEYS=False)
    app.json.ensure_ascii = False
    store = StudioStore(directory)
    app.config["STUDIO_STORE"] = store
    csrf = secrets.token_urlsafe(32)
    workers: dict[str, threading.Thread] = {}
    worker_lock = threading.Lock()
    if seed:
        seed_library(store)
    # Jobs interrupted by an application restart remain resumable; never re-submit.
    for job in store.jobs():
        if job.get("status") in ACTIVE:
            store.event(job["id"], "La sesión anterior se interrumpió. Los resultados están guardados; revisa la producción antes de reanudar.", status="interrupted", progress=0)

    @app.before_request
    def local_only():
        host = request.host.partition(":")[0].lower()
        if host not in ("127.0.0.1", "localhost", "[::1]"):
            return jsonify(error="Este estudio solo acepta acceso local."), 403
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="Origen no permitido."), 403
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not secrets.compare_digest(request.headers.get("X-Studio-Token", ""), csrf):
                return jsonify(error="Recarga el estudio antes de guardar cambios."), 403

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ValueError)
    @app.errorhandler(ProviderError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(error="No se encontró ese recurso o producción."), 404

    def public_job(job: dict) -> dict:
        # Media is exposed through registered IDs; private source paths are not APIs.
        return {key: value for key, value in job.items() if key not in ("output_path", "generation_requests", "voice")}

    def public_asset(asset: dict) -> dict:
        return {key: value for key, value in asset.items() if key != "path"}

    def connection_states() -> dict:
        checked = store.settings().get("connection_checks", {})
        result = {}
        for provider in ("fal", "elevenlabs"):
            present = bool(store.credential(provider))
            status = checked.get(provider, {})
            result[provider] = {"configured": present, "verified": bool(present and status.get("verified")),
                                "message": "Conexión pendiente" if not present else "Clave guardada; falta comprobar la conexión.", **status}
            result[provider]["configured"] = present
        return result

    @app.get("/")
    def index():
        return send_file(static / "index.html")

    @app.get("/api/bootstrap")
    def bootstrap():
        settings = store.settings()
        connections = connection_states()
        return jsonify(style=default_style(), library=[public_asset(a) for a in store.library()],
                       jobs=[public_job(j) for j in store.jobs()], connections=connections,
                       voices=store.read("voices.json", []), voice_cast=settings.get("voice_cast", {}),
                       csrf_token=csrf, capabilities={"local_render": True, "video_api": "fal",
                           "voice_api": "elevenlabs", "commercial_voice_ready": connections["elevenlabs"].get("commercial_ready", False),
                           "automatic_publication": False, "human_review_required": True,
                           "new_scene_reference_required": True, "supports_voiceover": True,
                           "automatic_lipsync": False})

    def check_elevenlabs() -> dict:
        client = ElevenLabsClient(store.credential("elevenlabs"))
        account = client.status()
        voices = client.voices()
        store.write("voices.json", voices)
        commercial = voice_commercial_ready(account)
        status = {**account, "configured": True, "verified": True, "checked_at": now(),
                  "commercial_ready": commercial,
                  "message": "ElevenLabs conectado. Voces listas para seleccionar." if commercial else
                  "ElevenLabs conectado · plan gratuito. Las voces para anuncios requieren un plan con licencia comercial."}
        settings = store.settings()
        checks = settings.get("connection_checks", {})
        checks["elevenlabs"] = status
        store.update_settings({"connection_checks": checks})
        return status

    @app.get("/api/connections/elevenlabs/test")
    def eleven_status():
        return jsonify(check_elevenlabs())

    @app.get("/api/connections/fal/test")
    def fal_status():
        client = FalClient(store.credential("fal"))
        quote = client.pricing(SEEDANCE_FAST)
        status = {"configured": True, "verified": True, "checked_at": now(), "message": "fal conectado. Consulta de tarifas verificada.", "pricing": quote}
        settings = store.settings()
        checks = settings.get("connection_checks", {})
        checks["fal"] = status
        store.update_settings({"connection_checks": checks})
        return jsonify(status)

    @app.get("/api/voices")
    def voices():
        check_elevenlabs()
        return jsonify(voices=store.read("voices.json", []))

    @app.post("/api/voice-cast")
    def voice_cast():
        values = request.get_json(silent=True) or {}
        known = {voice["voice_id"] for voice in store.read("voices.json", [])}
        cast = {}
        for role in ("narrator", "son", "mother"):
            voice_id = str(values.get(role, "")).strip()
            if voice_id and voice_id not in known:
                raise ValueError("Esa voz no está disponible en tu cuenta. Actualiza el catálogo.")
            if voice_id:
                cast[role] = voice_id
        store.update_settings({"voice_cast": cast})
        return jsonify(voice_cast=cast)

    @app.post("/api/credentials")
    def credentials():
        values = request.get_json(silent=True) or {}
        provider = values.get("provider")
        if provider not in ("fal", "elevenlabs"):
            raise ValueError("Elige ElevenLabs o fal.")
        store.save_credential(provider, str(values.get("api_key", "")).strip())
        settings = store.settings()
        checks = settings.get("connection_checks", {})
        checks[provider] = {"verified": False, "message": "Clave guardada en privado; pendiente de comprobar."}
        store.update_settings({"connection_checks": checks})
        return jsonify(configured=True, verified=False)

    @app.post("/api/jobs")
    def new_job():
        values = request.get_json(silent=True) or {}
        brief = {key: values[key] for key in ("title", "concept", "format", "duration", "script", "voice_role", "model", "budget_usd", "reference_asset_id", "max_attempts") if key in values}
        brief["title"] = str(brief.get("title", "Nueva producción")).strip()[:160] or "Nueva producción"
        if len(str(brief.get("script", ""))) > 2000 or len(str(brief.get("concept", ""))) > 2000:
            raise ValueError("Resume la idea y el texto para un vídeo corto.")
        plan = build_plan(brief, store.library(), default_style())
        return jsonify(public_job(store.create_job(brief, plan))), 201

    @app.get("/api/jobs/<job_id>")
    def job_detail(job_id):
        return jsonify(public_job(store.job(job_id)))

    def launch(job_id: str, function, *args):
        with worker_lock:
            job = store.job(job_id)
            if job_id in workers and workers[job_id].is_alive():
                raise ValueError("Esta producción ya está en marcha.")
            if job.get("status") in ACTIVE:
                raise ValueError("Esta producción tiene una operación pendiente.")
            store.event(job_id, "Producción en cola.", status="queued", progress=1, ready_for_delivery=False)
            worker = threading.Thread(target=function, args=(store, job_id, *args), daemon=True,
                                      name="video-studio-" + job_id)
            workers[job_id] = worker
            worker.start()
        return jsonify(public_job(store.job(job_id))), 202

    @app.post("/api/jobs/<job_id>/render-local")
    def render_local(job_id):
        job = store.job(job_id)
        if float(job["plan"]["duration"]) > 15:
            raise ValueError("La prueba con material existente admite de 8 a 15 segundos. Genera nuevos planos para duraciones mayores.")
        return launch(job_id, run_local_preview)

    @app.post("/api/jobs/<job_id>/generate")
    def generate(job_id):
        values = request.get_json(silent=True) or {}
        job = store.job(job_id)
        limit = approved_budget(job, values.get("max_cost_usd", 0))
        errors = [issue for issue in validate_plan(job["plan"]) if issue["severity"] == "error"]
        if errors:
            raise ValueError(errors[0]["message"])
        account = check_elevenlabs()
        if not account.get("commercial_ready"):
            raise ValueError("ElevenLabs está conectado con un plan gratuito. Para generar voces de anuncios hace falta una licencia comercial. Puedes revisar el estilo y montar un ensayo local.")
        cast = store.settings().get("voice_cast", {})
        role = job["plan"]["narrations"][0]["voice_role"]
        if not cast.get(role):
            raise ValueError("Selecciona la voz del personaje antes de generar.")
        if not store.credential("fal"):
            raise ValueError("Falta conectar fal para crear nuevos planos.")
        return launch(job_id, run_generation, limit)

    @app.post("/api/jobs/<job_id>/review")
    def review(job_id):
        job = store.job(job_id)
        values = request.get_json(silent=True) or {}
        approved = values.get("approved") is True
        checks = values.get("checks", {})
        if not isinstance(checks, dict):
            raise ValueError("La revisión no es válida.")
        if approved:
            if job.get("technical_preview"):
                raise ValueError("Un ensayo técnico sin voz definitiva no se puede aprobar como anuncio nuevo.")
            if not (job.get("qa") or {}).get("technical_passed") or not job.get("output_path"):
                raise ValueError("Primero deben superarse los controles técnicos del archivo.")
            if not all(checks.get(category) is True for category in REVIEW_CATEGORIES):
                raise ValueError("Revisa los seis puntos antes de aprobar la entrega.")
        review = {"approved": approved, "checks": {c: checks.get(c) is True for c in REVIEW_CATEGORIES},
                  "notes": str(values.get("notes", ""))[:3000], "reviewed_at": now()}
        return jsonify(public_job(store.update_job(job_id, {"creative_review": review,
                        "ready_for_delivery": approved, "status": "approved" if approved else "changes_requested",
                        "message": "Revisión completada. Entrega aprobada." if approved else "Correcciones registradas; la entrega sigue pendiente."})))

    @app.get("/media/<asset_id>")
    def media(asset_id):
        return send_file(store.asset(asset_id)["path"], conditional=True)

    @app.get("/outputs/<job_id>")
    def output(job_id):
        job = store.job(job_id)
        path = Path(job.get("output_path", ""))
        if not path.is_file() or not path.resolve().is_relative_to(store.job_dir(job_id).resolve()):
            raise KeyError("No existe una exportación de esta producción.")
        return send_file(path, mimetype="video/mp4", conditional=True,
                         download_name=f"Dropradar-{job_id}.mp4")

    @app.post("/api/assets/upload")
    def upload():
        incoming = request.files.get("file")
        if not incoming:
            raise ValueError("Selecciona una imagen de referencia.")
        temporary = store.directory / ("upload_" + uuid.uuid4().hex + ".tmp")
        incoming.save(temporary)
        try:
            with Image.open(temporary) as image:
                if image.width < 640 or image.height < 960 or not .50 < image.width / image.height < .63:
                    raise ValueError("La referencia debe ser vertical 9:16 y de al menos 640 × 960.")
                target = temporary.with_suffix(".png")
                image.convert("RGB").save(target)
            asset = store.add_asset(target, kind="image", type="image", title=str(request.form.get("title") or "Nueva referencia")[:120],
                                    tags=["reference", "scene"], width=image.width, height=image.height, portrait=True,
                                    approved=False, approval_basis="Pendiente de revisión de personaje, entorno y luz")
            target.unlink(missing_ok=True)
            return jsonify(public_asset(asset)), 201
        finally:
            temporary.unlink(missing_ok=True)

    @app.post("/api/assets/<asset_id>/approve")
    def approve_asset(asset_id):
        store.asset(asset_id)
        values = request.get_json(silent=True) or {}
        if values.get("approved") is not True:
            raise ValueError("Confirma que has revisado personaje, escenario, manos y luz.")
        assets = store.library()
        for asset in assets:
            if asset["id"] == asset_id and asset.get("kind") == "image":
                asset.update(approved=True, approval_basis="Referencia revisada en el estudio", approved_at=now())
        store.write("library.json", assets)
        return jsonify(approved=True)

    return app


def main():
    parser = argparse.ArgumentParser(description="Estudio local de vídeo Dropradar")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("El puerto debe estar entre 1024 y 65535.")
    create_app(args.data).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
