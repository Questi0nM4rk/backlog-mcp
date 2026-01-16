import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

/**
 * Backlog MCP Schema
 *
 * Design: Single-task loading to prevent scope creep.
 * AI only sees summaries via list_tasks(), full context via get_task().
 */
export default defineSchema({
  /**
   * Projects table - groups tasks by project
   */
  projects: defineTable({
    name: v.string(),
    prefix: v.string(), // e.g., "JC" for JaCore → JC-TASK-001
    description: v.optional(v.string()),
    created_at: v.string(),
  }).index("by_prefix", ["prefix"]),

  /**
   * Tasks table - main backlog items
   *
   * Single-task loading pattern:
   * - list_tasks() returns only: id, name, status, priority
   * - get_task() returns full context for ONE task
   */
  tasks: defineTable({
    // Identity
    project: v.id("projects"),
    task_id: v.string(), // PREFIX-TASK-001 format
    type: v.union(
      v.literal("task"),
      v.literal("bug"),
      v.literal("spike"),
      v.literal("epic")
    ),

    // Summary (returned by list_tasks)
    name: v.string(),
    status: v.union(
      v.literal("backlog"),
      v.literal("ready"),
      v.literal("in_progress"),
      v.literal("blocked"),
      v.literal("done")
    ),
    priority: v.number(), // 1=critical, 2=high, 3=medium, 4=low

    // Full context (only returned by get_task)
    description: v.optional(v.string()),
    files_exclusive: v.array(v.string()), // Only this task modifies
    files_readonly: v.array(v.string()), // Can read only
    files_forbidden: v.array(v.string()), // Must not touch
    action: v.string(), // What to do
    verify: v.array(v.string()), // How to verify
    done_criteria: v.array(v.string()), // Completion checklist

    // Dependencies
    depends_on: v.array(v.string()), // Task IDs that must complete first
    blocks: v.array(v.string()), // Task IDs waiting on this

    // Execution metadata
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

    // Parent relationship (for tasks under epics)
    parent_id: v.optional(v.string()), // Epic ID if this is a task

    // Blocker info (when status=blocked)
    blocker_reason: v.optional(v.string()),
    blocker_since: v.optional(v.string()),
    blocker_needs: v.optional(v.string()),

    // Completion info (when status=done)
    completed_at: v.optional(v.string()),
    summary: v.optional(v.string()),
    commits: v.array(v.string()),

    // Timestamps
    created_at: v.string(),
    updated_at: v.string(),
  })
    .index("by_project", ["project"])
    .index("by_status", ["status"])
    .index("by_project_status", ["project", "status"])
    .index("by_task_id", ["task_id"])
    .index("by_parent", ["parent_id"]),
});
