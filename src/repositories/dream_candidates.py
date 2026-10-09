"""Dream candidates repository — parameterized PostgreSQL access (specs/029).

All queries are parameterized and scoped by ``user_id``. The ``ancora.
dream_candidates`` table is defined in specs/029-dream-personal-memory/
spec.md §3.2; its migration (T1) has not landed yet, so these queries are
untested against a real database — unit tests mock this repository, same
discipline already used for the T3 worker/adapter in this backlog item.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.dream.models import DreamCandidateSnapshot


class DreamCandidatesRepository:
    """Repository for consolidated preference candidates in the ancora schema."""

    def __init__(self, session: AsyncSession, *, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    async def list_active(self, user_id: str) -> list[DreamCandidateSnapshot]:
        """Return only `active` preferences — never `candidate`/tentative ones."""
        stmt = text("""
            SELECT id, category, key, value, status, evidence_count, confidence
            FROM ancora.dream_candidates
            WHERE user_id = :uid AND status = 'active'
            ORDER BY updated_at DESC
        """)
        result = await self._session.execute(stmt, {"uid": user_id})
        return [DreamCandidateSnapshot.model_validate(row) for row in result.mappings().all()]

    async def forget_one(self, user_id: str, candidate_id: UUID) -> bool:
        """Soft-delete one preference regardless of its current status.

        Never hard-deletes — the row's provenance stays auditable, only its
        status changes (specs/029 §4: "deleted" is a terminal status, not a
        removed row).
        """
        now = datetime.now(tz=UTC)
        stmt = text("""
            UPDATE ancora.dream_candidates
            SET status = 'deleted', updated_at = :now
            WHERE id = :id AND user_id = :uid AND status != 'deleted'
        """)
        result = await self._session.execute(stmt, {"id": candidate_id, "uid": user_id, "now": now})
        if self._auto_commit:
            await self._session.commit()
        return bool((getattr(result, "rowcount", 0) or 0) > 0)

    async def forget_all(self, user_id: str) -> int:
        """Soft-delete every non-deleted preference for this user."""
        now = datetime.now(tz=UTC)
        stmt = text("""
            UPDATE ancora.dream_candidates
            SET status = 'deleted', updated_at = :now
            WHERE user_id = :uid AND status != 'deleted'
        """)
        result = await self._session.execute(stmt, {"uid": user_id, "now": now})
        if self._auto_commit:
            await self._session.commit()
        return getattr(result, "rowcount", 0) or 0


__all__ = ["DreamCandidatesRepository"]
