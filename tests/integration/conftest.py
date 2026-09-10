"""Integration tests — real PostgreSQL via docker-compose (specs/009, BL-2).

Session setup:
- Start the docker-compose ``postgres`` service (skipped when
  ``ANCORA_TEST_DATABASE_URL`` points to a custom server).
- Create the dedicated test database (default ``ancoramind_test``) — the dev
  database (``ancoramind``) is never touched — and apply ``migrations/init.sql``.
- Without Docker/PostgreSQL the suite SKIPS with an actionable message.
  Set ``ANCORA_TEST_REQUIRE_DB=1`` to fail instead (used in CI).

Per test:
- A fresh ``AsyncSession``; all ``ancora`` tables are truncated afterwards.
  The async engine is created and disposed per test on purpose: pooled asyncpg
  connections are bound to the event loop that created them, and
  pytest-asyncio uses a fresh loop per test by default.
"""

import os
import subprocess
import time
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine.url import URL, make_url

from src.repositories.database import close_database, get_session, init_database

REPO_ROOT = Path(__file__).resolve().parents[2]
INIT_SQL_PATH = REPO_ROOT / "migrations" / "init.sql"

TEST_DB_NAME = os.environ.get("ANCORA_TEST_DATABASE", "ancoramind_test")
CUSTOM_URL = os.environ.get("ANCORA_TEST_DATABASE_URL")

if CUSTOM_URL:
    # Custom server mode: the caller manages the server; init.sql is idempotent.
    _custom = make_url(CUSTOM_URL)
    ENGINE_URL = CUSTOM_URL
    TEST_DSN = URL.create(
        "postgresql",
        username=_custom.username,
        password=_custom.password,
        host=_custom.host,
        port=_custom.port,
        database=_custom.database,
    ).render_as_string(hide_password=False)
else:
    ADMIN_DSN = os.environ.get(
        "ANCORA_TEST_ADMIN_DSN",
        "postgresql://ancora:ancora@localhost:5432/ancoramind",
    )
    _admin = make_url(ADMIN_DSN)
    ENGINE_URL = URL.create(
        "postgresql+asyncpg",
        username=_admin.username,
        password=_admin.password,
        host=_admin.host,
        port=_admin.port,
        database=TEST_DB_NAME,
    ).render_as_string(hide_password=False)
    TEST_DSN = URL.create(
        "postgresql",
        username=_admin.username,
        password=_admin.password,
        host=_admin.host,
        port=_admin.port,
        database=TEST_DB_NAME,
    ).render_as_string(hide_password=False)

TRUNCATE_SQL = """
    TRUNCATE TABLE ancora.notes, ancora.documents, ancora.ai_extractions,
        ancora.vehicles, ancora.vehicle_maintenance, ancora.action_proposals,
        ancora.reminders, ancora.calendar_events,
        ancora.todo_items, ancora.todo_lists
    RESTART IDENTITY CASCADE
"""

READY_TIMEOUT_SECONDS = 30.0


def _redact(dsn: str) -> str:
    return make_url(dsn).render_as_string()


def _try_connect(dsn: str, timeout: int = 2) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=timeout):
            return True
    except psycopg.OperationalError:
        return False


def _skip_or_fail(message: str) -> None:
    hint = (
        "PostgreSQL for integration tests is not available.\n"
        "  Start it with: docker compose up -d postgres\n"
        "  Or point to a custom server with: ANCORA_TEST_DATABASE_URL\n"
        f"  Details: {message}"
    )
    if os.environ.get("ANCORA_TEST_REQUIRE_DB"):
        pytest.fail(hint)
    pytest.skip(hint)


@pytest.fixture(scope="session")
def postgres_server():
    """Ensure PostgreSQL is reachable; skip (or fail in CI) otherwise."""
    if CUSTOM_URL:
        if not _try_connect(TEST_DSN):
            _skip_or_fail(f"ANCORA_TEST_DATABASE_URL unreachable: {_redact(TEST_DSN)}")
        return

    if not _try_connect(ADMIN_DSN):
        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d", "postgres"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            _skip_or_fail(f"docker compose not available: {exc}")
            raise  # pragma: no cover — pytest.skip already raised
        if result.returncode != 0:
            _skip_or_fail(result.stderr.strip() or "docker compose up failed")

    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _try_connect(ADMIN_DSN):
            return
        time.sleep(0.5)
    _skip_or_fail(
        f"PostgreSQL not ready within {READY_TIMEOUT_SECONDS:.0f}s "
        f"({_redact(ADMIN_DSN)})"
    )


@pytest.fixture(scope="session")
def test_database(postgres_server):
    """Provide the test database, migrated and empty.

    Default mode: drop/create the dedicated test database on the
    docker-compose server (the dev database is never touched), then apply
    migrations/init.sql. Custom mode (ANCORA_TEST_DATABASE_URL): the caller
    manages the server; only init.sql is applied (idempotent, IF NOT EXISTS).
    """
    init_sql = INIT_SQL_PATH.read_text(encoding="utf-8")

    if not CUSTOM_URL:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(TEST_DB_NAME)
                )
            )
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME))
            )

    with psycopg.connect(TEST_DSN) as conn:
        conn.execute(init_sql)
        conn.commit()


@pytest.fixture
async def session(test_database):
    """Fresh AsyncSession per test; ancora tables truncated afterwards."""
    init_database(ENGINE_URL)
    db_session = await get_session()
    try:
        yield db_session
    finally:
        try:
            await db_session.close()
        finally:
            with psycopg.connect(TEST_DSN) as conn:
                conn.execute(TRUNCATE_SQL)
                conn.commit()
            await close_database()


@pytest.fixture
def user_a() -> str:
    return "it-user-a"


@pytest.fixture
def user_b() -> str:
    return "it-user-b"
