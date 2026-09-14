"""Unit tests for the T8 ExecutionBudget (tools, fingerprints, cost, deadline)."""

from __future__ import annotations

import asyncio
import time

import pytest

from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
)
from src.domain.runtime_config.models import bootstrap_runtime_configuration


def _budget(**overrides: object) -> ExecutionBudget:
    config = bootstrap_runtime_configuration().execution_budget
    values = {
        "max_runtime_seconds": config.max_runtime_seconds,
        "max_model_calls": config.max_model_calls,
        "max_tool_calls": config.max_tool_calls,
        "max_same_tool_args_after_success": config.max_same_tool_args_after_success,
        "max_gateway_requests": config.max_gateway_requests,
        "max_gateway_attempts_per_model_call": config.max_gateway_attempts_per_model_call,
        "max_estimated_cost_usd": config.max_estimated_cost_usd,
        "started_at_monotonic": time.monotonic(),
    }
    values.update(overrides)
    return ExecutionBudget(**values)  # type: ignore[arg-type]


def test_tool_calls_are_counted_per_fingerprint() -> None:
    budget = _budget()

    budget.reserve_tool_call("fp-a")
    budget.reserve_tool_call("fp-a")
    budget.reserve_tool_call("fp-b")

    assert budget.tool_calls == 3
    assert budget.tool_fingerprint_attempts == {"fp-a": 2, "fp-b": 1}


def test_tool_hard_ceiling_blocks_thirteenth_call() -> None:
    budget = _budget(max_tool_calls=12)
    for index in range(12):
        budget.reserve_tool_call(f"fp-{index}")

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_tool_call("fp-12")

    assert exc_info.value.limit == "max_tool_calls"
    assert budget.tool_calls == 12


def test_identical_tool_call_blocked_after_success() -> None:
    budget = _budget()

    budget.reserve_tool_call("fp-a")
    budget.record_tool_success("fp-a")

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_tool_call("fp-a")

    assert exc_info.value.limit == "max_same_tool_args_after_success"


def test_failing_tool_call_gets_exactly_one_retry() -> None:
    budget = _budget()

    budget.reserve_tool_call("fp-a")
    budget.record_tool_failure("fp-a")
    budget.reserve_tool_call("fp-a")  # approved single retry
    budget.record_tool_failure("fp-a")

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_tool_call("fp-a")

    assert exc_info.value.limit == "tool_fingerprint_attempts"
    assert budget.tool_fingerprint_attempts["fp-a"] == 2


def test_successful_repeat_does_not_grant_error_retries() -> None:
    budget = _budget(max_same_tool_args_after_success=2)

    budget.reserve_tool_call("fp-a")
    budget.record_tool_success("fp-a")
    budget.reserve_tool_call("fp-a")
    budget.record_tool_success("fp-a")

    assert budget.successful_tool_fingerprints["fp-a"] == 2


def test_tool_reservation_respects_deadline() -> None:
    budget = _budget(started_at_monotonic=time.monotonic() - 121)

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_tool_call("fp-a")

    assert exc_info.value.limit == "max_runtime_seconds"
    assert budget.tool_calls == 0


async def test_tool_counters_survive_concurrent_async_tools() -> None:
    budget = _budget(max_tool_calls=5)
    guard = {"rejections": 0}

    async def tool(name: str) -> None:
        try:
            budget.reserve_tool_call(name)
            await asyncio.sleep(0)
            budget.record_tool_success(name)
        except ExecutionBudgetExceededError:
            guard["rejections"] += 1

    await asyncio.gather(*(tool(f"fp-{i % 6}") for i in range(12)))

    assert budget.tool_calls == 5
    assert guard["rejections"] == 7


def test_estimated_cost_is_reserved_against_approved_ceiling() -> None:
    budget = _budget(max_estimated_cost_usd=0.01)

    assert budget.reserve_estimated_cost(0.004) == pytest.approx(0.004)
    assert budget.reserve_estimated_cost(0.003) == pytest.approx(0.007)

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_estimated_cost(0.005)

    assert exc_info.value.limit == "max_estimated_cost_usd"
    assert budget.estimated_cost_usd == pytest.approx(0.007)


def test_atomic_model_reservation_does_not_consume_calls_on_cost_rejection() -> None:
    budget = _budget(max_estimated_cost_usd=0.01)

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_model_call(0.02)

    assert exc_info.value.limit == "max_estimated_cost_usd"
    assert budget.model_calls == 0
    assert budget.gateway_requests == 0
    assert budget.estimated_cost_usd == 0.0


def test_cost_accounting_accumulates_without_a_hard_ceiling() -> None:
    budget = _budget(max_estimated_cost_usd=None)

    assert budget.reserve_estimated_cost(5.0) == 5.0
    budget.settle_actual_cost(None)

    assert budget.estimated_cost_usd == 5.0
    assert budget.actual_cost_usd is None


def test_actual_cost_reconciles_accrued_estimate() -> None:
    budget = _budget(max_estimated_cost_usd=1.0)
    budget.reserve_estimated_cost(0.02)
    budget.reserve_estimated_cost(0.01)

    budget.settle_actual_cost(0.025)

    assert budget.estimated_cost_usd == pytest.approx(0.03)
    assert budget.actual_cost_usd == pytest.approx(0.025)


def test_gateway_attempt_ceiling_per_model_call() -> None:
    budget = _budget(max_gateway_attempts_per_model_call=2)

    budget.reserve_model_call()
    budget.reserve_gateway_attempt()  # approved single attempt for this call

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_gateway_attempt()

    assert exc_info.value.limit == "max_gateway_attempts_per_model_call"


def test_gateway_attempts_consume_the_total_request_ceiling() -> None:
    budget = _budget(max_gateway_requests=2, max_gateway_attempts_per_model_call=5)

    budget.reserve_model_call()
    budget.reserve_gateway_attempt()

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        budget.reserve_gateway_attempt()

    assert exc_info.value.limit == "max_gateway_requests"
    assert budget.gateway_requests == 2


def test_new_model_call_resets_per_call_attempt_counter() -> None:
    budget = _budget(max_gateway_attempts_per_model_call=2)

    budget.reserve_model_call()
    budget.reserve_gateway_attempt()
    budget.reserve_model_call()

    assert budget.gateway_attempts_current_call == 1
    assert budget.gateway_requests == 3
