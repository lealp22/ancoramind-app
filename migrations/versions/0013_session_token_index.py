"""Index agno_session_id so cumulative-token lookups stay cheap (BL-34)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_session_token_index"
down_revision: str | None = "0012_document_content_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = """
CREATE INDEX IF NOT EXISTS idx_telegram_interactions_agno_session_id
    ON ancora.telegram_interactions(agno_session_id);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ancora.idx_telegram_interactions_agno_session_id;")
