"""Command line entry point."""

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Config, Paths
from .ingest import ingest_pending
from .search import search as run_search
from .store import Store


def desktop_config_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if system == "Windows":
        return Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def cmd_init(args) -> int:
    paths = Paths.resolve().ensure()
    Config.load(paths.config)
    Store(paths.index)
    print(f"context-note home: {paths.root}")
    print(f"drop your Claude data export zip in: {paths.imports}")
    print("then run: context-note ingest")
    return 0


def cmd_ingest(args) -> int:
    paths = Paths.resolve().ensure()
    cfg = Config.load(paths.config)
    results = ingest_pending(paths, cfg)
    if not results:
        print(f"nothing new in {paths.imports}")
        return 0
    print(f"indexed {sum(results.values())} chunks from {len(results)} file(s)")
    return 0


def cmd_search(args) -> int:
    paths = Paths.resolve()
    cfg = Config.load(paths.config)
    store = Store(paths.index)
    results = run_search(
        store, cfg, args.query, limit=args.limit, exclude_project=args.exclude_project
    )
    if not results:
        print("no matches")
        return 0
    for r in results:
        print(f"\n[{r['project']}] {r['conversation']}  {r['date']}  ({r['role']})")
        snippet = r["text"][:400].replace("\n", " ")
        print(f"  {snippet}{'...' if len(r['text']) > 400 else ''}")
    return 0


def cmd_stats(args) -> int:
    paths = Paths.resolve()
    if not paths.index.exists():
        print("no index yet, run: context-note init")
        return 1
    print(json.dumps(Store(paths.index).stats(), indent=2))
    return 0


def cmd_watch(args) -> int:
    from .watch import run

    dirs = [Path(d).expanduser() for d in args.dir] if args.dir else None
    run(watch_dirs=dirs, once=args.once)
    return 0


def cmd_install(args) -> int:
    """Register the MCP server with Claude Desktop."""
    if args.service:
        from .service import install_service

        return install_service(Paths.resolve().ensure().root / "watch.log")

    cfg_path = desktop_config_path()
    if not cfg_path.parent.exists():
        print(f"Claude Desktop config directory not found at {cfg_path.parent}")
        print("Is Claude Desktop installed?")
        return 1

    existing = {}
    if cfg_path.exists():
        shutil.copy(cfg_path, cfg_path.with_suffix(".json.bak"))
        try:
            existing = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            print(f"existing config at {cfg_path} is not valid JSON, refusing to overwrite")
            return 1

    servers = existing.setdefault("mcpServers", {})
    servers["context-note"] = {
        "command": sys.executable,
        "args": ["-m", "context_note.server"],
    }
    cfg_path.write_text(json.dumps(existing, indent=2))
    print(f"registered context-note in {cfg_path}")
    print("restart Claude Desktop to pick it up")

    from .mcpb import build_mcpb

    mcpb_path = Paths.resolve().ensure().root / "context-note.mcpb"
    build_mcpb(mcpb_path)
    print(f"\nalso built {mcpb_path}")
    print(
        "On some Claude Desktop builds, local MCP server support like the "
        "registration above doesn't take effect (it can be feature-gated "
        "off independent of the config file). If restarting doesn't work, "
        "drag that file onto Settings -> Extensions instead."
    )
    if platform.system() == "Darwin":
        subprocess.run(["open", "-R", str(mcpb_path)], capture_output=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="context-note")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the home directory and empty index")
    sub.add_parser("ingest", help="index any new exports in imports/")
    sub.add_parser("stats", help="show index size")
    i = sub.add_parser("install", help="register the MCP server with Claude Desktop")
    i.add_argument(
        "--service",
        action="store_true",
        help="instead, install the watcher as a background service",
    )

    s = sub.add_parser("search", help="query the index from the terminal")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--exclude-project", default=None)

    w = sub.add_parser("watch", help="auto-ingest exports as they appear")
    w.add_argument(
        "--dir",
        action="append",
        help="directory to watch (repeatable, defaults to ~/Downloads)",
    )
    w.add_argument("--once", action="store_true", help="single pass then exit")

    return p


def main() -> int:
    args = build_parser().parse_args()
    return {
        "init": cmd_init,
        "ingest": cmd_ingest,
        "search": cmd_search,
        "stats": cmd_stats,
        "watch": cmd_watch,
        "install": cmd_install,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
