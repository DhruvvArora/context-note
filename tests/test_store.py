from context_note.store import Chunk, Store, pack, unpack


def make_chunk(
    conversation_id="c1",
    position=0,
    text="hello world",
    project="proj",
    created_at="2026-01-01T00:00:00Z",
):
    return Chunk(
        conversation_id=conversation_id,
        conversation_name="convo name",
        project_name=project,
        role="human",
        created_at=created_at,
        position=position,
        text=text,
    )


def test_pack_unpack_roundtrip():
    # Values are stored as float32, so only exactly-representable floats
    # round-trip bit for bit.
    vec = [0.5, -0.5, 3.25, 0.0]
    assert list(unpack(pack(vec))) == vec


def test_add_and_stats(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(make_chunk(text="alpha beta"), [1.0, 0.0])
    store.add(make_chunk(conversation_id="c2", text="gamma delta"), [0.0, 1.0])
    store.commit()
    stats = store.stats()
    assert stats["chunks"] == 2
    assert stats["conversations"] == 2
    assert "projects" not in stats


def test_stats_reports_date_range(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(
        make_chunk(conversation_id="c1", created_at="2026-06-03T17:19:11.906381Z"),
        [1.0, 0.0],
    )
    store.add(
        make_chunk(conversation_id="c2", created_at="2026-09-01T16:02:34.372575Z"),
        [0.0, 1.0],
    )
    store.add(
        make_chunk(conversation_id="c3", created_at="2026-07-15T00:00:00Z"),
        [0.5, 0.5],
    )
    store.commit()
    stats = store.stats()
    assert stats["earliest"] == "2026-06-03"
    assert stats["latest"] == "2026-09-01"


def test_stats_date_range_ignores_missing_created_at(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(make_chunk(conversation_id="c1", created_at=""), [1.0, 0.0])
    store.commit()
    stats = store.stats()
    assert stats["earliest"] is None
    assert stats["latest"] is None


def test_stats_date_range_none_on_empty_index(tmp_path):
    store = Store(tmp_path / "index.db")
    stats = store.stats()
    assert stats["chunks"] == 0
    assert stats["earliest"] is None
    assert stats["latest"] is None


def test_lexical_search_uses_fts(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(make_chunk(text="the chunking strategy uses paragraph boundaries"), [1.0])
    store.add(make_chunk(conversation_id="c2", text="completely unrelated topic"), [0.0])
    store.commit()
    rows = store.lexical("chunking", 10)
    assert len(rows) == 1
    assert "chunking" in rows[0]["text"]


def test_by_ids_and_conversation_ordering(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(make_chunk(conversation_id="c1", position=1, text="second"), [0.0])
    store.add(make_chunk(conversation_id="c1", position=0, text="first"), [0.0])
    store.commit()
    convo = store.conversation("c1")
    assert [r["text"] for r in convo] == ["first", "second"]

    ids = [r["id"] for r in convo]
    rows = {r["id"]: r for r in store.by_ids(ids)}
    assert len(rows) == 2

    assert store.by_ids([]) == []


def test_drop_conversation_removes_rows_and_fts_entries(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(make_chunk(conversation_id="c1", text="keep this searchable text"), [0.0])
    store.add(make_chunk(conversation_id="c2", text="drop this searchable text"), [0.0])
    store.commit()

    store.drop_conversation("c2")
    store.commit()

    assert store.conversation("c2") == []
    rows = store.lexical("searchable", 10)
    assert len(rows) == 1
    assert rows[0]["conversation_id"] == "c1"


def test_already_ingested_and_mark_ingested(tmp_path):
    store = Store(tmp_path / "index.db")
    content_hash = "a" * 64
    assert store.already_ingested(content_hash) is False
    store.mark_ingested(content_hash, "export.zip", "2026-01-01T00:00:00Z", 42)
    assert store.already_ingested(content_hash) is True


def test_already_ingested_keys_on_content_not_filename(tmp_path):
    # Anthropic reuses the same filename for every export, so two different
    # files sharing a name must be tracked as distinct ingests.
    store = Store(tmp_path / "index.db")
    store.mark_ingested("hash-one", "conversations-000.zip", "2026-01-01T00:00:00Z", 10)
    assert store.already_ingested("hash-one") is True
    assert store.already_ingested("hash-two") is False


def test_already_opened_manifest_and_mark_manifest_opened(tmp_path):
    store = Store(tmp_path / "index.db")
    content_hash = "b" * 64
    assert store.already_opened_manifest(content_hash) is False
    store.mark_manifest_opened(content_hash, "manifest-abc.json", "2026-01-01T00:00:00Z")
    assert store.already_opened_manifest(content_hash) is True


def test_all_embeddings_skips_null(tmp_path):
    store = Store(tmp_path / "index.db")
    store.add(make_chunk(text="has an embedding"), [1.0, 2.0])
    store.commit()
    rows = list(store.all_embeddings())
    assert len(rows) == 1
    assert list(unpack(rows[0]["embedding"])) == [1.0, 2.0]
