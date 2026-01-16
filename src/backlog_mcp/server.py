"""
Backlog MCP Server - Single-Task Loading for Claude Code

Connects to self-hosted Convex backend for task management.
Core principle: AI sees ONE task at a time to prevent scope creep.

Tools:
- list_tasks: Get task summaries (id, name, status only)
- get_task: Get full context for ONE task
- get_next_task: Get highest-priority ready task
- create_task: Create a new task
- update_task_status: Update task status
- complete_task: Mark done and unblock dependents
- get_backlog_summary: Dashboard view

Environment:
- CONVEX_URL: Convex backend URL (default: http://localhost:3210)
"""

import json
import logging
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Convex configuration
CONVEX_URL = os.environ.get("CONVEX_URL", "http://localhost:3210")

# Initialize FastMCP server
mcp = FastMCP(
    "backlog",
    instructions="""Backlog management for Claude Code with single-task loading.

IMPORTANT: This MCP enforces tunnel vision. Use list_tasks() for summaries,
then get_task() or get_next_task() for FULL context of ONE task at a time.

This prevents scope creep and ensures focused implementation.""",
)


def _convex_request(
    function_type: str, function_name: str, args: dict[str, Any]
) -> dict[str, Any]:
    """
    Make a request to Convex backend.

    Args:
        function_type: 'query' or 'mutation'
        function_name: Function name (e.g., 'listTasks')
        args: Function arguments

    Returns:
        Convex response data

    Raises:
        ConnectionError: If Convex is not available
    """
    url = f"{CONVEX_URL}/api/{function_type}"

    payload = json.dumps(
        {
            "path": f"functions:{function_name}",
            "args": args,
            "format": "json",
        }
    ).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

            if "value" in result:
                value = result["value"]
                return dict(value) if isinstance(value, dict) else value
            elif "errorMessage" in result:
                raise ValueError(result["errorMessage"])
            else:
                return dict(result)

    except URLError as e:
        raise ConnectionError(
            f"backlog-mcp cannot connect to Convex at {CONVEX_URL}\n"
            f"Run: codeagent start convex\n"
            f"Error: {e}"
        ) from e


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
        result = _convex_request(
            "mutation",
            "createProject",
            {
                "name": name,
                "prefix": prefix.upper(),
                "description": description,
            },
        )
        return {
            "created": True,
            "id": result["id"],
            "prefix": result["prefix"],
        }
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def list_projects() -> dict[str, Any]:
    """
    List all projects.

    Returns:
        List of projects with name and prefix
    """
    try:
        projects = _convex_request("query", "listProjects", {})
        return {
            "projects": projects,
            "count": len(projects),
        }
    except ConnectionError as e:
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
        args: dict[str, Any] = {"limit": limit}
        if project:
            args["project_prefix"] = project.upper()
        if status:
            args["status"] = status
        if task_type:
            args["type"] = task_type

        tasks = _convex_request("query", "listTasks", args)

        return {
            "tasks": tasks,
            "count": len(tasks),
            "note": "Summaries only. Use get_task(id) for full context.",
        }
    except ConnectionError as e:
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
        task = _convex_request("query", "getTask", {"task_id": task_id})

        if not task:
            return {"found": False, "error": f"Task '{task_id}' not found"}

        return {
            "found": True,
            "task": task,
        }
    except ConnectionError as e:
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
        args: dict[str, Any] = {}
        if project:
            args["project_prefix"] = project.upper()
        if task_type:
            args["type"] = task_type

        task = _convex_request("query", "getNextTask", args)

        if not task:
            return {
                "found": False,
                "message": "No ready tasks found",
            }

        return {
            "found": True,
            "task": task,
        }
    except ConnectionError as e:
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

    Returns:
        Created task ID and initial status
    """
    try:
        args: dict[str, Any] = {
            "project_prefix": project.upper(),
            "type": task_type,
            "name": name,
            "action": action,
            "priority": priority,
        }

        if description:
            args["description"] = description
        if files_exclusive:
            args["files_exclusive"] = files_exclusive
        if files_readonly:
            args["files_readonly"] = files_readonly
        if files_forbidden:
            args["files_forbidden"] = files_forbidden
        if verify:
            args["verify"] = verify
        if done_criteria:
            args["done_criteria"] = done_criteria
        if depends_on:
            args["depends_on"] = depends_on
        if parent_id:
            args["parent_id"] = parent_id
        if execution_strategy:
            args["execution_strategy"] = execution_strategy
        if checkpoint_type:
            args["checkpoint_type"] = checkpoint_type

        result = _convex_request("mutation", "createTask", args)

        return {
            "created": True,
            "id": result["id"],
            "status": result["status"],
        }
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
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
    try:
        args: dict[str, Any] = {
            "task_id": task_id,
            "status": status,
        }

        if status == "blocked":
            if blocker_reason:
                args["blocker_reason"] = blocker_reason
            if blocker_needs:
                args["blocker_needs"] = blocker_needs

        result = _convex_request("mutation", "updateTaskStatus", args)

        return result
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def complete_task(
    task_id: str,
    summary: str | None = None,
    commits: list[str] | None = None,
) -> dict[str, Any]:
    """
    Mark task as done and unblock dependent tasks.

    Args:
        task_id: Task ID to complete
        summary: Brief summary of what was done
        commits: List of commit hashes/messages

    Returns:
        Completion status and list of unblocked tasks
    """
    try:
        args: dict[str, Any] = {"task_id": task_id}

        if summary:
            args["summary"] = summary
        if commits:
            args["commits"] = commits

        result = _convex_request("mutation", "completeTask", args)

        return {
            "completed": True,
            "id": result["id"],
            "unblocked": result.get("unblocked", []),
        }
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
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
        result = _convex_request("mutation", "deleteTask", {"task_id": task_id})
        return result
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
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
        args: dict[str, Any] = {}
        if project:
            args["project_prefix"] = project.upper()

        summary = _convex_request("query", "getBacklogSummary", args)

        return {
            "summary": summary,
            "dashboard_url": "http://localhost:6791",
        }
    except ConnectionError as e:
        return {"error": str(e)}


def main() -> None:
    """Entry point for the Backlog MCP server."""
    logger.info(f"Starting Backlog MCP server, Convex URL: {CONVEX_URL}")
    mcp.run()


if __name__ == "__main__":
    main()
