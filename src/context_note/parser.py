"""Parse a Claude data export into normalized messages.

The export is a zip containing conversations.json. Schema is not documented
and Anthropic can change it, so every field access here is defensive: unknown
shapes are skipped rather than raising.
"""

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class Message:
    conversation_id: str
    conversation_name: str
    project_name: str | None
    role: str
    text: str
    created_at: str
    index_in_conversation: int


def _text_from_content(content) -> str:
    """Content is sometimes a string, sometimes a list of typed blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def _message_text(msg: dict) -> str:
    # Newer exports use "content" blocks; older ones a flat "text" field.
    text = _text_from_content(msg.get("content"))
    if not text:
        text = msg.get("text", "") or ""
    return text.strip()


def parse_conversations(raw: list) -> Iterator[Message]:
    for convo in raw:
        if not isinstance(convo, dict):
            continue
        convo_id = convo.get("uuid") or convo.get("id")
        if not convo_id:
            continue
        name = convo.get("name") or "(untitled)"
        # The newer Settings > Privacy > Export data flow splits exports into
        # separate conversations/projects/users/memories files, and the
        # conversations one no longer carries any project reference at all
        # (checked: no "project" or "project_uuid" key, and the projects
        # file has no conversation-membership field either). There is
        # currently no way to recover this association from an export, so
        # project_name stays None for data from that flow -- this is not a
        # parsing bug, the data just isn't there. The dict/str handling
        # below is kept for older exports that do carry it.
        project = convo.get("project")
        project_name = None
        if isinstance(project, dict):
            project_name = project.get("name")
        elif isinstance(project, str):
            project_name = project

        messages = convo.get("chat_messages") or convo.get("messages") or []
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            text = _message_text(msg)
            if not text:
                continue
            yield Message(
                conversation_id=convo_id,
                conversation_name=name,
                project_name=project_name,
                role=msg.get("sender") or msg.get("role") or "unknown",
                text=text,
                created_at=msg.get("created_at") or convo.get("created_at") or "",
                index_in_conversation=i,
            )


def read_export(path: Path) -> Iterator[Message]:
    """Accept either the raw export zip or an already-extracted json file."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            target = next(
                (n for n in zf.namelist() if n.endswith("conversations.json")), None
            )
            if target is None:
                raise ValueError(f"no conversations.json inside {path.name}")
            with zf.open(target) as fh:
                raw = json.load(fh)
    elif path.suffix == ".json":
        with path.open() as fh:
            raw = json.load(fh)
    else:
        raise ValueError(f"unsupported export file: {path.name}")

    if not isinstance(raw, list):
        raise ValueError("expected conversations.json to contain a list")
    yield from parse_conversations(raw)
