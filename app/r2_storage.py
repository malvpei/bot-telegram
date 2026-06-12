from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


R2_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
R2_ACCESS_KEY_ID_LENGTH = 32


@dataclass(frozen=True)
class R2Object:
    key: str
    size: int


class R2StorageError(RuntimeError):
    pass


class R2StorageClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.r2_bucket
            and self.settings.r2_access_key_id
            and self.settings.r2_secret_access_key
            and (self.settings.r2_endpoint_url or self.settings.r2_account_id)
        )

    def pick_video(self, prefix: str) -> R2Object:
        objects = self.list_videos(prefix)
        if not objects:
            raise R2StorageError(
                "No encontré vídeos .mp4/.mov/.m4v/.webm en R2"
                + (f" bajo el prefijo {prefix!r}." if prefix else ".")
            )
        # Deterministic newest-ish fallback would need LastModified; stable sort
        # keeps tests predictable while service-level random picks can shuffle.
        return sorted(objects, key=lambda item: item.key)[0]

    def list_videos(self, prefix: str) -> list[R2Object]:
        client = self._boto_client()
        paginator = client.get_paginator("list_objects_v2")
        videos: list[R2Object] = []
        for page in paginator.paginate(
            Bucket=self.settings.r2_bucket,
            Prefix=prefix.strip().lstrip("/"),
        ):
            for item in page.get("Contents", []):
                key = str(item.get("Key") or "")
                if not key or key.endswith("/"):
                    continue
                if Path(key).suffix.lower() not in R2_VIDEO_EXTENSIONS:
                    continue
                videos.append(R2Object(key=key, size=int(item.get("Size") or 0)))
        return videos

    def download(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._boto_client().download_file(
            self.settings.r2_bucket,
            key,
            str(destination),
        )
        return destination

    def _boto_client(self):
        if not self.is_configured:
            raise R2StorageError(
                "Falta configurar R2. Necesito R2_BUCKET, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY y R2_ACCOUNT_ID o R2_ENDPOINT_URL."
            )
        if len(self.settings.r2_access_key_id) != R2_ACCESS_KEY_ID_LENGTH:
            raise R2StorageError(
                "R2_ACCESS_KEY_ID no es válido: debe tener 32 caracteres. "
                "En Coolify pega el valor de 'ID de clave de acceso' de las "
                "credenciales S3 de R2, no el valor del token ni un placeholder."
            )
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as error:
            raise R2StorageError(
                "Falta instalar boto3 para conectar con R2. Ejecuta "
                "`pip install -r requirements.txt` tras actualizar requirements."
            ) from error

        endpoint_url = self.settings.r2_endpoint_url or (
            f"https://{self.settings.r2_account_id}.r2.cloudflarestorage.com"
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.settings.r2_access_key_id,
            aws_secret_access_key=self.settings.r2_secret_access_key,
            region_name="auto",
        )
        return self._client
