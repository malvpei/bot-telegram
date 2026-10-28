"""Publication copy grounded in the delivered slides, with persistent variety."""

from __future__ import annotations

import hashlib
import itertools
import random
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from typing import TYPE_CHECKING

from app.models import GenerationResult, Language, SocialCopy, VideoType

if TYPE_CHECKING:
    from app.publication_writer import PublicationWriter
    from app.state import StateStore


HISTORY_LIMIT = 120
_STYLES = ("none", "short", "medium")
_PARKEZ_TYPES = {
    VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.PARKEZ_ADVICE,
    VideoType.PARKEZ_APPS, VideoType.TOOLS,
}
_ENTITIES = (
    "Notion", "Claude", "Waze", "Mathway", "ScreenZen", "Fintonic", "ParkEz",
    "RadarBot", "Google Maps", "miDGT", "Shopify", "ChatGPT", "PayPal", "Stripe",
    "Canva", "CapCut", "Instagram", "TikTok", "DeepSeek", "Dropradar",
    "GoGraduate", "Todoist", "Evernote", "Forest", "Duolingo", "Amazon FBA", "Clipping", "Print on demand",
    "Marketing de afiliados", "Affiliate marketing", "Trading",
)
_FORBIDDEN_PROMISES = re.compile(
    r"garantiz\w*|guarantee\w*|100\s*%|sin riesgo|risk.free|dinero f[aá]cil|"
    r"easy money|aprobado asegurado|plaza asegurada", re.IGNORECASE,
)
_ESSENTIALS = {
    "dropradar": ("#dropshipping", "#Dropradar"),
    "parkez": ("#coches", "#ParkEz"),
    "gograduate": ("#estudiantes", "#gograduate"),
}
_TOPICS = {
    ("story", "es"): (
        "entender las primeras pruebas de una tienda", "investigar antes de volver a lanzar",
        "aprender de un producto que no funciona", "mirar la demanda con más criterio",
        "poner en perspectiva los primeros resultados", "revisar cómo se elige un producto",
    ),
    ("story", "en"): (
        "understand a store's first experiments", "research before launching again",
        "learn from a product that does not sell", "look at demand more carefully",
        "put early results into perspective", "rethink how to choose a product",
    ),
    ("tips", "es"): (
        "elegir productos con más criterio", "revisar una idea antes de lanzarla",
        "entender qué puede mejorar una tienda", "preparar la siguiente prueba",
        "encontrar señales de demanda", "organizar mejor el trabajo de una tienda",
    ),
    ("tips", "en"): (
        "choose products more carefully", "review an idea before launching it",
        "understand what a store could improve", "prepare the next experiment",
        "look for signs of demand", "organize the work behind an online store",
    ),
    ("tools", "es"): (
        "organizar las herramientas de tu tienda", "dar una función a cada herramienta",
        "preparar contenido para una tienda", "investigar productos y organizar el trabajo",
        "montar un flujo de trabajo sencillo", "elegir herramientas según lo que necesitas",
    ),
    ("tools", "en"): (
        "organize the tools behind your store", "give each tool a clear job",
        "prepare content for a store", "research products and organize the work",
        "build a straightforward workflow", "choose tools around what you need",
    ),
    ("apps", "es"): (
        "elegir apps que resuelvan algo concreto", "preparar mejor tu día a día",
        "organizar tus apps por lo que hacen", "preparar la llegada a tu destino",
        "buscar aparcamiento con más información", "combinar apps para tareas distintas",
    ),
    ("apps", "en"): (
        "choose apps that solve a specific problem", "prepare for your day",
        "organize apps around what they do", "plan your arrival before setting off",
        "look for parking with more information", "combine apps for different tasks",
    ),
    ("driving", "es"): (
        "preparar el trayecto antes de salir", "planear dónde buscar aparcamiento",
        "organizar la llegada a tu destino", "buscar sitio dando menos vueltas",
        "conducir con menos improvisaciones", "preparar tus apps antes del viaje",
    ),
    ("driving", "en"): (
        "prepare your journey before setting off", "plan where to look for parking",
        "organize your arrival", "look for parking with less circling",
        "leave less to chance on a drive", "set up your apps before a journey",
    ),
    ("study", "es"): (
        "repasar lo que todavía cuesta", "recordar antes de releer",
        "detectar tus dudas al estudiar", "organizar tus repasos",
        "trabajar con tus apuntes", "aprender de los errores de un repaso",
    ),
    ("study", "en"): (
        "review what still feels difficult", "recall before rereading",
        "spot gaps while studying", "organize your revision",
        "work with your notes", "learn from mistakes during revision",
    ),
}
_TITLE_FRAMES = {
    "es": ("{topic}", "Cómo {lower}", "Antes de {lower}", "Una idea para {lower}",
           "Por dónde empezar para {lower}", "Lo que revisaría para {lower}",
           "¿Quieres {lower}?", "Otra forma de {lower}", "Para {lower}, empieza aquí",
           "Lo que conviene mirar al {lower}"),
    "en": ("{topic}", "How to {lower}", "Before you {lower}", "An idea to {lower}",
           "Where to start if you want to {lower}", "What to check when you {lower}",
           "Want to {lower}?", "Another way to {lower}", "A starting point to {lower}",
           "A closer look at how to {lower}"),
}


@lru_cache(maxsize=8192)
def _identity(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(re.findall(r"[^\W\d_]+", plain))


@lru_cache(maxsize=8192)
def _similarity(first: str, second: str) -> float:
    a, b = _identity(first), _identity(second)
    if a == b:
        return 1.0
    words_a, words_b = set(a.split()), set(b.split())
    overlap = len(words_a & words_b) / max(1, len(words_a | words_b))
    return max(SequenceMatcher(None, a, b, autojunk=False).ratio(), overlap)


def _entity_names(text: str) -> list[str]:
    return [name for name in _ENTITIES if re.search(
        r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.IGNORECASE,
    )]


def _sentence(text: str, maximum: int = 210) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    first = re.split(r"(?<=[.!?])\s+", text)[0]
    if len(first) > maximum:
        first = first[:maximum].rsplit(" ", 1)[0].rstrip(",;:")
    return first.rstrip(".") + "." if first else ""


def _family(video_type: VideoType) -> str:
    if video_type == VideoType.GOGRADUATE_TYPE_1:
        return "study"
    if video_type in {VideoType.PARKEZ, VideoType.PARKEZ_MODE3}:
        return "driving"
    if video_type in _PARKEZ_TYPES:
        return "apps"
    if video_type == VideoType.TYPE_5:
        return "business"
    if video_type in {VideoType.TYPE_1, VideoType.TYPE_4}:
        return "story"
    return "tools" if video_type == VideoType.TYPE_3 else "tips"


def publication_context(result: GenerationResult) -> dict:
    video_type = result.video_type
    brand = ("parkez" if video_type in _PARKEZ_TYPES else
             "gograduate" if video_type == VideoType.GOGRADUATE_TYPE_1 else "dropradar")
    slides = [{"role": slide.role.value, "text": slide.text[:1800]}
              for slide in result.slides if slide.text.strip()]
    # Only delivered copy is evidence. Decorative media captions are unrelated.
    content = "\n".join(slide["text"] for slide in slides) or result.preview_text[:9000]
    own_app = {"dropradar": "Dropradar", "parkez": "ParkEz", "gograduate": "GoGraduate"}[brand]
    named_cards = [
        re.sub(r"^\s*\d+\.\s*", "", slide["text"].splitlines()[0]).strip()
        for slide in slides
        if slide["role"] == "app_store" or slide["role"].startswith("car_tool_")
    ]
    return {"brand": brand, "brand_name": "gograduate.io" if brand == "gograduate" else own_app,
            "language": result.language.value, "family": _family(video_type),
            "video_type": video_type.value, "slides": slides,
            "content": content[:12000], "entities": list(dict.fromkeys([own_app, *_entity_names(content), *named_cards]))}


def _planned_format(history: dict, brand: str) -> tuple[str, list[str]]:
    remaining = history.get("formats_remaining")
    if not isinstance(remaining, list) or len(remaining) != len(set(
        item for item in remaining if isinstance(item, str)
    )) or any(item not in _STYLES for item in remaining):
        remaining = []
    remaining = list(remaining)
    if not remaining:
        count = history.get("count", 0)
        count = count if isinstance(count, int) and count >= 0 else 0
        seed = hashlib.sha256(f"{brand}:{count // 3}:publication-v1".encode()).hexdigest()
        random.Random(seed).shuffle(remaining := list(_STYLES))
        if remaining[0] == "none" and history.get("last_format") == "none":
            remaining[0], remaining[1] = remaining[1], remaining[0]
    return remaining[0], remaining[1:]


def _records(history: dict, language: str) -> list[dict]:
    profiles = history.get("languages", {})
    profile = profiles.get(language, []) if isinstance(profiles, dict) else []
    return [entry for entry in profile if isinstance(entry, dict)][-HISTORY_LIMIT:] if isinstance(profile, list) else []


def _recent(records: list[dict], field: str) -> list[str]:
    return [entry[field] for entry in records if isinstance(entry.get(field), str) and entry[field]]


def _allowed_text(text: str, context: dict) -> bool:
    if _FORBIDDEN_PROMISES.search(text) or re.search(r"(?<!\w)#[^\W\d_]\w*", text) or re.search(r"https?://", text):
        return False
    allowed = {_identity(name) for name in context["entities"]}
    if any(_identity(name) not in allowed for name in _entity_names(text)):
        return False
    # Counts may refer to the actual slides; revenue, percentages and dates
    # must come from the content, not be invented to make a stronger headline.
    number_pattern = r"\d+(?:[.,]\d+)*"
    source_numbers = {value.replace(",", "").replace(".", "") for value in re.findall(number_pattern, context["content"])}
    slide_count = len(context.get("slides", []))
    source_numbers.update(str(value) for value in range(1, slide_count + 1))
    numbers = {value.replace(",", "").replace(".", "") for value in re.findall(number_pattern, text)}
    if not numbers <= source_numbers:
        return False
    invented_result = re.search(
        r"\b(?:ayer gan[eé]|he ganado|me hice millonari[oa]|me gradu[eé]|"
        r"i earned|i made money|i graduated|sin estudiar|sin esfuerzo)\b", text, re.IGNORECASE,
    )
    return invented_result is None or _identity(invented_result.group()) in _identity(context["content"])


def _valid_written(copy: object, context: dict, style: str, records: list[dict], hook: str) -> bool:
    if not isinstance(copy, dict) or not all(isinstance(copy.get(key), str) for key in ("title", "description")):
        return False
    title, description = copy["title"].strip(), copy["description"].strip()
    limit = 220 if style == "short" else 550
    if not 8 <= len(title) <= 120 or "\n" in title or _identity(title) == _identity(hook):
        return False
    if (style == "none" and description) or (style != "none" and not 20 <= len(description) <= limit):
        return False
    if not _allowed_text(title + " " + description, context):
        return False
    if any(re.match(r"(?:explora|descubre|optimiza|en este v[ií]deo|in this video|discover|unlock)\b", text, re.IGNORECASE) for text in (title, description)):
        return False
    if any(_similarity(title, old) >= 0.86 for old in _recent(records, "title")):
        return False
    return not description or not any(
        _similarity(description, old) >= 0.88 for old in _recent(records, "description")[-60:]
    )


def _brand_wording(copy: object, context: dict) -> object:
    if context["brand"] != "gograduate" or not isinstance(copy, dict):
        return copy
    return {
        key: re.sub(r"\bgograduate(?:\.[a-z]+)*\b", "gograduate.io", value, flags=re.IGNORECASE)
        if isinstance(value, str) else value
        for key, value in copy.items()
    }


def _fallback_topics(context: dict) -> list[str]:
    language, family = context["language"], context["family"]
    if family == "business":
        entities = [name for name in context["entities"] if name in {
            "Trading", "Clipping", "Amazon FBA", "Print on demand",
            "Marketing de afiliados", "Affiliate marketing",
        }]
        names = " y ".join(entities) if language == "es" else " and ".join(entities)
        if not names:
            names = "negocios online" if language == "es" else "online businesses"
        return ([f"comparar {names}", f"valorar qué exige {names}",
                 f"elegir un modelo de negocio con criterio", "entender AI + Dropshipping",
                 "comparar el trabajo detrás de cada negocio", "revisar cómo empezar un negocio online"]
                if language == "es" else
                [f"compare {names}", f"look at the work behind {names}",
                 "choose an online business model", "understand AI + Dropshipping",
                 "compare what each business involves", "review how to start an online business"])
    topics = list(_TOPICS[(family, language)])
    if family in {"apps", "tools"}:
        for name in context["entities"]:
            topics.append(f"entender para qué sirve {name}" if language == "es" else f"see what {name} is for")
    return topics


def _facts(context: dict) -> list[str]:
    facts = []
    for slide in context.get("slides", []):
        if slide["role"] in {"hook", "story_original_reference"}:
            continue
        text = slide["text"]
        if slide["role"] == "advice_card":
            parts = []
            for part in re.split(r"(?:^|\n)\s*\d+\.\s+", text):
                lines = [line.strip() for line in part.splitlines() if line.strip()]
                parts.append(f"{lines[0]}: {' '.join(lines[1:])}" if len(lines) > 1 else part)
        else:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if slide["role"] == "app_store" and len(lines) > 1:
                names = _entity_names(lines[0])
                name = names[0] if names else lines[0]
                body = re.sub(r"^te permite\s+", "permite ", lines[-1], flags=re.IGNORECASE)
                body = re.sub(r"\s+de una manera que ninguna app iguala[.!]?", ".", body, flags=re.IGNORECASE)
                parts = [f"{name} {body[0].lower() + body[1:]}" if body else name]
            else:
                parts = [f"{lines[0]}: {lines[-1]}" if len(lines) > 1 else text]
        for part in parts:
            sentence = _sentence(part)
            if sentence and _allowed_text(sentence, context):
                facts.append(sentence)
    if not facts:
        facts = [_sentence(part) for part in re.split(r"(?<=[.!?])\s+", context["content"]) if part.strip()]
    return list(dict.fromkeys(fact for fact in facts if _allowed_text(fact, context)))


def _pick_text(candidates: list[str], recent: list[str], forbidden: str = "") -> str:
    unique = list({ _identity(text): text for text in candidates if text.strip() and _identity(text) != _identity(forbidden)}.values())
    if not unique:
        raise ValueError("No hay textos de publicación adecuados para este contenido.")
    seen = {_identity(text) for text in recent}
    unseen = [text for text in unique if _identity(text) not in seen]
    if unseen:
        pool = unseen
    else:
        # When the offline bank is exhausted, reuse the oldest wording rather
        # than falling back to the first few entries on every subsequent call.
        last_use = {_identity(text): index for index, text in enumerate(recent)}
        oldest = min(last_use.get(_identity(text), -1) for text in unique)
        pool = [text for text in unique if last_use.get(_identity(text), -1) == oldest]
    scored = [(max((_similarity(text, old) for old in recent[-30:]), default=0), text) for text in pool]
    scored.sort(key=lambda pair: pair[0])
    best = scored[0][0]
    return random.choice([text for score, text in scored if score <= best + 0.05])


def _fallback_copy(context: dict, style: str, records: list[dict], hook: str) -> dict:
    language = context["language"]
    titles = []
    for topic in _fallback_topics(context):
        fields = {"lower": topic, "topic": topic[0].upper() + topic[1:]}
        titles.extend(frame.format(**fields) for frame in _TITLE_FRAMES[language])
    # Use the actual selected advice as additional angles, so switching packs
    # changes the offline bank as well as the AI prompt.
    headings = [
        heading.strip().split(": ", 1)[0]
        for slide in context.get("slides", []) if slide["role"] == "advice_card"
        for heading in re.findall(r"(?:^|\n)\s*\d+\.\s*([^\n]+)", slide["text"])
    ]
    heading_frames = (
        ("{heading}", "{heading}: una idea para probar", "Una pausa para esto: {lower}",
         "Empieza por esto: {lower}", "Una idea concreta: {lower}", "Para tu próxima sesión: {lower}")
        if language == "es" else
        ("{heading}", "{heading}: an idea to try", "Take a moment to {lower}",
         "Start here: {lower}", "A practical idea: {lower}", "For your next session: {lower}")
    )
    for heading in headings:
        if 8 <= len(heading) <= 85:
            titles.extend(frame.format(heading=heading, lower=heading[0].lower() + heading[1:]) for frame in heading_frames)
    title = _pick_text([text for text in titles if len(text) <= 120 and _allowed_text(text, context)], _recent(records, "title"), hook)
    if style == "none":
        return {"title": title, "description": ""}
    facts = _facts(context)
    if not facts:
        facts = (["Dropradar ayuda a investigar productos para una tienda online."] if context["brand"] == "dropradar" else
                 ["ParkEz orienta la búsqueda de aparcamiento cerca del destino."] if context["brand"] == "parkez" else
                 ["gograduate.io permite trabajar con tus apuntes y repasar tus dudas."])
        if language == "en":
            facts = ["A closer look at the practical ideas shown here."]
    intros = ("", "Lo práctico: ", "Una opción para el día a día: ") if language == "es" else ("", "A practical detail: ", "An option for everyday use: ")
    descriptions = [intro + fact for intro, fact in itertools.product(intros, facts)]
    if style == "medium":
        links = (" ", " Por su parte, ", "\n\n") if language == "es" else (" ", " Meanwhile, ", "\n\n")
        descriptions.extend(a + link + b for a, b in itertools.permutations(facts, 2) for link in links)
    limit = 220 if style == "short" else 550
    candidates = [text for text in descriptions if 20 <= len(text) <= limit]
    if not candidates:
        candidates = [_sentence(facts[0], maximum=limit - 1)]
    return {"title": title, "description": _pick_text(candidates, _recent(records, "description"))}


def _hashtag_options(context: dict) -> list[str]:
    brand, content = context["brand"], _identity(context["content"])
    pools = {
        "dropradar": ["#ecommerce", "#tiendaonline", "#negociosonline", "#emprendimiento", "#ventasonline", "#comercioelectronico"],
        "parkez": ["#aparcamiento", "#conduccion", "#movilidad", "#appsutiles", "#trayectos", "#conductores"],
        "gograduate": ["#estudio", "#examenes", "#apuntes", "#repaso", "#aprendizaje", "#tecnicasdeestudio"],
    }
    if context["language"] == "en":
        pools = {
            "dropradar": ["#ecommerce", "#onlinestore", "#onlinebusiness", "#entrepreneurship", "#onlineselling", "#productresearch"],
            "parkez": ["#parking", "#driving", "#mobility", "#usefulapps", "#roadtrip", "#drivers"],
            "gograduate": ["#studytips", "#exams", "#notes", "#revision", "#learning", "#studyhabits"],
        }
    tags = list(pools[brand])
    keywords = {"producto": "#productos", "anuncio": "#publicidadonline", "notion": "#Notion", "waze": "#Waze", "screenzen": "#ScreenZen", "iphone": "#iPhone", "shopify": "#Shopify", "chatgpt": "#ChatGPT", "claude": "#Claude", "mathway": "#Mathway", "fintonic": "#Fintonic", "trading": "#trading", "clipping": "#clipping"}
    tags.extend(tag for word, tag in keywords.items() if word in content)
    if context["language"] == "en":
        tags.extend({"dropradar": ["#onlinestore", "#productresearch"], "parkez": ["#cars", "#parking"], "gograduate": ["#studytips", "#revision"]}[brand])
    return list(dict.fromkeys(tags))


def _choose_hashtags(context: dict, records: list[dict]) -> list[str]:
    required = list(_ESSENTIALS[context["brand"]])
    options = _hashtag_options(context)
    recent_sets = [
        tuple(sorted(tag.casefold() for tag in tags if isinstance(tag, str)))
        for entry in records[-60:]
        for tags in [entry.get("hashtags", [])]
        if isinstance(tags, list)
    ]
    counts = Counter(tag for tags in recent_sets[-15:] for tag in tags)
    candidates = [required + list(extra) for size in (2, 3, 4) for extra in itertools.combinations(options, size)]
    unseen = [tags for tags in candidates if tuple(sorted(tag.casefold() for tag in tags)) not in recent_sets]
    pool = unseen or candidates
    minimum = min(sum(counts[tag.casefold()] for tag in tags) for tags in pool)
    best = [tags for tags in pool if sum(counts[tag.casefold()] for tag in tags) <= minimum + 1]
    tags = list(random.choice(best))
    random.shuffle(tags)
    return tags


class PublicationComposer:
    def __init__(self, state: StateStore, writer: PublicationWriter | None = None) -> None:
        self.state, self.writer = state, writer

    def compose(self, result: GenerationResult, *, lowercase: bool = False) -> SocialCopy:
        return self._compose(publication_context(result), result.social_copy.hook, lowercase)

    def compose_template(self, copy: SocialCopy, language: Language) -> SocialCopy:
        context = {"brand": "dropradar", "language": language.value, "family": "tools",
                   "video_type": "template", "slides": [], "content": copy.description[:12000],
                   "entities": list(dict.fromkeys(["Dropradar", *_entity_names(copy.description)]))}
        return self._compose(context, copy.hook, False)

    def _compose(self, context: dict, hook: str, lowercase: bool) -> SocialCopy:
        brand, language = context["brand"], context["language"]
        snapshot = self.state.publication_copy_snapshot(brand)
        style, _remaining = _planned_format(snapshot, brand)
        records = _records(snapshot, language)
        written = None
        if self.writer is not None:
            for _ in range(2):
                candidate = _brand_wording(self.writer.write(
                    context, {"titles": _recent(records, "title")[-12:],
                              "descriptions": _recent(records, "description")[-6:]}, style,
                ), context)
                if _valid_written(candidate, context, style, records, hook):
                    written = candidate
                    break
                if candidate is None:
                    break

        def choose(history: dict) -> tuple[SocialCopy, dict]:
            actual_style, remaining = _planned_format(history, brand)
            actual_records = _records(history, language)
            use_written = actual_style == style and _valid_written(written, context, actual_style, actual_records, hook)
            selected = written if use_written else _brand_wording(_fallback_copy(context, actual_style, actual_records, hook), context)
            title, description = selected["title"].strip(), selected["description"].strip()
            tags = _choose_hashtags(context, actual_records)
            if lowercase:
                title, description, tags = title.lower(), description.lower(), [tag.lower() for tag in tags]
            record = {"title": title, "description": description, "hashtags": list(tags),
                      "format": actual_style, "family": context["family"],
                      "source": "writer" if use_written else "local"}
            profiles = history.get("languages")
            profiles = dict(profiles) if isinstance(profiles, dict) else {}
            profiles[language] = [*actual_records, record][-HISTORY_LIMIT:]
            count = history.get("count", 0)
            history.update(count=(count if isinstance(count, int) else 0) + 1,
                           formats_remaining=remaining, last_format=actual_style, languages=profiles)
            return SocialCopy(title=title, description=description, hashtags=tags, hook=hook), history

        return self.state.update_publication_copy(brand, choose)
