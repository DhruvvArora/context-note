"""Watch for new Claude export archives and ingest them automatically.

Removes every manual step after the download: you click Export data, the file
lands in Downloads, and this picks it up. Polls rather than using inotify so
the same code works on macOS, Linux, and Windows with no extra dependency.
"""

import shutil
import time
from pathlib import Path

from .config import Config, Paths
from .ingest import ingest_pending

POLL_SECONDS = 20
# A large export can take a while to finish writing. Only touch a file whose
# size has stopped changing, or we ingest a truncated zip.
STABLE_CHECKS = 2


def default_watch_dirs() -> list[Path]:
    downloads = Path.home() / "Downloads"
    return [d for d in (downloads,) if d.is_dir()]


def looks_like_export(path: Path) -> bool:
    """Anthropic names exports with a date stamp, but users rename things.

    Match on shape rather than exact filename: a zip whose name mentions the
    export, or any conversations.json.
    """
    name = path.name.lower()
    if path.suffix == ".json":
        return name == "conversations.json"
    if path.suffix != ".zip":
        return False
    return "claude" in name or "export" in name or "data-" in name


def is_stable(path: Path, seen: dict[Path, tuple[int, int]]) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    prev_size, count = seen.get(path, (-1, 0))
    if size == prev_size:
        count += 1
    else:
        count = 0
    seen[path] = (size, count)
    return count >= STABLE_CHECKS


def collect(watch_dirs: list[Path], paths: Paths, seen: dict) -> list[Path]:
    """Move stable export archives into imports/. Copies, never deletes."""
    moved = []
    for directory in watch_dirs:
        if not directory.is_dir():
            continue
        for candidate in directory.iterdir():
            if not candidate.is_file() or not looks_like_export(candidate):
                continue
            target = paths.imports / candidate.name
            if target.exists() or (paths.processed / candidate.name).exists():
                continue
            if not is_stable(candidate, seen):
                continue
            shutil.copy2(candidate, target)
            moved.append(target)
    return moved


def run(watch_dirs: list[Path] | None = None, once: bool = False) -> int:
    paths = Paths.resolve().ensure()
    cfg = Config.load(paths.config)
    dirs = watch_dirs or default_watch_dirs()
    seen: dict = {}

    print(f"watching: {', '.join(str(d) for d in dirs)}")
    print(f"ingesting into: {paths.index}")
    print("ctrl-c to stop")

    total = 0
    while True:
        found = collect(dirs, paths, seen)
        if found:
            print(f"\nfound {len(found)} new export(s)")
        results = ingest_pending(paths, cfg, verbose=bool(found))
        total += sum(results.values())
        if once:
            return total
        try:
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print(f"\nstopped. {total} chunks indexed this session.")
            return total
