"""Reminders repository — parameterized SQL."""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.reminders.models import Reminder, ReminderCreate


class RemindersRepository:
    """Repository for reminders in ancora schema."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, user_id: str, data: ReminderCreate) -> Reminder:
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.reminders
                (user_id,title,description,trigger_at,status,source_document_id,source_action_id,created_at)
            VALUES (:uid,:title,:desc,:trigger,'pending',:src_doc,:src_action,:now)
            RETURNING *
        """)
        r = await self._session.execute(stmt, {
            "uid": user_id, "title": data.title, "desc": data.description,
            "trigger": data.trigger_at, "src_doc": data.source_document_id,
            "src_action": data.source_action_id, "now": now,
        })
        row = r.fetchone()
        await self._session.commit()
        return _row_to_reminder(row)

    async def list_by_user(self, user_id: str, status: str | None = None) -> list[Reminder]:
        if status:
            stmt = text("""
                SELECT * FROM ancora.reminders
                WHERE user_id=:uid AND status=:status
                ORDER BY trigger_at
            """)
            r = await self._session.execute(stmt, {"uid": user_id, "status": status})
        else:
            stmt = text("SELECT * FROM ancora.reminders WHERE user_id=:uid ORDER BY trigger_at")
            r = await self._session.execute(stmt, {"uid": user_id})
        return [_row_to_reminder(row) for row in r.fetchall()]


def _row_to_reminder(row) -> Reminder:
    return Reminder(
        id=row.id, user_id=row.user_id, title=row.title, description=row.description,
        trigger_at=row.trigger_at, status=row.status,
        source_document_id=row.source_document_id, source_action_id=row.source_action_id,
        created_at=row.created_at,
    )
