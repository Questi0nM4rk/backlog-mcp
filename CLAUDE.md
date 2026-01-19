# backlog-mcp

Single-task loading MCP server for Claude Code - prevents scope creep by exposing ONE task at a time.

## Structure

| Path | Purpose |
|------|---------|
| `src/backlog_mcp/server.py` | Main MCP server with all tools |
| `src/backlog_mcp/__init__.py` | Package exports |
| `pyproject.toml` | Dependencies and build config |

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
uv run mypy src/

# Run tests
uv run pytest tests/ -v

# Run server (uses local libSQL database)
uv run backlog-mcp
```

## Storage

Database: `~/.codeagent/codeagent.db` (libSQL/SQLite)

## Git Workflow

**IMPORTANT**: Direct push to `main` is disabled. All changes must go through PRs.

1. Create a feature branch: `git checkout -b feat/description`
2. Make changes and commit
3. Push branch: `git push -u origin feat/description`
4. Create PR via `gh pr create` or GitHub UI
5. CodeRabbit provides automated review
6. After addressing comments, **resolve each GitHub conversation**
7. Merge when approved

### CodeRabbit Tips

- Push fixes for review comments
- Click "Resolve conversation" on each addressed comment
- CodeRabbit auto-approves when all resolved and checks pass
