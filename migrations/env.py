"""Alembic environment for the AncoraMind canonical PostgreSQL schema."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _database_url() -> str:
    """Resolve a synchronous psycopg URL without exposing it in source control."""
    configured = config.attributes.get("database_url") or os.environ.get("ANCORA_DATABASE_URL")
    if not configured:
        from src.config import Settings

        configured = Settings().ancora_database_url
    if not configured:
        raise RuntimeError(
            "ANCORA_DATABASE_URL is required for Alembic. Set it in .env/the process "
            "environment or inject config.attributes['database_url'] in tests."
        )

    url = str(configured)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _configure(connection: Connection | None = None, *, url: str | None = None) -> None:
    if url is not None:
        context.configure(
            url=url,
            target_metadata=target_metadata,
            version_table="alembic_version",
            version_table_schema="ancora",
            compare_type=True,
            transactional_ddl=True,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
    else:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version",
            version_table_schema="ancora",
            compare_type=True,
            transactional_ddl=True,
        )


def run_migrations_offline() -> None:
    """Emit migration SQL without opening a database connection."""
    _configure(url=_database_url())
    context.execute("CREATE SCHEMA IF NOT EXISTS ancora")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in one transactional PostgreSQL connection."""
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS ancora")
        connection.commit()
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
