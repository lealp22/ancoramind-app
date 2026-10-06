"""Reminders repository — parameterized SQL."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.reminders.models import Reminder, ReminderCreate
from src.domain.shared.recurrence import RecurrenceRule, rule_to_jsonb_param


class RemindersRepository:
    """Repository for reminders in ancora schema."""

    def __init__(self, session: AsyncSession, *, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    async def create(self, user_id: str, data: ReminderCreate) -> Reminder:
        now = datetime.now(tz=UTC)
        stmt = text("""
            INSERT INTO ancora.reminders
                (user_id,title,description,trigger_at,status,source_document_id,
                 source_action_id,created_at,recurrence_rule,recurrence_parent_id)
            VALUES (:uid,:title,:desc,:trigger,'pending',:src_doc,:src_action,:now,
                    CAST(:rec AS jsonb),:parent)
            RETURNING *
        """)
        r = await self._session.execute(
            stmt,
            {
                "uid": user_id,
                "title": data.title,
                "desc": data.description,
                "trigger": data.trigger_at,
                "src_doc": data.source_document_id,
                "src_action": data.source_action_id,
                "now": now,
                "rec": rule_to_jsonb_param(data.recurrence_rule),
                "parent": data.recurrence_parent_id,
            },
        )
        row = r.fetchone()
        if row is None:
            raise RuntimeError("Reminder insert did not return a row")
        if self._auto_commit:
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

    async def get_by_id(self, user_id: str, reminder_id: UUID) -> Reminder | None:
        stmt = text("SELECT * FROM ancora.reminders WHERE id=:id AND user_id=:uid")
        r = await self._session.execute(stmt, {"id": reminder_id, "uid": user_id})
        row = r.fetchone()
        return _row_to_reminder(row) if row is not None else None

    async def list_due(self, now: datetime, limit: int = 50) -> list[Reminder]:
        """List pending reminders whose trigger_at is due (worker — BL-5)."""
        stmt = text("""
            SELECT * FROM ancora.reminders
            WHERE status='pending' AND trigger_at <= :now
            ORDER BY trigger_at
            LIMIT :limit
        """)
        r = await self._session.execute(stmt, {"now": now, "limit": limit})
        return [_row_to_reminder(row) for row in r.fetchall()]

    async def mark_fired(self, reminder_id: UUID, user_id: str) -> bool:
        """Mark a pending reminder as fired (idempotent on status).

        Only updates rows still in 'pending' so retries or a racing second
        worker cannot fire a reminder twice (returns False in that case).
        Also stamps ``fired_at``, used both for the "late" display note and
        as the retention cutoff (specs/024).
        """
        now = datetime.now(tz=UTC)
        stmt = text("""
            UPDATE ancora.reminders
            SET status='fired', fired_at=:now
            WHERE id=:id AND user_id=:uid AND status='pending'
            RETURNING id
        """)
        r = await self._session.execute(stmt, {"id": reminder_id, "uid": user_id, "now": now})
        if self._auto_commit:
            await self._session.commit()
        return r.fetchone() is not None

    async def create_next_occurrence(self, fired: Reminder, next_trigger_at: datetime) -> Reminder:
        """Insert the next pending occurrence of a recurring reminder.

        Called by the worker after ``fired`` was successfully delivered and
        marked fired — that row stays as a permanent audit record; this
        inserts a *new* row for the next occurrence, carrying the same
        recurrence rule forward. ``recurrence_parent_id`` always points at
        the chain's root (never the immediate predecessor), so lineage stays
        flat however long the chain gets.
        """
        return await self._insert_followup(
            fired,
            next_trigger_at,
            recurrence_rule=fired.recurrence_rule,
            source_action_id=fired.source_action_id,
        )

    async def create_snoozed(
        self, original: Reminder, trigger_at: datetime, source_action_id: UUID
    ) -> Reminder:
        """Insert a one-off snoozed copy of a reminder.

        Unlike ``create_next_occurrence``, the snoozed copy carries no
        recurrence of its own (it must not itself start recurring), and its
        ``source_action_id`` is the snooze proposal that was just confirmed,
        not the original creation proposal.
        """
        return await self._insert_followup(
            original,
            trigger_at,
            recurrence_rule=None,
            source_action_id=source_action_id,
        )

    async def _insert_followup(
        self,
        origin: Reminder,
        trigger_at: datetime,
        recurrence_rule: RecurrenceRule | None,
        source_action_id: UUID | None,
    ) -> Reminder:
        parent_id = origin.recurrence_parent_id or origin.id
        data = ReminderCreate(
            title=origin.title,
            description=origin.description,
            trigger_at=trigger_at,
            source_document_id=origin.source_document_id,
            source_action_id=source_action_id,
            recurrence_rule=recurrence_rule,
            recurrence_parent_id=parent_id,
        )
        return await self.create(origin.user_id, data)

    async def delete_old_fired(self, before: datetime) -> int:
        """Purge 'fired' reminders older than ``before`` (retention — specs/024).

        Intentionally NOT scoped by user_id: this is global system
        housekeeping (an automatic retention policy), not a per-user action,
        which is also why it needs no governance/propose-execute pair —
        unlike every other query in this repository. Rows fired before the
        ``fired_at`` column existed (``fired_at IS NULL``) are never matched,
        so they are never purged by this method.
        """
        stmt = text("""
            DELETE FROM ancora.reminders
            WHERE status='fired' AND fired_at IS NOT NULL AND fired_at < :before
            RETURNING id
        """)
        r = await self._session.execute(stmt, {"before": before})
        deleted = r.fetchall()
        if self._auto_commit:
            await self._session.commit()
        return len(deleted)


def _row_to_reminder(row: Row[tuple[object, ...]]) -> Reminder:
    return Reminder(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        description=row.description,
        trigger_at=row.trigger_at,
        status=row.status,
        source_document_id=row.source_document_id,
        source_action_id=row.source_action_id,
        created_at=row.created_at,
        recurrence_rule=row.recurrence_rule,
        recurrence_parent_id=row.recurrence_parent_id,
        fired_at=row.fired_at,
    )
