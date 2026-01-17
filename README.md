# backlog-mcp

Single-task loading backlog MCP for Claude Code - libSQL backend.

## Philosophy

**Prevent AI scope creep** through information hiding:

- `list_tasks()` returns summaries only (id, name, status)
- `get_task()` returns full context for ONE task

AI has tunnel vision. Cannot see other tasks while working. Stays focused.

## Features

| Tool | Description |
|------|-------------|
| `list_tasks` | Get task summaries only (prevents scope creep) |
| `get_task` | Full context for ONE task |
| `get_next_task` | Highest priority ready task |
| `create_task` | Create a new task |
| `create_project` | Create a project for organizing tasks |
| `list_projects` | List all projects |
| `update_task_status` | Update task status |
| `complete_task` | Mark done, auto-unblock dependents |
| `delete_task` | Remove a task |
| `get_backlog_summary` | Dashboard view |

## Task Types

- `task` - Standard implementation task
- `bug` - Bug fix (prioritized)
- `spike` - Research/investigation
- `epic` - Parent for related tasks

## Task Statuses

- `backlog` - Not ready (has pending dependencies)
- `ready` - Available for work
- `in_progress` - Currently being worked on
- `blocked` - Waiting on something
- `done` - Completed

## Requirements

- Python 3.10+
- uv (recommended) or pip

## Installation

```bash
pip install git+https://github.com/Questi0nM4rk/backlog-mcp.git
```

Or with uv:

```bash
uv pip install git+https://github.com/Questi0nM4rk/backlog-mcp.git
```

## Usage with Claude Code

```bash
claude mcp add backlog -- python -m backlog_mcp.server
```

## Storage

Database: `~/.codeagent/codeagent.db` (libSQL/SQLite)

The database is created automatically on first use.

## Task Context Fields

When you call `get_task()`, you get full implementation context:

```json
{
  "id": "JC-TASK-001",
  "name": "Add user authentication",
  "action": "Implementation instructions...",
  "files_exclusive": ["src/auth/"],
  "files_readonly": ["src/config/"],
  "files_forbidden": ["src/core/"],
  "verify": ["npm test", "npm run lint"],
  "done_criteria": ["Tests pass", "No lint errors"]
}
```

## Development

```bash
# Clone the repository
git clone https://github.com/Questi0nM4rk/backlog-mcp.git
cd backlog-mcp

# Install dependencies
uv sync

# Run linting
uv run ruff check src/ tests/

# Run formatting
uv run ruff format src/ tests/

# Type check
uv run mypy src/ tests/

# Run tests
uv run pytest tests/ -v
```

## License

MIT
