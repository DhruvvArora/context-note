"""Hybrid retrieval: BM25 and dense vectors fused with Reciprocal Rank Fusion.

Chat history is full of proper nouns, error strings, and identifiers where
lexical match beats embeddings, and full of vague callbacks ("that thing we
decided") where it loses. Running both and fusing ranks handles each.
"""

import math
import re

from .config import Config
from .embed import embed_batch
from .store import Store, unpack

RRF_K = 60


def _fts_query(text: str) -> str:
    """FTS5 chokes on bare punctuation, so reduce to OR'd bare terms."""
    terms = re.findall(r"[\w']+", text)
    return " OR ".join(t for t in terms if len(t) > 1) or text


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(
    store: Store,
    cfg: Config,
    query: str,
    limit: int = 8,
    project: str | None = None,
    exclude_project: str | None = None,
    pool: int = 60,
) -> list[dict]:
    ranks: dict[int, float] = {}

    for rank, row in enumerate(store.lexical(_fts_query(query), pool)):
        ranks[row["id"]] = ranks.get(row["id"], 0) + 1 / (RRF_K + rank + 1)

    qvec = embed_batch([query], cfg.embedding_model)[0]
    scored = [
        (row["id"], _cosine(qvec, unpack(row["embedding"])))
        for row in store.all_embeddings()
    ]
    scored.sort(key=lambda p: p[1], reverse=True)
    for rank, (cid, _) in enumerate(scored[:pool]):
        ranks[cid] = ranks.get(cid, 0) + 1 / (RRF_K + rank + 1)

    ordered = sorted(ranks.items(), key=lambda p: p[1], reverse=True)
    rows = {r["id"]: r for r in store.by_ids([cid for cid, _ in ordered])}

    results = []
    for cid, score in ordered:
        row = rows.get(cid)
        if row is None:
            continue
        pname = row["project_name"]
        if project is not None and pname != project:
            continue
        if exclude_project is not None and pname == exclude_project:
            continue
        results.append(
            {
                "score": round(score, 5),
                "conversation_id": row["conversation_id"],
                "conversation": row["conversation_name"],
                "project": pname or "(no project)",
                "role": row["role"],
                "date": (row["created_at"] or "")[:10],
                "text": row["text"],
            }
        )
        if len(results) >= limit:
            break
    return results
