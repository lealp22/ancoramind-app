"""Bound access-notice quota/outbox scans without indexing other responses (BL-52)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_access_notice_index"
down_revision: str | None = "0016_voice_guard_search_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DDL = """
CREATE INDEX IF NOT EXISTS idx_access_notice_created
    ON ancora.logical_responses(created_at)
    WHERE response_kind = 'access_denied_notice';
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ancora.idx_access_notice_created;")
