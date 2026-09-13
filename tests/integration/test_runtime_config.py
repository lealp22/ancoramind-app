"""PostgreSQL integration tests for T6 runtime-config revisions and CAS activation."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager
from src.repositories.database import get_session
from src.repositories.runtime_config import RuntimeConfigConflictError

pytestmark = pytest.mark.integration


def _payload(*, default_route: str = "ancoramind-default") -> dict[str, object]:
    return bootstrap_runtime_configuration(default_route).model_dump(mode="json", by_alias=True)


def _manager() -> RuntimeConfigManager:
    return RuntimeConfigManager(
        session_factory=get_session,
        bootstrap=bootstrap_runtime_configuration(),
    )


async def test_initialize_bootstraps_once_and_snapshot_has_no_database_io(
    session: AsyncSession,
) -> None:
    first = _manager()
    second = _manager()

    await first.initialize()
    await second.initialize()

    assert first.snapshot().source == "database"
    assert first.snapshot().revision == second.snapshot().revision == 1
    rows = (
        await session.execute(
            text("SELECT revision, created_by, reason FROM ancora.runtime_config_revisions")
        )
    ).fetchall()
    assert [(row.revision, row.created_by) for row in rows] == [(1, "system:bootstrap")]


async def test_publish_activate_rollback_preserves_immutable_history(session: AsyncSession) -> None:
    manager = _manager()
    await manager.initialize()
    bootstrap_snapshot = manager.snapshot()
    changed_payload = _payload(default_route="ancoramind-fast")

    revision = await manager.publish(
        changed_payload,
        actor="alice@example.test",
        reason="test fast route",
    )
    assert revision.revision == 2
    assert manager.snapshot() == bootstrap_snapshot

    activated = await manager.activate(
        revision.revision,
        expected_current_revision=bootstrap_snapshot.revision,
        actor="alice@example.test",
        reason="activate fast route",
    )
    assert activated.revision == revision.revision
    assert activated.config.routing.default_route == "ancoramind-fast"

    rolled_back = await manager.rollback(
        bootstrap_snapshot.revision,
        expected_current_revision=activated.revision,
        actor="alice@example.test",
        reason="restore bootstrap",
    )
    assert rolled_back.revision == bootstrap_snapshot.revision
    assert rolled_back.config.routing.default_route == "ancoramind-default"

    revision_rows = (
        await session.execute(
            text(
                "SELECT revision, validation_status "
                "FROM ancora.runtime_config_revisions ORDER BY revision"
            )
        )
    ).fetchall()
    assert [(row.revision, row.validation_status) for row in revision_rows] == [
        (1, "valid"),
        (2, "valid"),
    ]
    activations = (
        await session.execute(
            text("""
                SELECT revision, previous_revision, actor, reason
                FROM ancora.runtime_config_activations
                ORDER BY activated_at, id
            """)
        )
    ).fetchall()
    assert [(row.revision, row.previous_revision, row.actor) for row in activations] == [
        (1, None, "system:bootstrap"),
        (2, 1, "alice@example.test"),
        (1, 2, "alice@example.test"),
    ]
    assert activations[-1].reason == "rollback: restore bootstrap"


async def test_concurrent_cas_allows_one_activation_and_lost_notification_reconciles(
    session: AsyncSession,
) -> None:
    manager_a = _manager()
    manager_b = _manager()
    await manager_a.initialize()
    await manager_b.initialize()
    first = await manager_a.publish(
        _payload(default_route="ancoramind-fast"),
        actor="alice@example.test",
        reason="first candidate",
    )
    second = await manager_a.publish(
        _payload(default_route="ancoramind-vision"),
        actor="bob@example.test",
        reason="second candidate",
    )

    results = await asyncio.gather(
        manager_a.activate(
            first.revision,
            expected_current_revision=1,
            actor="alice@example.test",
            reason="activate first",
        ),
        manager_b.activate(
            second.revision,
            expected_current_revision=1,
            actor="bob@example.test",
            reason="activate second",
        ),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [result for result in results if isinstance(result, RuntimeConfigConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1

    active_revision = (
        await session.execute(
            text(
                "SELECT active_revision FROM ancora.runtime_config_active WHERE singleton_id = TRUE"
            )
        )
    ).scalar_one()
    assert active_revision in {first.revision, second.revision}

    reconciled_manager = _manager()
    await reconciled_manager.initialize()
    assert reconciled_manager.snapshot().revision == active_revision


async def test_invalid_config_never_creates_revision_or_replaces_last_known_good(
    session: AsyncSession,
) -> None:
    manager = _manager()
    await manager.initialize()
    before = manager.snapshot()
    invalid = deepcopy(_payload())
    gateway = invalid["gateway"]
    assert isinstance(gateway, dict)
    gateway["api_key"] = "must-not-persist"

    with pytest.raises(ValueError):
        await manager.publish(invalid, actor="alice@example.test", reason="invalid secret")

    assert manager.snapshot() == before
    assert (
        await session.execute(text("SELECT count(*) FROM ancora.runtime_config_revisions"))
    ).scalar_one() == 1
