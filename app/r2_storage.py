from __future__ import annotations

from dataclasses import dataclass
import mimetypes
from pathlib import Path

from app.config import Settings


R2_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
R2_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".avif"}
R2_IMAGE_CONTENT_TYPE_MARKERS = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/avif",
}
R2_ACCESS_KEY_ID_LENGTH = 32


@dataclass(frozen=True)
class R2Object:
    key: str
    size: int
    etag: str = ""


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
        return self._list_objects_by_extension(prefix, R2_VIDEO_EXTENSIONS)

    def list_images(self, prefix: str) -> list[R2Object]:
        return self._list_image_objects(prefix)

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> R2Object:
        normalized_key = self._normalize_key(key)
        resolved_content_type = (
            content_type
            or mimetypes.guess_type(normalized_key)[0]
            or "application/octet-stream"
        )
        self._boto_client().put_object(
            Bucket=self.settings.r2_bucket,
            Key=normalized_key,
            Body=data,
            ContentType=resolved_content_type,
        )
        return R2Object(key=normalized_key, size=len(data))

    def download_bytes(self, key: str) -> tuple[bytes, str]:
        normalized_key = self._normalize_key(key)
        response = self._boto_client().get_object(
            Bucket=self.settings.r2_bucket,
            Key=normalized_key,
        )
        body = response["Body"].read()
        content_type = str(
            response.get("ContentType")
            or mimetypes.guess_type(normalized_key)[0]
            or "application/octet-stream"
        )
        return body, content_type

    def object_exists(self, key: str) -> bool:
        try:
            self._boto_client().head_object(
                Bucket=self.settings.r2_bucket,
                Key=self._normalize_key(key),
            )
        except Exception as error:  # noqa: BLE001 - boto3 exceptions are dynamic.
            response = getattr(error, "response", {})
            error_data = response.get("Error", {}) if isinstance(response, dict) else {}
            metadata = (
                response.get("ResponseMetadata", {}) if isinstance(response, dict) else {}
            )
            code = str(error_data.get("Code", ""))
            status = metadata.get("HTTPStatusCode")
            if status == 404:
                return False
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def _list_objects_by_extension(
        self,
        prefix: str,
        extensions: set[str],
    ) -> list[R2Object]:
        client = self._boto_client()
        paginator = client.get_paginator("list_objects_v2")
        objects: list[R2Object] = []
        for page in paginator.paginate(
            Bucket=self.settings.r2_bucket,
            Prefix=prefix.strip().lstrip("/"),
        ):
            for item in page.get("Contents", []):
                key = str(item.get("Key") or "")
                if not key or key.endswith("/"):
                    continue
                if Path(key).suffix.lower() not in extensions:
                    continue
                objects.append(
                    R2Object(
                        key=key,
                        size=int(item.get("Size") or 0),
                        etag=str(item.get("ETag") or "").strip('"'),
                    )
                )
        return objects

    def _list_image_objects(self, prefix: str) -> list[R2Object]:
        client = self._boto_client()
        paginator = client.get_paginator("list_objects_v2")
        objects: list[R2Object] = []
        for page in paginator.paginate(
            Bucket=self.settings.r2_bucket,
            Prefix=prefix.strip().lstrip("/"),
        ):
            for item in page.get("Contents", []):
                key = str(item.get("Key") or "")
                if not key or key.endswith("/"):
                    continue
                if Path(key).suffix.lower() in R2_IMAGE_EXTENSIONS:
                    objects.append(
                        R2Object(
                            key=key,
                            size=int(item.get("Size") or 0),
                            etag=str(item.get("ETag") or "").strip('"'),
                        )
                    )
                    continue
                if self._key_looks_like_image_content_type(key):
                    objects.append(
                        R2Object(
                            key=key,
                            size=int(item.get("Size") or 0),
                            etag=str(item.get("ETag") or "").strip('"'),
                        )
                    )
                    continue
                if self._object_has_content_type(key, "image/"):
                    objects.append(
                        R2Object(
                            key=key,
                            size=int(item.get("Size") or 0),
                            etag=str(item.get("ETag") or "").strip('"'),
                        )
                    )
        return objects

    def download(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._boto_client().download_file(
            self.settings.r2_bucket,
            key,
            str(destination),
        )
        return destination

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = key.strip().replace("\\", "/").lstrip("/")
        if not normalized or normalized.endswith("/"):
            raise R2StorageError("La clave R2 no puede estar vacia.")
        if any(part == ".." for part in normalized.split("/")):
            raise R2StorageError("La clave R2 no puede contener '..'.")
        return normalized

    def _object_has_content_type(self, key: str, prefix: str) -> bool:
        try:
            response = self._boto_client().head_object(
                Bucket=self.settings.r2_bucket,
                Key=self._normalize_key(key),
            )
        except Exception:  # noqa: BLE001 - a bad HEAD should not break listing.
            return False
        content_type = str(response.get("ContentType") or "").lower()
        return content_type.startswith(prefix.lower())

    @staticmethod
    def _key_looks_like_image_content_type(key: str) -> bool:
        lowered = key.lower()
        return any(marker in lowered for marker in R2_IMAGE_CONTENT_TYPE_MARKERS)

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
