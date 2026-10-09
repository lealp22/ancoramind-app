"""User-facing preference read/forget service (specs/029 §6, T5).

Framework-independent — invoked from an Agno tool today, could be invoked
from a REST API or CLI without change (same discipline as NotesService).
"""

from __future__ import annotations

from uuid import UUID

from src.domain.dream.models import DreamCandidateSnapshot
from src.repositories.dream_candidates import DreamCandidatesRepository
from src.security.user_context import UserContext


class DreamPreferenceService:
    """Read/forget consolidated preferences — never touches canonical memory."""

    def __init__(self, repository: DreamCandidatesRepository):
        self._repo = repository

    async def list_preferences(self, user: UserContext) -> list[DreamCandidateSnapshot]:
        """Return the user's active (confirmed) preferences, newest first."""
        return await self._repo.list_active(user_id=user.user_id)

    async def forget(self, user: UserContext, candidate_id: UUID | None) -> bool | int:
        """Forget one preference (by id) or all of them when ``candidate_id`` is None.

        Returns the ``bool`` from ``forget_one`` when a specific id was asked
        for (``False`` means not found/owned — a real error), or the ``int``
        row count from ``forget_all`` (0 is a valid, non-error outcome:
        nothing to forget). Callers that treat a bare ``False`` as failure
        must not do the same for ``0`` — they are deliberately different
        types for that reason.
        """
        if candidate_id is not None:
            return await self._repo.forget_one(user.user_id, candidate_id)
        return await self._repo.forget_all(user.user_id)


__all__ = ["DreamPreferenceService"]
