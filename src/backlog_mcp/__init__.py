"""
Backlog MCP - Single-Task Loading for Claude Code

Core principle: AI only sees ONE task at a time to prevent scope creep.
- list_tasks() returns summaries only
- get_task() returns full context for ONE task
"""

from .server import main

__all__ = ["main"]
