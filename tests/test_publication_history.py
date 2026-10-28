from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import app.state as state_module
from app.models import SocialCopy
from app.state import StateStore


def _copy(title="Una publicación"):
    return SocialCopy(title=title, description="Texto de publicación.", hashtags=["#dropshipping"])


def test_publication_snapshot_does_not_create_or_consume_history(tmp_path):
    store = StateStore(tmp_path)

    assert store.publication_copy_snapshot("dropradar") == {}
    assert not (tmp_path / "publication_copy_history.json").exists()


def test_publication_history_survives_restart_and_is_isolated_by_brand(tmp_path):
    store = StateStore(tmp_path)
    selected = _copy("Primer título")
    updated = {
        "counter": 1,
        "remaining_formats": ["short", "medium"],
        "profiles": {"es": {"titles": [selected.title]}},
    }

    assert store.update_publication_copy("dropradar", lambda previous: (selected, updated)) is selected
    store.update_publication_copy("parkez", lambda previous: (_copy("Otro título"), {"counter": 7}))
    restarted = StateStore(tmp_path)

    assert restarted.publication_copy_snapshot("dropradar") == updated
    assert restarted.publication_copy_snapshot("parkez") == {"counter": 7}
    assert restarted.publication_copy_snapshot("gograduate") == {}
    persisted = json.loads((tmp_path / "publication_copy_history.json").read_text())
    assert persisted["version"] == 1
    assert set(persisted["brands"]) == {"dropradar", "parkez"}


def test_publication_snapshot_and_callback_mutations_do_not_leak(tmp_path):
    store = StateStore(tmp_path)
    initial = {"profiles": {"es": {"titles": ["Publicado"]}}}
    store.update_publication_copy("dropradar", lambda previous: (_copy(), initial))
    original_bytes = (tmp_path / "publication_copy_history.json").read_bytes()

    snapshot = store.publication_copy_snapshot("dropradar")
    snapshot["profiles"]["es"]["titles"].append("No publicado")
    initial["profiles"]["es"]["titles"].append("Referencia externa")

    def fail(previous):
        previous["profiles"]["es"]["titles"].append("Selección fallida")
        raise ValueError("No se completó el texto")

    with pytest.raises(ValueError, match="No se completó"):
        store.update_publication_copy("dropradar", fail)
    assert (tmp_path / "publication_copy_history.json").read_bytes() == original_bytes
    assert store.publication_copy_snapshot("dropradar") == {"profiles": {"es": {"titles": ["Publicado"]}}}


@pytest.mark.parametrize("raw", (
    "not-json", "[]", "null", "3", '{}',
    '{"version": 1, "brands": []}',
    '{"version": true, "brands": {"dropradar": {"counter": 99}}}',
    '{"version": 2, "brands": {"dropradar": {"counter": 99}}}',
    '{"version": 1, "brands": {"dropradar": []}}',
))
def test_malformed_publication_history_recovers_on_the_next_success(tmp_path, raw):
    path = tmp_path / "publication_copy_history.json"
    path.write_text(raw)
    store = StateStore(tmp_path)

    assert store.publication_copy_snapshot("dropradar") == {}
    assert path.read_text() == raw
    store.update_publication_copy("dropradar", lambda previous: (_copy(), {"counter": 1}))
    assert store.publication_copy_snapshot("dropradar") == {"counter": 1}


def test_malformed_brand_does_not_erase_other_brand_history(tmp_path):
    path = tmp_path / "publication_copy_history.json"
    path.write_text(json.dumps({
        "version": 1,
        "brands": {"dropradar": [], "parkez": {"counter": 7}},
    }))
    store = StateStore(tmp_path)

    store.update_publication_copy("dropradar", lambda previous: (_copy(), {"counter": 1}))

    assert store.publication_copy_snapshot("parkez") == {"counter": 7}


@pytest.mark.parametrize("brand", ("unknown", "../../outside", "", None, ["dropradar"]))
def test_invalid_brand_never_executes_the_selection_or_writes_history(tmp_path, brand):
    store = StateStore(tmp_path)

    def unexpected(previous):
        pytest.fail("Invalid brands must be rejected before selection")

    with pytest.raises(ValueError, match="Marca"):
        store.publication_copy_snapshot(brand)
    with pytest.raises(ValueError, match="Marca"):
        store.update_publication_copy(brand, unexpected)
    assert not (tmp_path / "publication_copy_history.json").exists()


@pytest.mark.parametrize("returned", ((None, {}), (_copy(), [])))
def test_invalid_selection_result_does_not_commit(tmp_path, returned):
    store = StateStore(tmp_path)

    with pytest.raises(TypeError):
        store.update_publication_copy("dropradar", lambda previous: returned)

    assert not (tmp_path / "publication_copy_history.json").exists()


def test_unserializable_history_preserves_last_successful_selection(tmp_path):
    store = StateStore(tmp_path)
    store.update_publication_copy("dropradar", lambda previous: (_copy(), {"counter": 1}))
    path = tmp_path / "publication_copy_history.json"
    previous_bytes = path.read_bytes()

    with pytest.raises(TypeError):
        store.update_publication_copy("dropradar", lambda previous: (_copy(), {"titles": {"invalid-set"}}))

    assert path.read_bytes() == previous_bytes
    assert not list(tmp_path.glob("publication_copy_history.json.*"))


@pytest.mark.skipif(not state_module._HAS_FILELOCK, reason="Cross-instance protection requires filelock")
def test_concurrent_stores_do_not_lose_history_updates(tmp_path):
    stores = [StateStore(tmp_path) for _ in range(8)]

    def publish(index):
        def select(previous):
            count = previous.get("counter", 0) + 1
            time.sleep(0.002)
            previous["counter"] = count
            previous.setdefault("titles", []).append(str(count))
            return _copy(str(count)), previous

        return stores[index % len(stores)].update_publication_copy("dropradar", select).title

    with ThreadPoolExecutor(max_workers=8) as executor:
        titles = list(executor.map(publish, range(32)))

    assert {int(title) for title in titles} == set(range(1, 33))
    snapshot = StateStore(tmp_path).publication_copy_snapshot("dropradar")
    assert snapshot["counter"] == 32
    assert snapshot["titles"] == [str(value) for value in range(1, 33)]


def test_publication_updates_leave_unrelated_state_files_untouched(tmp_path):
    sentinels = {
        "used_media.json": b'{"existing-photo": {"job_id": "prior-job"}}',
        "type5_social_queue.json": b'{"pending": ["type5-03"]}',
    }
    for filename, contents in sentinels.items():
        (tmp_path / filename).write_bytes(contents)
    store = StateStore(tmp_path)

    store.update_publication_copy("dropradar", lambda previous: (_copy(), {"counter": 1}))

    for filename, contents in sentinels.items():
        assert (tmp_path / filename).read_bytes() == contents
