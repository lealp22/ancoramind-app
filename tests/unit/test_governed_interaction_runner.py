"""Unit tests for the governed interaction runner (T5 port, T7 semantics)."""

from __future__ import annotations

import inspect
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_interaction_runner import GovernedInteractionRunner
from src.domain.interactions.processor import InteractionAgentRunner
from src.domain.llm_access.context import current_execution_context
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionContext,
    GovernanceViolationError,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)
from src.domain.runtime_config.service import RuntimeConfigManager


def _snapshot() -> RuntimeConfigSnapshot:
    config = bootstrap_runtime_configuration()
    return RuntimeConfigSnapshot(
        revision=3,
        checksum=config_checksum(config),
        source="database",
        config=config,
    )


class _FakeManager(RuntimeConfigManager):
    """Manager stub that only serves the cached snapshot."""

    def __init__(self, snapshot: RuntimeConfigSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> RuntimeConfigSnapshot:
        return self._snapshot


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def arun(self, input_text: str, **kwargs: Any) -> Any:
        context = current_execution_context()  # fails closed if unbound
        self.calls.append({"input_text": input_text, "context": context, **kwargs})

        class _Output:
            content = "respuesta gobernada"

        return _Output()


class _FakeFactory(GovernedAgentFactory):
    """Factory stub that records the context seen at Agent-creation time."""

    def __init__(self) -> None:
        self.created_contexts: list[ExecutionContext] = []
        self.agent = _FakeAgent()

    def create_for_run(
        self,
        execution_context: ExecutionContext,
        *,
        route_name: str | None = None,
    ) -> Any:
        # Must be creatable only inside the governed scope.
        self.created_contexts.append(current_execution_context())
        return self.agent


def _runner() -> tuple[GovernedInteractionRunner, _FakeFactory]:
    factory = _FakeFactory()
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_snapshot()),
        factory=factory,
    )
    return runner, factory


async def test_runner_binds_context_metadata_and_returns_text() -> None:
    runner, factory = _runner()
    correlation_id = uuid4()

    output = await runner.run(
        "hola",
        user_id="88",
        session_id="tg:ancoramind:77",
        run_id="run-42",
        correlation_id=correlation_id,
        telegram_update_id=9001,
        telegram_message_id=9002,
    )

    assert output == "respuesta gobernada"
    assert len(factory.agent.calls) == 1
    call = factory.agent.calls[0]
    assert call["input_text"] == "hola"
    assert call["stream"] is False
    assert call["user_id"] == "88"
    assert call["session_id"] == "tg:ancoramind:77"
    assert call["run_id"] == "run-42"

    context: ExecutionContext = call["context"]
    assert context.correlation_id == correlation_id
    assert context.telegram_update_id == 9001
    assert context.telegram_message_id == 9002
    assert context.agno_run_id == "run-42"
    assert context.agno_session_id == "tg:ancoramind:77"
    assert context.config.revision == 3
    assert context.traceparent is not None
    assert context.budget.model_calls == 0  # runner itself makes no model calls

    metadata = call["run_context"].metadata
    assert metadata["correlation_id"] == str(correlation_id)
    assert metadata["traceparent"] == context.traceparent
    assert metadata["config_revision"] == 3

    # The Agent was created inside the same governed scope.
    assert factory.created_contexts == [context]


async def test_runner_scope_is_released_after_run() -> None:
    runner, _ = _runner()

    await runner.run(
        "hola",
        user_id="88",
        session_id="tg:ancoramind:77",
        run_id="run-42",
        correlation_id=uuid4(),
        telegram_update_id=9001,
    )

    with pytest.raises(GovernanceViolationError):
        current_execution_context()


async def test_runner_rejects_non_text_content() -> None:
    runner, factory = _runner()

    class _NonTextAgent:
        async def arun(self, input_text: str, **kwargs: Any) -> Any:
            class _Output:
                content = {"structured": True}

            return _Output()

    factory.agent = _NonTextAgent()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="non-text"):
        await runner.run(
            "hola",
            user_id="88",
            session_id="tg:ancoramind:77",
            run_id="run-42",
            correlation_id=uuid4(),
            telegram_update_id=9001,
        )


def test_budget_defaults_match_approved_policy() -> None:
    config = bootstrap_runtime_configuration().execution_budget
    budget = ExecutionBudget.from_config(config, started_at_monotonic=0.0)

    assert budget.max_runtime_seconds == 120
    assert budget.max_model_calls == 6
    assert budget.max_tool_calls == 12
    assert budget.max_gateway_requests == 8
    assert budget.max_gateway_attempts_per_model_call == 2


def test_runner_port_signature_matches_domain_protocol() -> None:
    port_params = set(inspect.signature(InteractionAgentRunner.run).parameters)
    runner_params = set(inspect.signature(GovernedInteractionRunner.run).parameters)

    assert port_params <= runner_params
    assert {"telegram_update_id", "telegram_message_id"} <= runner_params


def _uuid() -> UUID:  # pragma: no cover - helper kept for future tests
    return uuid4()
