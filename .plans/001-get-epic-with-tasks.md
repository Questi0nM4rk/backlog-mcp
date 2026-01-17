# Plan: Add get_epic_with_tasks Function

## Problem

Currently, getting an epic doesn't return its child tasks. The main orchestrating agent needs to see the epic overview + task list to dispatch work to implementer subagents.

This maintains GSD+ philosophy:
- **Main agent**: sees epic + task summaries (orchestration)
- **Implementer subagents**: see ONE task at a time (tunnel vision)

## Implementation

### 1. Add Convex Query

**File:** `convex/functions.ts`

```typescript
/**
 * Get epic with its child tasks (summaries only).
 *
 * For orchestration - main agent sees overview,
 * implementers still get single tasks via getTask().
 */
export const getEpicWithTasks = query({
  args: {
    epic_id: v.string(),
  },
  handler: async (ctx, args) => {
    // Parse epic ID to get task_id
    const epic = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.epic_id))
      .first();

    if (!epic || epic.type !== "epic") {
      return { error: "Epic not found or not an epic type" };
    }

    // Get child tasks using by_parent index
    const children = await ctx.db
      .query("tasks")
      .withIndex("by_parent", (q) => q.eq("parent_id", args.epic_id))
      .collect();

    // Sort by priority, then by depends_on (tasks with no deps first)
    const sorted = children.sort((a, b) => {
      if (a.priority !== b.priority) return a.priority - b.priority;
      return a.depends_on.length - b.depends_on.length;
    });

    // Find next ready task
    const nextReady = sorted.find((t) => t.status === "ready");

    return {
      epic: {
        id: epic.task_id,
        name: epic.name,
        description: epic.description,
        status: epic.status,
        done_criteria: epic.done_criteria,
        created_at: epic.created_at,
      },
      tasks: sorted.map((t) => ({
        id: t.task_id,
        name: t.name,
        status: t.status,
        priority: t.priority,
        depends_on: t.depends_on,
        execution_strategy: t.execution_strategy,
      })),
      next_task_id: nextReady?.task_id || null,
      stats: {
        total: children.length,
        done: children.filter((t) => t.status === "done").length,
        ready: children.filter((t) => t.status === "ready").length,
        blocked: children.filter((t) => t.status === "blocked").length,
      },
    };
  },
});
```

### 2. Add Python MCP Tool

**File:** `src/backlog_mcp/server.py`

```python
@mcp.tool()
def get_epic_with_tasks(epic_id: str) -> dict[str, Any]:
    """
    Get epic overview with child task summaries.

    For orchestration: main agent sees the big picture,
    then dispatches individual tasks to implementer subagents.

    Args:
        epic_id: Epic task ID (e.g., "MP-EPIC-001")

    Returns:
        - epic: Epic summary (name, description, done_criteria)
        - tasks: Child task summaries (id, name, status, depends_on)
        - next_task_id: Highest priority ready task
        - stats: Counts by status
    """
    try:
        result = _convex_request(
            "query",
            "getEpicWithTasks",
            {"epic_id": epic_id},
        )
        return result
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
```

### 3. Update README

Add to workflow section:

```markdown
## Epic Orchestration

Main agent workflow:
```python
# Get epic overview + child tasks
epic_data = get_epic_with_tasks("MP-EPIC-001")

# Epic: {name, description, done_criteria}
# Tasks: [{id, name, status, depends_on}, ...]
# next_task_id: "MP-TASK-002"

# Dispatch to implementer (gets full context)
task = get_task(epic_data["next_task_id"])
```

This maintains tunnel vision for workers while giving orchestrator context.
```

## Verification

```bash
# Test Convex function
curl -X POST http://localhost:3210/api/query \
  -H "Content-Type: application/json" \
  -d '{"path": "functions:getEpicWithTasks", "args": {"epic_id": "MP-EPIC-001"}}'

# Test MCP tool
python -c "from backlog_mcp.server import get_epic_with_tasks; print(get_epic_with_tasks('MP-EPIC-001'))"
```

## Done Criteria

- [ ] Convex query added and deployed
- [ ] Python MCP tool added
- [ ] README updated with orchestration workflow
- [ ] Tests pass
