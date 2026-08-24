"""Notes domain service — business logic for personal notes.

Framework-independent. Can be invoked from: Agno Tool, REST API, CLI, etc.
"""

from src.domain.notes.models import Note, NoteCreate
from src.repositories.notes import NotesRepository
from src.security.user_context import UserContext


class NotesService:
    """Service for managing personal notes in canonical memory."""

    def __init__(self, repository: NotesRepository):
        self._repo = repository

    async def remember(
        self,
        user_context: UserContext,
        content: str,
    ) -> Note:
        """Store a personal note in canonical memory.

        Args:
            user_context: Resolved trusted user context.
            content: Note content to persist.

        Returns:
            The created Note.
        """
        data = NoteCreate(content=content)
        return await self._repo.create(
            user_id=user_context.user_id,
            data=data,
        )

    async def search(
        self,
        user_context: UserContext,
        query: str | None = None,
    ) -> list[Note]:
        """Search personal notes for the user.

        Args:
            user_context: Resolved trusted user context.
            query: Optional search term.

        Returns:
            Matching notes, newest first.
        """
        return await self._repo.search(
            user_id=user_context.user_id,
            query=query,
        )