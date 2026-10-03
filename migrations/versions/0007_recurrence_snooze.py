"""Add recurrence + snooze support to calendar events and reminders (specs/024).

Revision ID: 0007_recurrence_snooze
Revises: 0006_proposal_consent
Create Date: 2026-10-03

Adds a `recurrence_rule` JSONB column to both `calendar_events` and
`reminders` (simple structured rule — frequency/interval/until, no RRULE —
see `src/domain/shared/recurrence.py`), plus `reminders.recurrence_parent_id`
(self-referencing lineage pointer, always the chain's root) and
`reminders.fired_at` (used both for a "fired late" display note and as the
retention cutoff: fired reminders older than 90 days are purged by the
worker, see `src/domain/reminders/worker.py`).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_recurrence_snooze"
down_revision: str | None = "0006_proposal_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE ancora.calendar_events ADD COLUMN IF NOT EXISTS recurrence_rule JSONB")
    op.execute("ALTER TABLE ancora.reminders ADD COLUMN IF NOT EXISTS recurrence_rule JSONB")
    op.execute(
        "ALTER TABLE ancora.reminders ADD COLUMN IF NOT EXISTS recurrence_parent_id UUID "
        "REFERENCES ancora.reminders(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE ancora.reminders ADD COLUMN IF NOT EXISTS fired_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_calendar_recurrence ON ancora.calendar_events(user_id) "
        "WHERE recurrence_rule IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_fired_at ON ancora.reminders(fired_at) "
        "WHERE status = 'fired'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ancora.idx_reminders_fired_at")
    op.execute("DROP INDEX IF EXISTS ancora.idx_calendar_recurrence")
    op.execute("ALTER TABLE ancora.reminders DROP COLUMN IF EXISTS fired_at")
    op.execute("ALTER TABLE ancora.reminders DROP COLUMN IF EXISTS recurrence_parent_id")
    op.execute("ALTER TABLE ancora.reminders DROP COLUMN IF EXISTS recurrence_rule")
    op.execute("ALTER TABLE ancora.calendar_events DROP COLUMN IF EXISTS recurrence_rule")
