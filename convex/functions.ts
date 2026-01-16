import { v } from "convex/values";
import { mutation, query } from "./_generated/server";
import { Id } from "./_generated/dataModel";

/**
 * Backlog MCP Functions
 *
 * Core principle: Single-task loading prevents scope creep.
 * AI sees summaries only, requests full context for ONE task at a time.
 */

// ============================================
// Project Functions
// ============================================

/**
 * Create a new project
 */
export const createProject = mutation({
  args: {
    name: v.string(),
    prefix: v.string(),
    description: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    // Check if prefix already exists
    const existing = await ctx.db
      .query("projects")
      .withIndex("by_prefix", (q) => q.eq("prefix", args.prefix))
      .first();

    if (existing) {
      throw new Error(`Project with prefix "${args.prefix}" already exists`);
    }

    const projectId = await ctx.db.insert("projects", {
      name: args.name,
      prefix: args.prefix.toUpperCase(),
      description: args.description,
      created_at: new Date().toISOString(),
    });

    return { id: projectId, prefix: args.prefix.toUpperCase() };
  },
});

/**
 * List all projects
 */
export const listProjects = query({
  args: {},
  handler: async (ctx) => {
    const projects = await ctx.db.query("projects").collect();
    return projects.map((p) => ({
      id: p._id,
      name: p.name,
      prefix: p.prefix,
      description: p.description,
    }));
  },
});

/**
 * Get project by prefix
 */
export const getProjectByPrefix = query({
  args: { prefix: v.string() },
  handler: async (ctx, args) => {
    const project = await ctx.db
      .query("projects")
      .withIndex("by_prefix", (q) => q.eq("prefix", args.prefix.toUpperCase()))
      .first();

    if (!project) {
      return null;
    }

    return {
      id: project._id,
      name: project.name,
      prefix: project.prefix,
      description: project.description,
    };
  },
});

// ============================================
// Task Functions - SINGLE-TASK LOADING
// ============================================

/**
 * List tasks - SUMMARIES ONLY
 *
 * Returns minimal info to prevent scope creep.
 * AI must call get_task() for full context.
 */
export const listTasks = query({
  args: {
    project_prefix: v.optional(v.string()),
    status: v.optional(
      v.union(
        v.literal("backlog"),
        v.literal("ready"),
        v.literal("in_progress"),
        v.literal("blocked"),
        v.literal("done")
      )
    ),
    type: v.optional(
      v.union(
        v.literal("task"),
        v.literal("bug"),
        v.literal("spike"),
        v.literal("epic")
      )
    ),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    let tasksQuery = ctx.db.query("tasks");

    // Filter by status if provided
    if (args.status) {
      tasksQuery = tasksQuery.withIndex("by_status", (q) =>
        q.eq("status", args.status!)
      );
    }

    const tasks = await tasksQuery.collect();

    // Filter by project if provided
    let filtered = tasks;
    if (args.project_prefix) {
      const project = await ctx.db
        .query("projects")
        .withIndex("by_prefix", (q) =>
          q.eq("prefix", args.project_prefix!.toUpperCase())
        )
        .first();

      if (project) {
        filtered = tasks.filter((t) => t.project === project._id);
      } else {
        filtered = [];
      }
    }

    // Filter by type if provided
    if (args.type) {
      filtered = filtered.filter((t) => t.type === args.type);
    }

    // Sort by priority (1=critical first)
    filtered.sort((a, b) => a.priority - b.priority);

    // Apply limit
    if (args.limit && args.limit > 0) {
      filtered = filtered.slice(0, args.limit);
    }

    // Return SUMMARIES ONLY - no full context
    return filtered.map((t) => ({
      id: t.task_id,
      name: t.name,
      type: t.type,
      status: t.status,
      priority: t.priority,
      parent_id: t.parent_id,
      depends_on_count: t.depends_on.length,
      blocks_count: t.blocks.length,
    }));
  },
});

/**
 * Get task - FULL CONTEXT FOR ONE TASK
 *
 * This is the only way AI gets full task details.
 * Enforces single-task focus.
 */
export const getTask = query({
  args: { task_id: v.string() },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.task_id))
      .first();

    if (!task) {
      return null;
    }

    // Get project info
    const project = await ctx.db.get(task.project);

    // Return FULL CONTEXT for this ONE task
    return {
      id: task.task_id,
      type: task.type,
      project: project
        ? { name: project.name, prefix: project.prefix }
        : null,

      // Summary
      name: task.name,
      description: task.description,
      status: task.status,
      priority: task.priority,

      // Implementation context (the key data)
      files_exclusive: task.files_exclusive,
      files_readonly: task.files_readonly,
      files_forbidden: task.files_forbidden,
      action: task.action,
      verify: task.verify,
      done_criteria: task.done_criteria,

      // Dependencies
      depends_on: task.depends_on,
      blocks: task.blocks,
      parent_id: task.parent_id,

      // Execution
      execution_strategy: task.execution_strategy,
      checkpoint_type: task.checkpoint_type,

      // Blocker info (if blocked)
      blocker:
        task.status === "blocked"
          ? {
              reason: task.blocker_reason,
              since: task.blocker_since,
              needs: task.blocker_needs,
            }
          : null,

      // Completion (if done)
      completion:
        task.status === "done"
          ? {
              completed_at: task.completed_at,
              summary: task.summary,
              commits: task.commits,
            }
          : null,

      // Timestamps
      created_at: task.created_at,
      updated_at: task.updated_at,
    };
  },
});

/**
 * Get next task - HIGHEST PRIORITY READY TASK
 *
 * Returns full context for the most important ready task.
 * Use this for `/implement` without arguments.
 */
export const getNextTask = query({
  args: {
    project_prefix: v.optional(v.string()),
    type: v.optional(
      v.union(
        v.literal("task"),
        v.literal("bug"),
        v.literal("spike"),
        v.literal("epic")
      )
    ),
  },
  handler: async (ctx, args) => {
    // Get ready tasks
    const readyTasks = await ctx.db
      .query("tasks")
      .withIndex("by_status", (q) => q.eq("status", "ready"))
      .collect();

    if (readyTasks.length === 0) {
      return null;
    }

    let filtered = readyTasks;

    // Filter by project if provided
    if (args.project_prefix) {
      const project = await ctx.db
        .query("projects")
        .withIndex("by_prefix", (q) =>
          q.eq("prefix", args.project_prefix!.toUpperCase())
        )
        .first();

      if (project) {
        filtered = readyTasks.filter((t) => t.project === project._id);
      } else {
        return null;
      }
    }

    // Filter by type if provided
    if (args.type) {
      filtered = filtered.filter((t) => t.type === args.type);
    }

    if (filtered.length === 0) {
      return null;
    }

    // Priority order: bugs first (by severity), then tasks by priority
    filtered.sort((a, b) => {
      // Bugs with lower priority number come first
      if (a.type === "bug" && b.type !== "bug") return -1;
      if (a.type !== "bug" && b.type === "bug") return 1;
      return a.priority - b.priority;
    });

    const task = filtered[0];
    const project = await ctx.db.get(task.project);

    // Return FULL CONTEXT
    return {
      id: task.task_id,
      type: task.type,
      project: project
        ? { name: project.name, prefix: project.prefix }
        : null,
      name: task.name,
      description: task.description,
      status: task.status,
      priority: task.priority,
      files_exclusive: task.files_exclusive,
      files_readonly: task.files_readonly,
      files_forbidden: task.files_forbidden,
      action: task.action,
      verify: task.verify,
      done_criteria: task.done_criteria,
      depends_on: task.depends_on,
      blocks: task.blocks,
      parent_id: task.parent_id,
      execution_strategy: task.execution_strategy,
      checkpoint_type: task.checkpoint_type,
      created_at: task.created_at,
      updated_at: task.updated_at,
    };
  },
});

/**
 * Create task
 */
export const createTask = mutation({
  args: {
    project_prefix: v.string(),
    type: v.union(
      v.literal("task"),
      v.literal("bug"),
      v.literal("spike"),
      v.literal("epic")
    ),
    name: v.string(),
    description: v.optional(v.string()),
    priority: v.number(),
    files_exclusive: v.optional(v.array(v.string())),
    files_readonly: v.optional(v.array(v.string())),
    files_forbidden: v.optional(v.array(v.string())),
    action: v.string(),
    verify: v.optional(v.array(v.string())),
    done_criteria: v.optional(v.array(v.string())),
    depends_on: v.optional(v.array(v.string())),
    parent_id: v.optional(v.string()),
    execution_strategy: v.optional(
      v.union(v.literal("A"), v.literal("B"), v.literal("C"))
    ),
    checkpoint_type: v.optional(
      v.union(
        v.literal("auto"),
        v.literal("human-verify"),
        v.literal("decision")
      )
    ),
  },
  handler: async (ctx, args) => {
    // Get project
    const project = await ctx.db
      .query("projects")
      .withIndex("by_prefix", (q) =>
        q.eq("prefix", args.project_prefix.toUpperCase())
      )
      .first();

    if (!project) {
      throw new Error(`Project with prefix "${args.project_prefix}" not found`);
    }

    // Generate task ID
    const typeAbbrev = args.type.toUpperCase();
    const existingTasks = await ctx.db
      .query("tasks")
      .withIndex("by_project", (q) => q.eq("project", project._id))
      .collect();

    const sameTypeTasks = existingTasks.filter((t) => t.type === args.type);
    const nextNum = sameTypeTasks.length + 1;
    const taskId = `${project.prefix}-${typeAbbrev}-${String(nextNum).padStart(3, "0")}`;

    // Determine initial status
    const hasDependencies = args.depends_on && args.depends_on.length > 0;
    const initialStatus = hasDependencies ? "backlog" : "ready";

    const now = new Date().toISOString();

    await ctx.db.insert("tasks", {
      project: project._id,
      task_id: taskId,
      type: args.type,
      name: args.name,
      description: args.description,
      status: initialStatus,
      priority: args.priority,
      files_exclusive: args.files_exclusive || [],
      files_readonly: args.files_readonly || [],
      files_forbidden: args.files_forbidden || [],
      action: args.action,
      verify: args.verify || [],
      done_criteria: args.done_criteria || [],
      depends_on: args.depends_on || [],
      blocks: [],
      parent_id: args.parent_id,
      execution_strategy: args.execution_strategy,
      checkpoint_type: args.checkpoint_type || "auto",
      commits: [],
      created_at: now,
      updated_at: now,
    });

    // Update blocks field of dependencies
    if (args.depends_on) {
      for (const depId of args.depends_on) {
        const depTask = await ctx.db
          .query("tasks")
          .withIndex("by_task_id", (q) => q.eq("task_id", depId))
          .first();

        if (depTask) {
          const newBlocks = [...depTask.blocks, taskId];
          await ctx.db.patch(depTask._id, { blocks: newBlocks });
        }
      }
    }

    return { id: taskId, status: initialStatus };
  },
});

/**
 * Update task status
 */
export const updateTaskStatus = mutation({
  args: {
    task_id: v.string(),
    status: v.union(
      v.literal("backlog"),
      v.literal("ready"),
      v.literal("in_progress"),
      v.literal("blocked"),
      v.literal("done")
    ),
    blocker_reason: v.optional(v.string()),
    blocker_needs: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.task_id))
      .first();

    if (!task) {
      throw new Error(`Task "${args.task_id}" not found`);
    }

    const updates: Record<string, unknown> = {
      status: args.status,
      updated_at: new Date().toISOString(),
    };

    // Handle blocked status
    if (args.status === "blocked") {
      updates.blocker_reason = args.blocker_reason || "Unknown";
      updates.blocker_since = new Date().toISOString();
      updates.blocker_needs = args.blocker_needs;
    } else {
      // Clear blocker info if not blocked
      updates.blocker_reason = undefined;
      updates.blocker_since = undefined;
      updates.blocker_needs = undefined;
    }

    await ctx.db.patch(task._id, updates);

    return { ok: true, id: args.task_id, status: args.status };
  },
});

/**
 * Complete task - marks done and unblocks dependents
 */
export const completeTask = mutation({
  args: {
    task_id: v.string(),
    summary: v.optional(v.string()),
    commits: v.optional(v.array(v.string())),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.task_id))
      .first();

    if (!task) {
      throw new Error(`Task "${args.task_id}" not found`);
    }

    const now = new Date().toISOString();

    // Mark task as done
    await ctx.db.patch(task._id, {
      status: "done",
      completed_at: now,
      summary: args.summary,
      commits: args.commits || [],
      updated_at: now,
    });

    // Check and unblock dependent tasks
    const unblocked: string[] = [];

    for (const blockedId of task.blocks) {
      const blockedTask = await ctx.db
        .query("tasks")
        .withIndex("by_task_id", (q) => q.eq("task_id", blockedId))
        .first();

      if (blockedTask && blockedTask.status === "backlog") {
        // Check if all dependencies are now done
        let allDepsDone = true;
        for (const depId of blockedTask.depends_on) {
          if (depId === args.task_id) continue; // Skip the just-completed task

          const depTask = await ctx.db
            .query("tasks")
            .withIndex("by_task_id", (q) => q.eq("task_id", depId))
            .first();

          if (depTask && depTask.status !== "done") {
            allDepsDone = false;
            break;
          }
        }

        if (allDepsDone) {
          await ctx.db.patch(blockedTask._id, {
            status: "ready",
            updated_at: now,
          });
          unblocked.push(blockedId);
        }
      }
    }

    return {
      ok: true,
      id: args.task_id,
      unblocked: unblocked,
    };
  },
});

/**
 * Delete task
 */
export const deleteTask = mutation({
  args: { task_id: v.string() },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("task_id", args.task_id))
      .first();

    if (!task) {
      throw new Error(`Task "${args.task_id}" not found`);
    }

    // Remove from blocks arrays of dependencies
    for (const depId of task.depends_on) {
      const depTask = await ctx.db
        .query("tasks")
        .withIndex("by_task_id", (q) => q.eq("task_id", depId))
        .first();

      if (depTask) {
        const newBlocks = depTask.blocks.filter((b) => b !== args.task_id);
        await ctx.db.patch(depTask._id, { blocks: newBlocks });
      }
    }

    await ctx.db.delete(task._id);

    return { ok: true, id: args.task_id };
  },
});

// ============================================
// Backlog Summary Functions
// ============================================

/**
 * Get backlog summary - for dashboard and /backlog command
 */
export const getBacklogSummary = query({
  args: { project_prefix: v.optional(v.string()) },
  handler: async (ctx, args) => {
    let tasks = await ctx.db.query("tasks").collect();

    // Filter by project if provided
    if (args.project_prefix) {
      const project = await ctx.db
        .query("projects")
        .withIndex("by_prefix", (q) =>
          q.eq("prefix", args.project_prefix!.toUpperCase())
        )
        .first();

      if (project) {
        tasks = tasks.filter((t) => t.project === project._id);
      } else {
        tasks = [];
      }
    }

    // Count by status and type
    const summary = {
      total: tasks.length,
      by_status: {
        backlog: 0,
        ready: 0,
        in_progress: 0,
        blocked: 0,
        done: 0,
      },
      by_type: {
        epic: 0,
        task: 0,
        bug: 0,
        spike: 0,
      },
      in_progress: [] as { id: string; name: string; type: string }[],
      ready: [] as { id: string; name: string; type: string; priority: number }[],
      blocked: [] as { id: string; name: string; reason: string }[],
    };

    for (const task of tasks) {
      summary.by_status[task.status]++;
      summary.by_type[task.type]++;

      if (task.status === "in_progress") {
        summary.in_progress.push({
          id: task.task_id,
          name: task.name,
          type: task.type,
        });
      } else if (task.status === "ready") {
        summary.ready.push({
          id: task.task_id,
          name: task.name,
          type: task.type,
          priority: task.priority,
        });
      } else if (task.status === "blocked") {
        summary.blocked.push({
          id: task.task_id,
          name: task.name,
          reason: task.blocker_reason || "Unknown",
        });
      }
    }

    // Sort ready by priority
    summary.ready.sort((a, b) => a.priority - b.priority);

    return summary;
  },
});
