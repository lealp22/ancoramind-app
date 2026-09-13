"""Unit tests for governed execution budget, context and trace propagation."""

from __future__ import annotations

import re
import time
from uuid import uuid4

import pytest

from src.domain.llm_access.context import (
    current_execution_context,
    execution_context_scope,
)
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionContext,
    GovernanceViolationError,
    generate_traceparent,
    governance_metadata,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)

TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-01$")


def _snapshot() -> RuntimeConfigSnapshot:
    config = bootstrap_runtime_configuration()
    return RuntimeConfigSnapshot(
        revision=1,
        checksum=config_checksum(config),
        source="database",
        config=config,
    )


def _context(**budget_overrides: float) -> ExecutionContext:
    config = bootstrap_runtime_configuration()
    budget_kwargs: dict[str, float] = {}
    if budget_overrides:
        budget_kwargs = dict(budget_overrides)
    budget = ExecutionBudget.from_config(
        config.execution_budget,
        started_at_monotonic=time.monotonic(),
    )
    for key, value in budget_kwargs.items():
        setattr(budget, key, value)
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=10,
        agno_run_id="run-1",
        agno_session_id="tg:ancoramind:77",
        config=_snapshot(),
        budget=budget,
        telegram_message_id=11,
        traceparent=generate_traceparent(),
    )


def test_traceparent_is_w3c_formatted_and_unique() -> None:
    first = generate_traceparent()
    second = generate_traceparent()

    assert TRACEPARENT_PATTERN.fullmatch(first)
    assert TRACEPARENT_PATTERN.fullmatch(second)
    assert first != second


def test_budget_reserves_model_call_and_gateway_request_together() -> None:
    budget = ExecutionBudget.from_config(
        bootstrap_runtime_configuration().execution_budget,
        started_at_monotonic=time.monotonic(),
    )

    assert budget.model_calls == 0
    assert budget.gateway_requests == 0

    budget.reserve_model_call()

    assert budget.model_calls == 1
    assert budget.gateway_requests == 1


def test_budget_fails_closed_on_model_call_ceiling() -> None:
    budget = ExecutionBudget.from_config(
        bootstrap_runtime_configuration().execution_budget,
        started_at_monotonic=time.monotonic(),
    )
    budget.max_model_calls = 1

    budget.reserve_model_call()
    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_model_call()

    assert exc_info.value.limit == "max_model_calls"
    assert budget.model_calls == 1


def test_budget_fails_closed_on_gateway_request_ceiling() -> None:
    budget = ExecutionBudget.from_config(
        bootstrap_runtime_configuration().execution_budget,
        started_at_monotonic=time.monotonic(),
    )
    budget.max_gateway_requests = 1

    budget.reserve_model_call()
    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_model_call()

    assert exc_info.value.limit == "max_gateway_requests"


def test_budget_fails_closed_on_deadline() -> None:
    budget = ExecutionBudget.from_config(
        bootstrap_runtime_configuration().execution_budget,
        started_at_monotonic=time.monotonic() - 121,
    )

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_model_call()

    assert exc_info.value.limit == "max_runtime_seconds"


def test_context_scope_binds_and_restores() -> None:
    context = _context()

    with execution_context_scope(context):
        assert current_execution_context() is context

    with pytest.raises(GovernanceViolationError):
        current_execution_context()


def test_context_scope_resets_after_exception() -> None:
    context = _context()

    with pytest.raises(RuntimeError, match="boom"), execution_context_scope(context):
        raise RuntimeError("boom")

    with pytest.raises(GovernanceViolationError):
        current_execution_context()


def test_governance_metadata_propagates_correlation_and_trace() -> None:
    context = _context()

    metadata = governance_metadata(context)

    assert metadata["correlation_id"] == str(context.correlation_id)
    assert metadata["traceparent"] == context.traceparent
    assert metadata["config_revision"] == context.config.revision
