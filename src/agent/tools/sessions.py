"""Per-tool-call DB session lifecycle (specs/023 T3).

Tools build services through small ``_get_*`` factories that open a fresh
``AsyncSession``. Those sessions were never closed, so every tool call leaked
a pooled connection. ``closes_sessions`` scopes one tool call: every session
registered with ``track_session`` during that call is closed when the call
returns or raises. Transaction semantics are unchanged — repositories keep
their explicit ``commit()`` calls.

The decorator preserves the wrapped signature, name, docstring and type hints
(``functools.wraps``), which is what Agno reads to build the tool schema and
to inject ``run_context``.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_TRACKED_SESSIONS: ContextVar[list[AsyncSession] | None] = ContextVar(
    "ancora_tool_sessions", default=None
)


def track_session(session: AsyncSession) -> AsyncSession:
    """Register a session to be closed when the current tool call ends."""
    tracked = _TRACKED_SESSIONS.get()
    if tracked is None:
        logger.warning("DB session opened outside a closes_sessions tool scope")
    else:
        tracked.append(session)
    return session


def closes_sessions[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Close every session tracked during one async tool call."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        sessions: list[AsyncSession] = []
        token = _TRACKED_SESSIONS.set(sessions)
        try:
            return await func(*args, **kwargs)
        finally:
            _TRACKED_SESSIONS.reset(token)
            for session in sessions:
                try:
                    await session.close()
                except Exception as exc:  # pragma: no cover - close rarely fails
                    logger.warning(
                        "Tool DB session close failed (error_class=%s)",
                        type(exc).__name__,
                    )

    return wrapper
