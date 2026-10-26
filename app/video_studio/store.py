from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "video_studio"
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class StudioStore:
    def __init__(self, directory: Path | str = DATA):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.directory / ".lock"))
        for name in ("jobs", "library", "cache", "outputs"):
            (self.directory / name).mkdir(exist_ok=True)

    def read(self, name: str, default: Any = None) -> Any:
        path = self.directory / name
        return json.loads(path.read_text()) if path.exists() else default

    def write(self, name: str, value: Any) -> None:
        with self.lock:
            atomic_json(self.directory / name, value)

    def settings(self) -> dict:
        return self.read("settings.json", {"voice_cast": {}, "connection_checks": {}})

    def update_settings(self, updates: dict) -> dict:
        with self.lock:
            data = self.settings()
            data.update(updates)
            atomic_json(self.directory / "settings.json", data)
            return data

    def credential(self, provider: str) -> str:
        keys = {"fal": "FAL_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}
        key = keys[provider]
        private = dotenv_values(self.directory / "credentials.env")
        project = dotenv_values(ROOT / ".env")
        return str(os.environ.get(key) or private.get(key) or project.get(key) or "").strip()

    def save_credential(self, provider: str, value: str) -> None:
        key = {"fal": "FAL_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}[provider]
        if not value or len(value) > 512 or any(c.isspace() for c in value) or any(c in value for c in "'\"\\"):
            raise ValueError("La clave no tiene un formato válido.")
        path = self.directory / "credentials.env"
        with self.lock:
            values = dict(dotenv_values(path))
            values[key] = value
            temporary = path.with_suffix(".tmp")
            descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                for name, secret in values.items():
                    if name in ("FAL_KEY", "ELEVENLABS_API_KEY") and secret:
                        stream.write(f"{name}='{secret}'\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)

    def library(self) -> list[dict]:
        return self.read("library.json", [])

    def asset(self, asset_id: str) -> dict:
        if not SAFE_ID.fullmatch(asset_id):
            raise KeyError("Recurso no encontrado.")
        return next((a for a in self.library() if a["id"] == asset_id), None) or self._missing_asset()

    @staticmethod
    def _missing_asset():
        raise KeyError("Recurso no encontrado.")

    def add_asset(self, source: Path, *, asset_id: str | None = None, **metadata) -> dict:
        if not source.is_file():
            raise ValueError("El archivo no existe.")
        asset_id = asset_id or "asset_" + uuid.uuid4().hex[:12]
        if not SAFE_ID.fullmatch(asset_id):
            raise ValueError("Identificador no válido.")
        digest = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
        with self.lock:
            library = self.library()
            existing = next((a for a in library if a["id"] == asset_id), None)
            if existing:
                return existing
            destination = self.directory / "library" / (asset_id + source.suffix.lower())
            shutil.copy2(source, destination)
            asset = {"id": asset_id, "path": str(destination), "sha256": digest,
                     "bytes": destination.stat().st_size, "created_at": now(),
                     "source_name": source.name, "url": "/media/" + asset_id,
                     "approved": False, **metadata}
            library.append(asset)
            atomic_json(self.directory / "library.json", library)
            return asset

    def jobs(self) -> list[dict]:
        jobs = [json.loads(p.read_text()) for p in (self.directory / "jobs").glob("*/job.json")]
        return sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)

    def job_dir(self, job_id: str) -> Path:
        if not SAFE_ID.fullmatch(job_id):
            raise KeyError("Producción no encontrada.")
        return self.directory / "jobs" / job_id

    def job(self, job_id: str) -> dict:
        path = self.job_dir(job_id) / "job.json"
        if not path.exists():
            raise KeyError("Producción no encontrada.")
        return json.loads(path.read_text())

    def create_job(self, brief: dict, plan: dict) -> dict:
        job = {"id": "video_" + uuid.uuid4().hex[:12], "title": brief["title"],
               "created_at": now(), "updated_at": now(), "status": "draft", "progress": 0,
               "brief": brief, "plan": plan, "estimated_cost_usd": plan.get("estimated_cost_usd", 0),
               "reserved_cost_usd": 0, "events": [], "generation_requests": {},
               "output_url": None, "qa": None, "creative_review": None,
               "message": "Plan preparado. Revisa la referencia, la voz y los planos."}
        self.write("jobs/" + job["id"] + "/job.json", job)
        return job

    def update_job(self, job_id: str, updates: dict) -> dict:
        with self.lock:
            job = self.job(job_id)
            job.update(updates)
            job["updated_at"] = now()
            atomic_json(self.job_dir(job_id) / "job.json", job)
            return job

    def event(self, job_id: str, message: str, **updates) -> dict:
        with self.lock:
            job = self.job(job_id)
            job.update(updates)
            job["message"] = message
            job["updated_at"] = now()
            job["events"] = (job.get("events", []) + [{"at": now(), "message": message}])[-100:]
            atomic_json(self.job_dir(job_id) / "job.json", job)
            return job


def seed_library(store: StudioStore) -> None:
    """Import only known accepted assets; originals are never edited or removed."""
    base = ROOT.parent
    latest = base / "dropradar-produccion-2026-10-26-v2"
    old = base / "dropradar-produccion-2026-10-19"
    items = [
        ("reference_office", latest / "assets/office-scene-start-01.png", "image", "Oficina · protagonista", ["reference", "office", "son", "success"]),
        ("reference_family", latest / "assets/office-scene-start-02.png", "image", "Oficina · madre e hijo", ["reference", "office", "mother", "son", "family"]),
        ("real_website", old / "assets/dropradar-web-real-2026-10-19.png", "image", "Web real · conservar textos", ["website", "real_screen"]),
        ("scene_success", latest / "raw/clip07-office-success-flow.mp4", "video", "Éxito en la oficina · escena aceptada", ["office", "success", "son"]),
        ("scene_family", latest / "raw/clip08-office-family-flow.mp4", "video", "Abrazo · escena aceptada", ["office", "family", "mother", "son"]),
        ("screen_reveal", base / "dropradar-produccion-2026-10-24-v2/processed/clip03-web-reveal-1s.mp4", "video", "Web real dentro del portátil · 1 s", ["website", "real_screen", "discovery"]),
        ("accepted_ad", latest / "renders/Dropradar_Veo_oficina_26oct_80pt.mp4", "video", "Anuncio de referencia · 26 de octubre", ["historical", "finished_reference"]),
    ]
    for asset_id, path, kind, title, tags in items:
        if not path.is_file():
            continue
        duration = {"scene_success": 8, "scene_family": 8, "screen_reveal": 1, "accepted_ad": 35.416667}.get(asset_id)
        store.add_asset(path, asset_id=asset_id, kind=kind, type=kind, title=title, tags=tags,
                        approved=True, approval_basis="Material aceptado en la producción anterior",
                        duration=duration, width=1080 if kind == "video" else None,
                        height=1920 if kind == "video" else None, portrait=asset_id != "real_website",
                        contains_dialogue=asset_id in ("scene_family", "accepted_ad"),
                        reference_for=["son", "mother"] if asset_id == "reference_family" else ["son"],
                        historical=asset_id == "accepted_ad")
