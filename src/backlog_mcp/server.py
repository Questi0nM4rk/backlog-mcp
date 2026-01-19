"""
Backlog MCP Server - Single-Task Loading for Claude Code

Uses libSQL for local task storage.
Core principle: AI sees ONE task at a time to prevent scope creep.

Tools:
- list_tasks: Get task summaries (id, name, status only)
- get_task: Get full context for ONE task
- get_next_task: Get highest-priority ready task
- create_task: Create a new task
- update_task_status: Update task status
- complete_task: Mark done and unblock dependents
- get_backlog_summary: Dashboard view

Database: ~/.codeagent/codeagent.db
"""

import json
import logging
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

import libsql_experimental as libsql  # type: ignore[import-untyped]  # pyright: ignore[reportMissingModuleSource]
from mcp.server.fastmcp import FastMCP

# Valid values for task_type, status, and model
VALID_TASK_TYPES = frozenset({"task", "bug", "spike", "epic"})
VALID_STATUSES = frozenset({"backlog", "ready", "in_progress", "blocked", "done"})
VALID_MODELS = frozenset({"haiku", "sonnet", "opus"})

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
CODEAGENT_DIR = Path.home() / ".codeagent"
DB_PATH = CODEAGENT_DIR / "codeagent.db"

# Initialize FastMCP server
mcp = FastMCP(
    "backlog",
    instructions="""Backlog management for Claude Code with single-task loading.

IMPORTANT: This MCP enforces tunnel vision. Use list_tasks() for summaries,
then get_task() or get_next_task() for FULL context of ONE task at a time.

This prevents scope creep and ensures focused implementation.""",
)


def _get_db() -> "libsql.Connection":  # pyright: ignore[reportAttributeAccessIssue]
    """Get database connection, creating schema if needed."""
    CODEAGENT_DIR.mkdir(parents=True, exist_ok=True)
    conn = libsql.connect(str(DB_PATH))  # pyright: ignore[reportAttributeAccessIssue]
    _init_schema(conn)
    return conn


def _init_schema(conn: "libsql.Connection") -> None:  # pyright: ignore[reportAttributeAccessIssue]
    """Initialize database schema."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
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
            files_exclusive TEXT,
            files_readonly TEXT,
            files_forbidden TEXT,
            verify TEXT,
            done_criteria TEXT,
            depends_on TEXT,
            parent_id TEXT,
            execution_strategy TEXT,
            checkpoint_type TEXT,
            suggested_model TEXT,
            resolved_by_episode TEXT,
            blocker_reason TEXT,
            blocker_needs TEXT,
            summary TEXT,
            commits TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
    """)
    conn.commit()


def _json_loads(val: str | None) -> list[str] | None:
    """Parse JSON array or return None."""
    if val is None:
        return None
    try:
        result = json.loads(val)
        if isinstance(result, list):
            return result
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _json_dumps(val: list[str] | None) -> str | None:
    """Serialize list to JSON or return None."""
    if val is None:
        return None
    return json.dumps(val)


def _row_to_task(row: tuple[Any, ...], columns: list[str]) -> dict[str, Any]:
    """Convert database row to task dict with JSON parsing."""
    task = dict(zip(columns, row, strict=False))

    # Parse JSON fields
    json_fields = [
        "files_exclusive",
        "files_readonly",
        "files_forbidden",
        "verify",
        "done_criteria",
        "depends_on",
        "commits",
    ]
    for field in json_fields:
        if field in task:
            task[field] = _json_loads(task[field])

    return task


def _get_next_task_number(
    conn: "libsql.Connection",  # pyright: ignore[reportAttributeAccessIssue]
    project_id: int,
    task_type: str,
) -> int:
    """Get the next task number for a project/type combo.

    Uses MAX to find highest existing number, avoiding race conditions
    that COUNT(*) would cause with concurrent inserts.

    Parses numeric suffix after the last hyphen in task_id to handle
    numbers >= 1000 correctly (not limited to 3-digit extraction).
    """
    cursor = conn.execute(
        "SELECT task_id FROM tasks WHERE project_id = ? AND type = ?",
        (project_id, task_type),
    )
    max_num = 0
    for (task_id,) in cursor.fetchall():
        # task_id format: PREFIX-TYPE-NNN (e.g., JC-TASK-001, JC-TASK-1234)
        parts = task_id.rsplit("-", 1)
        if len(parts) == 2:
            try:
                num = int(parts[1])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return max_num + 1


# ============================================
# Project Tools
# ============================================


@mcp.tool()
def create_project(
    name: str,
    prefix: str,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Create a new project for backlog management.

    Args:
        name: Project name (e.g., "JaCore")
        prefix: ID prefix (e.g., "JC" -> JC-TASK-001)
        description: Optional project description

    Returns:
        Created project with ID and prefix
    """
    try:
        with closing(_get_db()) as conn:
            prefix_upper = prefix.upper()

            cursor = conn.execute(
                """
                INSERT INTO projects (name, prefix, description)
                VALUES (?, ?, ?)
                """,
                (name, prefix_upper, description),
            )
            conn.commit()

            return {
                "created": True,
                "id": cursor.lastrowid,
                "prefix": prefix_upper,
            }
    except libsql.IntegrityError:  # pyright: ignore[reportAttributeAccessIssue]
        return {"error": f"Project with prefix '{prefix}' already exists"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def list_projects() -> dict[str, Any]:
    """
    List all projects.

    Returns:
        List of projects with name and prefix
    """
    try:
        with closing(_get_db()) as conn:
            cursor = conn.execute(
                "SELECT id, name, prefix, description, created_at FROM projects ORDER BY name"
            )
            columns = ["id", "name", "prefix", "description", "created_at"]
            projects = [
                dict(zip(columns, row, strict=False)) for row in cursor.fetchall()
            ]

            return {
                "projects": projects,
                "count": len(projects),
            }
    except Exception as e:
        return {"error": str(e)}


# ============================================
# Task Tools - SINGLE-TASK LOADING
# ============================================


@mcp.tool()
def list_tasks(
    project: str | None = None,
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    List task SUMMARIES only - prevents scope creep.

    Returns minimal info: id, name, status, priority.
    Use get_task() for full context of ONE task.

    Args:
        project: Filter by project prefix (e.g., "JC")
        status: Filter by status (backlog, ready, in_progress, blocked, done)
        task_type: Filter by type (task, bug, spike, epic)
        limit: Maximum results (default 20)

    Returns:
        List of task summaries (NOT full context)
    """
    try:
        with closing(_get_db()) as conn:
            query = """
                SELECT t.task_id, t.name, t.status, t.priority, t.type, p.prefix
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE 1=1
            """
            params: list[Any] = []

            if project:
                query += " AND p.prefix = ?"
                params.append(project.upper())
            if status:
                query += " AND t.status = ?"
                params.append(status)
            if task_type:
                query += " AND t.type = ?"
                params.append(task_type)

            query += " ORDER BY t.priority ASC, t.created_at ASC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            columns = ["task_id", "name", "status", "priority", "type", "project"]
            tasks = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

            return {
                "tasks": tasks,
                "count": len(tasks),
                "note": "Summaries only. Use get_task(id) for full context.",
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_task(task_id: str) -> dict[str, Any]:
    """
    Get FULL context for ONE task - enforces single-task focus.

    Returns complete implementation details:
    - Files (exclusive, readonly, forbidden)
    - Action instructions
    - Verification steps
    - Done criteria

    Args:
        task_id: Task ID (e.g., "JC-TASK-001")

    Returns:
        Full task context for implementation
    """
    try:
        with closing(_get_db()) as conn:
            cursor = conn.execute(
                """
                SELECT t.*, p.prefix, p.name as project_name
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE t.task_id = ?
                """,
                (task_id,),
            )

            row = cursor.fetchone()
            if not row:
                return {"found": False, "error": f"Task '{task_id}' not found"}

            # Get column names from cursor description
            columns = [desc[0] for desc in cursor.description]
            task = _row_to_task(row, columns)

            return {
                "found": True,
                "task": task,
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_next_task(
    project: str | None = None,
    task_type: str | None = None,
) -> dict[str, Any]:
    """
    Get highest-priority READY task with full context.

    Use this for /implement without arguments.
    Returns ONE task ready for work.

    Args:
        project: Filter by project prefix
        task_type: Filter by type (task, bug, spike, epic)

    Returns:
        Full context for the highest-priority ready task
    """
    try:
        with closing(_get_db()) as conn:
            query = """
                SELECT t.*, p.prefix, p.name as project_name
                FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE t.status = 'ready'
            """
            params: list[Any] = []

            if project:
                query += " AND p.prefix = ?"
                params.append(project.upper())
            if task_type:
                query += " AND t.type = ?"
                params.append(task_type)

            query += " ORDER BY t.priority ASC, t.created_at ASC LIMIT 1"

            cursor = conn.execute(query, params)
            row = cursor.fetchone()

            if not row:
                return {
                    "found": False,
                    "message": "No ready tasks found",
                }

            columns = [desc[0] for desc in cursor.description]
            task = _row_to_task(row, columns)

            return {
                "found": True,
                "task": task,
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def create_task(
    project: str,
    task_type: str,
    name: str,
    action: str,
    priority: int = 3,
    description: str | None = None,
    files_exclusive: list[str] | None = None,
    files_readonly: list[str] | None = None,
    files_forbidden: list[str] | None = None,
    verify: list[str] | None = None,
    done_criteria: list[str] | None = None,
    depends_on: list[str] | None = None,
    parent_id: str | None = None,
    execution_strategy: str | None = None,
    checkpoint_type: str | None = None,
    suggested_model: str | None = None,
) -> dict[str, Any]:
    """
    Create a new task in the backlog.

    Args:
        project: Project prefix (e.g., "JC")
        task_type: Type (task, bug, spike, epic)
        name: Task name
        action: Implementation instructions
        priority: 1=critical, 2=high, 3=medium, 4=low (default 3)
        description: Optional longer description
        files_exclusive: Files only this task modifies
        files_readonly: Files this task can only read
        files_forbidden: Files this task must not touch
        verify: Verification commands/checks
        done_criteria: Completion checklist items
        depends_on: Task IDs that must complete first
        parent_id: Parent epic ID (for tasks under epics)
        execution_strategy: A (auto), B (human-verify), C (decision)
        checkpoint_type: auto, human-verify, decision
        suggested_model: Recommended model (haiku, sonnet, opus) based on task complexity

    Returns:
        Created task ID and initial status
    """
    # Validate task_type
    task_type_lower = task_type.lower()
    if task_type_lower not in VALID_TASK_TYPES:
        return {
            "error": f"Invalid task_type '{task_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_TASK_TYPES))}"
        }

    # Validate suggested_model if provided
    model_lower = suggested_model.lower() if suggested_model else None
    if model_lower and model_lower not in VALID_MODELS:
        return {
            "error": f"Invalid suggested_model '{suggested_model}'. "
            f"Must be one of: {', '.join(sorted(VALID_MODELS))}"
        }

    try:
        with closing(_get_db()) as conn:
            prefix_upper = project.upper()

            # Get project ID
            cursor = conn.execute(
                "SELECT id FROM projects WHERE prefix = ?",
                (prefix_upper,),
            )
            row = cursor.fetchone()
            if not row:
                return {"error": f"Project '{prefix_upper}' not found"}
            project_id: int = row[0]

            # Determine initial status
            initial_status = "backlog"
            if depends_on:
                # Check if all dependencies exist and are done
                placeholders = ",".join("?" * len(depends_on))
                cursor = conn.execute(
                    f"""
                    SELECT
                        COUNT(*) AS found,
                        SUM(CASE WHEN status != 'done' THEN 1 ELSE 0 END) AS incomplete
                    FROM tasks
                    WHERE task_id IN ({placeholders})
                    """,
                    depends_on,
                )
                row = cursor.fetchone()
                found: int = row[0] if row else 0
                incomplete: int = row[1] if row and row[1] is not None else 0
                if found != len(depends_on):
                    return {"error": "One or more dependencies not found"}
                if incomplete == 0:
                    initial_status = "ready"
            else:
                initial_status = "ready"

            # Generate task ID and insert with retry for race conditions
            max_attempts = 3
            for attempt in range(max_attempts):
                task_num = _get_next_task_number(conn, project_id, task_type_lower)
                task_id = f"{prefix_upper}-{task_type_lower.upper()}-{task_num:03d}"

                try:
                    cursor = conn.execute(
                        """
                        INSERT INTO tasks (
                            project_id, task_id, type, name, status, priority,
                            description, action, files_exclusive, files_readonly,
                            files_forbidden, verify, done_criteria, depends_on,
                            parent_id, execution_strategy, checkpoint_type, suggested_model
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            task_id,
                            task_type_lower,
                            name,
                            initial_status,
                            priority,
                            description,
                            action,
                            _json_dumps(files_exclusive),
                            _json_dumps(files_readonly),
                            _json_dumps(files_forbidden),
                            _json_dumps(verify),
                            _json_dumps(done_criteria),
                            _json_dumps(depends_on),
                            parent_id,
                            execution_strategy,
                            checkpoint_type,
                            model_lower,
                        ),
                    )
                    conn.commit()

                    return {
                        "created": True,
                        "id": task_id,
                        "status": initial_status,
                        "suggested_model": model_lower,
                    }
                except libsql.IntegrityError:  # pyright: ignore[reportAttributeAccessIssue]
                    # Task ID collision from race condition, retry
                    if attempt == max_attempts - 1:
                        raise
                    continue

            # Should not reach here, but handle gracefully
            return {"error": "Failed to create task after multiple attempts"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def update_task_status(
    task_id: str,
    status: str,
    blocker_reason: str | None = None,
    blocker_needs: str | None = None,
) -> dict[str, Any]:
    """
    Update task status.

    Args:
        task_id: Task ID to update
        status: New status (backlog, ready, in_progress, blocked, done)
        blocker_reason: Reason if setting to blocked
        blocker_needs: What's needed to unblock

    Returns:
        Update confirmation
    """
    # Validate status
    if status not in VALID_STATUSES:
        return {
            "updated": False,
            "error": f"Invalid status '{status}'. "
            f"Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        }

    try:
        with closing(_get_db()) as conn:
            now = datetime.now().isoformat()

            if status == "blocked":
                cursor = conn.execute(
                    """
                    UPDATE tasks SET
                        status = ?, blocker_reason = ?, blocker_needs = ?,
                        updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status, blocker_reason, blocker_needs, now, task_id),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE tasks SET
                        status = ?, blocker_reason = NULL, blocker_needs = NULL,
                        updated_at = ?
                    WHERE task_id = ?
                    """,
                    (status, now, task_id),
                )

            if cursor.rowcount == 0:
                return {"updated": False, "error": f"Task '{task_id}' not found"}

            conn.commit()

            return {
                "updated": True,
                "id": task_id,
                "status": status,
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def complete_task(
    task_id: str,
    summary: str | None = None,
    commits: list[str] | None = None,
    resolved_by_episode: str | None = None,
) -> dict[str, Any]:
    """
    Mark task as done and unblock dependent tasks.

    Args:
        task_id: Task ID to complete
        summary: Brief summary of what was done
        commits: List of commit hashes/messages
        resolved_by_episode: Episode ID from reflection-mcp that helped resolve this task

    Returns:
        Completion status and list of unblocked tasks
    """
    try:
        with closing(_get_db()) as conn:
            now = datetime.now().isoformat()

            # Update the task
            cursor = conn.execute(
                """
                UPDATE tasks SET
                    status = 'done', summary = ?, commits = ?,
                    resolved_by_episode = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (summary, _json_dumps(commits), resolved_by_episode, now, task_id),
            )

            if cursor.rowcount == 0:
                return {"completed": False, "error": f"Task '{task_id}' not found"}

            # Find and unblock dependent tasks
            cursor = conn.execute(
                """
                SELECT task_id, depends_on FROM tasks
                WHERE depends_on LIKE ? AND status = 'backlog'
                """,
                (f'%"{task_id}"%',),
            )

            unblocked: list[str] = []
            for row in cursor.fetchall():
                dep_task_id, depends_on_json = row
                deps = _json_loads(depends_on_json) or []

                if task_id in deps:
                    # Check if all dependencies are now done
                    remaining = [d for d in deps if d != task_id]
                    if remaining:
                        placeholders = ",".join("?" * len(remaining))
                        check = conn.execute(
                            f"""
                            SELECT COUNT(*) FROM tasks
                            WHERE task_id IN ({placeholders}) AND status != 'done'
                            """,
                            remaining,
                        )
                        check_row = check.fetchone()
                        incomplete: int = check_row[0] if check_row else 0
                    else:
                        incomplete = 0

                    if incomplete == 0:
                        conn.execute(
                            "UPDATE tasks SET status = 'ready', updated_at = ? WHERE task_id = ?",
                            (now, dep_task_id),
                        )
                        unblocked.append(dep_task_id)

            conn.commit()

            return {
                "completed": True,
                "id": task_id,
                "resolved_by_episode": resolved_by_episode,
                "unblocked": unblocked,
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def delete_task(task_id: str) -> dict[str, Any]:
    """
    Delete a task from the backlog.

    Args:
        task_id: Task ID to delete

    Returns:
        Deletion confirmation
    """
    try:
        with closing(_get_db()) as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE task_id = ?",
                (task_id,),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return {"deleted": False, "error": f"Task '{task_id}' not found"}

            return {"deleted": True, "id": task_id}
    except Exception as e:
        return {"error": str(e)}


# ============================================
# Summary Tools
# ============================================


@mcp.tool()
def get_backlog_summary(project: str | None = None) -> dict[str, Any]:
    """
    Get backlog overview for dashboard view.

    Returns counts by status/type and lists of active items.

    Args:
        project: Filter by project prefix

    Returns:
        Summary with counts and highlighted items
    """
    try:
        with closing(_get_db()) as conn:
            # Build base query conditions
            base_condition = ""
            params: list[Any] = []
            if project:
                base_condition = "WHERE p.prefix = ?"
                params = [project.upper()]

            # Count by status
            cursor = conn.execute(
                f"""
                SELECT t.status, COUNT(*) FROM tasks t
                JOIN projects p ON t.project_id = p.id
                {base_condition}
                GROUP BY t.status
                """,
                params,
            )
            by_status = dict(cursor.fetchall())

            # Count by type
            cursor = conn.execute(
                f"""
                SELECT t.type, COUNT(*) FROM tasks t
                JOIN projects p ON t.project_id = p.id
                {base_condition}
                GROUP BY t.type
                """,
                params,
            )
            by_type = dict(cursor.fetchall())

            # Get in-progress tasks
            cursor = conn.execute(
                f"""
                SELECT t.task_id, t.name, t.priority FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE t.status = 'in_progress'
                {"AND p.prefix = ?" if project else ""}
                ORDER BY t.priority ASC
                """,
                params,
            )
            in_progress = [
                {"task_id": row[0], "name": row[1], "priority": row[2]}
                for row in cursor.fetchall()
            ]

            # Get blocked tasks
            cursor = conn.execute(
                f"""
                SELECT t.task_id, t.name, t.blocker_reason FROM tasks t
                JOIN projects p ON t.project_id = p.id
                WHERE t.status = 'blocked'
                {"AND p.prefix = ?" if project else ""}
                """,
                params,
            )
            blocked = [
                {"task_id": row[0], "name": row[1], "reason": row[2]}
                for row in cursor.fetchall()
            ]

            return {
                "summary": {
                    "by_status": by_status,
                    "by_type": by_type,
                    "in_progress": in_progress,
                    "blocked": blocked,
                    "total": sum(by_status.values()),
                },
            }
    except Exception as e:
        return {"error": str(e)}


def main() -> None:
    """Entry point for the Backlog MCP server."""
    logger.info("Starting Backlog MCP server, database: %s", DB_PATH)
    mcp.run()


if __name__ == "__main__":
    main()
