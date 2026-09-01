"""Turn export files in imports/ into rows in the index."""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, Paths
from .embed import embed_batch, to_chunks
from .parser import read_export
from .store import Store

BATCH = 64


def ingest_file(path: Path, store: Store, cfg: Config, verbose: bool = True) -> int:
    messages = [
        m
        for m in read_export(path)
        if len(m.text) >= cfg.min_message_chars
        and (m.project_name or "") not in cfg.excluded_projects
    ]
    if not messages:
        return 0

    # An export is a full snapshot, so clear prior copies of these chats first.
    for cid in {m.conversation_id for m in messages}:
        store.drop_conversation(cid)

    chunks: list = []
    for msg in messages:
        chunks.extend(to_chunks(msg, cfg.chunk_max_chars, cfg.chunk_overlap_chars))

    for start in range(0, len(chunks), BATCH):
        batch = chunks[start : start + BATCH]
        vectors = embed_batch([c.text for c in batch], cfg.embedding_model)
        for chunk, vec in zip(batch, vectors):
            store.add(chunk, vec)
        if verbose:
            done = min(start + BATCH, len(chunks))
            print(f"  embedded {done}/{len(chunks)}", end="\r", flush=True)

    store.commit()
    if verbose:
        print(" " * 40, end="\r")
    return len(chunks)


def ingest_pending(paths: Paths, cfg: Config, verbose: bool = True) -> dict:
    store = Store(paths.index)
    results = {}
    candidates = sorted(
        p
        for p in paths.imports.iterdir()
        if p.is_file() and p.suffix in {".zip", ".json"}
    )
    for path in candidates:
        if store.already_ingested(path.name):
            if verbose:
                print(f"skip {path.name} (already ingested)")
            continue
        if verbose:
            print(f"ingesting {path.name}")
        try:
            count = ingest_file(path, store, cfg, verbose)
        except Exception as exc:
            print(f"  failed: {exc}")
            results[path.name] = 0
            continue
        store.mark_ingested(
            path.name, datetime.now(timezone.utc).isoformat(), count
        )
        shutil.move(str(path), str(paths.processed / path.name))
        results[path.name] = count
        if verbose:
            print(f"  {count} chunks")
    return results
