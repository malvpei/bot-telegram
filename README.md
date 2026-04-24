# Bot de Telegram para videos desde Instagram

Este proyecto monta un bot de Telegram que:

- lee un archivo local `accounts.txt` con las cuentas de Instagram a usar
- pregunta tipo de video e idioma mediante un wizard corto
- descarga una vez una biblioteca local por cuenta y luego selecciona desde disco
  (sin reutilizar imágenes entre videos, salvo `imagen6.png`)
- elige automáticamente las fotos según reglas para `tipo 1` o `tipo 2`
- genera el texto en español o en inglés
- evita repetir el mismo guion seguido y mantiene un historial de firmas
- renderiza un video vertical `.mp4` listo para subir

## Lo que hace el pipeline

- **Tipo 1** — 7 slides, narrativa octubre → marzo con una única cuenta.
  Slide 6 es siempre `imagen6.png` (febrero). El texto de febrero menciona
  obligatoriamente Dropradar. Nunca se mezclan imágenes de dos cuentas en el
  mismo video.
- **Tipo 2** — 5 slides, hook con cara visible preferente, 4 consejos. Slide
  3 es `imagen6.png` y menciona Dropradar. Los textos se sanean de `;`, `—`,
  `–`, `―` y variantes Unicode similares antes de devolverse. Permite
  estética lifestyle / lujo en las imágenes.

Ambos tipos:

- Reservan atómicamente las IDs de imagen antes de empezar a renderizar, así
  dos jobs en paralelo no pueden coger la misma foto.
- Empalman el texto con el slide **por rol**, no por posición, así un cambio
  de orden nunca desincroniza "texto de febrero" con "imagen de enero".
- Mantienen un historial acotado (`HISTORY_MAX_PER_BUCKET`) de firmas para
  que el dedup no degenere con el tiempo.

## Heurísticas — limitaciones importantes

- La detección de **paisaje** combina aspect ratio, un ratio aproximado de
  "cielo" en el tercio superior (HSV) y palabras clave del caption. Es una
  heurística — no es un clasificador visual real.
- La detección de **lujo extremo** (para excluir tipo 1) mira keywords del
  caption **y** un score visual aproximado (reflejos dorados o cromados).
  Sigue siendo débil: un Ferrari con caption vacío puede pasar.
- La detección de **cara** usa Haar cascade (OpenCV). Hay falsos positivos y
  negativos; no garantiza que sea el usuario.
- El score de **día / buena iluminación** se basa en brillo medio. Un
  estudio bien iluminado pasa aunque la foto no sea de día.

Si necesitas garantías fuertes sobre estas reglas, engancha un clasificador
visual externo.

## Estructura

```
app/
  config.py      — carga de .env y paths
  instagram.py   — login diferido, sesión persistente, retries con backoff
  selector.py    — scoring, asignación por rol, fallback de paisaje
  texts.py       — guiones es/en, coherencia monetaria, validación de tokens
  render.py      — render vertical, fallback de fuentes, enforce de tamaño
  state.py       — JSON + filelock cross-proceso, writes atómicos
  service.py     — orquestación, reserva atómica, limpieza de outputs
  bot.py         — handlers del bot, error handler que responde al chat
assets/
  fixed/imagen6.png      — imagen fija obligatoria
  fonts/*.ttf            — opcional, fuentes preferidas para el render
data/
  downloads/             — cache de imágenes por cuenta
  outputs/<job_id>/      — .mp4 y script.txt por job
  state/                 — JSON de used_media, firmas, log de jobs, sesión IG
```

## Instalación

Requiere **Python 3.10 o superior** (usa PEP 604 y genéricos nativos de
dict / set).

```bash
cd bot-telegram
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

Coloca la imagen fija:

```
assets/fixed/imagen6.png
```

(o indica otra ruta absoluta en `FIXED_IMAGE_PATH`).

Opcionalmente, deja una o dos fuentes `.ttf` en `assets/fonts/` (una bold y
una regular). Si no, el renderer usa las fuentes del sistema y, en último
caso, la bitmap por defecto de Pillow.

## Configuración

Todas las variables viven en `.env`. Las interesantes:

| Variable | Default | Qué hace |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | token del bot (obligatorio) |
| `TELEGRAM_ALLOWED_CHAT_IDS` | vacío = todos | coma-separado, whitelist |
| `DATA_DIR` | `data` local, `/app/data` en Docker | carpeta persistente para memoria, cache y outputs |
| `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | vacío | login opcional |
| `INSTAGRAM_SESSION_PATH` | `data/state/instagram_session` | session file de instaloader |
| `FIXED_IMAGE_PATH` | `assets/fixed/imagen6.png` | ubicación de imagen6 |
| `ACCOUNTS_FILE` | `accounts.txt` | archivo con cuentas (una por línea) |
| `MAX_POSTS_PER_ACCOUNT` | 100 | posts con foto a escanear por cuenta |
| `MAX_URLS_PER_JOB` | 8 | URLs máximas por job (del archivo) |
| `VIDEO_WIDTH/HEIGHT/FPS` | 1080/1920/30 | render vertical |
| `SLIDE_SECONDS` | 3.8 | duración de cada slide |
| `TRANSITION_SECONDS` | 0.35 | fade entre slides |
| `MAX_VIDEO_SIZE_MB` | 48 | si se supera, reencode automático |
| `HISTORY_MAX_PER_BUCKET` | 200 | tope del historial de firmas |
| `DOWNLOAD_RETRIES` | 3 | reintentos por imagen |
| `DOWNLOAD_BACKOFF_SECONDS` | 1.5 | backoff base exponencial |
| `OUTPUT_RETENTION_DAYS` | 7 | días que se guardan outputs |
| `ACCOUNT_CACHE_TTL_HOURS` | 0 | 0 = cache permanente; las cuentas ya descargadas se leen de `data/downloads/<cuenta>` |
| `ACCOUNT_PICK_ATTEMPTS` | 0 | objetivo inicial heredado; el selector puede seguir probando más cuentas para evitar falsos "sin imágenes" |

### Instagram y 2FA

El login se hace **diferido**: la primera vez que un job necesita descargar
algo. Si Instagram pide 2FA, genera un session file localmente con:

```bash
instaloader --login <usuario>
```

y coloca el archivo resultante en `INSTAGRAM_SESSION_PATH`. El bot lo
reutiliza en arranques posteriores.

## Uso

### Preparar las cuentas

Copia `accounts.example.txt` a `accounts.txt` y añade una cuenta por línea.
Se aceptan URLs (`https://instagram.com/usuario`), `@usuario` o solo
`usuario`. Las líneas vacías y lo que vaya después de `#` se ignoran. El
archivo se relee en cada `/create`, así que puedes editarlo sin reiniciar
el bot.

### Comandos

```text
/start        — intro
/help         — flujo y notas
/accounts     — lista las cuentas cargadas
/sync         — descarga una vez la biblioteca local por cuenta
/create       — lanza el wizard (tipo → idioma → render)
/wizard       — alias de /create
/cancel       — cancela el wizard en curso
```

Flujo recomendado: ejecuta **/sync** para poblar `data/downloads/<cuenta>` con
las imágenes de cada cuenta. Después, en el wizard eliges **Tipo 1**, **Tipo 2**
o **Tipo 3**, después **Español** o **English**, y el bot elige solo imágenes ya
guardadas de una única cuenta para ese video.

## Salida

- `.mp4` enviado al chat (si supera 50MB, se avisa y se deja en disco)
- preview de texto en el chat
- `script.txt` enviado como documento
- archivos persistidos en `data/downloads/`, `data/outputs/<job_id>/` y
  `data/state/`

## Estado persistente

- `data/state/used_media.json` — reservas de imágenes (nunca se reutilizan)
- `data/state/recent_scripts.json` — última firma generada por (tipo, idioma)
- `data/state/script_history.json` — historial acotado de firmas
- `data/state/jobs_log.json` — histórico de jobs
- `data/state/.state.lock` — lock de `filelock` cross-proceso

## Docker / Coolify / Hetzner

El bot guarda la memoria de fotos usadas en `DATA_DIR/state/used_media.json`.
En Docker el proyecto fija `DATA_DIR=/app/data` y el `Dockerfile` declara
`/app/data` como volumen. Si despliegas con `docker-compose.yml`, se crea el
volumen nombrado `bot_telegram_data` y la memoria sobrevive a redeploys.

En Coolify, usa preferiblemente el despliegue con `docker-compose.yml`, o
asegurate de crear un Persistent Storage en la app concreta del proyecto con:

```text
Mount path: /app/data
```

Todo lo que debe sobrevivir vive ahi: `state/used_media.json`,
`state/telegram_owner.json`, `state/jobs_log.json`, `downloads/` y `outputs/`.
Tras desplegar, ejecuta `/memory`: debe mostrar `DATA_DIR: /app/data` y
`Persistent Storage: OK (/app/data montado)`. Si aparece `ERROR`, el storage
no esta montado en esa app de Coolify y el siguiente redeploy puede borrar la
memoria.

## Ejecutar

```bash
python -m app.main
```

## Comprobaciones rápidas

```bash
python -m compileall app tests
python -m pytest tests
```

## Que probar manualmente antes de producción

- Generar 4-5 videos seguidos del mismo tipo/idioma y confirmar que no se
  repiten (ni en hook ni en cuerpo).
- Verificar que el `.mp4` en Telegram pesa < 50 MB.
- Generar con una cuenta pequeña (< 20 posts) para ver si hay suficientes
  imágenes válidas tras el filtro.
- Probar una cuenta con 2FA para confirmar que el session file funciona.
- Revisar `script.txt`: slide 6 tipo 1 debe decir `Fuente: fixed` y el
  texto debe mencionar Dropradar; slide 4 tipo 2 idem para el consejo 3.
- En Linux/Docker, dejar una fuente en `assets/fonts/` antes de renderizar.
#   b o t - t e l e g r a m  
 
