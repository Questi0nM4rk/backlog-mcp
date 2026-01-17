"""Tests for backlog_mcp.server module."""

from backlog_mcp.server import (
    _json_dumps,
    _json_loads,
    _row_to_task,
)


class TestJsonHelpers:
    """Tests for JSON helper functions."""

    def test_json_loads_valid_list(self) -> None:
        """_json_loads should parse valid JSON array."""
        result = _json_loads('["a", "b", "c"]')
        assert result == ["a", "b", "c"]

    def test_json_loads_none(self) -> None:
        """_json_loads should return None for None input."""
        result = _json_loads(None)
        assert result is None

    def test_json_loads_invalid(self) -> None:
        """_json_loads should return None for invalid JSON."""
        result = _json_loads("not json")
        assert result is None

    def test_json_loads_object_returns_none(self) -> None:
        """_json_loads should return None for JSON objects."""
        result = _json_loads('{"key": "value"}')
        assert result is None

    def test_json_dumps_list(self) -> None:
        """_json_dumps should serialize list to JSON."""
        result = _json_dumps(["a", "b", "c"])
        assert result == '["a", "b", "c"]'

    def test_json_dumps_none(self) -> None:
        """_json_dumps should return None for None input."""
        result = _json_dumps(None)
        assert result is None


class TestRowToTask:
    """Tests for _row_to_task function."""

    def test_basic_conversion(self) -> None:
        """_row_to_task should convert row to dict."""
        columns = ["task_id", "name", "status"]
        row = ("TST-001", "Test task", "ready")

        result = _row_to_task(row, columns)

        assert result["task_id"] == "TST-001"
        assert result["name"] == "Test task"
        assert result["status"] == "ready"

    def test_parses_json_fields(self) -> None:
        """_row_to_task should parse JSON array fields."""
        columns = ["task_id", "files_exclusive", "verify"]
        row = ("TST-001", '["file1.py", "file2.py"]', '["pytest"]')

        result = _row_to_task(row, columns)

        assert result["files_exclusive"] == ["file1.py", "file2.py"]
        assert result["verify"] == ["pytest"]

    def test_handles_none_json_fields(self) -> None:
        """_row_to_task should handle None in JSON fields."""
        columns = ["task_id", "files_exclusive"]
        row = ("TST-001", None)

        result = _row_to_task(row, columns)

        assert result["files_exclusive"] is None
