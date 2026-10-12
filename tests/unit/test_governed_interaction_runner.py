"""Unit tests for the governed interaction runner (T5 port, T7 semantics)."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_interaction_runner import GovernedInteractionRunner
from src.domain.emergency_stop.models import EmergencyStopActiveError, EmergencyStopState
from src.domain.interactions.media import ResolvedTelegramMedia
from src.domain.interactions.processor import InteractionAgentRunner
from src.domain.llm_access.context import current_execution_context
from src.domain.llm_access.cost_governance import CostGovernanceError, SpendSummary
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionContext,
    GovernanceViolationError,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    RuntimeConfiguration,
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
        compaction_summary: str | None = None,
        reduced_history_runs: int | None = None,
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
    # BL-38 follow-up: a fresh in-memory scratch dict per run, for tool-level
    # dedup (export_document) — never Agno's persisted session_state.
    assert call["run_context"].session_state == {}

    # The Agent was created inside the same governed scope.
    assert factory.created_contexts == [context]


async def test_prepared_context_preserves_snapshot_and_consumed_stt_budget() -> None:
    runner, factory = _runner()
    correlation_id = uuid4()
    context = await runner.prepare_execution_context(
        session_id="voice", run_id="run", correlation_id=correlation_id, telegram_update_id=5
    )
    context.budget.reserve_model_call()
    await runner.run(
        "transcript",
        user_id="88",
        session_id="voice",
        run_id="run",
        correlation_id=correlation_id,
        telegram_update_id=5,
        execution_context=context,
    )
    assert factory.created_contexts[0] is context
    assert factory.created_contexts[0].budget.model_calls == 1


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


async def test_runner_ingests_media_before_a_text_only_agent_turn(monkeypatch) -> None:
    """Telegram bytes stay out of the main Agent and its provider request."""
    runner, factory = _runner()
    ingest = AsyncMock(
        return_value=(
            'Datos recuperados:\n{"trust":"untrusted_data",'
            '"source":"telegram_attachment_ingestion","records":[]}'
        )
    )
    monkeypatch.setattr(
        "src.agent.governed_interaction_runner.ingest_resolved_telegram_media", ingest
    )

    output = await runner.run(
        "He adjuntado un documento.",
        user_id="88",
        session_id="tg:ancoramind:77",
        run_id="run-media",
        correlation_id=uuid4(),
        telegram_update_id=9001,
        media=(
            ResolvedTelegramMedia(
                content=b"\x89PNG\r\n\x1a\nbody",
                filename="factura.png",
                mime_type="image/png",
                is_image=True,
            ),
        ),
    )

    assert output == "respuesta gobernada"
    ingest.assert_awaited_once()
    assert ingest.await_args.args[0].user_id == "88"
    assert ingest.await_args.args[1][0].filename == "factura.png"
    assert len(factory.agent.calls) == 1
    call = factory.agent.calls[0]
    assert call["input_text"].startswith("He adjuntado un documento.")
    assert '"trust":"untrusted_data"' in call["input_text"]
    assert call["session_id"] == "tg:ancoramind:77"
    assert "images" not in call
    assert "files" not in call
    assert len(factory.created_contexts) == 1


async def test_runner_rejects_non_text_content_with_media(monkeypatch) -> None:
    runner, factory = _runner()
    monkeypatch.setattr(
        "src.agent.governed_interaction_runner.ingest_resolved_telegram_media",
        AsyncMock(return_value='Datos recuperados:\n{"trust":"untrusted_data","records":[]}'),
    )

    class _NonTextAgent:
        async def arun(self, input_text: str, **kwargs: Any) -> Any:
            class _Output:
                content = {"structured": True}

            return _Output()

    factory.agent = _NonTextAgent()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="non-text"):
        await runner.run(
            "He adjuntado un documento.",
            user_id="88",
            session_id="tg:ancoramind:77",
            run_id="run-media-non-text",
            correlation_id=uuid4(),
            telegram_update_id=9001,
            media=(
                ResolvedTelegramMedia(
                    content=b"%PDF-1.4",
                    filename="factura.pdf",
                    mime_type="application/pdf",
                    is_image=False,
                ),
            ),
        )


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


async def test_runner_cancels_run_after_approved_runtime_budget() -> None:
    base = bootstrap_runtime_configuration()
    tight = base.model_copy(
        update={
            "execution_budget": base.execution_budget.model_copy(update={"max_runtime_seconds": 1}),
            "gateway": base.gateway.model_copy(update={"request_timeout_seconds": 1}),
        }
    )
    snapshot = RuntimeConfigSnapshot(
        revision=5,
        checksum=config_checksum(tight),
        source="database",
        config=tight,
    )
    factory = _FakeFactory()
    started_calls: list[float] = []

    class _SlowAgent:
        async def arun(self, input_text: str, **kwargs: Any) -> Any:
            started_calls.append(time.monotonic())
            await asyncio.sleep(1.5)

            class _Output:
                content = "nunca llega"

            return _Output()

    factory.agent = _SlowAgent()  # type: ignore[assignment]
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(snapshot),
        factory=factory,
    )

    with pytest.raises(ExecutionBudgetExceededError) as exc_info:
        await runner.run(
            "hola",
            user_id="88",
            session_id="tg:ancoramind:77",
            run_id="run-slow",
            correlation_id=uuid4(),
            telegram_update_id=9001,
        )

    assert exc_info.value.limit == "max_runtime_seconds"
    assert len(started_calls) == 1
    with pytest.raises(GovernanceViolationError):
        current_execution_context()


def _snapshot_with_cost_governance() -> RuntimeConfigSnapshot:
    payload = bootstrap_runtime_configuration().model_dump(mode="json", by_alias=True)
    payload["cost_governance"] = {
        "external_hard_limit_usd": 20.0,
        "alert_threshold_pct": 60,
        "strong_alert_threshold_pct": 80,
        "hard_stop_threshold_pct": 90,
        "daily_budget_usd": 1.0,
        "monthly_budget_usd": 15.0,
        "route_monthly_budgets_usd": {},
    }
    config = RuntimeConfiguration.model_validate(payload)
    return RuntimeConfigSnapshot(
        revision=4,
        checksum=config_checksum(config),
        source="database",
        config=config,
    )


class _FakeSpendReader:
    def __init__(self, summary: SpendSummary) -> None:
        self.summary = summary
        self.calls: list[object] = []

    async def summarize_spend(self, *, now: object) -> SpendSummary:
        self.calls.append(now)
        return self.summary


async def test_cost_hard_stop_runs_before_any_agent_creation() -> None:
    factory = _FakeFactory()
    reader = _FakeSpendReader(SpendSummary(today_usd=1.0, month_usd=1.0))
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_snapshot_with_cost_governance()),
        factory=factory,
        spend_reader=reader,
    )

    with pytest.raises(CostGovernanceError) as exc_info:
        await runner.run(
            "hola",
            user_id="88",
            session_id="tg:ancoramind:77",
            run_id="run-cost",
            correlation_id=uuid4(),
            telegram_update_id=9001,
        )

    assert exc_info.value.limit == "daily_budget_exhausted"
    assert factory.created_contexts == []
    assert factory.agent.calls == []
    assert len(reader.calls) == 1


async def test_cost_governance_without_spend_reader_fails_closed() -> None:
    factory = _FakeFactory()
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_snapshot_with_cost_governance()),
        factory=factory,
    )

    with pytest.raises(GovernanceViolationError, match="spend reader"):
        await runner.run(
            "hola",
            user_id="88",
            session_id="tg:ancoramind:77",
            run_id="run-cost",
            correlation_id=uuid4(),
            telegram_update_id=9001,
        )

    assert factory.created_contexts == []


class _FakeStopReader:
    def __init__(self, state: EmergencyStopState) -> None:
        self._state = state

    def current(self) -> EmergencyStopState:
        return self._state


async def test_emergency_stop_blocks_before_any_agent_creation() -> None:
    """BL-44/specs/031: a manual stop short-circuits before building the Agent."""
    factory = _FakeFactory()
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_snapshot()),
        factory=factory,
        stop_reader=_FakeStopReader(EmergencyStopState(active=True, reason="cost spike")),
    )

    with pytest.raises(EmergencyStopActiveError) as exc_info:
        await runner.run(
            "hola",
            user_id="88",
            session_id="tg:ancoramind:77",
            run_id="run-stop",
            correlation_id=uuid4(),
            telegram_update_id=9001,
        )

    assert exc_info.value.reason == "cost spike"
    assert factory.created_contexts == []
    assert factory.agent.calls == []


async def test_runner_proceeds_when_emergency_stop_is_inactive() -> None:
    factory = _FakeFactory()
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_snapshot()),
        factory=factory,
        stop_reader=_FakeStopReader(EmergencyStopState(active=False)),
    )

    output = await runner.run(
        "hola",
        user_id="88",
        session_id="tg:ancoramind:77",
        run_id="run-ok",
        correlation_id=uuid4(),
        telegram_update_id=9001,
    )

    assert output == "respuesta gobernada"
