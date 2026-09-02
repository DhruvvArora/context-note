"""MCP server over stdio, for Claude Desktop.

Kept deliberately thin: it wraps search.py and store.py and does no work of its
own, so adding an HTTP transport later means adding a file, not a rewrite.
"""

import json

from mcp.server.fastmcp import FastMCP

from .config import Config, Paths
from .search import search as run_search
from .store import Store

mcp = FastMCP("context-note")

_paths = Paths.resolve().ensure()
_cfg = Config.load(_paths.config)
_store = Store(_paths.index)


@mcp.tool()
def search_context(
    query: str,
    limit: int = 8,
    project: str | None = None,
    exclude_project: str | None = None,
) -> str:
    """Search past Claude conversations across every project and non-project chat.

    Use this when the user refers to something discussed before that is not in
    the current conversation or project. Pass `project` to restrict to one
    project, or `exclude_project` to skip the one you are already in.
    """
    results = run_search(
        _store, _cfg, query, limit=limit, project=project, exclude_project=exclude_project
    )
    if not results:
        return "No matching past conversations."
    return json.dumps(results, indent=2)


@mcp.tool()
def get_conversation(conversation_id: str, max_chunks: int = 40) -> str:
    """Fetch a full past conversation by id, in order.

    Call after search_context when a snippet is on-target but truncated.
    """
    rows = _store.conversation(conversation_id)
    if not rows:
        return f"No conversation found with id {conversation_id}."
    header = f"{rows[0]['conversation_name']} (project: {rows[0]['project_name'] or 'none'})"
    body = "\n\n".join(f"[{r['role']}] {r['text']}" for r in rows[:max_chunks])
    suffix = "" if len(rows) <= max_chunks else f"\n\n[truncated, {len(rows)} chunks total]"
    return f"{header}\n\n{body}{suffix}"


@mcp.tool()
def index_stats() -> str:
    """Report how much conversation history is currently indexed."""
    return json.dumps(_store.stats(), indent=2)


# A prompt rather than a tool: this one shows up in Claude Desktop's picker
# for choosing to search on purpose, versus search_context above, which
# Claude calls on its own when something in the conversation calls for it.
# Its docstring is shown to the user verbatim as the prompt's description,
# so keep it user-facing -- not documentation for whoever reads this file.
@mcp.prompt(name="da Cross Context", title="Cross Context")
def search_history(query: str) -> str:
    """Search your past Claude conversations across every project."""
    return f"Use context-note to search my other projects and non-project chats for: {query}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
