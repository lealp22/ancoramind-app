"""Unit tests for system utility tools."""

from datetime import UTC, datetime

from src.agent.tools.system import get_current_datetime


class TestGetCurrentDatetime:
    """Tests for the get_current_datetime tool."""

    def test_returns_string(self):
        """Should return a string."""
        result = get_current_datetime()
        assert isinstance(result, str)

    def test_returns_iso_8601_format(self):
        """Should return ISO 8601 formatted datetime."""
        result = get_current_datetime()
        # ISO 8601 format: 2026-08-23T22:00:00+00:00 or 2026-08-23T22:00:00Z
        assert "T" in result
        # Should be parseable
        datetime.fromisoformat(result)

    def test_returns_current_time(self):
        """Should return a time within a few seconds of now."""
        before = datetime.now(tz=UTC)
        result = get_current_datetime()
        after = datetime.now(tz=UTC)

        parsed = datetime.fromisoformat(result)
        assert before <= parsed <= after

    def test_has_docstring(self):
        """The tool should have a docstring (used by Agno as tool description)."""
        assert get_current_datetime.__doc__ is not None
        assert "current date and time" in get_current_datetime.__doc__
