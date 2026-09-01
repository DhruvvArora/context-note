import json
import zipfile

import context_note.ingest as ingest_mod
from context_note.config import Config, Paths
from context_note.ingest import ingest_file, ingest_pending
from context_note.store import Store


def fake_embed_batch(texts, model_name):
    return [[float(len(t)), 0.0] for t in texts]


def make_paths(tmp_path) -> Paths:
    root = tmp_path
    paths = Paths(
        root=root,
        imports=root / "imports",
        processed=root / "processed",
        index=root / "index.db",
        config=root / "config.json",
    )
    return paths.ensure()


def write_export(path, conversation_id="c1", texts=("first message here", "second message here")):
    raw = [
        {
            "uuid": conversation_id,
            "name": "test convo",
            "project": {"name": "proj"},
            "chat_messages": [
                {"sender": "human", "text": t} for t in texts
            ],
        }
    ]
    path.write_text(json.dumps(raw))


def test_ingest_file_indexes_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_mod, "embed_batch", fake_embed_batch)
    export = tmp_path / "conversations.json"
    write_export(export)

    store = Store(tmp_path / "index.db")
    cfg = Config(min_message_chars=1)
    count = ingest_file(export, store, cfg, verbose=False)

    assert count == 2
    assert store.stats()["chunks"] == 2
    assert store.stats()["conversations"] == 1


def test_ingest_file_drops_short_messages_and_excluded_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_mod, "embed_batch", fake_embed_batch)
    export = tmp_path / "conversations.json"
    write_export(export, texts=("ok", "a message long enough to survive filtering"))

    store = Store(tmp_path / "index.db")
    cfg = Config(min_message_chars=10)
    count = ingest_file(export, store, cfg, verbose=False)
    assert count == 1

    store2 = Store(tmp_path / "index2.db")
    cfg_excluded = Config(min_message_chars=1, excluded_projects=["proj"])
    count2 = ingest_file(export, store2, cfg_excluded, verbose=False)
    assert count2 == 0


def test_ingest_file_replaces_prior_copy_of_same_conversation(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_mod, "embed_batch", fake_embed_batch)
    export = tmp_path / "conversations.json"
    write_export(export, conversation_id="c1", texts=("original message content",))

    store = Store(tmp_path / "index.db")
    cfg = Config(min_message_chars=1)
    ingest_file(export, store, cfg, verbose=False)
    assert store.stats()["chunks"] == 1

    write_export(export, conversation_id="c1", texts=("replaced message content one", "replaced message content two"))
    ingest_file(export, store, cfg, verbose=False)
    assert store.stats()["chunks"] == 2


def test_ingest_pending_moves_files_and_skips_already_ingested(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_mod, "embed_batch", fake_embed_batch)
    paths = make_paths(tmp_path)
    cfg = Config(min_message_chars=1)

    write_export(paths.imports / "conversations.json")

    results = ingest_pending(paths, cfg, verbose=False)
    assert results == {"conversations.json": 2}
    assert not (paths.imports / "conversations.json").exists()
    assert (paths.processed / "conversations.json").exists()

    # A second pass with no new files finds nothing to do.
    assert ingest_pending(paths, cfg, verbose=False) == {}


def write_export_zip(path, conversation_id="c1", texts=("first message here",)):
    raw = [
        {
            "uuid": conversation_id,
            "name": "test convo",
            "project": {"name": "proj"},
            "chat_messages": [{"sender": "human", "text": t} for t in texts],
        }
    ]
    # Fixed date_time so identical content always produces byte-identical
    # zips -- zipfile otherwise stamps each entry with the current time,
    # which would make file_hash() differ between calls even for what
    # should count as "the same file".
    info = zipfile.ZipInfo("conversations.json", date_time=(2026, 1, 1, 0, 0, 0))
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(info, json.dumps(raw))


def test_ingest_pending_reingests_same_filename_with_new_content(tmp_path, monkeypatch):
    # Anthropic reuses the same filename (e.g. conversations-000.zip) for
    # every export -- a stale re-export must not be silently skipped just
    # because a file of that name was already processed once before.
    monkeypatch.setattr(ingest_mod, "embed_batch", fake_embed_batch)
    paths = make_paths(tmp_path)
    cfg = Config(min_message_chars=1)

    write_export_zip(paths.imports / "conversations-000.zip", conversation_id="c1")
    first = ingest_pending(paths, cfg, verbose=False)
    assert first == {"conversations-000.zip": 1}

    # Re-downloading gives the same filename but different content.
    write_export_zip(
        paths.imports / "conversations-000.zip",
        conversation_id="c2",
        texts=("a completely new conversation", "with different content entirely"),
    )
    second = ingest_pending(paths, cfg, verbose=False)
    assert second == {"conversations-000.zip": 2}

    store = Store(paths.index)
    assert store.stats()["conversations"] == 2

    # An unchanged re-download of the exact same bytes is still skipped.
    write_export_zip(
        paths.imports / "conversations-000.zip",
        conversation_id="c2",
        texts=("a completely new conversation", "with different content entirely"),
    )
    third = ingest_pending(paths, cfg, verbose=False)
    assert third == {}


def test_ingest_pending_records_failure_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_mod, "embed_batch", fake_embed_batch)
    paths = make_paths(tmp_path)
    cfg = Config(min_message_chars=1)

    bad = paths.imports / "conversations.json"
    bad.write_text("not valid json")

    results = ingest_pending(paths, cfg, verbose=False)
    assert results == {"conversations.json": 0}
    # A failed file is left in place rather than moved to processed/.
    assert bad.exists()
