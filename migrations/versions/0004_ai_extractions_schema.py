"""Add schema_version column to ancora.ai_extractions.

The canonical baseline (0001 and init.sql) declares schema_version, but
databases created before that baseline was sealed never received the column,
so every INSERT of an extraction failed with 42703 (undefined column) right
after a successful inference call.

Revision ID: 0004_ai_extractions_schema
Revises: 0003_telegram_admission_indexes
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_ai_extractions_schema"
down_revision: str | None = "0003_telegram_admission_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Align deployed ai_extractions tables with the canonical baseline."""
    op.execute("""
        ALTER TABLE ancora.ai_extractions
        ADD COLUMN IF NOT EXISTS schema_version VARCHAR(31) NOT NULL DEFAULT '1.0'
    """)


def downgrade() -> None:
    """Remove the schema_version column."""
    op.execute("ALTER TABLE ancora.ai_extractions DROP COLUMN IF EXISTS schema_version")
