from dataclasses import replace
from io import BytesIO

from PIL import Image

from app.config import get_settings
from app.r2_storage import R2Object
from app.upload_site import create_upload_app


class FakeImageStorage:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    def list_images(self, prefix: str):
        return [
            R2Object(key=key, size=len(data))
            for key, (data, _content_type) in self.objects.items()
            if key.startswith(prefix)
        ]

    def upload_bytes(self, key: str, data: bytes, *, content_type: str | None = None):
        self.objects[key] = (data, content_type or "application/octet-stream")
        return R2Object(key=key, size=len(data))

    def download_bytes(self, key: str):
        return self.objects[key]

    def object_exists(self, key: str):
        return key in self.objects


def _png_bytes() -> BytesIO:
    handle = BytesIO()
    Image.new("RGB", (24, 32), (20, 120, 80)).save(handle, format="PNG")
    handle.seek(0)
    return handle


def test_upload_site_uploads_image_to_selected_prefix():
    settings = replace(
        get_settings(),
        r2_image_prefix="imagenes/referencias",
        upload_site_password="",
        upload_site_max_image_mb=5,
    )
    storage = FakeImageStorage()
    app = create_upload_app(settings, storage)

    response = app.test_client().post(
        "/images",
        data={
            "prefix": "imagenes/campana",
            "images": (_png_bytes(), "referencia.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "imagenes/campana/referencia.png" in storage.objects
    assert b"Subida:" in response.data


def test_upload_site_requires_auth_when_password_is_configured():
    settings = replace(
        get_settings(),
        upload_site_username="admin",
        upload_site_password="secret",
    )
    app = create_upload_app(settings, FakeImageStorage())

    response = app.test_client().get("/images")

    assert response.status_code == 401
