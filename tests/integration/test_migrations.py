"""Alembic lifecycle tests for the canonical AncoraMind schema (BL-12/T2)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy.engine.url import URL, make_url

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
INIT_SQL = (REPO_ROOT / "migrations" / "init.sql").read_text(encoding="utf-8")

def _canonical_head() -> str:
    """Read the migrations head from the Alembic scripts.

    A literal here silently drifts every time a revision is added — that is how
    this suite broke when ``0004_ai_extractions_schema`` landed — so the head is
    always read from the migration sources.
    """
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    if head is None:  # pragma: no cover - the migrations directory is never empty
        raise RuntimeError("Alembic reports no head revision")
    return head


def _down_revision(revision: str) -> str:
    """Return the parent revision recorded in the Alembic scripts."""
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(revision)
    if script is None or script.down_revision is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Revision {revision} has no parent")
    down_revision = script.down_revision
    if isinstance(down_revision, tuple):  # pragma: no cover - no merge revisions today
        raise RuntimeError(f"Revision {revision} is a merge point")
    return down_revision


HEAD_REVISION = _canonical_head()
"""Head read from the Alembic scripts; never a hand-maintained literal that
silently drifts when a revision is added (it went stale with 0004)."""
BASELINE_REVISION = "0001_ancora_baseline"
GOVERNANCE_REVISION = "0002_llm_governance"
DOCUMENT_HASH_REVISION = "0012_document_content_hash"
SESSION_INDEX_REVISION = "0013_session_token_index"
WRITE_TRIVIAL_REVISION = "0014_write_trivial_consent_mode"

BASELINE_TABLES = {
    "action_proposals",
    "ai_extractions",
    "calendar_events",
    "documents",
    "notes",
    "reminders",
    "todo_items",
    "todo_lists",
    "vehicle_maintenance",
    "vehicles",
}

GOVERNANCE_TABLES = {
    "llm_usage_events",
    "logical_responses",
    "runtime_config_activations",
    "runtime_config_active",
    "runtime_config_revisions",
    "telegram_deliveries",
    "telegram_interactions",
    "telegram_response_deliveries",
}

PAIRING_TABLES = {
    "telegram_pairing_authorizations",
    "telegram_pairing_invitations",
    "telegram_pairing_requests",
}

CONSENT_COLUMNS = {
    "payload_hash",
    "chat_id",
    "bot_id",
    "presented_at",
    "presented_response_id",
    "expires_at",
    "confirming_interaction_id",
    "executing_at",
    "completed_at",
    "failure_reason",
}
"""Columns added by 0006_proposal_consent (specs/023 T4.1)."""


@dataclass(frozen=True)
class MigrationDatabase:
    """Connection URLs for an isolated temporary migration database."""

    name: str
    dsn: str
    alembic_url: str


def _database_urls(admin_dsn: str, database: str) -> tuple[str, str]:
    parsed = make_url(admin_dsn)
    dsn = URL.create(
        "postgresql",
        username=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        database=database,
    ).render_as_string(hide_password=False)
    alembic_url = URL.create(
        "postgresql+psycopg",
        username=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        database=database,
    ).render_as_string(hide_password=False)
    return dsn, alembic_url


@pytest.fixture
def migration_database(postgres_server: object) -> Iterator[MigrationDatabase]:
    """Create a disposable database without touching dev, Supabase or production."""
    if os.environ.get("ANCORA_TEST_DATABASE_URL"):
        pytest.skip(
            "Migration lifecycle tests require create/drop database permissions; "
            "custom ANCORA_TEST_DATABASE_URL is externally managed"
        )

    admin_dsn = os.environ.get(
        "ANCORA_TEST_ADMIN_DSN",
        "postgresql://ancora:ancora@localhost:5432/ancoramind",
    )
    name = f"ancoramind_migration_{uuid4().hex[:12]}"
    dsn, alembic_url = _database_urls(admin_dsn, name)

    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    try:
        yield MigrationDatabase(name=name, dsn=dsn, alembic_url=alembic_url)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


def _alembic_config(database: MigrationDatabase) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database.alembic_url
    return config


def _tables(database: MigrationDatabase) -> set[str]:
    with psycopg.connect(database.dsn) as connection:
        rows = connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'ancora'
            """
        ).fetchall()
    return {row[0] for row in rows}


def _columns(database: MigrationDatabase, table: str) -> set[str]:
    with psycopg.connect(database.dsn) as connection:
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'ancora' AND table_name = %s
            """,
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _indexes(database: MigrationDatabase, table: str) -> set[str]:
    with psycopg.connect(database.dsn) as connection:
        rows = connection.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'ancora' AND tablename = %s
            """,
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _constraints(database: MigrationDatabase, table: str) -> set[str]:
    with psycopg.connect(database.dsn) as connection:
        rows = connection.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'ancora' AND table_name = %s
            """,
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def _current_revision(database: MigrationDatabase) -> str:
    with psycopg.connect(database.dsn) as connection:
        row = connection.execute("SELECT version_num FROM ancora.alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _note_count(database: MigrationDatabase, content: str) -> int:
    with psycopg.connect(database.dsn) as connection:
        row = connection.execute(
            "SELECT count(*) FROM ancora.notes WHERE content = %s",
            (content,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_alembic_fresh_install_and_latest_downgrade(
    migration_database: MigrationDatabase,
) -> None:
    """Head builds the canonical schema; downgrading head preserves data."""
    config = _alembic_config(migration_database)

    command.upgrade(config, "head")

    assert _current_revision(migration_database) == HEAD_REVISION
    assert _tables(migration_database) >= BASELINE_TABLES | GOVERNANCE_TABLES | PAIRING_TABLES
    assert "voice_preparations" in _tables(migration_database)
    assert "transcript_ciphertext" in _columns(migration_database, "voice_preparations")
    assert "content_hash" in _columns(migration_database, "documents")
    assert "idx_documents_user_content_hash" in _indexes(migration_database, "documents")
    assert {
        "source_interaction_id",
        "idempotency_key",
        "arguments_fingerprint",
    } <= _columns(migration_database, "action_proposals")
    assert _columns(migration_database, "action_proposals") >= CONSENT_COLUMNS
    assert {
        "idx_telegram_interactions_user_accepted_at",
        "idx_telegram_interactions_accepted_queue",
    } <= _indexes(migration_database, "telegram_interactions")

    with psycopg.connect(migration_database.dsn) as connection:
        connection.execute(
            "INSERT INTO ancora.notes (user_id, content) VALUES (%s, %s)",
            ("migration-user", "preserved through downgrade"),
        )
        connection.commit()

    command.downgrade(config, "-1")

    # Revision-relative on purpose: a new head must not need editing here.
    assert _current_revision(migration_database) == _down_revision(HEAD_REVISION)
    assert _tables(migration_database) >= BASELINE_TABLES | GOVERNANCE_TABLES
    assert _note_count(migration_database, "preserved through downgrade") == 1

    # Check revision-owned schema changes at explicit boundaries, not relative
    # offsets from head: adding a new migration must not shift these assertions.
    command.upgrade(config, "head")
    command.downgrade(config, WRITE_TRIVIAL_REVISION)

    assert _current_revision(migration_database) == WRITE_TRIVIAL_REVISION
    assert "consent_mode" in _columns(migration_database, "action_proposals")
    assert "ck_action_proposals_consent_mode" in _constraints(
        migration_database, "action_proposals"
    )

    command.downgrade(config, _down_revision(WRITE_TRIVIAL_REVISION))

    assert _current_revision(migration_database) == SESSION_INDEX_REVISION
    assert "consent_mode" not in _columns(migration_database, "action_proposals")
    assert "ck_action_proposals_consent_mode" not in _constraints(
        migration_database, "action_proposals"
    )
    assert "idx_telegram_interactions_agno_session_id" in _indexes(
        migration_database, "telegram_interactions"
    )
    assert "content_hash" in _columns(migration_database, "documents")
    assert "idx_documents_user_content_hash" in _indexes(migration_database, "documents")
    assert "voice_preparations" in _tables(migration_database)
    assert _note_count(migration_database, "preserved through downgrade") == 1

    command.downgrade(config, _down_revision(SESSION_INDEX_REVISION))

    assert _current_revision(migration_database) == DOCUMENT_HASH_REVISION
    assert "idx_telegram_interactions_agno_session_id" not in _indexes(
        migration_database, "telegram_interactions"
    )
    assert "content_hash" in _columns(migration_database, "documents")
    assert "idx_documents_user_content_hash" in _indexes(migration_database, "documents")
    assert _note_count(migration_database, "preserved through downgrade") == 1

    command.downgrade(config, _down_revision(DOCUMENT_HASH_REVISION))

    assert _current_revision(migration_database) == _down_revision(DOCUMENT_HASH_REVISION)
    assert "content_hash" not in _columns(migration_database, "documents")
    assert "idx_documents_user_content_hash" not in _indexes(migration_database, "documents")
    assert "voice_preparations" in _tables(migration_database)
    assert _note_count(migration_database, "preserved through downgrade") == 1

    command.downgrade(config, GOVERNANCE_REVISION)

    assert "voice_preparations" not in _tables(migration_database)
    assert not (PAIRING_TABLES & _tables(migration_database))
    assert not (CONSENT_COLUMNS & _columns(migration_database, "action_proposals"))
    assert _note_count(migration_database, "preserved through downgrade") == 1

    command.upgrade(config, "head")

    assert _current_revision(migration_database) == HEAD_REVISION
    assert _note_count(migration_database, "preserved through downgrade") == 1

    command.downgrade(config, BASELINE_REVISION)

    assert _current_revision(migration_database) == BASELINE_REVISION
    assert _tables(migration_database) >= BASELINE_TABLES
    assert not (GOVERNANCE_TABLES & _tables(migration_database))
    assert "source_interaction_id" not in _columns(migration_database, "action_proposals")
    assert {
        "idx_telegram_interactions_user_accepted_at",
        "idx_telegram_interactions_accepted_queue",
    } & _indexes(migration_database, "telegram_interactions") == set()
    assert _note_count(migration_database, "preserved through downgrade") == 1


def test_upgrade_adopts_unversioned_existing_schema_with_data(
    migration_database: MigrationDatabase,
) -> None:
    """An existing pre-Alembic baseline is adopted without losing domain data."""
    config = _alembic_config(migration_database)
    command.upgrade(config, BASELINE_REVISION)

    with psycopg.connect(migration_database.dsn) as connection:
        connection.execute(
            "INSERT INTO ancora.notes (user_id, content) VALUES (%s, %s)",
            ("legacy-user", "legacy data survives adoption"),
        )
        connection.execute("DROP TABLE ancora.alembic_version")
        connection.commit()

    command.upgrade(config, "head")

    assert _current_revision(migration_database) == HEAD_REVISION
    assert _note_count(migration_database, "legacy data survives adoption") == 1
    assert _tables(migration_database) >= GOVERNANCE_TABLES


def test_consent_downgrade_folds_new_states_back_to_the_legacy_model(
    migration_database: MigrationDatabase,
) -> None:
    """0006 downgrade must leave only statuses the previous model understood."""
    config = _alembic_config(migration_database)
    command.upgrade(config, "0006_proposal_consent")

    with psycopg.connect(migration_database.dsn) as connection:
        for status in ("executing", "failed_ambiguous", "expired", "discarded", "executed"):
            connection.execute(
                """
                INSERT INTO ancora.action_proposals (user_id, tool_name, status, payload)
                VALUES (%s, 'create_reminder', %s, '{}'::jsonb)
                """,
                ("migration-user", status),
            )
        connection.commit()

    command.downgrade(config, "0005_telegram_pairing")

    with psycopg.connect(migration_database.dsn) as connection:
        statuses = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT status FROM ancora.action_proposals"
            ).fetchall()
        }
    assert statuses <= {"pending_confirmation", "confirmed", "executed"}
    assert not (CONSENT_COLUMNS & _columns(migration_database, "action_proposals"))

    command.upgrade(config, "head")
    assert _current_revision(migration_database) == HEAD_REVISION


def test_init_sql_is_compatible_with_alembic_head(
    migration_database: MigrationDatabase,
) -> None:
    """The fresh-install SQL can be adopted by Alembic without schema loss."""
    with psycopg.connect(migration_database.dsn) as connection:
        connection.execute(INIT_SQL)
        connection.execute(INIT_SQL)
        connection.execute(
            "INSERT INTO ancora.notes (user_id, content) VALUES (%s, %s)",
            ("init-user", "init sql data survives alembic adoption"),
        )
        connection.commit()

    command.upgrade(_alembic_config(migration_database), "head")

    assert _current_revision(migration_database) == HEAD_REVISION
    assert _note_count(migration_database, "init sql data survives alembic adoption") == 1
    assert _tables(migration_database) >= BASELINE_TABLES | GOVERNANCE_TABLES
