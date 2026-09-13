"""In-memory last-known-good manager for immutable runtime configuration revisions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.runtime_config.models import (
    RuntimeConfigRevision,
    RuntimeConfigSnapshot,
    RuntimeConfiguration,
    RuntimeConfigValidationError,
    RuntimeConfigValidationResult,
    config_checksum,
    parse_runtime_config,
    validate_runtime_config,
)
from src.repositories.runtime_config import RuntimeConfigRepository

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Awaitable[AsyncSession]]


class RuntimeConfigControlPlaneUnavailableError(RuntimeError):
    """PostgreSQL control-plane work cannot safely be performed at this time."""


class RuntimeConfigManager:
    """Own the cached immutable snapshot and durable control-plane operations."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        bootstrap: RuntimeConfiguration,
    ):
        self._session_factory = session_factory
        self._bootstrap_snapshot = RuntimeConfigSnapshot(
            revision=0,
            checksum=config_checksum(bootstrap),
            source="bootstrap",
            config=bootstrap,
        )
        self._snapshot = self._bootstrap_snapshot
        self._database_available = False
        self._last_initialize_error: str | None = None

    async def initialize(self) -> None:
        """Load active config or create bootstrap; preserve in-memory LKG on DB failure."""
        try:
            session = await self._session_factory()
        except (RuntimeError, SQLAlchemyError) as exc:
            self._database_available = False
            self._last_initialize_error = type(exc).__name__
            logger.warning("Runtime config control plane unavailable; using bootstrap snapshot")
            return
        try:
            repository = RuntimeConfigRepository(session)
            revision = await repository.ensure_bootstrap(
                self._bootstrap_snapshot.config,
                checksum=self._bootstrap_snapshot.checksum,
            )
            self._snapshot = self._snapshot_from_revision(revision)
            self._database_available = True
            self._last_initialize_error = None
        except (ValueError, SQLAlchemyError, RuntimeError, KeyError) as exc:
            self._database_available = False
            self._last_initialize_error = type(exc).__name__
            logger.warning(
                "Runtime config initialization failed; preserving last-known-good snapshot",
                exc_info=True,
            )
        finally:
            await session.close()

    def snapshot(self) -> RuntimeConfigSnapshot:
        """Return the current immutable snapshot without I/O."""
        return self._snapshot

    @property
    def database_available(self) -> bool:
        """Whether the control plane completed its most recent database initialization."""
        return self._database_available

    @property
    def last_initialize_error(self) -> str | None:
        """Return a class-only health signal without SQL or secret detail."""
        return self._last_initialize_error

    async def validate(self, payload: object) -> RuntimeConfigValidationResult:
        """Validate an untrusted configuration payload without persisting it."""
        return validate_runtime_config(payload)

    async def publish(
        self,
        payload: object,
        *,
        actor: str,
        reason: str,
    ) -> RuntimeConfigRevision:
        """Create a valid immutable revision without changing the active snapshot."""
        self._validate_audit_fields(actor, reason)
        config = parse_runtime_config(payload)
        repository, session = await self._repository()
        try:
            return await repository.create_revision(
                config,
                checksum=config_checksum(config),
                created_by=actor,
                reason=reason,
            )
        except SQLAlchemyError as exc:
            self._mark_control_plane_unavailable(exc)
            raise RuntimeConfigControlPlaneUnavailableError(
                "Runtime config database control plane is unavailable"
            ) from exc
        finally:
            await session.close()

    async def activate(
        self,
        revision: int,
        *,
        expected_current_revision: int,
        actor: str,
        reason: str,
    ) -> RuntimeConfigSnapshot:
        """CAS the active revision then replace the cached snapshot for future runs only."""
        self._validate_audit_fields(actor, reason)
        repository, session = await self._repository()
        try:
            target = await repository.get_revision(revision)
            if target is None:
                raise KeyError(f"Runtime config revision {revision} does not exist")
            if target.validation_status != "valid":
                raise RuntimeConfigValidationError(target.validation_errors)
            parse_runtime_config(target.config.model_dump(mode="json", by_alias=True))
            await repository.activate(
                revision=revision,
                expected_current_revision=expected_current_revision,
                actor=actor,
                reason=reason,
            )
            snapshot = self._snapshot_from_revision(target)
            self._snapshot = snapshot
            self._database_available = True
            self._last_initialize_error = None
            return snapshot
        except SQLAlchemyError as exc:
            self._mark_control_plane_unavailable(exc)
            raise RuntimeConfigControlPlaneUnavailableError(
                "Runtime config database control plane is unavailable"
            ) from exc
        finally:
            await session.close()

    async def rollback(
        self,
        revision: int,
        *,
        expected_current_revision: int,
        actor: str,
        reason: str,
    ) -> RuntimeConfigSnapshot:
        """Activate an older immutable revision through the same audited CAS path."""
        return await self.activate(
            revision,
            expected_current_revision=expected_current_revision,
            actor=actor,
            reason=f"rollback: {reason}",
        )

    async def _repository(self) -> tuple[RuntimeConfigRepository, AsyncSession]:
        if not self._database_available:
            raise RuntimeConfigControlPlaneUnavailableError(
                "Runtime config database control plane is unavailable"
            )
        try:
            session = await self._session_factory()
        except (RuntimeError, SQLAlchemyError) as exc:
            self._database_available = False
            self._last_initialize_error = type(exc).__name__
            raise RuntimeConfigControlPlaneUnavailableError(
                "Runtime config database control plane is unavailable"
            ) from exc
        return RuntimeConfigRepository(session), session

    def _mark_control_plane_unavailable(self, exc: Exception) -> None:
        """Retain LKG while recording only the failed infrastructure exception class."""
        self._database_available = False
        self._last_initialize_error = type(exc).__name__

    @staticmethod
    def _snapshot_from_revision(revision: RuntimeConfigRevision) -> RuntimeConfigSnapshot:
        if revision.validation_status != "valid":
            raise RuntimeConfigValidationError(revision.validation_errors)
        return RuntimeConfigSnapshot(
            revision=revision.revision,
            checksum=revision.checksum,
            source="database",
            config=revision.config,
        )

    @staticmethod
    def _validate_audit_fields(actor: str, reason: str) -> None:
        if not actor.strip():
            raise ValueError("actor must not be blank")
        if not reason.strip():
            raise ValueError("reason must not be blank")
