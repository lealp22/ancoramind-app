"""Pin the voice preparation trigger function to an empty search path.

Revision ID: 0016_voice_guard_search_path
Revises: 0015_ancora_rls_hardening
Create Date: 2026-10-15

The function body already schema-qualifies its only relation. An empty search
path therefore removes caller-controlled name resolution without changing the
trigger's behavior and resolves Supabase lint 0011_function_search_path_mutable.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_voice_guard_search_path"
down_revision: str | None = "0015_ancora_rls_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Prevent the trigger function from inheriting a caller's search path."""
    op.execute("""
        ALTER FUNCTION ancora.voice_preparation_parent_guard()
        SET search_path = ''
    """)


def downgrade() -> None:
    """Restore the previous behavior where the function inherited search_path."""
    op.execute("""
        ALTER FUNCTION ancora.voice_preparation_parent_guard()
        RESET search_path
    """)
