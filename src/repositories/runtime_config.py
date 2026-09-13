"""Async PostgreSQL persistence for immutable runtime-config revisions and CAS activation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.runtime_config.models import (
    RuntimeConfigActivation,
    RuntimeConfigRevision,
    RuntimeConfiguration,
)

RUNTIME_CONFIG_ADVISORY_LOCK = 813_013_006


class RuntimeConfigConflictError(RuntimeError):
    """The active revision changed before a requested compare-and-swap completed."""


class RuntimeConfigRepository:
    """Persist revision history and one active pointer using parameterized SQL only."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_active_revision(self) -> RuntimeConfigRevision | None:
        """Return the active immutable revision, if a pointer exists."""
        result = await self._session.execute(
            text("""
                SELECT revision, schema_version, config, checksum, validation_status,
                    validation_errors, created_by, reason, created_at
                FROM ancora.runtime_config_active active
                JOIN ancora.runtime_config_revisions revision
                  ON revision.revision = active.active_revision
                WHERE active.singleton_id = TRUE
            """)
        )
        row = result.fetchone()
        return self._revision_from_row(row) if row is not None else None

    async def get_revision(self, revision: int) -> RuntimeConfigRevision | None:
        """Return an immutable revision by number."""
        result = await self._session.execute(
            text("""
                SELECT revision, schema_version, config, checksum, validation_status,
                    validation_errors, created_by, reason, created_at
                FROM ancora.runtime_config_revisions
                WHERE revision = :revision
            """),
            {"revision": revision},
        )
        row = result.fetchone()
        return self._revision_from_row(row) if row is not None else None

    async def create_revision(
        self,
        config: RuntimeConfiguration,
        *,
        checksum: str,
        created_by: str,
        reason: str,
    ) -> RuntimeConfigRevision:
        """Create one valid immutable revision without changing the active pointer."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    INSERT INTO ancora.runtime_config_revisions (
                        schema_version, config, checksum, validation_status,
                        validation_errors, created_by, reason, created_at
                    ) VALUES (
                        :schema_version, CAST(:config AS jsonb), :checksum, 'valid',
                        CAST(:validation_errors AS jsonb), :created_by, :reason, :created_at
                    )
                    RETURNING revision, schema_version, config, checksum, validation_status,
                        validation_errors, created_by, reason, created_at
                """),
                {
                    "schema_version": config.schema_version,
                    "config": json.dumps(config.model_dump(mode="json", by_alias=True)),
                    "checksum": checksum,
                    "validation_errors": "[]",
                    "created_by": created_by,
                    "reason": reason,
                    "created_at": now,
                },
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
            raise RuntimeError("Runtime config revision insert did not return a row")
        return self._revision_from_row(row)

    async def ensure_bootstrap(
        self,
        config: RuntimeConfiguration,
        *,
        checksum: str,
    ) -> RuntimeConfigRevision:
        """Atomically create/activate the bootstrap revision only when no pointer exists."""
        now = datetime.now(tz=UTC)
        try:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": RUNTIME_CONFIG_ADVISORY_LOCK},
            )
            active = await self.get_active_revision()
            if active is not None:
                await self._session.rollback()
                return active
            created = await self._session.execute(
                text("""
                    INSERT INTO ancora.runtime_config_revisions (
                        schema_version, config, checksum, validation_status,
                        validation_errors, created_by, reason, created_at
                    ) VALUES (
                        :schema_version, CAST(:config AS jsonb), :checksum, 'valid',
                        CAST(:validation_errors AS jsonb), 'system:bootstrap',
                        'initial runtime configuration from environment bootstrap', :now
                    )
                    RETURNING revision, schema_version, config, checksum, validation_status,
                        validation_errors, created_by, reason, created_at
                """),
                {
                    "schema_version": config.schema_version,
                    "config": json.dumps(config.model_dump(mode="json", by_alias=True)),
                    "checksum": checksum,
                    "validation_errors": "[]",
                    "now": now,
                },
            )
            row = created.fetchone()
            if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
                raise RuntimeError("Bootstrap runtime config insert did not return a row")
            revision = self._revision_from_row(row)
            await self._session.execute(
                text("""
                    INSERT INTO ancora.runtime_config_active (
                        singleton_id, active_revision, updated_at
                    ) VALUES (TRUE, :revision, :now)
                """),
                {"revision": revision.revision, "now": now},
            )
            await self._session.execute(
                text("""
                    INSERT INTO ancora.runtime_config_activations (
                        revision, previous_revision, actor, reason, activated_at
                    ) VALUES (
                        :revision, NULL, 'system:bootstrap',
                        'initial runtime configuration from environment bootstrap', :now
                    )
                """),
                {"revision": revision.revision, "now": now},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return revision

    async def activate(
        self,
        *,
        revision: int,
        expected_current_revision: int,
        actor: str,
        reason: str,
    ) -> RuntimeConfigActivation:
        """Atomically CAS the active pointer and append an activation audit row."""
        now = datetime.now(tz=UTC)
        try:
            valid_revision = await self._session.execute(
                text("""
                    SELECT revision
                    FROM ancora.runtime_config_revisions
                    WHERE revision = :revision AND validation_status = 'valid'
                """),
                {"revision": revision},
            )
            if valid_revision.fetchone() is None:
                await self._session.rollback()
                raise KeyError(f"Runtime config revision {revision} is not activatable")
            changed = await self._session.execute(
                text("""
                    UPDATE ancora.runtime_config_active
                    SET active_revision = :revision, updated_at = :now
                    WHERE singleton_id = TRUE
                      AND active_revision = :expected_current_revision
                    RETURNING active_revision
                """),
                {
                    "revision": revision,
                    "expected_current_revision": expected_current_revision,
                    "now": now,
                },
            )
            if changed.fetchone() is None:
                await self._session.rollback()
                raise RuntimeConfigConflictError(
                    "Runtime config active revision changed concurrently"
                )
            result = await self._session.execute(
                text("""
                    INSERT INTO ancora.runtime_config_activations (
                        revision, previous_revision, actor, reason, activated_at
                    ) VALUES (
                        :revision, :previous_revision, :actor, :reason, :activated_at
                    )
                    RETURNING revision, previous_revision, actor, reason, activated_at
                """),
                {
                    "revision": revision,
                    "previous_revision": expected_current_revision,
                    "actor": actor,
                    "reason": reason,
                    "activated_at": now,
                },
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
            raise RuntimeError("Runtime config activation insert did not return a row")
        return RuntimeConfigActivation.model_validate(row, from_attributes=True)

    @staticmethod
    def _revision_from_row(row: object) -> RuntimeConfigRevision:
        return RuntimeConfigRevision.model_validate(row, from_attributes=True)
