"""Unit tests for the GovernedModel adapter (fail-closed, budget, usage audit)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse

from src.agent.governed_model import (
    GovernanceStreamingOrSyncError,
    build_governed_model,
    governed_model_cls,
)
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionContext,
    GovernanceViolationError,
    LlmUsageEventCreate,
    generate_traceparent,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


@dataclass
class FakeProviderModel(Model):
    """Concrete in-memory provider used to exercise the governed mixin."""

    fail: bool = False
    ttft: int | float | None = None
    provider_calls: int = field(default=0, repr=False)

    def invoke(self, *args: Any, **kwargs: Any) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError
        yield  # pragma: no cover

    def _parse_provider_response(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:  # pragma: no cover
        raise NotImplementedError

    def _parse_provider_response_delta(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self.provider_calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return ModelResponse(
            content="ok",
            input_tokens=3,
            output_tokens=5,
            total_tokens=8,
            time_to_first_token=self.ttft if self.ttft is not None else 120,
        )


def _context() -> ExecutionContext:
    config = bootstrap_runtime_configuration()
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=10,
        agno_run_id="run-1",
        agno_session_id="tg:ancoramind:77",
        config=RuntimeConfigSnapshot(
            revision=1,
            checksum=config_checksum(config),
            source="database",
            config=config,
        ),
        budget=ExecutionBudget.from_config(
            config.execution_budget,
            started_at_monotonic=time.monotonic(),
        ),
        traceparent=generate_traceparent(),
    )


def _model(
    *,
    recorder: Any = None,
    fail: bool = False,
    ttft: int | float | None = None,
) -> FakeProviderModel:
    return build_governed_model(
        FakeProviderModel,
        {"id": "fake-model", "fail": fail, "ttft": ttft},
        recorder=recorder,
        route_name="ancoramind-default",
        effective_route="ancoramind-default-r1",
        revision=1,
    )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[LlmUsageEventCreate] = []

    async def __call__(self, event: LlmUsageEventCreate) -> None:
        self.events.append(event)


async def test_ainvoke_fails_closed_without_execution_context() -> None:
    model = _model()

    with pytest.raises(GovernanceViolationError):
        await model.ainvoke([])

    assert model.provider_calls == 0


async def test_ainvoke_records_completed_usage_with_tokens() -> None:
    recorder = _Recorder()
    model = _model(recorder=recorder)
    context = _context()

    with execution_context_scope(context):
        response = await model.ainvoke([])

    assert response.content == "ok"
    assert model.provider_calls == 1
    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event.status == "completed"
    assert event.interaction_id == context.correlation_id
    assert event.config_revision == 1
    assert event.logical_route == "ancoramind-default"
    assert event.effective_gateway_route == "ancoramind-default-r1"
    assert (event.input_tokens, event.output_tokens, event.total_tokens) == (3, 5, 8)
    assert event.time_to_first_token_ms == 120
    assert event.error_class is None
    assert event.latency_ms is not None


async def test_ainvoke_normalizes_float_ttft_seconds_to_milliseconds() -> None:
    recorder = _Recorder()
    model = _model(recorder=recorder, ttft=0.125)
    context = _context()

    with execution_context_scope(context):
        await model.ainvoke([])

    assert recorder.events[0].time_to_first_token_ms == 125


async def test_ainvoke_reserves_budget_and_fails_before_provider_call() -> None:
    recorder = _Recorder()
    model = _model(recorder=recorder)
    context = _context()
    context.budget.max_model_calls = 0

    with execution_context_scope(context), pytest.raises(ExecutionBudgetExceededError):
        await model.ainvoke([])

    assert model.provider_calls == 0
    assert recorder.events == []


async def test_ainvoke_records_error_class_and_propagates_failure() -> None:
    recorder = _Recorder()
    model = _model(recorder=recorder, fail=True)
    context = _context()

    with execution_context_scope(context), pytest.raises(RuntimeError, match="unavailable"):
        await model.ainvoke([])

    assert model.provider_calls == 1
    assert len(recorder.events) == 1
    assert recorder.events[0].status == "error"
    assert recorder.events[0].error_class == "RuntimeError"


async def test_recorder_failure_is_fail_open() -> None:
    async def failing_recorder(event: LlmUsageEventCreate) -> None:
        raise RuntimeError("audit database down")

    model = _model(recorder=failing_recorder)
    context = _context()

    with execution_context_scope(context):
        response = await model.ainvoke([])

    assert response.content == "ok"


async def test_sync_and_streaming_paths_are_rejected() -> None:
    model = _model()

    with pytest.raises(GovernanceStreamingOrSyncError):
        model.invoke([])
    with pytest.raises(GovernanceStreamingOrSyncError):
        model.invoke_stream([])
    with pytest.raises(GovernanceStreamingOrSyncError):
        await model.ainvoke_stream([])


def test_governed_class_preserves_provider_class_and_forces_zero_retries() -> None:
    governed_cls = governed_model_cls(FakeProviderModel)
    model = build_governed_model(
        FakeProviderModel,
        {"id": "fake-model", "retries": 5},
        recorder=None,
        route_name="ancoramind-default",
        effective_route="ancoramind-default-r1",
        revision=1,
    )

    assert issubclass(governed_cls, FakeProviderModel)
    assert model.retries == 0


def test_governed_class_is_cached_per_provider_class() -> None:
    assert governed_model_cls(FakeProviderModel) is governed_model_cls(FakeProviderModel)


def test_unique_llm_call_ids_per_model_call() -> None:
    assert LlmUsageEventCreate.new_call_id() != LlmUsageEventCreate.new_call_id()


def _priced_snapshot() -> RuntimeConfigSnapshot:
    from src.domain.runtime_config.models import PricingConfig, RoutePricing

    base = bootstrap_runtime_configuration()
    priced = base.model_copy(
        update={
            "pricing": PricingConfig(
                routes={
                    "ancoramind-default-r1": RoutePricing(
                        input_cost_per_1m_usd=1.0,
                        output_cost_per_1m_usd=2.0,
                    )
                }
            )
        }
    )
    return RuntimeConfigSnapshot(
        revision=2,
        checksum=config_checksum(priced),
        source="database",
        config=priced,
    )


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


async def test_ainvoke_reserves_estimated_and_settles_actual_cost() -> None:
    recorder = _Recorder()
    model = _model(recorder=recorder)
    snapshot = _priced_snapshot()
    context = ExecutionContext(
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

    with execution_context_scope(context):
        response = await model.ainvoke([_Message("x" * 400)])

    assert response.content == "ok"
    event = recorder.events[0]
    # input estimate: 400/4=100 tokens * 1.0 USD/1M + 1024 * 2.0 USD/1M
    assert event.estimated_cost == pytest.approx(100 * 1.0 / 1e6 + 1024 * 2.0 / 1e6)
    assert event.actual_cost == pytest.approx(3 * 1.0 / 1e6 + 5 * 2.0 / 1e6)
    assert event.cost_source == "pricing_snapshot"
    assert context.budget.estimated_cost_usd == pytest.approx(event.estimated_cost)
    assert context.budget.actual_cost_usd == pytest.approx(event.actual_cost)


async def test_cost_ceiling_blocks_call_before_provider() -> None:
    recorder = _Recorder()
    model = _model(recorder=recorder)
    snapshot = _priced_snapshot()
    capped = snapshot.config.model_copy(
        update={
            "execution_budget": snapshot.config.execution_budget.model_copy(
                update={"max_estimated_cost_usd": 0.000001}
            )
        }
    )
    context = ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=10,
        agno_run_id="run-1",
        agno_session_id="tg:ancoramind:77",
        config=RuntimeConfigSnapshot(
            revision=2,
            checksum=config_checksum(capped),
            source="database",
            config=capped,
        ),
        budget=ExecutionBudget.from_config(
            capped.execution_budget,
            started_at_monotonic=time.monotonic(),
        ),
        traceparent=generate_traceparent(),
    )

    with (
        execution_context_scope(context),
        pytest.raises(ExecutionBudgetExceededError) as exc_info,
    ):
        await model.ainvoke([_Message("x" * 400)])

    assert exc_info.value.limit == "max_estimated_cost_usd"
    assert model.provider_calls == 0
    assert recorder.events == []
    assert context.budget.model_calls == 0
    assert context.budget.gateway_requests == 0
    assert context.budget.estimated_cost_usd == 0.0
