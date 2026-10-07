"""Per-user document deduplication by content hash (BL-31)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_document_content_hash"
down_revision: str | None = "0011_voice_preparation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = """
ALTER TABLE ancora.documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_user_content_hash
    ON ancora.documents(user_id, content_hash)
    WHERE content_hash IS NOT NULL;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ancora.idx_documents_user_content_hash;
        ALTER TABLE ancora.documents DROP COLUMN IF EXISTS content_hash;
    """)
