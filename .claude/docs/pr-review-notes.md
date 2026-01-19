# PR #2 Review - libSQL Migration

## Overview

This document tracks all issues raised in PR #2 review by CodeRabbit and their resolution status.

## Issues Summary

### 1. Dependency Version Pinning (pyproject.toml, Line 10)
**Status**: ✅ RESOLVED

**Issue**: `libsql-experimental>=0.0.50` was too permissive for an experimental package.

**Fix Applied**: Pinned to `libsql-experimental>=0.0.50,<0.1.0` to prevent breaking updates.

**Commit**: 61ad297

---

### 2. Mypy Import-Untyped Error (server.py, Line 26)
**Status**: ✅ RESOLVED

**Issue**: `libsql_experimental` lacks type stubs, causing mypy failure.

**Fix Applied**: Added `# type: ignore[import-untyped]` comment to import.

**Commit**: 755f01c

---

### 3. Foreign Key Constraints Not Enforced (server.py, Line 64)
**Status**: ✅ RESOLVED

**Issue**: SQLite does not enforce FOREIGN KEY constraints by default, allowing orphaned tasks.

**Fix Applied**: Added `PRAGMA foreign_keys = ON` in `_init_schema()` before schema creation.

**Details**:
- Located in `_init_schema()` at line 64
- Executed before `executescript()` to enable enforcement
- Prevents orphaned tasks from being created

**Commit**: 755f01c

---

### 4. JSON Parsing Type Safety (server.py, Line 116)
**Status**: ✅ RESOLVED

**Issue**: `json.loads()` returns `Any`, requiring type casting.

**Fix Applied**: Explicit `isinstance(result, list)` check in `_json_loads()` provides type narrowing.

**Details**:
- Already had proper type checking before returning
- Pyright can infer the type through the isinstance guard
- No additional changes needed beyond existing implementation

---

### 5. Dependency Validation in create_task (server.py, Lines 492-513)
**Status**: ✅ RESOLVED

**Issue**: Code set `initial_status="ready"` when `incomplete == 0` even if some dependencies didn't exist.

**Fix Applied**: Added validation to check that all dependencies exist before marking as ready.

**Details**:
- Query counts found dependencies vs. provided dependencies
- Returns error if `found != len(depends_on)`
- Only marks ready when both conditions met: `found == len(depends_on)` AND `incomplete == 0`

**Commit**: 61ad297 to 119cf07

---

### 6. complete_task UPDATE Rowcount Check (server.py, Line 672)
**Status**: ✅ RESOLVED

**Issue**: UPDATE result wasn't checked, could return `completed: True` even when no row existed.

**Fix Applied**: Captured cursor and checked `cursor.rowcount` before unblocking.

**Details**:
- Line 662: `cursor = conn.execute(...)` captures result
- Line 672: `if cursor.rowcount == 0:` returns error immediately
- Prevents false success and unblocking of dependent tasks

**Commit**: 61ad297 to 119cf07

---

### 7. CLAUDE.md Documentation - Mypy → Pyright (Line 38)
**Status**: ✅ RESOLVED

**Issue**: Type check command still referenced mypy but project uses pyright.

**Fix Applied**: Updated command to `uv run pyright src/ tests/`

**Commit**: 8b2ab54

---

### 8. Pyright Import Suppression (server.py, Line 26)
**Status**: ✅ RESOLVED

**Issue**: Existing `# type: ignore[import-untyped]` is mypy-only syntax; pyright needs separate suppression.

**Fix Applied**: Added pyright-specific suppression: `# pyright: ignore[reportMissingModuleSource]`

**Line**: 26

**Details**:
```python
import libsql_experimental as libsql  # type: ignore[import-untyped]  # pyright: ignore[reportMissingModuleSource]
```

---

### 9. Pyright Type Hints - libsql.Connection (server.py, Lines 54, 62, 153)
**Status**: ✅ RESOLVED

**Issue**: Pyright reports `"Connection" is not a known attribute` because libsql_experimental has no stubs.

**Fix Applied**: Used string annotations for type hints with pyright suppression on definition lines.

**Details**:
- Line 54: `def _get_db() -> "libsql.Connection":  # pyright: ignore[reportAttributeAccessIssue]`
- Line 62: `def _init_schema(conn: "libsql.Connection") -> None:  # pyright: ignore[reportAttributeAccessIssue]`
- Line 153: `conn: "libsql.Connection", project_id: int, task_type: str  # pyright: ignore[reportAttributeAccessIssue]`

**Why String Annotations?**
- String annotations defer type evaluation
- Allows pyright to skip attribute resolution for problematic types
- Maintains type checking for non-untyped attributes

---

### 10. Pyright Exception Handling - libsql.IntegrityError (server.py, Lines 220, 560)
**Status**: ✅ RESOLVED

**Issue**: Pyright reports `"IntegrityError" is not a known attribute` in exception handlers.

**Fix Applied**: Added `# pyright: ignore[reportAttributeAccessIssue]` to both except clauses.

**Details**:
- Line 220: In `create_project()` - handles duplicate prefix
- Line 560: In `create_task()` - handles task ID race condition

**Code**:
```python
except libsql.IntegrityError:  # pyright: ignore[reportAttributeAccessIssue]
    # ...
```

---

## Performance Considerations

### _get_next_task_number() Implementation
**Status**: ✅ DOCUMENTED (not changed)

**Note**: The implementation fetches all task_id rows and iterates in Python (lines 163-177) rather than using SQL MAX aggregation. This was intentional per the docstring - it's a trade-off:
- **Trade-off Chosen**: Simpler Python iteration to avoid race conditions
- **Alternative Not Used**: SQL-based MAX extraction (suggested in review) would be more efficient for large datasets

The current approach:
1. Fetches all task IDs matching project/type
2. Parses numeric suffix after last hyphen
3. Returns max + 1

This is acceptable for typical backlog sizes (hundreds of tasks).

---

## Testing & Validation

All fixes have been validated with:

```bash
# Type checking
uv run pyright src/ tests/

# Linting
uv run ruff check .
uv run ruff format .

# Tests
uv run pytest tests/ -v
```

---

## Key Learnings

1. **Experimental Packages**: Require version pinning to avoid breaking changes
2. **Type Stubs**: When unavailable, use:
   - String annotations for type hints
   - Suppression comments for both mypy and pyright
   - Explicit isinstance checks for runtime type narrowing
3. **Database Constraints**: SQLite requires `PRAGMA foreign_keys = ON` to enforce referential integrity
4. **Transaction Safety**: Always check UPDATE/DELETE rowcounts before proceeding with dependent operations
5. **Tool Migration**: Update all documentation when swapping typing tools (mypy → pyright)

