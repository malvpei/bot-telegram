"use strict";

(() => {
  const state = { data: null, view: "studio", filter: "all", job: null, poll: null, toast: null, castDirty: false };
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const names = { studio: "Estudio", style: "Estilo y personajes", voices: "Voces", library: "Biblioteca", connections: "Conexiones" };
  const roles = { narrator: { name: "Narrador", symbol: "≋", description: "La voz que guía las demostraciones y conecta las escenas." }, son: { name: "Chico", symbol: "C", description: "Adulto de 23 años. Cercano, expresivo y con acento de España." }, mother: { name: "Madre", symbol: "M", description: "Una voz adulta cálida, con carácter y acento de España." } };
  const reviewChecks = { identity: "Personajes y aspecto consistentes", hands: "Caras, manos y objetos correctos", screen: "Pantalla real nítida y bien integrada", subtitles: "Subtítulos completos y legibles", audio: "Voces completas y música equilibrada", continuity: "Movimiento y transiciones naturales" };
  const activeStatuses = new Set(["queued", "rendering", "generating", "processing", "voice_generating", "generating_voice", "generating_scenes", "assembling", "running"]);
  const fmtMoney = value => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} USD` : "—";
  const fmtDuration = value => Number.isFinite(Number(value)) ? `${Number(value).toFixed(Number(value) % 1 ? 1 : 0)} s` : "—";
  const normStatus = job => String(job.status || "draft").toLowerCase();
  function statusInfo(job) {
    const status = normStatus(job);
    if (status.includes("fail") || status === "error") return ["Requiere atención", "error"];
    if (status === "approved" || status === "delivered") return ["Aprobado", "success"];
    if (status === "rejected" || status === "changes_requested") return ["Cambios pendientes", "warning"];
    if (activeStatuses.has(status)) return [{ queued: "En cola", rendering: "Montando", generating: "Generando", processing: "Preparando", voice_generating: "Creando voz", generating_voice: "Creando voz", generating_scenes: "Creando escenas", assembling: "Montando", running: "En producción" }[status], "progress"];
    if (job.output_url || ["ready_for_review", "awaiting_review", "needs_review", "review", "rendered", "draft_rendered"].includes(status)) return ["Pendiente de revisión", "warning"];
    if (status === "blocked") return ["Falta completar", "warning"];
    return ["Plan preparado", "neutral"];
  }
  function url(value) {
    if (!value) return "";
    try { const parsed = new URL(value, location.origin); return parsed.origin === location.origin || parsed.protocol === "https:" ? parsed.href : ""; } catch { return ""; }
  }
  function assetKind(asset) {
    const kind = String(asset.kind || asset.type || asset.media_type || "").toLowerCase();
    if (kind.includes("video") || /\.(mp4|mov|webm)$/i.test(asset.path || asset.filename || "")) return "video";
    if (kind.includes("audio") || /\.(mp3|wav|m4a|aac)$/i.test(asset.path || asset.filename || "")) return "audio";
    return "image";
  }
  const assetName = asset => asset.name || asset.title || asset.label || asset.id || "Recurso";
  const assetUrl = asset => url(asset.url || asset.media_url || `/media/${encodeURIComponent(asset.id)}`);
  const thumbUrl = asset => url(asset.thumbnail_url || asset.thumb_url || asset.poster_url || (assetKind(asset) === "image" ? assetUrl(asset) : ""));
  const jobPlan = job => job.plan || job;
  const jobDuration = job => job.duration || job.target_duration || jobPlan(job).duration || jobPlan(job).target_duration || job.brief?.duration;
  const jobBudget = job => job.budget_usd ?? job.brief?.budget_usd ?? jobPlan(job).budget_usd ?? jobPlan(job).budget?.limit_usd;
  const jobSpend = job => job.spent_usd ?? job.cost_usd ?? job.cost?.spent_usd ?? job.budget?.spent_usd ?? job.reserved_cost_usd ?? 0;
  const spendLabel = job => job.spent_usd !== undefined || job.cost_usd !== undefined || job.cost?.spent_usd !== undefined ? "Consumo" : "Reserva";
  function toast(message, error = false) {
    clearTimeout(state.toast);
    const el = $("#toast"); el.textContent = message; el.classList.toggle("error", error); el.hidden = false;
    state.toast = setTimeout(() => { el.hidden = true; }, 6500);
  }
  async function api(path, options = {}) {
    const headers = { "Accept": "application/json", "X-Studio-Token": state.data?.csrf_token || "", ...(options.headers || {}) };
    if (options.body && typeof options.body !== "string") { headers["Content-Type"] = "application/json"; options.body = JSON.stringify(options.body); }
    const response = await fetch(path, { credentials: "same-origin", ...options, headers });
    const type = response.headers.get("content-type") || "";
    const result = type.includes("application/json") ? await response.json() : {};
    if (!response.ok) throw new Error(result.error || result.message || "No se pudo completar la operación. Inténtalo de nuevo.");
    return result;
  }
  async function busy(button, action) {
    if (button.disabled) return;
    const original = button.innerHTML; button.disabled = true; button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Un momento';
    try { return await action(); } catch (error) { toast(error.message, true); } finally { button.disabled = false; button.innerHTML = original; }
  }
  function setView(view) {
    if (!names[view]) view = "studio";
    state.view = view; $$(".view").forEach(el => { el.hidden = el.id !== `view-${view}`; });
    $$(".main-nav .nav-item").forEach(button => { const selected = button.dataset.view === view; button.classList.toggle("active", selected); if (selected) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current"); });
    $("#view-label").textContent = names[view]; history.replaceState(null, "", `#${view}`); window.scrollTo({ top: 0 });
  }
  function connectionText(provider) {
    const connection = state.data?.connections?.[provider] || {};
    return connection.verified ? ["Conexión verificada", "success"] : connection.configured ? ["Acceso guardado", "warning"] : ["Pendiente de conectar", "neutral"];
  }
  function renderJobs() {
    const jobs = state.data.jobs || [];
    $("#stat-jobs").textContent = jobs.length;
    $("#stat-review").textContent = jobs.filter(job => statusInfo(job)[0] === "Pendiente de revisión").length;
    $("#stat-library").textContent = (state.data.library || []).length;
    $("#stat-voices").textContent = `${Object.keys(roles).filter(role => state.data.voice_cast?.[role]).length} / 3`;
    $("#jobs-list").innerHTML = jobs.length ? jobs.map((job, index) => {
      const [label, cls] = statusInfo(job); const poster = url(job.thumbnail_url || job.poster_url); const output = url(job.output_url);
      return `<article class="job-card" tabindex="0" role="button" data-job-id="${escape(job.id)}" aria-label="Abrir ${escape(job.title || "Vídeo")}"><div class="job-card-visual">${poster ? `<img src="${escape(poster)}" alt="" loading="lazy">` : output ? `<video src="${escape(output)}#t=0.15" muted preload="metadata" playsinline aria-hidden="true"></video>` : `<span class="number">${String(jobs.length - index).padStart(2, "0")}</span>`}<span class="duration-pill">${escape(fmtDuration(jobDuration(job)))}</span></div><div class="job-card-body"><span class="badge ${cls}">${escape(label)}</span><h3>${escape(job.title || job.brief?.title || "Vídeo sin título")}</h3><div class="job-card-meta"><span>${escape(({ hook: "Gancho breve", demo: "Demostración", story: "Minihistoria" })[job.format || job.brief?.format || jobPlan(job).format] || "Pieza de Dropradar")}</span><span>${escape(fmtMoney(jobSpend(job)))}</span></div></div></article>`;
    }).join("") : `<div class="empty-state"><span class="empty-symbol" aria-hidden="true">◫</span><h3>La primera pieza empieza aquí.</h3><p>Define una idea, elige su duración y prepara el plan. Las referencias de tu anuncio ya están en la biblioteca.</p><button class="button secondary" data-action="new-job">Preparar mi primer vídeo <span aria-hidden="true">→</span></button></div>`;
  }
  function renderStyle() {
    const style = state.data.style || {};
    const images = (state.data.library || []).filter(asset => assetKind(asset) === "image");
    const findImage = words => images.find(asset => words.some(word => `${asset.id} ${assetName(asset)} ${asset.role || ""}`.toLowerCase().includes(word))) || images[0];
    const office = findImage(["office-scene-start-01", "office_start_01", "office_01", "oficina", "office"]);
    const son = findImage(["son", "chico", "boy", "identity"]); const mother = findImage(["mother", "madre", "family"]);
    if (office) $("#style-preview").innerHTML = `<img src="${escape(assetUrl(office))}" alt="Referencia de la animación 3D de Dropradar">`;
    $("#style-version").textContent = style.version ? `Perfil ${style.version}` : "Perfil de Dropradar";
    $("#character-grid").innerHTML = [{ name: "El chico", role: "PROTAGONISTA", text: "23 años, pelo castaño y sudadera negra. Un adulto expresivo y reconocible, con el mismo aspecto entre escenas.", asset: son }, { name: "La madre", role: "PERSONAJE RECURRENTE", text: "Adulta, pelo castaño rojizo y chaqueta coral. Su aspecto y su voz se conservan en cada aparición.", asset: mother }].map(item => `<article class="character-card">${item.asset ? `<img src="${escape(assetUrl(item.asset))}" alt="Referencia de ${escape(item.name)}" loading="lazy">` : ""}<div class="character-card-content"><div class="eyebrow">${item.role}</div><h3>${item.name}</h3><p>${item.text}</p></div></article>`).join("");
    const rules = [
      ["◈", "Animación 3D cinematográfica", "Personajes expresivos, luz integrada y escenarios completos. Las referencias guían la generación de cada plano."],
      ["▤", "La web real, siempre nítida", "La captura se compone dentro de la pantalla del ordenador. Aparición breve y legible, conservando su diseño."],
      ["Aa", "Subtítulos blancos y grandes", "Sin contorno negro ni sombra. Frases completas, un máximo de dos líneas y colocación visible en el móvil."],
      ["≋", "Voces fijas en español", "Un reparto de ElevenLabs para mantener cada timbre. Se ajusta el montaje a la locución sin cortar palabras."],
      ["↝", "Continuidad y ritmo", "Acciones claras, movimientos coherentes y transiciones intencionadas. Se revisan los cambios de plano."],
      ["◌", "Un final natural", "Sin tarjeta final de marca ni rótulo superior. Historias ficticias sin cifras inventadas presentadas como resultados reales."]
    ];
    $("#style-rules").innerHTML = rules.map(([icon, title, text]) => `<article class="rule-card"><span class="rule-icon" aria-hidden="true">${icon}</span><h3>${title}</h3><p>${text}</p></article>`).join("");
    const reference = $("#reference-select"); const selected = reference.value;
    reference.innerHTML = '<option value="">Selecciona una escena de la biblioteca</option>' + images.filter(asset => asset.approved !== false && !/screen|web|captura/i.test(`${asset.id} ${asset.role || ""} ${assetName(asset)}`)).map(asset => `<option value="${escape(asset.id)}">${escape(assetName(asset))}</option>`).join("");
    if ([...reference.options].some(option => option.value === selected)) reference.value = selected;
    else if (office) reference.value = office.id;
  }
  function renderLibrary() {
    const library = state.data.library || []; $("#library-count").textContent = `${library.length} recursos`;
    const list = library.filter(asset => state.filter === "all" || assetKind(asset) === state.filter);
    $("#library-grid").innerHTML = list.length ? list.map(asset => {
      const kind = assetKind(asset), thumb = thumbUrl(asset), media = assetUrl(asset);
      const label = asset.historical || asset.role === "previous_final" || /final|anuncio|master/.test(String(asset.id)) ? "Referencia anterior" : kind === "video" ? "Vídeo" : kind === "audio" ? "Audio" : "Imagen";
      return `<article class="asset-card" tabindex="0" role="button" data-asset-id="${escape(asset.id)}" aria-label="Ver ${escape(assetName(asset))}"><div class="asset-thumb">${thumb ? `<img src="${escape(thumb)}" alt="" loading="lazy">` : kind === "video" ? `<video src="${escape(media)}#t=0.1" muted preload="metadata" playsinline aria-hidden="true"></video>` : '<span class="media-icon" aria-hidden="true">≋</span>'}<span class="kind-label">${escape(label)}</span></div><div class="asset-info"><h3>${escape(assetName(asset))}</h3><p>${escape(asset.description || (asset.duration ? fmtDuration(asset.duration) : asset.approved === true ? "Referencia disponible" : "Recurso de trabajo"))}</p></div></article>`;
    }).join("") : '<div class="empty-state"><h3>No hay recursos en esta categoría.</h3><p>Las escenas y voces producidas se guardan para poder reutilizarlas.</p></div>';
  }
  function renderVoices() {
    if (state.castDirty) return;
    const voices = state.data.voices || []; const connection = state.data.connections?.elevenlabs || {};
    $("#voices-notice").textContent = connection.verified ? "ElevenLabs está conectado. Elige las voces disponibles y escucha sus muestras antes de fijar el reparto." : connection.configured ? "Hay un acceso guardado. Actualiza las voces para comprobar la conexión con ElevenLabs." : "Falta conectar ElevenLabs. Puedes preparar el estudio mientras completas la conexión desde la pestaña Conexiones.";
    $("#load-voices").disabled = !connection.configured;
    $("#voice-cards").innerHTML = Object.entries(roles).map(([role, info]) => {
      const value = state.data.voice_cast?.[role] || "";
      return `<article class="voice-card"><div class="voice-avatar" aria-hidden="true">${info.symbol}</div><h3>${info.name}</h3><p>${info.description}</p><label>Voz de ElevenLabs<select name="${role}" ${!voices.length ? "disabled" : ""}><option value="">Sin asignar</option>${voices.map(voice => `<option value="${escape(voice.voice_id || voice.id)}" ${(voice.voice_id || voice.id) === value ? "selected" : ""}>${escape(voice.name || voice.voice_id)}</option>`).join("")}</select></label><div class="voice-preview" data-preview-role="${role}"></div></article>`;
    }).join("");
    $("#cast-form button[type=submit]").disabled = !voices.length;
    Object.keys(roles).forEach(renderVoicePreview);
  }
  function renderVoicePreview(role) {
    const select = $(`#cast-form select[name="${role}"]`); if (!select) return;
    const voice = (state.data.voices || []).find(item => (item.voice_id || item.id) === select.value); const target = $(`[data-preview-role="${role}"]`); const preview = url(voice?.preview_url);
    const labels = voice?.labels && typeof voice.labels === "object" ? Object.values(voice.labels).filter(value => typeof value === "string").slice(0, 4).join(" · ") : "";
    target.innerHTML = preview ? `<audio src="${escape(preview)}" controls preload="none" aria-label="Muestra de ${escape(voice.name)}"></audio><p class="voice-hint">${escape(labels || "Muestra facilitada por ElevenLabs.")}</p>` : `<p class="voice-hint">${voice ? "Esta voz no tiene una muestra disponible." : "Selecciona una voz para escuchar su muestra."}</p>`;
  }
  function renderConnections() {
    const providers = [{ id: "elevenlabs", name: "ElevenLabs", icon: "Ⅱ", description: "Voces de los personajes y narración con tiempos para sincronizar los subtítulos.", link: "https://elevenlabs.io/app/settings/api-keys", label: "Abrir ElevenLabs" }, { id: "fal", name: "fal", icon: "fal", description: "Generación de escenas a partir de referencias, con un límite de gasto por pieza.", link: "https://fal.ai/dashboard/keys", label: "Abrir fal" }];
    $("#connection-cards").innerHTML = providers.map(provider => {
      const connection = state.data.connections?.[provider.id] || {}; const [label, cls] = connectionText(provider.id);
      return `<article class="connection-card"><div class="connection-card-header"><div class="provider-name"><span class="provider-icon ${provider.id}" aria-hidden="true">${provider.icon}</span>${provider.name}</div><span class="badge ${cls}">${label}</span></div><p>${provider.description}</p><div class="connection-message">${escape(connection.message || (connection.verified ? "El servicio ha respondido correctamente." : connection.configured ? "El acceso está guardado. La disponibilidad se comprueba al conectar con el servicio." : "Completa la conexión para usar este servicio."))}</div><div class="connection-actions">${provider.id === "elevenlabs" ? `<button class="button secondary small" data-action="test-elevenlabs" ${!connection.configured ? "disabled" : ""}>Comprobar conexión</button>` : ""}<a class="text-button" href="${provider.link}" target="_blank" rel="noopener noreferrer">${provider.label} ↗</a></div><details ${!connection.configured ? "open" : ""}><summary>${connection.configured ? "Actualizar acceso" : "Conectar con una clave de API"}</summary><form data-credential-form="${provider.id}" autocomplete="off"><label>Clave privada de ${provider.name}<input type="password" name="api_key" required minlength="10" autocomplete="new-password" spellcheck="false" aria-label="Clave privada de ${provider.name}"></label><small>Se guarda en el servidor local. No se mostrará después de guardarla.</small><button class="button primary small" type="submit">Guardar acceso</button></form></details></article>`;
    }).join("");
    const count = Object.values(state.data.connections || {}).filter(item => item?.verified).length;
    $("#connection-summary").textContent = count ? `${count} ${count === 1 ? "conexión verificada" : "conexiones verificadas"}` : "Conexiones por completar";
  }
  function renderAll() { renderJobs(); renderStyle(); renderLibrary(); renderVoices(); renderConnections(); }
  async function refresh({ silent = false } = {}) {
    try {
      state.data = await api("/api/bootstrap"); state.data.jobs ||= []; state.data.library ||= []; state.data.voices ||= [];
      $("#load-error").hidden = true; renderAll(); schedulePoll();
    } catch (error) { if (!silent) { $("#load-error").textContent = `No se pudo cargar el estudio. ${error.message}`; $("#load-error").hidden = false; } }
  }
  function schedulePoll() {
    clearTimeout(state.poll);
    if ((state.data?.jobs || []).some(job => activeStatuses.has(normStatus(job)))) state.poll = setTimeout(async () => {
      await refresh({ silent: true });
      if (state.job && $("#job-dialog").open && activeStatuses.has(normStatus(state.job))) {
        const updated = state.data.jobs.find(job => job.id === state.job.id); if (updated) showJob(updated, false);
      }
    }, 3500);
  }
  function normalizeJob(result) { return result.job || result; }
  async function openJob(id) {
    try { const job = normalizeJob(await api(`/api/jobs/${encodeURIComponent(id)}`)); showJob(job); }
    catch (error) { toast(error.message, true); }
  }
  function showJob(job, open = true) {
    state.job = job;
    const plan = jobPlan(job), brief = job.brief || {}; const [label, cls] = statusInfo(job); const output = url(job.output_url); const shots = plan.shots || job.shots || [];
    const connection = state.data.connections || {}; const voiceRole = brief.voice_role || plan.voice_role || "narrator"; const needsVoice = Boolean(brief.script || plan.script || plan.narrations?.some(item => item.text));
    const generating = activeStatuses.has(normStatus(job)); const hasReference = shots.some(shot => shot.reference_asset_id) || brief.reference_asset_id || plan.reference_asset_id;
    const canGenerate = !generating && connection.fal?.configured && (!needsVoice || (connection.elevenlabs?.configured && state.data.voice_cast?.[voiceRole])) && Boolean(hasReference) && Number.isFinite(Number(jobBudget(job))) && Number(jobBudget(job)) > 0 && !(job.issues || plan.issues || []).some(issue => issue.severity === "error");
    const disabledReasons = [];
    if (!connection.fal?.configured) disabledReasons.push("Conecta fal para generar escenas.");
    if (needsVoice && !connection.elevenlabs?.configured) disabledReasons.push("Conecta ElevenLabs para crear la locución.");
    if (needsVoice && !state.data.voice_cast?.[voiceRole]) disabledReasons.push("Asigna la voz seleccionada en el reparto.");
    if (!hasReference) disabledReasons.push("Selecciona una referencia visual al crear el plan.");
    const estimate = plan.estimate_usd ?? plan.estimated_cost_usd ?? plan.cost_estimate?.total_usd ?? plan.budget?.estimated_usd;
    const issues = job.issues || plan.issues || job.validation_issues || [];
    const qa = job.qa || job.quality || job.technical_review || {};
    const technical = qa.status || qa.technical_status || (qa.technical_passed === true || qa.passed === true ? "passed" : qa.technical_passed === false || qa.passed === false ? "failed" : "pending");
    const review = job.creative_review || job.review || {};
    const script = brief.script || plan.script || (plan.narrations || []).map(item => item.text).filter(Boolean).join("\n");
    const shotLabels = { hook: ["Inicio", "Una reacción del protagonista presenta la idea."], problem: ["El problema", "El protagonista se encuentra con una dificultad."], work: ["En marcha", "El personaje trabaja en su entorno habitual."], screen: ["La aplicación", "La web real se muestra dentro de la pantalla del ordenador."], research: ["La investigación", "El personaje compara opciones con gestos claros y naturales."], resolution: ["El desenlace", "El gesto final se completa y la escena termina de forma natural."] };
    const approved = normStatus(job) === "approved";
    $("#job-title").textContent = job.title || brief.title || "Vídeo de Dropradar";
    $("#job-eyebrow").textContent = output ? "MONTAJE PARA REVISAR" : "PLAN DE PRODUCCIÓN";
    $("#job-detail").innerHTML = `<div class="job-detail-layout"><div class="job-visual">${output ? `<video class="job-video" src="${escape(output)}" controls preload="metadata" playsinline></video><a class="button secondary small" style="width:100%;margin-top:10px" href="${escape(output)}" download>Descargar ${approved ? "vídeo" : "borrador"}</a>` : `<div class="job-poster"><strong>${escape(fmtDuration(jobDuration(job)))}</strong><span>El vídeo aparecerá aquí después del montaje.</span></div>`}</div><div><span class="badge ${cls}">${escape(label)}</span><div class="job-facts"><span>Duración: ${escape(fmtDuration(jobDuration(job)))}</span><span>Vídeo e imágenes: ${escape(fmtMoney(jobBudget(job)))}</span><span>${spendLabel(job)}: ${escape(fmtMoney(jobSpend(job)))}</span></div>${job.message || job.error ? `<div class="notice ${job.error ? "error" : ""}">${escape(job.error || job.message)}</div>` : ""}<p class="job-description">${escape(brief.concept || plan.concept || job.concept || "")}</p>${script ? `<h3 class="detail-heading">Locución</h3><p class="job-description">${escape(script)}</p>` : ""}<h3 class="detail-heading">Planos de la pieza</h3><ol class="shot-list">${shots.map((shot, index) => `<li><span class="shot-index">${String(index + 1).padStart(2, "0")}</span><div><strong>${escape(shot.title || shot.label || shotLabels[shot.role]?.[0] || `Plano ${index + 1}`)}</strong><p>${escape(shot.description || shotLabels[shot.role]?.[1] || "Plano de la biblioteca")}</p><small>${escape(fmtDuration(shot.duration ?? ((shot.source_out || 0) - (shot.source_in || 0))))} · ${shot.mode === "library" ? "Biblioteca existente" : "Nueva generación"}</small></div></li>`).join("") || '<li><div><p>El plan no contiene planos todavía.</p></div></li>'}</ol>${issues.length ? `<ul class="qa-list">${issues.map(issue => `<li><span>!</span>${escape(typeof issue === "string" ? issue : issue.message)}</li>`).join("")}</ul>` : ""}<div class="job-actions"><button class="button secondary small" data-job-action="render-local" ${generating ? "disabled" : ""}>Montar con biblioteca</button><button class="button primary small" data-job-action="generate" ${canGenerate ? "" : "disabled"}>Generar · tope ${escape(fmtMoney(jobBudget(job)))}</button></div><p class="cost-note">${estimate !== undefined ? `Estimación del plan: ${escape(fmtMoney(estimate))}. ` : ""}El tope corresponde a vídeo e imágenes. La voz consume por separado los créditos de tu plan de ElevenLabs. El montaje con biblioteca prepara un borrador con el material disponible.</p>${disabledReasons.length ? `<p class="cost-note">${escape(disabledReasons.join(" "))}</p>` : ""}</div></div>${output ? `<section class="review-section"><h3>Revisión antes de aprobar</h3><p>Comprobación del archivo: <strong>${escape(["pass", "passed", "ok"].includes(String(technical).toLowerCase()) ? "completada" : ["fail", "failed", "error"].includes(String(technical).toLowerCase()) ? "requiere correcciones" : "pendiente")}</strong>. Revisa también el contenido completo; esta aprobación no publica el vídeo.</p><form class="review-form"><div class="check-grid">${Object.entries(reviewChecks).map(([key, value]) => `<label><input type="checkbox" name="${key}" ${review.checks?.[key] === true ? "checked" : ""}>${value}</label>`).join("")}</div><label>Notas de revisión<textarea name="notes" rows="2" placeholder="Qué funciona y qué hay que corregir">${escape(review.notes || "")}</textarea></label><div class="job-actions"><button class="button secondary small" type="button" data-job-action="reject">Pedir correcciones</button><button class="button primary small" type="submit" ${qa.technical_passed === true || qa.passed === true || ["pass", "passed", "ok"].includes(String(technical).toLowerCase()) ? "" : "disabled"}>Aprobar revisión</button></div></form></section>` : ""}`;
    if (open && !$("#job-dialog").open) $("#job-dialog").showModal();
  }
  function openAsset(id) {
    const asset = (state.data.library || []).find(item => item.id === id); if (!asset) return;
    const kind = assetKind(asset), media = escape(assetUrl(asset)); $("#asset-title").textContent = assetName(asset);
    $("#asset-detail").innerHTML = `${kind === "video" ? `<video class="asset-detail-media" src="${media}" controls preload="metadata" playsinline></video>` : kind === "audio" ? `<audio class="asset-detail-media" src="${media}" controls preload="metadata"></audio>` : `<img class="asset-detail-media" src="${media}" alt="${escape(assetName(asset))}">`}<p class="asset-detail-caption">${escape(asset.description || "Recurso de la biblioteca del estudio.")}</p><p class="asset-detail-caption">Este recurso se conserva como material de referencia y reutilización.</p>`;
    $("#asset-dialog").showModal();
  }
  async function jobAction(action, button) {
    const job = state.job; if (!job) return;
    await busy(button, async () => {
      let result;
      if (action === "reject") {
        const form = $(".review-form"); const checks = Object.fromEntries(Object.keys(reviewChecks).map(key => [key, form.elements[key].checked]));
        result = await api(`/api/jobs/${encodeURIComponent(job.id)}/review`, { method: "POST", body: { approved: false, checks, notes: form.elements.notes.value } });
      } else result = await api(`/api/jobs/${encodeURIComponent(job.id)}/${action}`, { method: "POST", body: action === "generate" ? { max_cost_usd: Number(jobBudget(job)) } : {} });
      await refresh({ silent: true }); showJob(normalizeJob(result), false); toast(action === "reject" ? "Cambios solicitados guardados." : "Trabajo enviado al estudio.");
    });
  }
  document.addEventListener("click", async event => {
    const button = event.target.closest("button");
    const view = event.target.closest("[data-view]"); if (view) { setView(view.dataset.view); return; }
    if (button?.matches("[data-close-dialog]")) { button.closest("dialog").close(); return; }
    if (button?.dataset.action === "new-job") { $("#new-job-error").hidden = true; $("#new-job-dialog").showModal(); return; }
    const jobCard = event.target.closest("[data-job-id]"); if (jobCard) { openJob(jobCard.dataset.jobId); return; }
    const assetCard = event.target.closest("[data-asset-id]"); if (assetCard) { openAsset(assetCard.dataset.assetId); return; }
    if (button?.dataset.libraryFilter) { state.filter = button.dataset.libraryFilter; $$("[data-library-filter]").forEach(el => el.classList.toggle("active", el === button)); renderLibrary(); return; }
    if (button?.dataset.jobAction) { await jobAction(button.dataset.jobAction, button); return; }
    if (button?.id === "refresh-button") { await busy(button, () => refresh()); return; }
    if (button?.id === "load-voices" || button?.dataset.action === "test-elevenlabs") {
      await busy(button, async () => {
        const result = await api(button.id === "load-voices" ? "/api/voices" : "/api/connections/elevenlabs/test");
        if (result.verified === false || result.connected === false || result.ok === false) throw new Error(result.message || "No se pudo verificar la conexión.");
        state.castDirty = false; await refresh({ silent: true });
        if (button.id === "load-voices" && Array.isArray(result.voices || result)) { state.data.voices = result.voices || result; renderVoices(); }
        toast(button.id === "load-voices" ? "Voces actualizadas." : "Conexión con ElevenLabs comprobada.");
      });
    }
  });
  document.addEventListener("keydown", event => { if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-job-id],[data-asset-id]")) { event.preventDefault(); event.target.click(); } });
  document.addEventListener("change", event => { if (event.target.matches("#cast-form select")) { state.castDirty = true; renderVoicePreview(event.target.name); } });
  document.addEventListener("submit", async event => {
    const form = event.target;
    if (form.id === "new-job-form") {
      event.preventDefault(); const button = $("button[type=submit]", form); const data = Object.fromEntries(new FormData(form)); data.duration = Number(data.duration); data.budget_usd = Number(data.budget_usd);
      await busy(button, async () => {
        try { const result = normalizeJob(await api("/api/jobs", { method: "POST", body: data })); form.closest("dialog").close(); await refresh({ silent: true }); showJob(result); toast("Plan creado. Revisa los planos antes de generar."); }
        catch (error) { $("#new-job-error").textContent = error.message; $("#new-job-error").hidden = false; throw error; }
      });
    } else if (form.id === "cast-form") {
      event.preventDefault(); await busy($("button[type=submit]", form), async () => { await api("/api/voice-cast", { method: "POST", body: Object.fromEntries(new FormData(form)) }); state.castDirty = false; await refresh({ silent: true }); toast("Reparto guardado para las próximas piezas."); });
    } else if (form.dataset.credentialForm) {
      event.preventDefault(); await busy($("button[type=submit]", form), async () => {
        const key = form.elements.api_key.value.trim();
        try { await api("/api/credentials", { method: "POST", body: { provider: form.dataset.credentialForm, api_key: key } }); form.elements.api_key.value = ""; await refresh({ silent: true }); toast("Acceso guardado. Comprueba la conexión para verificarlo."); }
        catch (error) { form.elements.api_key.value = ""; throw error; }
      });
    } else if (form.matches(".review-form")) {
      event.preventDefault(); const checks = Object.fromEntries(Object.keys(reviewChecks).map(key => [key, form.elements[key].checked]));
      if (!Object.values(checks).every(Boolean)) { toast("Completa los seis puntos de revisión antes de aprobar.", true); return; }
      await busy($("button[type=submit]", form), async () => { const result = await api(`/api/jobs/${encodeURIComponent(state.job.id)}/review`, { method: "POST", body: { approved: true, checks, notes: form.elements.notes.value } }); await refresh({ silent: true }); showJob(normalizeJob(result), false); toast("Revisión guardada."); });
    }
  });
  $$("dialog").forEach(dialog => dialog.addEventListener("close", () => { $$("video,audio", dialog).forEach(media => media.pause()); }));
  window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
  setView(location.hash.slice(1) || "studio"); refresh();
})();
