# Plan: Migrate to libSQL

## Changes

Replace Convex HTTP API with libSQL.

### Files to Modify

- `src/backlog_mcp/server.py`:
  - Remove `_convex_request()` helper
  - Add `_get_db()` connection helper
  - Convert each tool function to SQL queries
  - Use `json.dumps/loads` for array fields

### Dependencies

```toml
[project.dependencies]
libsql-experimental = ">=0.0.50"
```

### Database Location

`~/.codeagent/codeagent.db` (shared with other MCPs)

### Schema

```sql
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    prefix TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'backlog',
    priority INTEGER DEFAULT 3,
    description TEXT,
    action TEXT,
    files_exclusive TEXT,  -- JSON array
    files_readonly TEXT,   -- JSON array
    files_forbidden TEXT,  -- JSON array
    verify TEXT,           -- JSON array
    done_criteria TEXT,    -- JSON array
    depends_on TEXT,       -- JSON array
    parent_id TEXT,
    execution_strategy TEXT,
    checkpoint_type TEXT,
    blocker_reason TEXT,
    blocker_needs TEXT,
    summary TEXT,
    commits TEXT,          -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
```

### Verification

- `uv run pytest tests/ -v`
- Manual: create_project, create_task, complete_task flow
