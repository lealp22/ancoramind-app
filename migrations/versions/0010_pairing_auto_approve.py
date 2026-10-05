"""Add opt-in auto_approve flag to governed Telegram pairing invitations.

Revision ID: 0010_pairing_auto_approve
Revises: 0009_maintenance_money
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_pairing_auto_approve"
down_revision: str | None = "0009_maintenance_money"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Default existing invitations to the reviewed (non-auto) behavior."""
    op.execute("""
        ALTER TABLE ancora.telegram_pairing_invitations
        ADD COLUMN IF NOT EXISTS auto_approve BOOLEAN NOT NULL DEFAULT false
    """)


def downgrade() -> None:
    """Drop the flag; redemption reverts to always requiring operator review."""
    op.execute("""
        ALTER TABLE ancora.telegram_pairing_invitations
        DROP COLUMN IF EXISTS auto_approve
    """)
