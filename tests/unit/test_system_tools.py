"""Unit tests for system utility tools."""

from datetime import UTC, datetime

from agno.run import RunContext

from src.agent.tools.system import get_current_datetime


def _context() -> RunContext:
    return RunContext(run_id="sys-test", session_id="tg:test:1", user_id="user-1")


class TestGetCurrentDatetime:
    """Tests for the get_current_datetime tool."""

    def test_returns_string(self):
        """Should return a string."""
        result = get_current_datetime(_context())
        assert isinstance(result, str)

    def test_returns_utc_and_local_lines(self):
        """Should return both a UTC line and a local (Europe/Madrid) line."""
        result = get_current_datetime(_context())
        lines = result.splitlines()
        assert len(lines) == 2
        utc_line, local_line = lines
        assert utc_line.startswith("UTC: ")
        assert local_line.startswith("Local (Europe/Madrid): ")

        utc_value = datetime.fromisoformat(utc_line.removeprefix("UTC: "))
        local_value = datetime.fromisoformat(
            local_line.removeprefix("Local (Europe/Madrid): ")
        )
        # Both are the same instant, just expressed in different offsets.
        assert utc_value == local_value

    def test_returns_current_time(self):
        """Should return a UTC time within a few seconds of now."""
        before = datetime.now(tz=UTC)
        result = get_current_datetime(_context())
        after = datetime.now(tz=UTC)

        utc_line = result.splitlines()[0].removeprefix("UTC: ")
        parsed = datetime.fromisoformat(utc_line)
        assert before <= parsed <= after

    def test_has_docstring(self):
        """The tool should have a docstring (used by Agno as tool description)."""
        assert get_current_datetime.__doc__ is not None
        assert "current date and time" in get_current_datetime.__doc__
