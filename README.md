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
  outputs/users/<telegram_user_id>/<job_id>/ — salidas aisladas por usuario
  state/                 — JSON de used_media, pool, cooldowns, jobs, sesión IG
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
| `DYNAMIC_PICK_MAX_POSTS_PER_ACCOUNT` | 24 | posts maximos por cuenta cuando `/create` cae a busqueda dinamica fuera del pool |
| `MAX_URLS_PER_JOB` | 8 | URLs máximas por job (del archivo) |
| `POOL_TARGET_IMAGES` | 100 | fotos disponibles que `/download_pool` intenta mantener en el pool |
| `POOL_LOW_STOCK_THRESHOLD` | 12 | aviso cuando el pool baja de este stock |
| `ACCOUNT_COOLDOWN_DAYS` | 30 | cooldown de cuenta tras revisar sus fotos |
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
| `R2_TYPE_5_IMAGE_PREFIX` | `tipo4/imagenstipo4` | carpeta R2 usada por la cola de cuatro imágenes del Tipo 5 |

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
/download_pool — rellena el pool precargado de fotos aptas
/pool         — muestra el stock del pool por tipo y cuenta
/create       — lanza el wizard (tipo → idioma → render)
/wizard       — alias de /create
/cancel       — cancela el wizard en curso
```

El **Tipo 4** genera una sola imagen vertical con cuatro consejos y no necesita
cuentas de Instagram. Rota entre fondo negro, fondo blanco y un diseño
ilustrado con tarjetas e iconos de dropshipping. También rota cuatro guiones en
español e inglés; el cuarto consejo siempre recomienda Dropradar. Cada entrega
incluye fuera de la imagen la frase de apertura correspondiente al idioma.
La **Historia IA** continúa disponible como una opción independiente.

El **Tipo 5** toma directamente cuatro imágenes diferentes del prefijo R2
`tipo4/imagenstipo4`, las recorre con una cola persistente independiente y
no borra objetos del bucket. Entrega las cuatro imágenes limpias, sin texto ni
iconos, y manda el hook «Top negocios para jubilar a tus padres 🫡» y las
comparaciones de Traiding, Clipping y AI + Dropshipping como cuatro mensajes
separados. Cada vídeo recibe un único título y una única descripción con
hashtags, en mensajes distintos, rotando entre doce parejas. Las rotaciones se
guardan en `DATA_DIR/state/type5_image_queue.json` y
`DATA_DIR/state/type5_social_queue.json`, por lo que continúan después de
reinicios o redeploys.

Flujo recomendado: ejecuta **/download_pool** para poblar un lote de fotos aptas
en `data/state/media_pool.json`. El comando revisa cuentas una por una, descarga
las fotos válidas, respeta `used_media.json`, y pone cada cuenta revisada en
cooldown durante `ACCOUNT_COOLDOWN_DAYS`. Después, **/create** elige desde ese
pool local, rota cuentas para evitar favoritismo, y permite **Pasar cuenta** si
quieres forzar la siguiente cuenta disponible.

### Colocacion de texto y rendimiento

El renderer detecta caras frontales y de perfil sobre una copia reducida de la
imagen, reserva una zona alrededor de cabeza/ojos y solo despues elige la zona
mas centrada y con menos ruido visual. Los hooks usan un contorno reforzado y
los captions mantienen tarjeta blanca. El layout se calcula una vez por slide y
se reutiliza durante todos sus frames.

Las metricas y fingerprints de las fotos quedan cacheadas en
`data/state/image_analysis_cache.json`. Los fondos decorativos del tipo 3 no se
analizan como retratos y el mismo canvas se reutiliza en sus seis slides. Los
videos plantilla usan `FFMPEG_PRESET=veryfast` por defecto y conservan en
`data/r2_downloads/template_cache` los originales ya descargados de R2, con una
poda LRU limitada a 8 archivos o 512 MB. El
carrusel IA usa por defecto `openai/gpt-image-2/edit` a traves de fal.ai. La
primera escena fija el personaje y el estilo; la segunda fija la habitacion; las
escenas restantes reutilizan esas referencias y generan hasta
`STORY_IMAGE_WORKERS=2` imagenes simultaneas. Los textos exactos se componen
despues para que el modelo no introduzca letras deformadas. Un revisor visual
barato valida cada escena y solo regenera las que no alcancen
`STORY_REVIEW_MIN_SCORE`: usa OpenAI si existe `OPENAI_API_KEY` y, si no, el
router visual de fal.ai con la misma `FAL_KEY`.

### Lotes y programacion diaria

`/batch [cantidad]` mete varias creaciones en una cola y mantiene el bot
disponible mientras se procesan. Se admiten entre 1 y 24 piezas; si se piden
mas de cinco, se repite el perfil de las cinco posiciones masculinas.

El primer lote de cinco es:

1. tipo 1 en espanol (hombre)
2. tipo 2 en espanol (hombre)
3. tipo 3 en ingles (hombre)
4. tipo 1 en espanol (hombre)
5. tipo 1 en ingles (hombre)

Cada posicion avanza por una secuencia adecuada a su idioma y genero. Los
hombres en espanol e ingles rotan por la misma secuencia:
`1 -> 2 -> 3 -> 1 -> 2 -> 3 -> IA -> herramientas`. Despues de herramientas,
el ciclo vuelve al tipo 1. El carril de mujeres queda temporalmente fuera de
los lotes. La historia IA usa una referencia de R2 y se genera en el idioma de
su carril, espanol o ingles. El paso actual, los horarios y el ultimo
resultado se guardan dentro de `DATA_DIR/state`, por lo que sobreviven a los
reinicios y redeploys. Solo se procesa un lote a la vez para no reutilizar
fotos ni compartir a la vez la sesion de Instagram.

Ejemplo para tener cinco piezas preparadas todos los dias para las 08:00 y las
17:00:

```text
/schedule 5 08:00 17:00
```

Comandos relacionados: `/schedule` muestra el estado, `/schedule off`
desactiva los horarios, `/batch 5` crea el siguiente lote ahora y
`/batch_reset` reinicia la rotacion. La zona horaria predeterminada es
`Europe/Madrid`, incluido el cambio de hora de verano; se puede cambiar con
`BATCH_TIMEZONE`. La preparacion empieza 120 minutos antes de cada objetivo
por defecto; ajusta `BATCH_PREPARATION_LEAD_MINUTES` si el proveedor IA tarda
mas o menos en tu despliegue. Si el bot arranca despues de la hora de inicio
pero aun esta dentro de esa ventana, recupera automaticamente el lote pendiente.

Los carruseles se entregan como un unico album de Telegram con todas sus
imagenes, tanto al ejecutar `/create` manualmente como en los lotes programados.

### Web para subir imagenes a R2

El proyecto incluye una web interna para subir imagenes al mismo bucket R2 que
usa el video plantilla. Sirve para cargar referencias o creatividades en una
carpeta/prefijo sin entrar manualmente en Cloudflare.

Variables principales:

| Variable | Default | Que hace |
|---|---|---|
| `UPLOAD_SITE_ENABLED` | `false` | si es `true`, arranca la web junto al bot |
| `UPLOAD_SITE_HOST` / `UPLOAD_SITE_PORT` | `0.0.0.0` / `8000` | host y puerto de escucha |
| `UPLOAD_SITE_USERNAME` / `UPLOAD_SITE_PASSWORD` | `admin` / vacio | auth basica; si la password queda vacia, no pide login |
| `UPLOAD_SITE_MAX_IMAGE_MB` | `20` | limite por imagen |
| `R2_IMAGE_PREFIX` | `imagenes/referencias` | carpeta R2 por defecto para las subidas |

Arranque junto al bot:

```bash
UPLOAD_SITE_ENABLED=true python -m app.main
```

Arranque standalone:

```bash
python -m app.upload_site
```

La web acepta JPG, PNG, WEBP, HEIC, HEIF y AVIF, permite subir varias imagenes
a la vez y lista las ultimas imagenes del prefijo seleccionado con preview.

## Salida

- `.mp4` enviado al chat (si supera 50MB, se avisa y se deja en disco)
- preview de texto en el chat
- `script.txt` enviado como documento
- archivos persistidos en `data/downloads/`,
  `data/outputs/users/<telegram_user_id>/<job_id>/` y
  `data/state/`

## Estado persistente

- `data/state/used_media.json` — reservas de imágenes (nunca se reutilizan)
- `data/state/media_pool.json` — pool precargado usado por `/create`
- `data/state/account_cooldowns.json` — cuentas ya revisadas y cooldown
- `data/state/recent_scripts.json` — última firma generada por (tipo, idioma)
- `data/state/script_history.json` — historial acotado de firmas
- `data/state/jobs_log.json` — histórico de jobs
- `data/state/telegram_users.json` — usuarios autorizados y último acceso
- `data/state/.state.lock` — lock de `filelock` cross-proceso

## Varios usuarios de Telegram

El bot funciona en chats privados para evitar que una entrega quede visible en
un grupo. El primer usuario autorizado queda como propietario. Los demás pueden
consultar su ID con `/my_id`; el propietario gestiona el acceso con:

```text
/add_user 123456789
/remove_user 123456789
/users
```

Todos consumen el mismo pool global: una foto reservada por cualquier usuario
desaparece para los demás y no vuelve a utilizarse. Las referencias de R2 de la
Historia IA siguen la misma regla. Los jobs, rutas de salida e historial mostrado por
`/memory` quedan separados por usuario. `/sync`, `/download_pool`, `/schedule`
y `/batch_reset` son comandos exclusivos del propietario porque modifican el
estado compartido.

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
`state/telegram_owner.json`, `state/telegram_users.json`, `state/jobs_log.json`,
`downloads/` y `outputs/`.
Tras desplegar, ejecuta `/memory`: debe mostrar `DATA_DIR: /app/data` y
`Persistent Storage: OK (/app/data montado)`. Si aparece `ERROR`, el storage
no esta montado en esa app de Coolify y el siguiente redeploy puede borrar la
memoria.

Para la Historia IA, `STORY_FAL_MODEL` controla el generador de historias
de forma independiente. Dejalo en `openai/gpt-image-2/edit`. Un `FAL_MODEL`
antiguo (por ejemplo, Flux Kontext) ya no puede degradar estas escenas. Al
arrancar, el log `Story AI settings` muestra el modelo que realmente se usara.

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
