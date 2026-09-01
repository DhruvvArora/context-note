#!/usr/bin/env python3
"""Build a context-note.mcpb Desktop Extension bundle for Claude Desktop.

Why this exists: on newer ("Cowork") Claude Desktop builds, `context-note
install`'s classic claude_desktop_config.json / mcpServers registration is
unreliable -- local MCP server support there can be feature-gated off
entirely, independent of anything in the config file. The .mcpb Desktop
Extension format (https://github.com/modelcontextprotocol/mcpb) is a
separate, currently-working install path: drag the built .mcpb file onto
Claude Desktop's Settings -> Extensions drop zone.

sentence-transformers/torch are too large to vendor into the bundle, so this
points the extension straight at an existing interpreter that already has
context-note installed (e.g. a venv you built with `pip install -e .`)
rather than bundling dependencies.

Usage:
    pip install -e .                      # from the repo root, if not done yet
    python packaging/mcpb/build.py [--python /path/to/venv/bin/python]

Requires the mcpb CLI to actually pack the bundle (`npm install -g
@anthropic-ai/mcpb`); without it, this still writes the build/ directory so
you can pack it by hand.

Known gotcha on macOS: if your venv lives under ~/Documents, ~/Desktop, or
~/Downloads, Claude Desktop's sandboxed subprocess may fail with
`PermissionError: ... pyvenv.cfg` even after granting the Claude app itself
folder access. macOS's TCC attributes that file-access request to the actual
interpreter binary (e.g. "python3.14"), not to Claude -- grant that binary
its own folder access under System Settings -> Privacy & Security -> Files
& Folders.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

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

    build_dir = HERE / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    (build_dir / "server").mkdir(parents=True)

    manifest = json.loads((HERE / "manifest.template.json").read_text())
    manifest["server"]["mcp_config"]["command"] = args.python
    (build_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    shutil.copy(HERE / "server" / "main.py", build_dir / "server" / "main.py")

    print(f"wrote {build_dir}")

    if shutil.which("mcpb") is None:
        print("\nmcpb CLI not found. Install it and pack manually:")
        print("  npm install -g @anthropic-ai/mcpb")
        print(f"  mcpb pack {build_dir} {args.out}")
        return 0

    subprocess.run(["mcpb", "validate", str(build_dir)], check=True)
    subprocess.run(["mcpb", "pack", str(build_dir), args.out], check=True)
    print(f"\nbuilt {args.out}")
    print("Drag it onto Claude Desktop's Settings -> Extensions drop zone to install.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
