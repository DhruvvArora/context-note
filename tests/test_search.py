import context_note.search as search_mod
from context_note.config import Config
from context_note.search import _fts_query, search
from context_note.store import Chunk, Store


def add(store, cid, text, project=None, vec=(0.0, 0.0)):
    store.add(
        Chunk(
            conversation_id=cid,
            conversation_name=f"convo-{cid}",
            project_name=project,
            role="human",
            created_at="2026-01-01",
            position=0,
            text=text,
        ),
        list(vec),
    )


def test_fts_query_strips_punctuation_to_or_terms():
    assert _fts_query("what's the plan?") == "what's OR the OR plan"


def test_fts_query_falls_back_to_raw_text_when_no_terms():
    assert _fts_query("???") == "???"


def test_search_finds_lexical_only_match(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    add(store, "c1", "database migration guide", vec=(1.0, 0.0))
    store.commit()

    # Query embedding deliberately dissimilar so only the lexical leg matches.
    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "database", limit=5)
    assert len(results) == 1
    assert results[0]["conversation_id"] == "c1"


def test_search_finds_vector_only_match(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    add(store, "c1", "totally unrelated cooking content", vec=(0.0, 1.0))
    store.commit()

    # Query text shares no lexical terms, but the query vector matches exactly.
    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "xyzzy plugh", limit=5)
    assert len(results) == 1
    assert results[0]["conversation_id"] == "c1"


def test_search_combines_both_legs_without_dropping_either(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    add(store, "lexical-hit", "database migration guide", vec=(1.0, 0.0))
    add(store, "vector-hit", "totally unrelated cooking content", vec=(0.0, 1.0))
    store.commit()

    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "database", limit=5)
    ids = {r["conversation_id"] for r in results}
    assert ids == {"lexical-hit", "vector-hit"}


def test_search_respects_project_filter(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    add(store, "c1", "database migration guide", project="work", vec=(1.0, 0.0))
    add(store, "c2", "database migration guide too", project="personal", vec=(1.0, 0.0))
    store.commit()

    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "database", project="work", limit=5)
    assert len(results) == 1
    assert results[0]["project"] == "work"


def test_search_respects_exclude_project(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    add(store, "c1", "database migration guide", project="work", vec=(1.0, 0.0))
    add(store, "c2", "database migration guide too", project="personal", vec=(1.0, 0.0))
    store.commit()

    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "database", exclude_project="personal", limit=5)
    assert len(results) == 1
    assert results[0]["project"] == "work"


def test_search_respects_limit(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    for i in range(5):
        add(store, f"c{i}", f"database migration guide number {i}", vec=(1.0, 0.0))
    store.commit()

    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "database", limit=2)
    assert len(results) == 2


def test_search_no_project_reports_placeholder(tmp_path, monkeypatch):
    store = Store(tmp_path / "index.db")
    add(store, "c1", "database migration guide", project=None, vec=(1.0, 0.0))
    store.commit()

    monkeypatch.setattr(search_mod, "embed_batch", lambda texts, model: [[0.0, 1.0]])

    results = search(store, Config(), "database", limit=5)
    assert results[0]["project"] == "(no project)"
