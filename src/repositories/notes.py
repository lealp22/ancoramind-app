"""Notes repository — parameterized PostgreSQL access for personal notes.

All queries are parameterized. No string interpolation. User-scoped data access.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.notes.models import Note, NoteCreate


class NotesRepository:
    """Repository for personal notes stored in ancora.notes."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, user_id: str, data: NoteCreate) -> Note:
        """Create a new note for the given user.

        Args:
            user_id: Resolved AncoraMind user identifier (from trusted context).
            data: Note content to store.

        Returns:
            The created Note with generated id and timestamps.
        """
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.notes (user_id, content, created_at, updated_at)
            VALUES (:user_id, :content, :now, :now)
            RETURNING id, user_id, content, created_at, updated_at
        """)
        result = await self._session.execute(stmt, {
            "user_id": user_id,
            "content": data.content,
            "now": now,
        })
        row = result.fetchone()
        await self._session.commit()
        return Note(
            id=row.id,
            user_id=row.user_id,
            content=row.content,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def search(self, user_id: str, query: str | None = None) -> list[Note]:
        """Search notes for the given user.

        Args:
            user_id: Resolved AncoraMind user identifier.
            query: Optional search term (ILIKE match on content).

        Returns:
            List of matching notes, ordered by created_at descending.
        """
        if query:
            stmt = text("""
                SELECT id, user_id, content, created_at, updated_at
                FROM ancora.notes
                WHERE user_id = :user_id
                  AND content ILIKE :pattern
                ORDER BY created_at DESC
                LIMIT 20
            """)
            params = {"user_id": user_id, "pattern": f"%{query}%"}
        else:
            stmt = text("""
                SELECT id, user_id, content, created_at, updated_at
                FROM ancora.notes
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 20
            """)
            params = {"user_id": user_id}

        result = await self._session.execute(stmt, params)
        rows = result.fetchall()

        return [
            Note(
                id=row.id,
                user_id=row.user_id,
                content=row.content,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
