# backlog-mcp

Single-task loading backlog MCP for Claude Code - Convex backend.

## Philosophy

**Prevent AI scope creep** through information hiding:

- `list_tasks()` returns summaries only (id, name, status)
- `get_task()` returns full context for ONE task

AI has tunnel vision. Cannot see other tasks while working. Stays focused.

Backed by [Convex](https://convex.dev) reactive database.

## Features

| Tool | Description |
|------|-------------|
| `list_tasks` | Get task summaries only (prevents scope creep) |
| `get_task` | Full context for ONE task |
| `get_next_task` | Highest priority ready task |
| `create_task` | Create a new task |
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

- Convex backend running at localhost:3210

## Installation

```bash
pip install git+https://github.com/Questi0nM4rk/backlog-mcp.git
```

## Usage with Claude Code

```bash
claude mcp add backlog -- python -m backlog_mcp.server
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONVEX_URL` | `http://localhost:3210` | Convex backend URL |

## Setting Up Convex Backend

The `convex/` folder contains the schema and functions for the self-hosted Convex backend:

1. Install Convex backend: https://docs.convex.dev/self-hosting
2. Deploy the schema and functions from `convex/`

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

## License

MIT
