"""System utility tools for the AncoraMind agent.

Plain Python functions — Agno auto-converts them to tools from type hints and docstrings.
"""

from datetime import datetime, timezone


def get_current_datetime() -> str:
    """Return the current date and time in ISO 8601 format.

    Use this tool when the user asks about the current time, date,
    or needs to know "now" for any time-sensitive operation.

    Returns:
        ISO 8601 formatted datetime string with timezone (UTC).
    """
    return datetime.now(tz=timezone.utc).isoformat()