from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import hmac
import logging
import mimetypes
from pathlib import Path
from threading import Thread
from uuid import uuid4

from flask import Flask, Response, redirect, render_template_string, request, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.config import Settings, get_settings
from app.r2_storage import R2_IMAGE_EXTENSIONS, R2Object, R2StorageClient

try:  # pragma: no cover - depends on optional binary support at runtime.
    import pillow_heif
except ImportError:  # pragma: no cover
    pillow_heif = None
else:  # pragma: no cover
    pillow_heif.register_heif_opener()


LOGGER = logging.getLogger(__name__)
MAX_LISTED_IMAGES = 80


class UploadSiteError(ValueError):
    pass


def create_upload_app(
    settings: Settings | None = None,
    storage_client: R2StorageClient | None = None,
) -> Flask:
    settings = settings or get_settings()
    storage = storage_client or R2StorageClient(settings)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (
        max(1, settings.upload_site_max_image_mb) * 1024 * 1024 * 20
    )

    @app.before_request
    def require_basic_auth():
        if not settings.upload_site_password:
            return None
        auth = request.authorization
        user_ok = hmac.compare_digest(
            auth.username if auth else "",
            settings.upload_site_username,
        )
        password_ok = hmac.compare_digest(
            auth.password if auth else "",
            settings.upload_site_password,
        )
        if user_ok and password_ok:
            return None
        return Response(
            "Autenticacion requerida",
            401,
            {"WWW-Authenticate": 'Basic realm="DropRadar uploads"'},
        )

    @app.get("/")
    def index():
        return redirect(url_for("images"))

    @app.route("/images", methods=["GET", "POST"])
    def images():
        uploaded: list[R2Object] = []
        errors: list[str] = []
        try:
            prefix = _clean_prefix(
                request.values.get("prefix") or settings.r2_image_prefix
            )
        except UploadSiteError as error:
            prefix = _clean_prefix(settings.r2_image_prefix)
            errors.append(str(error))
        if request.method == "POST":
            overwrite = request.form.get("overwrite") == "1"
            files = request.files.getlist("images")
            if not files or all(not file.filename for file in files):
                errors.append("Selecciona al menos una imagen.")
            else:
                for file in files:
                    try:
                        uploaded.append(
                            _upload_one_image(
                                storage,
                                file,
                                prefix=prefix,
                                max_bytes=settings.upload_site_max_image_mb
                                * 1024
                                * 1024,
                                overwrite=overwrite,
                            )
                        )
                    except Exception as error:  # noqa: BLE001
                        LOGGER.exception("Image upload failed")
                        filename = file.filename or "imagen"
                        errors.append(f"{filename}: {error}")

        listed: list[R2Object] = []
        list_error = ""
        try:
            listed = sorted(
                storage.list_images(prefix),
                key=lambda item: item.key,
                reverse=True,
            )[:MAX_LISTED_IMAGES]
        except Exception as error:  # noqa: BLE001
            LOGGER.exception("R2 image list failed")
            list_error = str(error)

        return render_template_string(
            IMAGE_UPLOAD_TEMPLATE,
            prefix=prefix,
            uploaded=uploaded,
            errors=errors,
            listed=listed,
            list_error=list_error,
            max_mb=settings.upload_site_max_image_mb,
            auth_enabled=bool(settings.upload_site_password),
        )

    @app.get("/images/file/<path:key>")
    def image_file(key: str):
        data, content_type = storage.download_bytes(key)
        if (
            Path(key).suffix.lower() not in R2_IMAGE_EXTENSIONS
            and not content_type.lower().startswith("image/")
        ):
            return Response("Formato no permitido", 415)
        return Response(
            data,
            mimetype=content_type,
            headers={"Cache-Control": "private, max-age=120"},
        )

    return app


def run_upload_site(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    app = create_upload_app(settings)
    app.run(
        host=settings.upload_site_host,
        port=settings.upload_site_port,
        debug=False,
        use_reloader=False,
    )


def start_upload_site_thread(settings: Settings | None = None) -> Thread:
    settings = settings or get_settings()
    thread = Thread(
        target=run_upload_site,
        kwargs={"settings": settings},
        name="upload-site",
        daemon=True,
    )
    thread.start()
    return thread


def _upload_one_image(
    storage: R2StorageClient,
    file: FileStorage,
    *,
    prefix: str,
    max_bytes: int,
    overwrite: bool,
) -> R2Object:
    filename = secure_filename(file.filename or "")
    if not filename:
        raise UploadSiteError("nombre de archivo vacio.")
    suffix = Path(filename).suffix.lower()
    if suffix not in R2_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(R2_IMAGE_EXTENSIONS))
        raise UploadSiteError(f"formato no permitido. Usa {allowed}.")

    data = file.read()
    if not data:
        raise UploadSiteError("archivo vacio.")
    if len(data) > max_bytes:
        raise UploadSiteError(
            f"supera el limite de {max_bytes // (1024 * 1024)} MB."
        )
    _validate_image_bytes(data)

    key = _join_key(prefix, filename)
    if not overwrite:
        key = _unique_key(storage, key)
    content_type = file.mimetype or mimetypes.guess_type(filename)[0] or "image/jpeg"
    if not content_type.startswith("image/"):
        content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    return storage.upload_bytes(key, data, content_type=content_type)


def _validate_image_bytes(data: bytes) -> None:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise UploadSiteError("no parece una imagen valida.") from error


def _clean_prefix(prefix: str) -> str:
    cleaned = prefix.strip().replace("\\", "/").strip("/")
    if not cleaned:
        return "imagenes/referencias"
    if any(part == ".." for part in cleaned.split("/")):
        raise UploadSiteError("el prefijo no puede contener '..'.")
    return cleaned


def _join_key(prefix: str, filename: str) -> str:
    return f"{_clean_prefix(prefix)}/{filename}".lstrip("/")


def _unique_key(storage: R2StorageClient, key: str) -> str:
    if not storage.object_exists(key):
        return key
    path = Path(key)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _attempt in range(20):
        candidate = (
            path.with_name(f"{path.stem}-{timestamp}-{uuid4().hex[:8]}{path.suffix}")
            .as_posix()
            .lstrip("/")
        )
        if not storage.object_exists(candidate):
            return candidate
    raise UploadSiteError("no pude generar un nombre unico para la imagen.")


IMAGE_UPLOAD_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DropRadar · Subida de imágenes</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fb;
      --ink: #171923;
      --muted: #667085;
      --line: #d9dee8;
      --panel: #ffffff;
      --accent: #12805c;
      --accent-dark: #0f684d;
      --danger-bg: #fff1f0;
      --danger: #b42318;
      --ok-bg: #ecfdf3;
      --ok: #027a48;
      --shadow: 0 18px 44px rgba(27, 39, 63, 0.09);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .shell {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      margin-bottom: 20px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 30px;
      line-height: 1.15;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }
    .status {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 8px 11px;
      border-radius: 8px;
      color: var(--muted);
      white-space: nowrap;
      font-size: 13px;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .panel {
      padding: 20px;
    }
    h2 {
      margin: 0 0 16px;
      font-size: 18px;
      line-height: 1.2;
    }
    label {
      display: block;
      margin-bottom: 8px;
      font-weight: 700;
      font-size: 13px;
    }
    input[type="text"], input[type="file"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      padding: 11px 12px;
      font: inherit;
    }
    input[type="file"] {
      min-height: 112px;
      cursor: pointer;
    }
    .field { margin-bottom: 16px; }
    .hint {
      margin: 7px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 9px;
      margin: 10px 0 18px;
      color: var(--muted);
      font-size: 14px;
    }
    .check input { width: 16px; height: 16px; }
    button {
      width: 100%;
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: white;
      padding: 12px 15px;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    .message {
      border-radius: 8px;
      padding: 11px 12px;
      margin-bottom: 10px;
      font-size: 14px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }
    .message.ok {
      color: var(--ok);
      background: var(--ok-bg);
      border: 1px solid #abefc6;
    }
    .message.error {
      color: var(--danger);
      background: var(--danger-bg);
      border: 1px solid #fecdca;
    }
    .list-head {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: center;
      padding: 18px 20px 0;
    }
    .count {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 12px;
      padding: 16px 20px 20px;
    }
    .item {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
      min-width: 0;
    }
    .thumb {
      width: 100%;
      aspect-ratio: 4 / 5;
      object-fit: cover;
      display: block;
      background: #eef1f6;
    }
    .meta {
      padding: 9px 10px 10px;
      min-width: 0;
    }
    .name {
      display: block;
      color: var(--ink);
      font-weight: 700;
      font-size: 13px;
      line-height: 1.35;
      overflow-wrap: anywhere;
      text-decoration: none;
    }
    .size {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .empty {
      padding: 18px 20px 22px;
      color: var(--muted);
      line-height: 1.5;
    }
    @media (max-width: 860px) {
      header { display: block; }
      .status { display: inline-block; margin-top: 12px; white-space: normal; }
      .layout { grid-template-columns: 1fr; }
      .shell { width: min(100% - 22px, 720px); padding-top: 18px; }
      h1 { font-size: 25px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>Subida de imágenes</h1>
        <p class="subtitle">Carga referencias en R2 para usarlas en carruseles y piezas visuales.</p>
      </div>
      <div class="status">{{ "Auth activada" if auth_enabled else "Auth sin configurar" }}</div>
    </header>

    <div class="layout">
      <section class="panel">
        <h2>Nueva carga</h2>
        {% for item in uploaded %}
          <div class="message ok">Subida: {{ item.key }}</div>
        {% endfor %}
        {% for error in errors %}
          <div class="message error">{{ error }}</div>
        {% endfor %}
        <form method="post" enctype="multipart/form-data">
          <div class="field">
            <label for="prefix">Carpeta R2</label>
            <input id="prefix" name="prefix" type="text" value="{{ prefix }}" autocomplete="off">
            <p class="hint">Usa el mismo concepto que los videos plantilla: una carpeta/prefijo dentro del bucket.</p>
          </div>
          <div class="field">
            <label for="images">Imágenes</label>
            <input id="images" name="images" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif" multiple required>
            <p class="hint">JPG, PNG, WEBP, HEIC, HEIF o AVIF. Límite: {{ max_mb }} MB por archivo.</p>
          </div>
          <label class="check">
            <input type="checkbox" name="overwrite" value="1">
            Sobrescribir si el nombre ya existe
          </label>
          <button type="submit">Subir imágenes</button>
        </form>
      </section>

      <section>
        <div class="list-head">
          <h2>Imágenes en {{ prefix }}</h2>
          <span class="count">{{ listed|length }} visibles</span>
        </div>
        {% if list_error %}
          <div class="empty">No pude listar R2: {{ list_error }}</div>
        {% elif listed %}
          <div class="grid">
            {% for item in listed %}
              <article class="item">
                <a href="{{ url_for('image_file', key=item.key) }}" target="_blank" rel="noopener">
                  <img class="thumb" src="{{ url_for('image_file', key=item.key) }}" alt="{{ item.key }}" loading="lazy">
                </a>
                <div class="meta">
                  <a class="name" href="{{ url_for('image_file', key=item.key) }}" target="_blank" rel="noopener">{{ item.key }}</a>
                  <span class="size">{{ "%.1f"|format(item.size / 1024) }} KB</span>
                </div>
              </article>
            {% endfor %}
          </div>
        {% else %}
          <div class="empty">Todavía no hay imágenes en esta carpeta.</div>
        {% endif %}
      </section>
    </div>
  </main>
</body>
</html>
"""


if __name__ == "__main__":
    run_upload_site()
