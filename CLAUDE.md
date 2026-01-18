# backlog-mcp

Single-task loading MCP server for Claude Code - prevents scope creep by exposing ONE task at a time.

## Structure

| Path | Purpose |
|------|---------|
| `src/backlog_mcp/server.py` | Main MCP server with all tools |
| `src/backlog_mcp/__init__.py` | Package exports |
| `pyproject.toml` | Dependencies and build config |
| `plans/` | Implementation plans and proposals |
| `docs/` | Extended documentation (architecture, patterns) |

## Prerequisites

Install uv (fast Python package manager):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, ensure `uv` is on your PATH (restart shell or source the profile).

## Commands

```bash
# Install dependencies
uv sync

# Run linting
uv run ruff check .

# Run formatting
uv run ruff format .

# Type check
uv run pyright src/ tests/

# Run tests
uv run pytest tests/ -v

# Run server (uses local libSQL database)
uv run backlog-mcp
```

## Storage

Database: `~/.codeagent/codeagent.db` (libSQL/SQLite)
