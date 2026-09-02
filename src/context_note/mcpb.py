"""Build a .mcpb Desktop Extension bundle for Claude Desktop, in pure Python.

A .mcpb file is just a zip containing a manifest.json (see
https://github.com/modelcontextprotocol/mcpb) -- packing one doesn't need
the mcpb CLI or a Node/npm install, only zipfile.

sentence-transformers/torch are too large to vendor into the bundle, so the
manifest points mcp_config.command at whatever interpreter already has
context-note installed rather than bundling dependencies.

Why this exists at all: on newer ("Cowork") Claude Desktop builds,
`context-note install`'s classic claude_desktop_config.json registration is
unreliable -- local MCP server support there can be feature-gated off
entirely, independent of anything in the config file. The .mcpb Desktop
Extension format is a separate, currently-working install path: drag the
built file onto Claude Desktop's Settings -> Extensions drop zone.
"""

import json
import sys
import zipfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

MANIFEST = {
    "manifest_version": "0.3",
    "name": "context-note",
    "description": "Local, cross-project search over your Claude conversation history.",
    "author": {"name": "context-note"},
    "server": {
        "type": "python",
        "entry_point": "server/main.py",
        "mcp_config": {
            "command": "",
            "args": ["-m", "context_note.server"],
        },
    },
    # Claude Desktop's extension loader lists an undeclared prompt fine but
    # refuses to actually call it ("attempted undeclared prompt"), unlike
    # tools, which work without a matching declaration here. This is a
    # separate, static-templating mechanism from MCP's own dynamic
    # prompts/get -- text is filled in client-side via ${arguments.NAME},
    # not by calling the server's @mcp.prompt() handler, so the template
    # has to be duplicated here and kept in sync with search_history()'s
    # f-string in server.py by hand. Only ever going to be a couple of
    # these, so that's an acceptable amount of manual sync.
    "prompts": [
        {
            "name": "da Cross Context",
            "description": "Search your past Claude conversations across every project.",
            "arguments": ["query"],
            "text": "Use context-note to search my other projects and non-project"
            " chats for: ${arguments.query}",
        }
    ],
}

# The manifest spec requires server.entry_point to point at a file inside
# the bundle, but the real server that actually runs is context_note.server,
# launched via mcp_config above using whichever interpreter has context-note
# installed. This placeholder is never executed.
SERVER_PLACEHOLDER = """\
# Placeholder only -- see manifest.json's server.mcp_config for what's
# actually launched. This file exists because the .mcpb manifest spec
# requires server.entry_point to point at a file inside the bundle.
"""


def _package_version() -> str:
    """The installed context-note version, so the bundle never drifts from
    pyproject.toml's -- there's only one place that sets the version, this
    just reads it back rather than duplicating it here by hand.
    """
    try:
        return version("context-note")
    except PackageNotFoundError:
        return "0.0.0"


def build_mcpb(out_path: Path, python: str | None = None) -> Path:
    """Pack a context-note.mcpb bundle at out_path and return it.

    python defaults to the interpreter running this function, i.e. whichever
    one has context-note installed if called from within context-note itself.
    """
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["version"] = _package_version()
    manifest["server"]["mcp_config"]["command"] = python or sys.executable

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("server/main.py", SERVER_PLACEHOLDER)
    return out_path
