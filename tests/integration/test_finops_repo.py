"""PostgreSQL integration tests for FinOps aggregates (specs/043 T2/T4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.runtime_config.models import bootstrap_runtime_configuration
from src.domain.runtime_config.service import RuntimeConfigManager
from src.repositories.database import get_session
from src.repositories.finops import FinopsRepository

pytestmark = pytest.mark.integration

SINCE = datetime.now(tz=UTC) - timedelta(days=1)


async def _revision() -> int:
    manager = RuntimeConfigManager(
        session_factory=get_session, bootstrap=bootstrap_runtime_configuration()
    )
    await manager.initialize()
    return manager.snapshot().revision


async def _interaction(session: AsyncSession, *, user: int, update: int, status: str) -> str:
    interaction_id = str(uuid4())
    await session.execute(
        text("""
            INSERT INTO ancora.telegram_interactions
                (id, bot_id, telegram_update_id, telegram_user_id, chat_id,
                 update_type, status, tool_call_count)
            VALUES (:id, 1, :update, :user, :user, 'message', :status, 2)
        """),
        {"id": interaction_id, "update": update, "user": user, "status": status},
    )
    return interaction_id


async def _usage(
    session: AsyncSession,
    interaction_id: str,
    revision: int,
    *,
    actual: float | None,
    estimated: float | None,
    status: str = "completed",
) -> None:
    await session.execute(
        text("""
            INSERT INTO ancora.llm_usage_events
                (interaction_id, llm_call_id, config_revision, logical_route,
                 effective_gateway_route, model, input_tokens, output_tokens,
                 total_tokens, estimated_cost, actual_cost, cost_source,
                 latency_ms, retry_count, fallback_used, status)
            VALUES (:i, :c, :r, 'ancoramind-default', 'ancoramind-default-r4',
                    'm', 10, 20, 30, :est, :act, 'pricing_snapshot',
                    100, 0, false, :status)
        """),
        {
            "i": interaction_id,
            "c": str(uuid4()),
            "r": revision,
            "est": estimated,
            "act": actual,
            "status": status,
        },
    )


async def test_cost_prefers_actual_isolates_users_and_skips_rejected(
    session: AsyncSession,
) -> None:
    revision = await _revision()
    a = await _interaction(session, user=7001, update=1, status="completed")
    b = await _interaction(session, user=7002, update=2, status="completed")
    rejected = await _interaction(session, user=7003, update=3, status="rejected")
    await _usage(session, a, revision, actual=0.002, estimated=0.5)
    await _usage(session, b, revision, actual=None, estimated=0.01)
    await _usage(session, rejected, revision, actual=9.0, estimated=9.0)
    await session.commit()

    repo = FinopsRepository(session)
    totals = await repo.totals(SINCE)
    assert totals.cost_usd == pytest.approx(0.012)
    assert totals.calls == 2
    assert totals.interactions == 2
    by_user = {uid: u.cost_usd for uid, u in await repo.by_user(SINCE)}
    assert by_user == {"7001": pytest.approx(0.002), "7002": pytest.approx(0.01)}
    assert len(await repo.daily(SINCE)) == 1
    assert (await repo.by_route_model(SINCE))[0].calls == 2
    assert {s.cost_source for s in await repo.by_cost_source(SINCE)} == {"pricing_snapshot"}


async def test_quality_queries_run_and_empty_window_is_zero(session: AsyncSession) -> None:
    repo = FinopsRepository(session)
    future = datetime.now(tz=UTC) + timedelta(days=1)
    assert (await repo.totals(future)).calls == 0
    assert await repo.daily(future) == []
    assert await repo.proposals(future) == []
    assert await repo.tool_calls_total(future) == 0
    assert (await repo.latency(future)).p50_ms is None

    revision = await _revision()
    a = await _interaction(session, user=7101, update=11, status="completed")
    await _usage(session, a, revision, actual=0.001, estimated=None)
    await session.commit()
    stats = await repo.latency(SINCE)
    assert stats.p50_ms == pytest.approx(100.0)
    assert {s.status: s.count for s in await repo.interactions_by_status(SINCE)} == {"completed": 1}
    assert await repo.tool_calls_total(SINCE) == 2
