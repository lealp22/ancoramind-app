"""System utility tools for the AncoraMind agent.

Plain Python functions — Agno auto-converts them to tools from type hints and docstrings.
"""

from datetime import UTC, datetime

from agno.run import RunContext

from src.domain.preferences.timezone import resolve_user_timezone
from src.security.user_context import UserContext


def get_current_datetime(run_context: RunContext) -> str:
    """Return the current date and time, in UTC and in the user's local timezone.

    Use this tool when the user asks about the current time, date, or needs
    to know "now" to resolve a relative expression ("hoy", "esta semana",
    "en 2 semanas") before calling propose_reminder/propose_calendar_event.
    Always use the "local" value to resolve what the user means by a time of
    day — it already accounts for the user's timezone and DST.

    Args:
        run_context: Injected by Agno.

    Returns:
        Both the current UTC datetime and the equivalent local datetime
        (ISO 8601, each with its own timezone offset), one per line.

    """
    user_ctx = UserContext.from_run_context(run_context)
    tz = resolve_user_timezone(user_ctx)
    now_utc = datetime.now(tz=UTC)
    now_local = now_utc.astimezone(tz)
    return f"UTC: {now_utc.isoformat()}\nLocal ({tz.key}): {now_local.isoformat()}"
