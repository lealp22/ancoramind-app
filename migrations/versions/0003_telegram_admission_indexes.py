"""Add admission rate-limit indexes for the Telegram interaction ledger.

Revision ID: 0003_telegram_admission_indexes
Revises: 0002_llm_governance
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_telegram_admission_indexes"
down_revision: str | None = "0002_llm_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Support durable user-window and accepted-queue admission queries."""
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_telegram_interactions_user_accepted_at
        ON ancora.telegram_interactions(telegram_user_id, accepted_at)
        WHERE accepted_at IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_telegram_interactions_accepted_queue
        ON ancora.telegram_interactions(received_at)
        WHERE status = 'accepted'
    """)


def downgrade() -> None:
    """Remove only indexes introduced for T4 durable admission."""
    op.execute("DROP INDEX IF EXISTS ancora.idx_telegram_interactions_accepted_queue")
    op.execute("DROP INDEX IF EXISTS ancora.idx_telegram_interactions_user_accepted_at")
