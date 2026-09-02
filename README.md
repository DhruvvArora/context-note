# context-note

Local, cross-project search over your Claude conversation history, exposed to Claude Desktop as an MCP server.

## Why

Claude scopes context strictly. Each project has its own memory space, and chat search only looks inside the project you are currently in (or, outside a project, only at non-project chats). That isolation is usually what you want. Sometimes it isn't: the thing you need is in a different project, or in a one-off chat you never filed anywhere.

There is no built-in way to bridge that. context-note builds a local index of your full history and hands Claude a search tool that ignores project boundaries, so you can pull context in deliberately without reorganizing anything.

Everything runs on your machine. No API keys, no accounts, nothing leaves the device.

## Install

```bash
git clone https://github.com/YOURNAME/context-note
cd context-note
pip install -e .
context-note init
context-note install             # registers the MCP server with Claude Desktop
context-note install --service   # runs the watcher in the background
```

Restart Claude Desktop.

### If Claude Desktop doesn't pick up the server

`context-note install` registers the server the classic way, by writing to
`claude_desktop_config.json`. On newer ("Cowork") Claude Desktop builds this
can silently not work: local MCP server support there is sometimes
feature-gated off entirely, independent of what's in the config file — the
app just shows "No servers added" no matter what the file contains, and
`~/Library/Logs/Claude/mcp.log` stays empty because it never even attempts
to load anything.

If that's what you're seeing, `context-note install` already built a
fallback for you: `~/.context-note/context-note.mcpb`, a Desktop Extension
bundle — a separate, currently-working install path on the same builds
(macOS also reveals it in Finder automatically after `install` runs). Get
it into Claude Desktop's Settings → Extensions: dragging the file onto the
drop zone worked reliably; if drag-and-drop doesn't work in your setup, the
panel usually has its own file picker/browse option as an alternative.

To rebuild it by hand (a custom output path, after moving your venv, etc.)
without re-running the rest of `install`:

```bash
python packaging/mcpb/build.py
```

No Node/npm needed — see [`context_note/mcpb.py`](src/context_note/mcpb.py)
for how the bundle gets built and a macOS permissions gotcha: a sandboxed
Python subprocess can get denied access to a venv living under
`~/Documents`, `~/Desktop`, or `~/Downloads` even after granting Claude
itself folder access. The fix is granting that specific Python binary its
own access under System Settings → Privacy & Security → Files & Folders.

## Load your history

There is no API for reading your claude.ai conversations, so the export itself
stays manual: in Claude, go to Settings > Privacy > Export data, wait for the
email, and click through.

The current export flow emails a `manifest-*.json` rather than a zip
directly -- that manifest lists several category files (`conversations`,
`projects`, `users`, `memories`), each behind a one-time-use signed URL:

```json
{
  "category": "conversations",
  "export_url": "https://claude.ai/export/.../download/...",
  "filename": "conversations-000.zip"
}
```

With the watcher running, you don't need to open that file yourself: once
the manifest lands in `~/Downloads`, `handle_manifests()` in `watch.py`
opens the conversations `export_url` in your default browser for you. That
still needs your logged-in session to actually complete the download (it's
launching a URL, not scripting a request), so it's a real click either way
-- but it's the browser tab that opens for you, not a JSON file you have to
read. Set `auto_open_export_manifest` to `false` in
`~/.context-note/config.json` to find and open that link by hand instead.

Everything after that is automatic. The watcher polls `~/Downloads`, spots the
export by name, waits until the file stops growing, copies it into `imports/`,
and indexes it. You never move a file or run `ingest` by hand.

### Project attribution doesn't survive this export flow

Search results and `--exclude-project`/`project` filtering will show
`(no project)` for anything ingested from the current export flow, even for
conversations you've organized into projects in the app. This isn't a
context-note bug: the `conversations-*.zip` no longer carries any
project reference on each conversation, and the `projects-*.zip` (project
names/descriptions) has no conversation-membership field either. Checked
both directly -- there is currently no data in the export that links the
two, so there's nothing for the parser to recover. If Anthropic adds that
link back to the export schema, `parser.py`'s `parse_conversations()` is
where to wire it back in.

```bash
context-note watch                  # foreground, ctrl-c to stop
context-note watch --dir ~/Desktop  # watch somewhere else, repeatable
context-note watch --once           # single pass, useful in cron
```

`install --service` registers it as a launchd agent on macOS or a systemd user
unit on Linux, so it survives reboots. On Windows, register `context-note watch`
with Task Scheduler.

Re-export whenever you want to refresh. Exports are full snapshots, so
re-ingesting replaces prior copies of the same conversations rather than
duplicating them, and the watcher skips a file it's already ingested --
by content hash, not filename, since Anthropic reuses the same filename
(`conversations-000.zip`) for every export.

### Why the export step isn't automated

Triggering an export means driving claude.ai's internal, undocumented endpoints
with your session cookie. That breaks whenever the frontend changes, and
shipping it in a public tool puts every user's session token in the blast
radius. One click a month is the better trade.

## Use

Inside any Claude Desktop chat:

> Search my other projects for what I decided about the chunking strategy.

Claude calls `search_context`, gets ranked snippets with project and date, and can call `get_conversation` to pull a full thread when a snippet is cut off.

From the terminal:

```bash
context-note search "chunking strategy"
context-note search "auth flow" --exclude-project "Job Search"
context-note stats
```

## How it works

```
~/.context-note/
  imports/      drop export zips here
  processed/    ingested zips move here
  index.db      SQLite: chunks, FTS5, embeddings
  config.json
```

Retrieval is hybrid. BM25 over FTS5 handles proper nouns, error strings, and identifiers. Dense vectors from a local sentence-transformers model handle vague callbacks. The two rankings are fused with Reciprocal Rank Fusion.

Embeddings are stored as float32 blobs and scored in Python rather than through a compiled vector extension. That costs some speed above roughly 100k chunks and buys a `pip install` that works everywhere, which for a local tool is the better trade.

## Configuration

Edit `~/.context-note/config.json`:

| Key | Default | Notes |
| --- | --- | --- |
| `embedding_model` | `all-MiniLM-L6-v2` | any sentence-transformers model |
| `chunk_max_chars` | 1200 | messages under this are never split |
| `min_message_chars` | 40 | drops "ok", "thanks" |
| `excluded_projects` | `[]` | project names to never index |
| `auto_open_export_manifest` | `true` | open the conversations link from an export manifest automatically |

Use `excluded_projects` for anything you want to stay siloed. The point is opt-in bridging, not a global dump.

## Limits

- Claude Desktop only. Browser claude.ai reaches remote connectors over HTTPS, not local stdio servers. A remote mode is plausible later; the retrieval layer is transport-agnostic on purpose.
- Ingestion is batch. Requesting the export takes one manual click, downloading the conversations file from the resulting manifest takes another (see "Load your history"); everything after that is automatic.
- No project attribution. The current export flow doesn't include any link between a conversation and the project it's filed under, so results always show `(no project)` and project filtering is a no-op regardless of how you've organized chats in the app. See "Load your history" above.
- The export schema is undocumented and can change. The parser skips shapes it does not recognize rather than failing, but a large format change will need a fix -- as happened with the move to the manifest + per-category zip format.

## License

MIT
