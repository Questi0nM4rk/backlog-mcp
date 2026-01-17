# Plan: Workflow Tools for GSD+

## 1. get_tasks_by_state

Filter tasks by status for quick views.

### Convex Query

```typescript
export const getTasksByState = query({
  args: {
    state: v.union(
      v.literal("backlog"),
      v.literal("ready"),
      v.literal("in_progress"),
      v.literal("blocked"),
      v.literal("done")
    ),
    project_prefix: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const tasks = await ctx.db
      .query("tasks")
      .withIndex("by_status", (q) => q.eq("status", args.state))
      .collect();

    // Filter by project if provided
    let filtered = tasks;
    if (args.project_prefix) {
      const project = await ctx.db
        .query("projects")
        .withIndex("by_prefix", (q) => q.eq("prefix", args.project_prefix!.toUpperCase()))
        .first();
      if (project) {
        filtered = tasks.filter((t) => t.project === project._id);
      }
    }

    return {
      state: args.state,
      count: filtered.length,
      tasks: filtered.map((t) => ({
        id: t.task_id,
        name: t.name,
        priority: t.priority,
        parent_id: t.parent_id,
        depends_on_count: t.depends_on.length,
      })),
    };
  },
});
```

### Python Tool

```python
@mcp.tool()
def get_tasks_by_state(
    state: str,
    project: str | None = None,
) -> dict[str, Any]:
    """
    Get all tasks in a specific state.

    Args:
        state: backlog, ready, in_progress, blocked, or done
        project: Optional project prefix filter

    Returns:
        Task summaries filtered by state
    """
    return _convex_request("query", "getTasksByState", {
        "state": state,
        "project_prefix": project,
    })
```

---

## 2. bulk_create_tasks

Create multiple tasks at once from /plan output.

### Convex Mutation

```typescript
export const bulkCreateTasks = mutation({
  args: {
    project_prefix: v.string(),
    epic_id: v.optional(v.string()),
    tasks: v.array(
      v.object({
        name: v.string(),
        type: v.union(v.literal("task"), v.literal("bug"), v.literal("spike")),
        action: v.string(),
        priority: v.optional(v.number()),
        description: v.optional(v.string()),
        files_exclusive: v.optional(v.array(v.string())),
        files_readonly: v.optional(v.array(v.string())),
        files_forbidden: v.optional(v.array(v.string())),
        verify: v.optional(v.array(v.string())),
        done_criteria: v.optional(v.array(v.string())),
        depends_on_index: v.optional(v.array(v.number())), // Index in this array
        execution_strategy: v.optional(v.string()),
        checkpoint_type: v.optional(v.string()),
      })
    ),
  },
  handler: async (ctx, args) => {
    const project = await ctx.db
      .query("projects")
      .withIndex("by_prefix", (q) => q.eq("prefix", args.project_prefix.toUpperCase()))
      .first();

    if (!project) {
      throw new Error(`Project ${args.project_prefix} not found`);
    }

    const createdIds: string[] = [];

    for (let i = 0; i < args.tasks.length; i++) {
      const task = args.tasks[i];

      // Generate task ID
      const count = await ctx.db.query("tasks").collect();
      const taskNum = count.filter((t) => t.project === project._id && t.type === task.type).length + 1;
      const taskId = `${project.prefix}-${task.type.toUpperCase()}-${String(taskNum).padStart(3, "0")}`;

      // Resolve depends_on from indices to actual IDs
      const dependsOn: string[] = [];
      if (task.depends_on_index) {
        for (const idx of task.depends_on_index) {
          if (idx < createdIds.length) {
            dependsOn.push(createdIds[idx]);
          }
        }
      }

      // Determine initial status
      const hasDeps = dependsOn.length > 0;
      const status = hasDeps ? "backlog" : "ready";

      await ctx.db.insert("tasks", {
        task_id: taskId,
        project: project._id,
        type: task.type,
        name: task.name,
        description: task.description,
        action: task.action,
        status,
        priority: task.priority || 3,
        files_exclusive: task.files_exclusive || [],
        files_readonly: task.files_readonly || [],
        files_forbidden: task.files_forbidden || [],
        verify: task.verify || [],
        done_criteria: task.done_criteria || [],
        depends_on: dependsOn,
        blocks: [],
        parent_id: args.epic_id,
        execution_strategy: task.execution_strategy,
        checkpoint_type: task.checkpoint_type,
        created_at: Date.now(),
        updated_at: Date.now(),
      });

      createdIds.push(taskId);
    }

    return {
      created: createdIds.length,
      task_ids: createdIds,
      epic_id: args.epic_id,
    };
  },
});
```

### Python Tool

```python
@mcp.tool()
def bulk_create_tasks(
    project: str,
    tasks: list[dict],
    epic_id: str | None = None,
) -> dict[str, Any]:
    """
    Create multiple tasks at once from /plan output.

    Args:
        project: Project prefix (e.g., "MP")
        tasks: List of task definitions with:
            - name: Task name
            - type: task, bug, or spike
            - action: Implementation instructions
            - priority: 1-4 (optional, default 3)
            - files_exclusive: Files to modify (optional)
            - files_readonly: Files to read only (optional)
            - files_forbidden: Files to avoid (optional)
            - verify: Verification commands (optional)
            - done_criteria: Completion checklist (optional)
            - depends_on_index: Indices of tasks in this list that must complete first (optional)
        epic_id: Parent epic ID (optional)

    Returns:
        List of created task IDs
    """
    return _convex_request("mutation", "bulkCreateTasks", {
        "project_prefix": project,
        "tasks": tasks,
        "epic_id": epic_id,
    })
```

---

## 3. get_parallel_groups

Analyze tasks under an epic and return groups that can run in parallel.

### Convex Query

```typescript
export const getParallelGroups = query({
  args: {
    epic_id: v.string(),
  },
  handler: async (ctx, args) => {
    // Get all tasks under this epic
    const tasks = await ctx.db
      .query("tasks")
      .withIndex("by_parent", (q) => q.eq("parent_id", args.epic_id))
      .collect();

    if (tasks.length === 0) {
      return { groups: [], conflicts: {} };
    }

    // Build file conflict map
    const fileOwners: Map<string, string[]> = new Map();
    for (const task of tasks) {
      for (const file of task.files_exclusive || []) {
        const owners = fileOwners.get(file) || [];
        owners.push(task.task_id);
        fileOwners.set(file, owners);
      }
    }

    // Find conflicts
    const conflicts: Record<string, string[]> = {};
    for (const [file, owners] of fileOwners.entries()) {
      if (owners.length > 1) {
        for (const owner of owners) {
          conflicts[owner] = conflicts[owner] || [];
          for (const other of owners) {
            if (other !== owner && !conflicts[owner].includes(other)) {
              conflicts[owner].push(other);
            }
          }
        }
      }
    }

    // Build dependency graph
    const dependsOn: Record<string, Set<string>> = {};
    for (const task of tasks) {
      dependsOn[task.task_id] = new Set(task.depends_on);
      // Add conflict dependencies (can't run together)
      for (const conflictId of conflicts[task.task_id] || []) {
        dependsOn[task.task_id].add(conflictId);
      }
    }

    // Topological sort into groups
    const groups: string[][] = [];
    const completed = new Set<string>();

    while (completed.size < tasks.length) {
      const group: string[] = [];

      for (const task of tasks) {
        if (completed.has(task.task_id)) continue;

        const deps = dependsOn[task.task_id];
        const allDepsComplete = [...deps].every((d) => completed.has(d));

        if (allDepsComplete) {
          group.push(task.task_id);
        }
      }

      if (group.length === 0) {
        // Circular dependency detected
        break;
      }

      groups.push(group);
      for (const id of group) {
        completed.add(id);
      }
    }

    return {
      groups,
      conflicts,
      total_tasks: tasks.length,
      parallelizable: groups.some((g) => g.length > 1),
    };
  },
});
```

### Python Tool

```python
@mcp.tool()
def get_parallel_groups(epic_id: str) -> dict[str, Any]:
    """
    Analyze tasks under an epic and return parallel execution groups.

    Groups are ordered by dependency - all tasks in group N can run
    in parallel, but group N+1 must wait for N to complete.

    Args:
        epic_id: Epic task ID

    Returns:
        - groups: [[task_ids in batch 1], [batch 2], ...]
        - conflicts: {task_id: [conflicting_task_ids]}
        - parallelizable: True if any group has multiple tasks
    """
    return _convex_request("query", "getParallelGroups", {"epic_id": epic_id})
```

---

## 4. search_tasks

Find tasks by keyword in name, description, or action.

### Convex Query

```typescript
export const searchTasks = query({
  args: {
    query: v.string(),
    project_prefix: v.optional(v.string()),
    include_done: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    const allTasks = await ctx.db.query("tasks").collect();
    const queryLower = args.query.toLowerCase();

    let filtered = allTasks.filter((t) => {
      const searchText = [
        t.task_id,
        t.name,
        t.description || "",
        t.action || "",
      ].join(" ").toLowerCase();

      return searchText.includes(queryLower);
    });

    // Filter by project
    if (args.project_prefix) {
      const project = await ctx.db
        .query("projects")
        .withIndex("by_prefix", (q) => q.eq("prefix", args.project_prefix!.toUpperCase()))
        .first();
      if (project) {
        filtered = filtered.filter((t) => t.project === project._id);
      }
    }

    // Filter out done unless requested
    if (!args.include_done) {
      filtered = filtered.filter((t) => t.status !== "done");
    }

    return {
      query: args.query,
      count: filtered.length,
      tasks: filtered.map((t) => ({
        id: t.task_id,
        name: t.name,
        status: t.status,
        priority: t.priority,
        parent_id: t.parent_id,
        match_preview: t.action?.substring(0, 100),
      })),
    };
  },
});
```

### Python Tool

```python
@mcp.tool()
def search_tasks(
    query: str,
    project: str | None = None,
    include_done: bool = False,
) -> dict[str, Any]:
    """
    Search tasks by keyword in name, description, or action.

    Args:
        query: Search keyword
        project: Optional project prefix filter
        include_done: Include completed tasks (default False)

    Returns:
        Matching tasks with preview of where keyword was found
    """
    return _convex_request("query", "searchTasks", {
        "query": query,
        "project_prefix": project,
        "include_done": include_done,
    })
```

---

## 5. archive_epic

Archive a completed epic with full summary in body.

### Convex Mutation

```typescript
export const archiveEpic = mutation({
  args: {
    epic_id: v.string(),
  },
  handler: async (ctx, args) => {
    // Get epic
    const epic = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.epic_id))
      .first();

    if (!epic || epic.type !== "epic") {
      throw new Error("Epic not found");
    }

    // Get all child tasks
    const children = await ctx.db
      .query("tasks")
      .withIndex("by_parent", (q) => q.eq("parent_id", args.epic_id))
      .collect();

    // Build archive summary
    const lines: string[] = [
      `# Archived Epic: ${epic.name}`,
      "",
      `**Original Description:** ${epic.description || "N/A"}`,
      `**Completed:** ${new Date().toISOString()}`,
      `**Tasks:** ${children.length}`,
      "",
      "## Tasks Summary",
      "",
    ];

    for (const task of children) {
      const status = task.status === "done" ? "✅" : "❌";
      lines.push(`### ${status} ${task.task_id}: ${task.name}`);

      // First 5 lines of action/description
      const desc = (task.action || task.description || "No description").split("\n").slice(0, 5).join("\n");
      lines.push(desc);
      lines.push("");
    }

    const archiveBody = lines.join("\n");

    // Update epic with archive
    await ctx.db.patch(epic._id, {
      status: "done",
      description: archiveBody,
      completed_at: Date.now(),
      summary: `Archived with ${children.length} tasks`,
      updated_at: Date.now(),
    });

    // Delete child tasks (they're now in the archive body)
    for (const child of children) {
      await ctx.db.delete(child._id);
    }

    return {
      archived: true,
      epic_id: args.epic_id,
      tasks_archived: children.length,
      archive_preview: archiveBody.substring(0, 500) + "...",
    };
  },
});
```

### Python Tool

```python
@mcp.tool()
def archive_epic(epic_id: str) -> dict[str, Any]:
    """
    Archive a completed epic with full content summary.

    The epic's body will contain:
    - Original description
    - All task names with status (done/not done)
    - First 5 lines of each task's description

    Child tasks are deleted after archiving into the epic body.

    Args:
        epic_id: Epic task ID to archive

    Returns:
        Archive confirmation with preview
    """
    return _convex_request("mutation", "archiveEpic", {"epic_id": epic_id})
```

---

## 6. link_worktree

Link a task to a git worktree for parallel execution tracking.

### Schema Addition

```typescript
// In schema.ts, add to tasks table:
worktree_path: v.optional(v.string()),
worktree_branch: v.optional(v.string()),
```

### Convex Mutation

```typescript
export const linkWorktree = mutation({
  args: {
    task_id: v.string(),
    worktree_path: v.string(),
    branch: v.string(),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.task_id))
      .first();

    if (!task) {
      throw new Error("Task not found");
    }

    await ctx.db.patch(task._id, {
      worktree_path: args.worktree_path,
      worktree_branch: args.branch,
      updated_at: Date.now(),
    });

    return {
      linked: true,
      task_id: args.task_id,
      worktree_path: args.worktree_path,
      branch: args.branch,
    };
  },
});

export const unlinkWorktree = mutation({
  args: {
    task_id: v.string(),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.task_id))
      .first();

    if (!task) {
      throw new Error("Task not found");
    }

    await ctx.db.patch(task._id, {
      worktree_path: undefined,
      worktree_branch: undefined,
      updated_at: Date.now(),
    });

    return { unlinked: true, task_id: args.task_id };
  },
});
```

### Python Tools

```python
@mcp.tool()
def link_worktree(
    task_id: str,
    worktree_path: str,
    branch: str,
) -> dict[str, Any]:
    """
    Link a task to a git worktree for parallel execution.

    Args:
        task_id: Task ID to link
        worktree_path: Absolute path to worktree
        branch: Branch name in the worktree

    Returns:
        Confirmation with linked details
    """
    return _convex_request("mutation", "linkWorktree", {
        "task_id": task_id,
        "worktree_path": worktree_path,
        "branch": branch,
    })


@mcp.tool()
def unlink_worktree(task_id: str) -> dict[str, Any]:
    """
    Remove worktree link from a task.

    Args:
        task_id: Task ID to unlink

    Returns:
        Confirmation
    """
    return _convex_request("mutation", "unlinkWorktree", {"task_id": task_id})
```

---

## Done Criteria

- [ ] Schema updated with worktree fields
- [ ] All 6 Convex functions added
- [ ] All Python MCP tools added
- [ ] Tests for each function
- [ ] README updated with new tools
