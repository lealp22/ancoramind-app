"""Regression tests for specs/030 T4: GovernedAgentFactory's history ceiling."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from agno.models.openai import OpenAIChat

from src.agent.governed_agent_factory import GovernedAgentFactory
from src.domain.llm_access.models import ExecutionBudget, ExecutionContext, generate_traceparent
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


class _FakeAccess:
    def model_for(self, route_name: str, execution_context: ExecutionContext) -> Any:
        del route_name, execution_context
        return OpenAIChat(id="fake-model")


def _snapshot_with_window(
    route_name: str, context_window_tokens: int | None
) -> RuntimeConfigSnapshot:
    base = bootstrap_runtime_configuration()
    route = base.routing.routes[route_name]
    updated_route = route.model_copy(update={"context_window_tokens": context_window_tokens})
    updated_routes = dict(base.routing.routes)
    updated_routes[route_name] = updated_route
    config = base.model_copy(
        update={"routing": base.routing.model_copy(update={"routes": updated_routes})}
    )
    return RuntimeConfigSnapshot(
        revision=1,
        checksum=config_checksum(config),
        source="database",
        config=config,
    )


def _context(snapshot: RuntimeConfigSnapshot) -> ExecutionContext:
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=10,
        agno_run_id="run-1",
        agno_session_id="tg:ancoramind:77",
        config=snapshot,
        budget=ExecutionBudget.from_config(
            snapshot.config.execution_budget,
            started_at_monotonic=time.monotonic(),
        ),
        traceparent=generate_traceparent(),
    )


def _factory() -> GovernedAgentFactory:
    return GovernedAgentFactory(llm_access=_FakeAccess(), db=None, tools=[], instructions=["instr"])


def test_large_window_route_gets_a_higher_ceiling_than_a_small_window_route() -> None:
    small_snapshot = _snapshot_with_window("ancoramind-default", 2_000)
    large_snapshot = _snapshot_with_window("ancoramind-default", 128_000)

    small_agent = _factory().create_for_run(
        _context(small_snapshot), route_name="ancoramind-default"
    )
    large_agent = _factory().create_for_run(
        _context(large_snapshot), route_name="ancoramind-default"
    )

    assert small_agent.num_history_runs < large_agent.num_history_runs


def test_ceiling_never_exceeds_ten_or_drops_below_one() -> None:
    tiny_snapshot = _snapshot_with_window("ancoramind-default", 1_024)
    huge_snapshot = _snapshot_with_window("ancoramind-default", 2_000_000)

    tiny_agent = _factory().create_for_run(_context(tiny_snapshot), route_name="ancoramind-default")
    huge_agent = _factory().create_for_run(_context(huge_snapshot), route_name="ancoramind-default")

    assert 1 <= tiny_agent.num_history_runs <= 10
    assert 1 <= huge_agent.num_history_runs <= 10


def test_missing_window_falls_back_to_the_conservative_default() -> None:
    snapshot = _snapshot_with_window("ancoramind-default", None)

    agent = _factory().create_for_run(_context(snapshot), route_name="ancoramind-default")

    assert 1 <= agent.num_history_runs <= 10
