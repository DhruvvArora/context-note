#!/usr/bin/env python3
"""Build a context-note.mcpb Desktop Extension bundle by hand.

`context-note install` already does this automatically as part of
registering with Claude Desktop. This script is a manual escape hatch --
for a custom output path, a different interpreter, or rebuilding without
running the rest of `install`.

Pure Python: no Node/npm or mcpb CLI needed. See context_note.mcpb for the
actual bundle-building logic and why this exists.

Usage:
    pip install -e .                      # from the repo root, if not done yet
    python packaging/mcpb/build.py [--python /path/to/venv/bin/python]
"""

import argparse
import sys
from pathlib import Path

from context_note.mcpb import build_mcpb

HERE = Path(__file__).parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Absolute path to the Python interpreter with context-note "
        "installed (defaults to the interpreter running this script).",
    )
    parser.add_argument(
        "--out",
        default=str(HERE / "context-note.mcpb"),
        help="Output .mcpb path.",
    )
    args = parser.parse_args()

    out_path = build_mcpb(Path(args.out), python=args.python)
    print(f"built {out_path}")
    print("Drag it onto Claude Desktop's Settings -> Extensions drop zone to install.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
