"""Filesystem layout for context-note.

Everything lives under one root so uninstall is `rm -rf ~/.context-note`.
Override with the CONTEXT_NOTE_HOME environment variable.
"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

ENV_HOME = "CONTEXT_NOTE_HOME"
DEFAULT_HOME = "~/.context-note"


def home() -> Path:
    raw = os.environ.get(ENV_HOME, DEFAULT_HOME)
    return Path(raw).expanduser().resolve()


@dataclass
class Paths:
    root: Path
    imports: Path
    processed: Path
    index: Path
    config: Path

    @classmethod
    def resolve(cls) -> "Paths":
        root = home()
        return cls(
            root=root,
            imports=root / "imports",
            processed=root / "processed",
            index=root / "index.db",
            config=root / "config.json",
        )

    def ensure(self) -> "Paths":
        self.root.mkdir(parents=True, exist_ok=True)
        self.imports.mkdir(exist_ok=True)
        self.processed.mkdir(exist_ok=True)
        return self


@dataclass
class Config:
    """User-tunable settings. Written on first run, edited by hand after."""

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 120
    # Projects listed here are never indexed. Match on project name.
    excluded_projects: list[str] = None
    # Skip messages shorter than this. Cuts "ok", "thanks", "yes".
    min_message_chars: int = 40
    # The watcher opens the conversations download link from an export
    # manifest automatically, in your default browser (see watch.py). Set
    # False to find and open that link by hand instead.
    auto_open_export_manifest: bool = True

    def __post_init__(self):
        if self.excluded_projects is None:
            self.excluded_projects = []

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg
        with path.open() as fh:
            return cls(**json.load(fh))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            json.dump(asdict(self), fh, indent=2)
