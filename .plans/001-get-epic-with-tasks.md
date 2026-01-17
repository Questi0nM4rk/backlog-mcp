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
export const getEpicWithTasks = query({
  args: { epic_id: v.string() },
  handler: async (ctx, args) => {
    const epic = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.epic_id))
      .first();

    if (!epic || epic.type !== "epic") {
      return { error: "Epic not found" };
    }

    const children = await ctx.db
      .query("tasks")
      .withIndex("by_parent", (q) => q.eq("parent_id", args.epic_id))
      .collect();

    return {
      epic: { id: epic.task_id, name: epic.name, ... },
      tasks: children.map(t => ({ id: t.task_id, name: t.name, status: t.status, ... })),
      next_task_id: children.find(t => t.status === "ready")?.task_id,
    };
  },
});
```

### 2. Add Python MCP Tool

**File:** `src/backlog_mcp/server.py`

```python
@mcp.tool()
def get_epic_with_tasks(epic_id: str) -> dict[str, Any]:
    """Get epic overview with child task summaries."""
    return _convex_request("query", "getEpicWithTasks", {"epic_id": epic_id})
```

## Done Criteria

- [ ] Convex query added and deployed
- [ ] Python MCP tool added
- [ ] README updated with orchestration workflow
- [ ] Tests pass
