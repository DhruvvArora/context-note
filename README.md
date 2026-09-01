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

## Load your history

There is no API for reading your claude.ai conversations, so the export itself
stays manual: in Claude, go to Settings > Privacy > Export data, wait for the
email, and download the zip.

Everything after that is automatic. The watcher polls `~/Downloads`, spots the
export by name, waits until the file stops growing, copies it into `imports/`,
and indexes it. You never move a file or run `ingest` by hand.

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
duplicating them, and the watcher skips files it has already seen.

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

Use `excluded_projects` for anything you want to stay siloed. The point is opt-in bridging, not a global dump.

## Limits

- Claude Desktop only. Browser claude.ai reaches remote connectors over HTTPS, not local stdio servers. A remote mode is plausible later; the retrieval layer is transport-agnostic on purpose.
- Ingestion is batch. Requesting the export is one manual click; everything after it is automatic.
- The export schema is undocumented and can change. The parser skips shapes it does not recognize rather than failing, but a large format change will need a fix.

## License

MIT
