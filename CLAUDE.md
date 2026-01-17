# backlog-mcp

Single-task loading MCP server for Claude Code - prevents scope creep by exposing ONE task at a time.

## Structure

| Path | Purpose |
|------|---------|
| `src/backlog_mcp/server.py` | Main MCP server with all tools |
| `src/backlog_mcp/__init__.py` | Package exports |
| `convex/` | Convex backend functions |
| `pyproject.toml` | Dependencies and build config |

## Commands

```bash
# Install dependencies
uv sync

# Run linting
uv run ruff check .

# Run formatting
uv run ruff format .

# Type check
uv run mypy src/

# Run server (requires Convex backend)
CONVEX_URL=http://localhost:3210 uv run backlog-mcp
```

## Environment

- `CONVEX_URL`: Backend URL (default: `http://localhost:3210`)
