# MCP server

`base-legal mcp` runs a **read-only** [Model Context Protocol](https://modelcontextprotocol.io)
server on stdio. The MCP host's own model writes the answer; Base Legal only
retrieves provisions and checks citations. It never calls Claude or any other
third party, and questions are embedded locally ([ADR 0003](adr/0003-asymmetric-voyage-embeddings.md)).

| Tool | What it does |
|---|---|
| `search_provisions(question, k=8)` | The provisions most relevant to a question in Portuguese (k ≤ 20), with canonical IDs and official text; `no_support` when nothing in the corpus supports it |
| `get_provision(provision_id, at=None)` | One provision by canonical ID (`lgpd:art7:incIX`, `lai:art31`, `res-anpd-15-2024:anx1:art6`), with its amendment notes, whether it is in force and the other provisions its text cites; `at="AAAA-MM-DD"` returns the wording in force on that date, with the act that introduced it and whether the date is certain (ADR 0014) |
| `get_provision_history(provision_id)` | Every recorded wording of a provision, oldest first, with the act that introduced each one and when it was in force (empty if never amended) |
| `verify_citation(provision_id, quote)` | Whether the provision exists, is in force and contains the quote verbatim |

All four are annotated read-only, non-destructive, idempotent and
closed-world; `tests/unit/test_mcp_server.py` asserts it, and
`tests/integration/test_mcp_stdio.py` runs the stdio server as a subprocess in
which constructing an Anthropic client aborts the process.

## Prerequisites

A PostgreSQL with the corpus ingested (see the README quickstart) and the
query model fetched (`uv run base-legal model fetch`). The server reads
`DATABASE_URL` and the other `BASE_LEGAL_*` settings from its environment.

## Claude Code

```bash
claude mcp add base-legal \
  --env DATABASE_URL=postgresql://base_legal:base_legal@localhost:5432/base_legal \
  -- uv --directory /absolute/path/to/base-legal run base-legal mcp
```

## Claude Desktop

Add to `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/`; Windows: `%APPDATA%\Claude\`), then
restart Claude Desktop:

```json
{
  "mcpServers": {
    "base-legal": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/base-legal", "run", "base-legal", "mcp"],
      "env": {
        "DATABASE_URL": "postgresql://base_legal:base_legal@localhost:5432/base_legal"
      }
    }
  }
}
```

`TODO(verify)`: both configurations were validated with the MCP Python SDK
client over stdio, not yet inside Claude Desktop or Claude Code (PLAN §9).

## Privacy

With MCP, Base Legal transfers nothing: retrieval is local and the question
goes to whichever model the host uses, under the host's terms. The server logs
no question text (stdout carries only the protocol; logs go to stderr).
