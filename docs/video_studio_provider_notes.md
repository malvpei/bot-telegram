# Proveedores del Estudio Dropradar

Comprobación documental: 26 de octubre de 2026. Implementación en
`app/video_studio/providers.py`; pruebas con respuestas simuladas, sin consumo
de saldo. Una integración implementada no demuestra acceso real a la cuenta
ni calidad visual de una nueva generación.

## ElevenLabs

- `ElevenLabsClient(api_key, session=None).status()` comprueba la suscripción
  mediante `GET /v1/user/subscription`, sin generar audio ni cambiar planes.
  Solo expone plan, estado, cuota y fecha de renovación; excluye facturas e
  identidad de facturación.
- `voices()` consulta `GET /v2/voices` con paginación y usa `/v1/voices` si la
  ruta nueva devuelve 404/405. Conserva nombre, etiquetas y muestra pública;
  excluye muestras privadas y grabaciones de verificación.
- `shared_voices(language="es", accent=None, locale="es-ES", gender=None,
  age=None, limit=30)` consulta exclusivamente `GET /v1/shared-voices` y muestra
  voces de biblioteca con sus previews existentes. No añade voces ni genera
  audio. Marca `requires_paid_api_access=True`: la biblioteca por API requiere
  una cuenta de pago según ElevenLabs. Poder ver una muestra pública no prueba
  que la cuenta conectada pueda sintetizar esa voz. Se excluyen tarifas
  personalizadas y moderación en vivo de esta búsqueda inicial.
- `synthesize(text, voice_id, model_id, settings, output_dir, seed=42)` utiliza
  `POST /v1/text-to-speech/{voice_id}/with-timestamps`. Devuelve rutas MP3 y JSON
  de alineación, duración alineada, caracteres, identificador y clave de caché.
- El modelo predeterminado es `eleven_multilingual_v2`, sin `language_code`
  porque ese modelo no lo admite. Los demás modelos configurados usan `es`.
  El acento español de España depende de la voz escogida y debe escucharse.
- El formato es MP3 44,1 kHz / 128 kbps; evita exigir los niveles de cuenta
  necesarios para ciertos formatos WAV/PCM de mayor calidad.
- La duración devuelta es el final del último carácter alineado, no la duración
  del contenedor. El montaje debe medir el archivo y conservar su cola completa.
- La caché incluye voz, texto, modelo, ajustes, semilla y formato. Un mismo
  trabajo concurrente no envía dos POST. Un timeout, respuesta malformada o
  interrupción deja la petición pendiente de comprobación, sin repetir el cobro.
  La semilla ayuda a reproducir, pero no garantiza resultados idénticos.
- `status()` y `voices()` son comprobaciones reales disponibles; no se afirma
  conexión hasta recibir respuesta satisfactoria de la cuenta.

Fuentes oficiales:

- <https://elevenlabs.io/docs/api-reference/authentication>
- <https://elevenlabs.io/docs/api-reference/user/subscription/get>
- <https://elevenlabs.io/docs/api-reference/voices/search>
- <https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared>
- <https://elevenlabs.io/docs/overview/capabilities/voices>
- <https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps/>

### Comprobación real de catálogo, sin generar audio

El 26 de octubre de 2026, `GET /v1/shared-voices` respondió satisfactoriamente
con filtros `language=es`, `locale=es-ES`, `gender=male`, `age=young`; también
con `gender=female`, `age=middle_aged`. Las seis voces siguientes devuelven
`accent=peninsular`. Son candidatas por sus metadatos: no se ha juzgado todavía
su interpretación ni se han añadido a la cuenta. Las muestras ya existían en
la biblioteca pública. El acceso satisfactorio al catálogo no levanta la
restricción de síntesis de voces de biblioteca en la API para cuentas Free.

| Papel | Nombre de biblioteca | ID | Muestra existente |
| --- | --- | --- | --- |
| Chico | David Martin - Confident and Balanced | `Nh2zY9kknu6z4pZy6FhD` | [Escuchar](https://storage.googleapis.com/eleven-public-prod/database/user/8RYUsFHsalUXjwVG0LjhNwH1j022/voices/Nh2zY9kknu6z4pZy6FhD/5VD3I67SoLbajJEbw7rH.mp3) |
| Chico | David Martin - Clear, Calm and Elegant | `y6WtESLj18d0diFRruBs` | [Escuchar](https://storage.googleapis.com/eleven-public-prod/database/user/8RYUsFHsalUXjwVG0LjhNwH1j022/voices/y6WtESLj18d0diFRruBs/kbnBDZknYZrJFS9NaH63.mp3) |
| Chico | Dani - Hurried, Dynamic and Engaging | `7QQzpAyzlKTVrRzQJmTE` | [Escuchar](https://storage.googleapis.com/eleven-public-prod/database/workspace/519a25545582420c91a38d970b9e73d6/voices/7QQzpAyzlKTVrRzQJmTE/FXHYsdSLVYvp0GHMgTjR.mp3) |
| Madre | Carolina - Natural, Neutral and Clear | `UOIqAnmS11Reiei1Ytkc` | [Escuchar](https://storage.googleapis.com/eleven-public-prod/custom/voices/UOIqAnmS11Reiei1Ytkc/iD8yOai01ygsrjOUknQ3.mp3) |
| Madre | Carolina Ruiz - Nasal, Natural and Clear | `h2cd3gvcqTp3m65Dysk7` | [Escuchar](https://storage.googleapis.com/eleven-public-prod/database/workspace/0a827733c0974887817bc85481951f95/voices/h2cd3gvcqTp3m65Dysk7/DvNPwmY8u2WKmyXeN8yh.mp3) |
| Madre | Lydia - Warm, Energetic and Confident | `SDVJaMLoJa7wc3s2sn7d` | [Escuchar](https://storage.googleapis.com/eleven-public-prod/database/user/xfUAh4PHDnPEpIVBn9V1eSD7mkG3/voices/SDVJaMLoJa7wc3s2sn7d/1atwAszwKf5JQPc4uggT.mp3) |

## fal

`FalClient(api_key, session=None)` admite explícitamente:

- `fal-ai/bytedance/seedance/v1/pro/fast/image-to-video`: 2–12 segundos enteros,
  vertical 9:16, referencia inicial. El montaje incorpora la locución aparte.
- `minimax/h3-max-turbo/image-to-video`: 5–15 segundos en este estudio, referencia
  inicial/final y audio opcional. El parámetro de resolución usa `480P`, `768P`
  o `1080P` en mayúsculas; 1080P es refinamiento desde 768P según la ficha.
- `openai/gpt-image-2/edit`: una nueva imagen de escena completa por petición,
  con hasta 16 referencias. La imagen debe revisarse antes de animarla.

`submit(model, payload)` devuelve `request_id`, `status_url`, `response_url` y
`model`. No repite el POST. `poll(model, request_id)` y `result(model, request_id)`
reconstruyen las rutas de cola solo con propietario/aplicación: por ejemplo,
`fal-ai/bytedance/requests/{id}`, sin el resto de la ruta del modelo. Esto permite
reanudar una petición guardada después de reiniciar el proceso. El llamador debe
persistir el identificador inmediatamente y reservar presupuesto antes del POST.

`download_video(result, destination)` y `download_image(...)` descargan desde
dominios multimedia reconocidos sin cabeceras de autenticación, comprueban cada
redirección, limitan tamaño y validan la firma del archivo. Nunca sobrescriben
un destino ya existente. El resultado debe seguir pasando revisión técnica y
visual: una firma MP4 válida no acredita identidad de personajes o continuidad.

`pricing(model)` consulta, solo mediante GET,
`https://api.fal.ai/v1/models/pricing?endpoint_id=...`. Devuelve la unidad y la
tarifa de la cuenta con fecha de consulta. No convierte una tarifa por tokens
en un precio fijo por imagen y no usa cero cuando faltan permisos o tarifas.

Comprobación real del 26 de octubre de 2026 a las 15:38:58 UTC: la consulta
de precios de Seedance Pro Fast respondió `unit_price=1.0`, `unit="1m tokens"`,
`currency="USD"`. La autenticación de esa consulta GET está verificada; esta
respuesta no acredita saldo, acceso a generación ni una tarifa fija por
segundo. No se envió ninguna generación de pago.

GPT Image 2 publica costes por millón de tokens: texto entrada 5 USD, texto
entrada en caché 1,25 USD, texto salida 10 USD, imagen entrada 8 USD, imagen
entrada en caché 2 USD e imagen salida 30 USD. La calidad y el tamaño cambian
el número de tokens, y el total se redondea a 0,0001 USD. Estas unidades están
disponibles en `PUBLISHED_IMAGE_PRICING`; no constituyen un presupuesto cerrado.
Para una primera fase sin cotización verificable, usar una imagen ya aceptada
y dejar bloqueada la preparación de nuevos escenarios, o cotizarla expresamente.

Fuentes oficiales:

- <https://fal.ai/docs/documentation/model-apis/inference/queue>
- <https://fal.ai/docs/documentation/model-apis/pricing>
- <https://fal.ai/models/fal-ai/bytedance/seedance/v1/pro/fast/image-to-video/api>
- <https://fal.ai/models/minimax/h3-max-turbo/image-to-video/api>
- <https://fal.ai/models/openai/gpt-image-2/edit/api>
- <https://fal.ai/models/openai/gpt-image-2/edit>

## Errores y autorización de gasto

Los errores expuestos al usuario contienen mensajes fijos y códigos, sin cuerpo
de respuesta, claves ni URL sensible. La API no sigue redirecciones con claves.
Un resultado desconocido de un POST exige comprobar el proveedor; no equivale
a fallo gratuito ni autoriza una segunda generación. El estudio debe aplicar
su presupuesto antes de llamar al adaptador; el adaptador no compra planes,
no recarga saldo y no cambia los permisos de una cuenta.
