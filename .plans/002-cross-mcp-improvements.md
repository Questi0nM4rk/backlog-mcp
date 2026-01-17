# Plan: Cross-MCP Improvements for backlog-mcp

From review session (Jan 2026).

## Improvements

### 1. Replace print() with logging

**Why:** Proper logging allows filtering, levels, and doesn't interfere with MCP stdout.

**Files:** `src/backlog_mcp/server.py`

**Change:**
```python
# Replace any remaining print() with logger.info/debug/error
```

### 2. Add Integration Tests

**Why:** Current tests are minimal. Need to test actual Convex interactions.

**Files:** `tests/test_integration.py` (new)

**Tests needed:**
- Create project → create task → get task → complete task
- Dependency unblocking flow
- Epic with children workflow

### 3. Add Convex Health Check Tool

**Why:** Currently errors are cryptic when Convex is down.

**Add tool:**
```python
@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check Convex backend connectivity."""
    try:
        _convex_request("query", "listProjects", {})
        return {"status": "healthy", "convex_url": CONVEX_URL}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## Done Criteria

- [ ] All print() replaced with logger
- [ ] Integration tests added
- [ ] Health check tool added
