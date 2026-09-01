"""SQLite index: chunk text in FTS5, embeddings as raw float32 blobs.

Vectors are held in a plain BLOB column and scored in Python. This is fine up
to roughly 100k chunks on a laptop and avoids requiring a compiled extension,
which is the single biggest install-friction item for a local tool.
"""

import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    conversation_name TEXT,
    project_name TEXT,
    role TEXT,
    created_at TEXT,
    position INTEGER,
    text TEXT NOT NULL,
    embedding BLOB
);

CREATE INDEX IF NOT EXISTS idx_chunks_convo ON chunks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_name);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TABLE IF NOT EXISTS ingested (
    content_hash TEXT PRIMARY KEY,
    source_name TEXT,
    ingested_at TEXT,
    chunk_count INTEGER
);

CREATE TABLE IF NOT EXISTS manifests_opened (
    content_hash TEXT PRIMARY KEY,
    source_name TEXT,
    opened_at TEXT
);
"""


@dataclass
class Chunk:
    conversation_id: str
    conversation_name: str
    project_name: str | None
    role: str
    created_at: str
    position: int
    text: str


def pack(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def unpack(blob: bytes):
    return struct.unpack(f"{len(blob) // 4}f", blob)


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def already_ingested(self, content_hash: str) -> bool:
        """Keyed on content, not filename: Anthropic reuses the same
        filename (e.g. conversations-000.zip) for every export, so a
        filename check would treat every re-export as already seen and
        silently skip genuinely new data.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM ingested WHERE content_hash = ?", (content_hash,)
        )
        return cur.fetchone() is not None

    def mark_ingested(
        self, content_hash: str, source_name: str, when: str, count: int
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ingested VALUES (?, ?, ?, ?)",
            (content_hash, source_name, when, count),
        )
        self.conn.commit()

    def already_opened_manifest(self, content_hash: str) -> bool:
        """Tracked separately from `ingested` and keyed the same way (by
        content, not filename) so a service restart doesn't re-open an
        export manifest's one-time-use conversations link a second time --
        that link is already spent, and re-opening it just shows an error.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM manifests_opened WHERE content_hash = ?", (content_hash,)
        )
        return cur.fetchone() is not None

    def mark_manifest_opened(
        self, content_hash: str, source_name: str, when: str
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO manifests_opened VALUES (?, ?, ?)",
            (content_hash, source_name, when),
        )
        self.conn.commit()

    def drop_conversation(self, conversation_id: str) -> None:
        """Re-ingesting an export replaces prior copies of the same chats."""
        self.conn.execute(
            "DELETE FROM chunks WHERE conversation_id = ?", (conversation_id,)
        )

    def add(self, chunk: Chunk, embedding) -> None:
        self.conn.execute(
            """INSERT INTO chunks
               (conversation_id, conversation_name, project_name, role,
                created_at, position, text, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.conversation_id,
                chunk.conversation_name,
                chunk.project_name,
                chunk.role,
                chunk.created_at,
                chunk.position,
                chunk.text,
                pack(embedding),
            ),
        )

    def commit(self) -> None:
        self.conn.commit()

    def stats(self) -> dict:
        cur = self.conn.execute(
            """SELECT COUNT(*) AS chunks,
                      COUNT(DISTINCT conversation_id) AS conversations,
                      COUNT(DISTINCT project_name) AS projects
               FROM chunks"""
        )
        return dict(cur.fetchone())

    def lexical(self, query: str, limit: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT c.*, bm25(chunks_fts) AS score
               FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
               WHERE chunks_fts MATCH ?
               ORDER BY score LIMIT ?""",
            (query, limit),
        ).fetchall()

    def all_embeddings(self):
        return self.conn.execute(
            "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
        )

    def by_ids(self, ids: list[int]) -> list[sqlite3.Row]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self.conn.execute(
            f"SELECT * FROM chunks WHERE id IN ({marks})", ids
        ).fetchall()

    def conversation(self, conversation_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM chunks WHERE conversation_id = ? ORDER BY position",
            (conversation_id,),
        ).fetchall()
