from __future__ import annotations

import copy
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.models import GenerationResult, Language, MediaCandidate, SlidePlan, SlideRole, SocialCopy, VideoType
from app.publication_copy import HISTORY_LIMIT, PublicationComposer, publication_context
from app.state import StateStore


def _slide(index, role, text):
    return SlidePlan(
        index=index,
        role=role,
        text=text,
        media=MediaCandidate(
            source_account="decorative-account",
            source_id=f"background-{index}",
            local_path=Path("unrelated-Claude-ScreenZen.jpg"),
            permalink="https://example.invalid/Mathway",
            caption="Claude, ScreenZen and Mathway are decorative source metadata.",
            width=1080,
            height=1920,
            created_at="",
        ),
    )


def _result(video_type=VideoType.PARKEZ_APPS, language=Language.ES):
    if video_type == VideoType.TYPE_5:
        rows = (
            (SlideRole.TYPE_5_TRADING, "Trading\n2/10: necesitas entender el mercado."),
            (SlideRole.TYPE_5_AMAZON_FBA, "Amazon FBA\n3/10: prepara inventario y logística."),
            (SlideRole.TYPE_5_AI_DROPSHIPPING, "AI + Dropshipping\n10/10: investiga productos con Dropradar."),
        )
    elif video_type == VideoType.GOGRADUATE_TYPE_1:
        rows = ((SlideRole.ADVICE_CARD,
                 "1. Recuerda antes de releer: cierra los apuntes y comprueba qué recuerdas.\n"
                 "2. Reparte tus repasos: vuelve a las preguntas días después.\n"
                 "3. gograduate.io analiza tus apuntes para repasar tus dudas."),)
    elif video_type in {VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.PARKEZ_ADVICE, VideoType.TOOLS}:
        rows = (
            (SlideRole.CAR_TOOL_WAZE, "Waze\nPrepara la ruta antes de salir."),
            (SlideRole.PARKEZ_PROMO, "ParkEz\nOrienta la búsqueda de aparcamiento cerca del destino."),
        )
    elif video_type == VideoType.PARKEZ_APPS:
        rows = (
            (SlideRole.APP_STORE, "Notion\nOrganiza tus notas y proyectos."),
            (SlideRole.APP_STORE, "Waze\nPrepara la ruta teniendo en cuenta el tráfico."),
            (SlideRole.PARKEZ_PROMO, "ParkEz\nOrienta la búsqueda de aparcamiento cerca del destino."),
            (SlideRole.APP_STORE, "Fintonic\nRevisa tus gastos y organiza tus finanzas."),
        )
    elif video_type == VideoType.TYPE_3:
        rows = (
            (SlideRole.TOOL_STORE, "Shopify\nPrepara una tienda online."),
            (SlideRole.TOOL_PRODUCT_SEARCH, "Dropradar\nInvestiga productos y señales de demanda."),
            (SlideRole.TOOL_SCRIPTS, "ChatGPT\nOrganiza las ideas de tus anuncios."),
        )
    else:
        rows = (
            (SlideRole.TIP1, "Revisa tu producto\nBusca señales de demanda antes de lanzarlo."),
            (SlideRole.TIP2, "Organiza tu tienda\nComprueba la oferta y presenta bien el producto."),
            (SlideRole.TIP3, "Dropradar\nInvestiga productos para preparar tu siguiente prueba."),
        )
    if language == Language.EN:
        rows = (
            (SlideRole.TOOL_STORE, "Shopify\nPrepare an online store."),
            (SlideRole.TOOL_PRODUCT_SEARCH, "Dropradar\nResearch products and signs of demand."),
            (SlideRole.TOOL_SCRIPTS, "ChatGPT\nOrganize ideas for your advertisements."),
        ) if video_type not in {VideoType.PARKEZ_APPS, VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.PARKEZ_ADVICE, VideoType.TOOLS} else (
            (SlideRole.CAR_TOOL_WAZE, "Waze\nPlan the route before setting off."),
            (SlideRole.PARKEZ_PROMO, "ParkEz\nPlan where to look for parking near your destination."),
        )
    slides = [_slide(index, role, text) for index, (role, text) in enumerate(rows, 1)]
    return GenerationResult(
        video_path=None,
        script_path=Path("unused-script.txt"),
        preview_text="\n\n".join(slide.text for slide in slides),
        social_copy=SocialCopy(
            hook="Hook literal que se entrega por separado",
            title="Título anterior del banco",
            description="Descripción anterior que no debe mutarse.",
            hashtags=["#anterior"],
        ),
        chosen_account="unrelated-background-account",
        video_type=video_type,
        language=language,
        fallback_accounts=[],
        slides=slides,
    )


class RecordingWriter:
    def __init__(self, candidate=None):
        self.candidate = candidate
        self.calls = []

    def write(self, context, history, style):
        self.calls.append(copy.deepcopy((context, history, style)))
        if self.candidate is None:
            return None
        return self.candidate(context, history, style)


@pytest.mark.parametrize("brand,types", (
    ("dropradar", (VideoType.TYPE_1, VideoType.TYPE_2, VideoType.TYPE_3, VideoType.TYPE_4, VideoType.TYPE_5, VideoType.ADVICE)),
    ("parkez", (VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.TOOLS, VideoType.PARKEZ_APPS, VideoType.PARKEZ_ADVICE)),
))
def test_one_description_free_publication_per_three_across_families_languages_and_restart(tmp_path, brand, types):
    formats = []
    for index in range(18):
        store = StateStore(tmp_path)
        result = _result(types[index % len(types)], Language.EN if index % 2 else Language.ES)
        selected = PublicationComposer(store).compose(result)
        history = store.publication_copy_snapshot(brand)
        style = history["last_format"]
        formats.append(style)
        assert bool(selected.description) == (style != "none")
        if style != "none":
            assert 20 <= len(selected.description) <= (220 if style == "short" else 550)
    for offset in range(0, len(formats), 3):
        assert sorted(formats[offset:offset + 3]) == ["medium", "none", "short"]
    assert all(first != "none" or second != "none" for first, second in zip(formats, formats[1:]))


@pytest.mark.parametrize("video_type", list(VideoType))
def test_required_hashtags_apply_to_every_video_family(tmp_path, video_type):
    result = _result(video_type)
    selected = PublicationComposer(StateStore(tmp_path)).compose(result)
    tags = {tag.casefold() for tag in selected.hashtags}
    expected = "#coches" if video_type in {VideoType.PARKEZ, VideoType.PARKEZ_MODE3, VideoType.PARKEZ_ADVICE, VideoType.PARKEZ_APPS, VideoType.TOOLS} else "#estudiantes" if video_type == VideoType.GOGRADUATE_TYPE_1 else "#dropshipping"
    assert expected in tags
    assert 4 <= len(tags) == len(selected.hashtags) <= 6


def test_composing_copy_keeps_original_hook_social_bank_and_slides_unchanged(tmp_path):
    result = _result()
    original = copy.deepcopy(result)

    selected = PublicationComposer(StateStore(tmp_path)).compose(result)

    assert selected is not result.social_copy
    assert selected.hook == original.social_copy.hook
    assert result == original
    selected.hashtags.append("#otra")
    assert result.social_copy.hashtags == ["#anterior"]


def test_writer_receives_delivered_apps_and_recent_copy_without_decorative_metadata(tmp_path):
    writer = RecordingWriter()
    composer = PublicationComposer(StateStore(tmp_path), writer)
    result = _result()
    first = composer.compose(result)
    composer.compose(result)

    context, history, _style = writer.calls[-1]
    assert set(context["entities"]) == {"Notion", "Waze", "Fintonic", "ParkEz"}
    assert "Claude" not in str(context)
    assert "ScreenZen" not in str(context)
    assert "Mathway" not in str(context)
    assert "unrelated" not in str(context)
    assert first.title in history["titles"]
    if first.description:
        assert first.description in history["descriptions"]


def test_business_context_contains_only_the_delivered_activities(tmp_path):
    writer = RecordingWriter()
    PublicationComposer(StateStore(tmp_path), writer).compose(_result(VideoType.TYPE_5))

    context = writer.calls[0][0]
    assert "Trading" in context["entities"]
    assert "Amazon FBA" in context["entities"]
    assert "Clipping" not in context["entities"]
    assert "Print on demand" not in context["entities"]
    assert "Marketing de afiliados" not in context["entities"]
    assert "AI + Dropshipping" in context["content"]


@pytest.mark.parametrize("bad_title,bad_description", (
    ("Claude para tu ruta de cada día", "Prepara tus aplicaciones antes de salir de casa."),
    ("Una plaza libre garantizada", "ParkEz garantiza una plaza siempre que llegas al destino."),
    ("Hook literal que se entrega por separado", "Prepara tus aplicaciones antes de salir de casa."),
    ("Un título con hashtags #coches", "Prepara tus aplicaciones antes de salir de casa."),
    ("Ayer gané 10.000€ con Fintonic", "Prepara tus aplicaciones antes de salir de casa."),
    ("Todoist para organizar el día", "Prepara tus aplicaciones antes de salir de casa."),
))
def test_invalid_provider_copy_uses_grounded_fallback(tmp_path, bad_title, bad_description):
    writer = RecordingWriter(lambda context, history, style: {
        "title": bad_title, "description": "" if style == "none" else bad_description,
    })
    result = _result()

    selected = PublicationComposer(StateStore(tmp_path), writer).compose(result)

    assert selected.title != bad_title
    assert "Claude" not in selected.title + selected.description
    assert "garantiz" not in (selected.title + selected.description).casefold()
    assert len(writer.calls) == 2


def test_valid_provider_copy_is_used_with_curated_tags_and_unchanged_hook(tmp_path):
    result = _result()
    writer = RecordingWriter(lambda context, history, style: {
        "title": "Llegar ya forma parte de tu plan",
        "description": "" if style == "none" else
        "Preparar la ruta con Waze y revisar la zona con ParkEz ayuda a organizar la llegada.",
    })

    selected = PublicationComposer(StateStore(tmp_path), writer).compose(result)

    assert selected.title == "Llegar ya forma parte de tu plan"
    assert selected.hook == result.social_copy.hook
    assert "#coches" in selected.hashtags
    assert len(writer.calls) == 1
    assert selected.description == writer.candidate(*writer.calls[0])["description"]


@pytest.mark.parametrize("suffix", ("!!!", " 2026!!!"))
def test_provider_descriptions_cannot_repeat_with_numbers_or_punctuation(tmp_path, suffix):
    store = StateStore(tmp_path)
    old_description = "Preparar la ruta antes de salir ayuda a elegir dónde buscar aparcamiento."
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, {
        "count": 1, "formats_remaining": ["short"],
        "languages": {"es": [{"title": "Un minuto para planear la llegada", "description": old_description, "hashtags": []}]},
    }))
    writer = RecordingWriter(lambda context, history, style: {
        "title": "Llegar con la zona de aparcamiento en mente",
        "description": old_description.upper() + suffix,
    })

    selected = PublicationComposer(store, writer).compose(_result())

    assert selected.title != "Llegar con la zona de aparcamiento en mente"
    assert selected.description != old_description
    assert len(writer.calls) == 2


@pytest.mark.parametrize("style,length", (("short", 221), ("medium", 551), ("none", 60)))
def test_wrong_provider_description_length_or_mode_falls_back(tmp_path, style, length):
    store = StateStore(tmp_path)
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, {
        "formats_remaining": [style],
    }))
    writer = RecordingWriter(lambda context, history, style: {
        "title": "Planifica la zona antes de llegar",
        "description": "Texto " + "x" * (length - 6),
    })

    selected = PublicationComposer(store, writer).compose(_result())

    assert selected.title != "Planifica la zona antes de llegar"
    assert not selected.description if style == "none" else len(selected.description) <= (220 if style == "short" else 550)


@pytest.mark.parametrize("bad_title", (
    "APPS PARA PREPARAR EL TRAYECTO 2026!!!",
    "Prepara tus apps antes de un viaje",
))
def test_provider_titles_cannot_repeat_with_numbers_punctuation_or_small_word_changes(tmp_path, bad_title):
    store = StateStore(tmp_path)
    old_title = "Apps para preparar el trayecto" if "2026" in bad_title else "Prepara tus apps antes del viaje"
    previous = {"count": 1, "formats_remaining": ["short"], "last_format": "none",
                "languages": {"es": [{"title": old_title, "description": "Una descripción publicada anteriormente.", "hashtags": ["#coches"], "format": "none"}]}}
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, previous))
    writer = RecordingWriter(lambda context, history, style: {
        "title": bad_title, "description": "Planifica dónde buscar aparcamiento antes de llegar a tu destino.",
    })

    selected = PublicationComposer(store, writer).compose(_result())

    assert selected.title != bad_title
    assert selected.title != old_title
    assert len(writer.calls) == 2


def test_hashtag_variety_changes_members_not_only_order(tmp_path):
    composer = PublicationComposer(StateStore(tmp_path))
    tag_sets = [frozenset(tag.casefold() for tag in composer.compose(_result()).hashtags) for _ in range(12)]

    assert len(set(tag_sets)) == len(tag_sets)
    assert all({"#coches", "#parkez"} <= tags for tags in tag_sets)


def test_offline_copy_has_no_title_repetitions_or_artificial_variant_suffixes(tmp_path):
    composer = PublicationComposer(StateStore(tmp_path))
    copies = [composer.compose(_result(VideoType.TYPE_3)) for _ in range(40)]

    assert len({selected.title.casefold() for selected in copies}) == len(copies)
    assert all(not re.search(r"(?:variante|versi[oó]n|edici[oó]n|version)\s*\d+|#\d+|\(\d+\)$", selected.title, re.IGNORECASE) for selected in copies)
    assert all(len(selected.description) <= 550 for selected in copies)


def test_history_is_bounded_and_keeps_the_latest_publications(tmp_path):
    store = StateStore(tmp_path)
    entries = [{"title": f"Título anterior {index}", "description": "", "hashtags": [], "format": "none"} for index in range(HISTORY_LIMIT + 30)]
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, {
        "count": len(entries), "languages": {"es": entries}, "formats_remaining": ["short", "medium", "none"],
    }))

    selected = PublicationComposer(store).compose(_result())

    persisted = store.publication_copy_snapshot("parkez")["languages"]["es"]
    assert len(persisted) == HISTORY_LIMIT
    assert persisted[-1]["title"] == selected.title
    assert entries[-1] in persisted
    assert entries[0] not in persisted


@pytest.mark.parametrize("broken", (
    {"languages": []},
    {"languages": {"es": "broken"}},
    {"languages": {"es": [None, "bad", 7]}},
    {"formats_remaining": ["short", "short"]},
    {"formats_remaining": ["unsupported"]},
    {"formats_remaining": [["none"]]},
    {"formats_remaining": "none"},
))
def test_malformed_profiles_and_format_bags_recover_on_success(tmp_path, broken):
    store = StateStore(tmp_path)
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, broken))

    selected = PublicationComposer(store).compose(_result())

    assert selected.title
    history = store.publication_copy_snapshot("parkez")
    assert history["count"] == 1
    assert history["last_format"] in {"none", "short", "medium"}
    assert history["languages"]["es"][-1]["title"] == selected.title


@pytest.mark.parametrize("bad_tags", (None, 17))
def test_corrupt_tag_history_does_not_block_a_publication(tmp_path, bad_tags):
    store = StateStore(tmp_path)
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, {
        "languages": {"es": [{"title": "Una publicación anterior", "description": "", "hashtags": bad_tags}]},
    }))

    selected = PublicationComposer(store).compose(_result())

    assert selected.title
    assert "#coches" in selected.hashtags


def test_concurrent_composers_preserve_format_counts_and_unique_titles(tmp_path):
    composers = [PublicationComposer(StateStore(tmp_path)) for _ in range(6)]

    def compose(index):
        return composers[index % len(composers)].compose(_result())

    with ThreadPoolExecutor(max_workers=6) as executor:
        copies = list(executor.map(compose, range(18)))

    assert len({selected.title.casefold() for selected in copies}) == 18
    assert sum(not selected.description for selected in copies) == 6
    history = StateStore(tmp_path).publication_copy_snapshot("parkez")
    assert history["count"] == 18
    records = history["languages"]["es"]
    assert all(sorted(record["format"] for record in records[offset:offset + 3]) == ["medium", "none", "short"] for offset in range(0, 18, 3))


def test_concurrent_provider_results_are_revalidated_against_newer_history(tmp_path):
    barrier = Barrier(6)

    class ConcurrentWriter:
        def write(self, context, history, style):
            # All requests leave with the same initial snapshot. They must not
            # hold the state lock while waiting for a writer response.
            barrier.wait(timeout=5)
            return {
                "title": "Organiza la llegada antes de arrancar",
                "description": "" if style == "none" else
                "Preparar la ruta con Waze ayuda a organizar la llegada.",
            }

    composers = [PublicationComposer(StateStore(tmp_path), ConcurrentWriter()) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as executor:
        copies = list(executor.map(lambda composer: composer.compose(_result()), composers))

    assert len({selected.title.casefold() for selected in copies}) == 6
    assert sum(not selected.description for selected in copies) == 2
    records = StateStore(tmp_path).publication_copy_snapshot("parkez")["languages"]["es"]
    assert len(records) == 6
    assert all(sorted(record["format"] for record in records[offset:offset + 3]) == ["medium", "none", "short"] for offset in (0, 3))


def test_english_offline_copy_is_english_and_preserves_hook(tmp_path):
    composer = PublicationComposer(StateStore(tmp_path))
    result = _result(VideoType.TYPE_3, Language.EN)
    copies = [composer.compose(result) for _ in range(9)]

    assert all(selected.hook == result.social_copy.hook for selected in copies)
    for selected in copies:
        assert not any(word in selected.title + selected.description for word in ("Una idea", "Para ponerlo", "Por aquí", "preparar", "herramientas"))
        assert "#dropshipping" in selected.hashtags


def test_description_free_copy_has_only_title_and_tags_after_independent_hook(tmp_path):
    store = StateStore(tmp_path)
    store.update_publication_copy("parkez", lambda history: (_result().social_copy, {
        "formats_remaining": ["none"], "count": 0,
    }))
    result = _result()

    selected = PublicationComposer(store).compose(result)

    assert selected.description == ""
    assert selected.messages == [result.social_copy.hook, selected.title, selected.hashtag_line]


def test_lowercase_formatting_does_not_rewrite_independent_literal_hook(tmp_path):
    result = _result()

    selected = PublicationComposer(StateStore(tmp_path)).compose(result, lowercase=True)

    assert selected.title == selected.title.lower()
    assert selected.description == selected.description.lower()
    assert all(tag == tag.lower() for tag in selected.hashtags)
    assert selected.hook == result.social_copy.hook


def test_template_copy_gets_title_essential_tags_and_same_brand_format_rotation(tmp_path):
    store = StateStore(tmp_path)
    composer = PublicationComposer(store)
    original = SocialCopy(title="", description="Shopify prepara la tienda y Dropradar ayuda a investigar productos.", hashtags=["#old"])

    copies = [composer.compose_template(original, Language.ES), composer.compose(_result(VideoType.TYPE_3)), composer.compose_template(original, Language.ES)]

    assert all(selected.title and "#dropshipping" in selected.hashtags for selected in copies)
    assert sum(not selected.description for selected in copies) == 1
    assert original.title == ""
    assert original.hashtags == ["#old"]


def test_publication_context_uses_actual_language_not_template_request_assumptions():
    result = _result(VideoType.PARKEZ_MODE3, Language.ES)
    context = publication_context(result)
    assert context["brand"] == "parkez"
    assert context["language"] == "es"
    assert context["family"] == "driving"


@pytest.mark.parametrize("brand_name", ("GoGraduate", "gograduate.org"))
def test_accepted_gograduate_copy_uses_io_domain_and_keeps_literal_hook(tmp_path, brand_name):
    store = StateStore(tmp_path)
    result = _result(VideoType.GOGRADUATE_TYPE_1)
    literal_hook = "Hook literal de GoGraduate.org que no se debe reescribir"
    result.social_copy.hook = literal_hook
    store.update_publication_copy("gograduate", lambda history: (result.social_copy, {
        "formats_remaining": ["short"],
    }))
    writer = RecordingWriter(lambda context, history, style: {
        "title": f"Repasa tus dudas con {brand_name}",
        "description": f"{brand_name} ayuda a trabajar con tus apuntes y organizar el repaso.",
    })

    selected = PublicationComposer(store, writer).compose(result)

    assert len(writer.calls) == 1  # The actual AI candidate survives validation.
    assert writer.calls[0][0]["brand_name"] == "gograduate.io"
    assert selected.title == "Repasa tus dudas con gograduate.io"
    assert selected.description == "gograduate.io ayuda a trabajar con tus apuntes y organizar el repaso."
    assert selected.hook == result.social_copy.hook == literal_hook
    record = store.publication_copy_snapshot("gograduate")["languages"]["es"][-1]
    assert record["title"] == selected.title
    assert record["description"] == selected.description
    assert ".org" not in record["title"] + record["description"]
