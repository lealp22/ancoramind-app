"""Session-scoped adapter for the cost-governance spend reader (specs/013 T12).

Infrastructure layer: opens one short-lived session per read so the governed
runner can evaluate spend ceilings before a run starts without holding a
session for the whole Agent execution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.llm_access.cost_governance import SpendSummary
from src.repositories.llm_usage import LlmUsageRepository

SessionFactory = Callable[[], Awaitable[AsyncSession]]


class SessionSpendReader:
    """Read the aggregated spend summary through a per-call database session."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    async def summarize_spend(self, *, now: datetime) -> SpendSummary:
        session = await self._session_factory()
        try:
            return await LlmUsageRepository(session).summarize_spend(now=now)
        finally:
            await session.close()


__all__ = ["SessionSpendReader"]
