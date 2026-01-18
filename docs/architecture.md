# Architecture

## Overview

backlog-mcp is a single-task loading MCP server that prevents AI scope creep by exposing ONE task at a time with full context.

## Core Principle

```
list_tasks() → summaries only (id, name, status, priority)
get_task()   → full context (files, action, verify, done_criteria)
```

This information hiding keeps the AI focused on a single task.

## Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Claude    │────▶│ backlog-mcp │────▶│   libSQL    │
│    Code     │◀────│   (FastMCP) │◀────│  database   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ~/.codeagent/
                    codeagent.db
```

## Database Schema

### projects
- `id` - Primary key
- `name` - Project name
- `prefix` - Unique identifier (e.g., "JC")
- `description` - Optional description

### tasks
- `task_id` - Format: PREFIX-TYPE-NNN (e.g., JC-TASK-001)
- `type` - task | bug | spike | epic
- `status` - backlog | ready | in_progress | blocked | done
- `action` - Implementation instructions
- `files_exclusive` - Files only this task modifies
- `files_readonly` - Read-only files
- `files_forbidden` - Off-limits files
- `verify` - Verification commands
- `done_criteria` - Completion checklist
- `depends_on` - Dependency chain

## Dependency Resolution

On task completion:
1. Mark task as done
2. Find tasks with `depends_on` containing this task_id
3. Check if ALL their dependencies are done
4. Auto-transition eligible tasks to `ready`

## Integration Points

Shared database with other CodeAgent MCPs:
- amem-mcp (semantic memory)
- reflection-mcp (episodic learning)
- codebase-mcp (code search)
