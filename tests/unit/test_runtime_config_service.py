"""Unit tests for T6 in-memory snapshot and last-known-good behavior."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import NoReturn, cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import src.domain.runtime_config.service as service_module
from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import (
    RuntimeConfigControlPlaneUnavailableError,
    RuntimeConfigManager,
)

SessionFactory = Callable[[], Awaitable[AsyncSession]]


def _manager(session_factory: SessionFactory) -> RuntimeConfigManager:
    return RuntimeConfigManager(
        session_factory=session_factory,
        bootstrap=bootstrap_runtime_configuration(),
    )


def test_snapshot_is_bootstrap_and_does_not_do_io() -> None:
    session_factory = AsyncMock()
    manager = _manager(session_factory)

    snapshot = manager.snapshot()

    assert snapshot.source == "bootstrap"
    assert snapshot.revision == 0
    session_factory.assert_not_awaited()
    with pytest.raises(ValidationError):
        snapshot.revision = 99


async def test_initialize_database_failure_preserves_bootstrap_snapshot() -> None:
    session_factory = AsyncMock(side_effect=RuntimeError("database offline"))
    manager = _manager(session_factory)

    await manager.initialize()

    assert manager.snapshot().source == "bootstrap"
    assert manager.snapshot().revision == 0
    assert manager.database_available is False
    assert manager.last_initialize_error == "RuntimeError"


async def test_publish_requires_available_control_plane() -> None:
    session_factory = AsyncMock()
    manager = _manager(session_factory)

    with pytest.raises(RuntimeConfigControlPlaneUnavailableError):
        await manager.publish(
            bootstrap_runtime_configuration().model_dump(mode="json", by_alias=True),
            actor="unit-test",
            reason="must not publish without initialized DB",
        )

    session_factory.assert_not_awaited()


async def test_initialize_preserves_last_known_good_when_repository_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session_factory = AsyncMock(return_value=cast(AsyncSession, session))
    manager = _manager(session_factory)
    manager._database_available = True

    class FailingRepository:
        def __init__(self, _: AsyncSession) -> None:
            pass

        async def ensure_bootstrap(self, *args: object, **kwargs: object) -> NoReturn:
            raise OperationalError("select 1", {}, RuntimeError("database lost"))

    monkeypatch.setattr(service_module, "RuntimeConfigRepository", FailingRepository)

    await manager.initialize()

    assert manager.snapshot().source == "bootstrap"
    assert manager.database_available is False
    assert manager.last_initialize_error == "OperationalError"
    session.close.assert_awaited_once()
