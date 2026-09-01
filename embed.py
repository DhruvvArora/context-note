"""Chunking and local embeddings.

The model is loaded lazily so that `context-note stats` and `--help` stay fast
and do not pull torch into memory for no reason.
"""

from .parser import Message
from .store import Chunk

_model = None


def get_model(name: str):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(name)
    return _model


def embed_batch(texts: list[str], model_name: str):
    model = get_model(model_name)
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def split(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split on paragraph boundaries, falling back to a hard cut.

    Messages are the natural unit here, so most never split at all. Only long
    ones do, and splitting mid-sentence loses meaning, so paragraphs first.
    """
    if len(text) <= max_chars:
        return [text]

    paras = [p for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paras:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
        if len(para) <= max_chars:
            current = para
        else:
            step = max_chars - overlap
            for i in range(0, len(para), step):
                chunks.append(para[i : i + max_chars])
            current = ""
    if current:
        chunks.append(current)
    return chunks


def to_chunks(msg: Message, max_chars: int, overlap: int) -> list[Chunk]:
    return [
        Chunk(
            conversation_id=msg.conversation_id,
            conversation_name=msg.conversation_name,
            project_name=msg.project_name,
            role=msg.role,
            created_at=msg.created_at,
            position=msg.index_in_conversation,
            text=piece,
        )
        for piece in split(msg.text, max_chars, overlap)
    ]
