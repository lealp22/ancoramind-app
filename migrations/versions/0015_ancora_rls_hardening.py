"""Enable RLS and keep the Ancora schema closed to public Data API roles.

Revision ID: 0015_ancora_rls_hardening
Revises: 0014_write_trivial_consent_mode
Create Date: 2026-10-15

Phase 1 is deliberately policy-free/default-deny for API roles. AncoraMind's
SQL runtime continues to connect as ``postgres`` (BYPASSRLS). The Supabase
``service_role`` keeps its existing absence of schema/table SQL grants because
it is used by ``SupabaseDocumentStorage`` against ``storage.*``, not
``ancora.*``. Revoking it here would add no protection and could surprise
future server-side Storage/API maintenance.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_ancora_rls_hardening"
down_revision: str | None = "0014_write_trivial_consent_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rls_sql(action: str) -> str:
    return f"""
DO $rls$
DECLARE table_name text;
BEGIN
    FOR table_name IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'ancora' AND c.relkind IN ('r', 'p')
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I {action} ROW LEVEL SECURITY',
            'ancora', table_name
        );
    END LOOP;
END $rls$;
"""


def upgrade() -> None:
    """Enable default-deny RLS and revoke public/API role SQL access."""
    op.execute(_rls_sql("ENABLE"))
    op.execute("REVOKE ALL ON SCHEMA ancora FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA ancora FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA ancora FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA ancora REVOKE ALL ON TABLES FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA ancora REVOKE ALL ON SEQUENCES FROM PUBLIC")
    # Supabase defines these API roles; plain PostgreSQL/Docker does not. Keep
    # the canonical migration portable while closing them whenever present.
    op.execute("""
        DO $api_roles$
        DECLARE api_role text;
        BEGIN
            FOR api_role IN
                SELECT rolname FROM pg_roles
                WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON SCHEMA ancora FROM %I', api_role);
                EXECUTE format(
                    'REVOKE ALL ON ALL TABLES IN SCHEMA ancora FROM %I', api_role
                );
                EXECUTE format(
                    'REVOKE ALL ON ALL SEQUENCES IN SCHEMA ancora FROM %I', api_role
                );
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA ancora '
                    'REVOKE ALL ON TABLES FROM %I', api_role
                );
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA ancora '
                    'REVOKE ALL ON SEQUENCES FROM %I', api_role
                );
            END LOOP;
        END $api_roles$;
    """)


def downgrade() -> None:
    """Disable RLS; intentionally do not broaden revoked privileges."""
    op.execute(_rls_sql("DISABLE"))
