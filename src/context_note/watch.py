"""Watch for new Claude export archives and ingest them automatically.

Once the conversations zip lands in Downloads, this picks it up with no
further steps. Polls rather than using inotify so the same code works on
macOS, Linux, and Windows with no extra dependency.

The newer Settings > Privacy > Export data flow emails a manifest.json of
one-time-use download URLs (one per category -- conversations, projects,
users, memories) instead of a zip directly. handle_manifests() below opens
the conversations one in your default browser automatically, so requesting
the export is still the only manual step; see the README for why this
never needs to touch your session cookie to do that.
"""

import json
import re
import shutil
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, Paths
from .ingest import file_hash, ingest_pending
from .store import Store

POLL_SECONDS = 20
# A large export can take a while to finish writing. Only touch a file whose
# size has stopped changing, or we ingest a truncated zip.
STABLE_CHECKS = 2


def default_watch_dirs() -> list[Path]:
    downloads = Path.home() / "Downloads"
    return [d for d in (downloads,) if d.is_dir()]


CONVERSATIONS_BATCH_RE = re.compile(r"^conversations-\d+\.zip$")


def looks_like_export(path: Path) -> bool:
    """Anthropic names exports with a date stamp, but users rename things.

    Match on shape rather than exact filename: a zip whose name mentions the
    export, any conversations.json, or a conversations-NNN.zip batch file.

    As of the newer Settings > Privacy > Export data flow, a request no
    longer produces one zip. It emails a manifest-*.json listing several
    category zips (conversations, projects, users, memories) behind
    one-time-use signed URLs, so only the conversations-NNN.zip the user
    downloads from that manifest is relevant here -- the manifest itself
    isn't ingestable, and the other categories carry no conversation
    content (see the "Load your history" section of the README for why
    project attribution isn't recoverable from this format).
    """
    name = path.name.lower()
    if path.suffix == ".json":
        return name == "conversations.json"
    if path.suffix != ".zip":
        return False
    return (
        "claude" in name
        or "export" in name
        or name.startswith("data-")
        or bool(CONVERSATIONS_BATCH_RE.match(name))
    )


MANIFEST_RE = re.compile(r"^manifest-.*\.json$")


def looks_like_manifest(path: Path) -> bool:
    """The manifest itself is never ingested (see looks_like_export()) but
    it's what points at the actual conversations download link."""
    return path.suffix == ".json" and bool(MANIFEST_RE.match(path.name.lower()))


def conversations_url_from_manifest(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    for entry in data.get("data_files", []):
        if isinstance(entry, dict) and entry.get("category") == "conversations":
            url = entry.get("export_url")
            return url if isinstance(url, str) else None
    return None


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
    """Move stable export archives into imports/. Copies, never deletes.

    Only checks whether a copy is already waiting in imports/ -- not
    whether one was already processed. Anthropic reuses the same filename
    (e.g. conversations-000.zip) for every export, so a "was this filename
    already processed" check would treat every re-export as a duplicate.
    Content-level dedup happens in ingest.ingest_pending() instead, which
    can tell an unchanged re-download from a genuinely new export.
    """
    moved = []
    for directory in watch_dirs:
        if not directory.is_dir():
            continue
        for candidate in directory.iterdir():
            if not candidate.is_file() or not looks_like_export(candidate):
                continue
            target = paths.imports / candidate.name
            if target.exists():
                continue
            if not is_stable(candidate, seen):
                continue
            shutil.copy2(candidate, target)
            moved.append(target)
    return moved


def handle_manifests(
    watch_dirs: list[Path], store: Store, cfg: Config, seen: dict
) -> list[Path]:
    """Auto-open the conversations download link from a fresh export manifest.

    The newer export flow emails a manifest.json of one-time-use signed
    URLs instead of a zip (see looks_like_export()'s docstring), and
    finding the right one by hand is real friction. Opening it just
    launches the browser at that URL -- the browser's own logged-in
    session handles auth, so this never touches your session cookie or
    credentials, the same boundary the rest of this tool holds to.

    Marks a manifest handled (by content hash, so a service restart won't
    re-open it) whether or not a usable link was found in it, so a
    manifest with an unrecognized shape doesn't get re-inspected forever.
    """
    if not cfg.auto_open_export_manifest:
        return []
    opened = []
    for directory in watch_dirs:
        if not directory.is_dir():
            continue
        for candidate in directory.iterdir():
            if not candidate.is_file() or not looks_like_manifest(candidate):
                continue
            if not is_stable(candidate, seen):
                continue
            content_hash = file_hash(candidate)
            if store.already_opened_manifest(content_hash):
                continue
            url = conversations_url_from_manifest(candidate)
            store.mark_manifest_opened(
                content_hash, candidate.name, datetime.now(timezone.utc).isoformat()
            )
            if url:
                webbrowser.open(url)
                opened.append(candidate)
    return opened


def run(watch_dirs: list[Path] | None = None, once: bool = False) -> int:
    paths = Paths.resolve().ensure()
    cfg = Config.load(paths.config)
    dirs = watch_dirs or default_watch_dirs()
    seen: dict = {}
    store = Store(paths.index)

    print(f"watching: {', '.join(str(d) for d in dirs)}")
    print(f"ingesting into: {paths.index}")
    print("ctrl-c to stop")

    total = 0
    while True:
        opened = handle_manifests(dirs, store, cfg, seen)
        if opened:
            names = ", ".join(p.name for p in opened)
            print(f"\nopened conversations download link from: {names}")
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
