"""Unit tests for the LLMAccess frontier and the per-run Agent factory."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import pytest
from agno.models.openai import OpenAIChat, OpenAILike

from src.agent.ancora_agent import SafeOpenAILike, SafeOpenRouter
from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_model import GovernedModelMixin
from src.agent.llm_access import AgnoLLMAccess
from src.config import Settings
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionContext,
    GovernanceViolationError,
    generate_traceparent,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


def _snapshot(revision: int = 1) -> RuntimeConfigSnapshot:
    config = bootstrap_runtime_configuration()
    return RuntimeConfigSnapshot(
        revision=revision,
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


def _access(provider: str = "openrouter") -> AgnoLLMAccess:
    settings = Settings(
        llm_provider=provider,
        llm_model="test/model",
        openrouter_api_key="router-key" if provider == "openrouter" else "",
        openai_api_key="" if provider == "openrouter" else "openai-key",
    )
    return AgnoLLMAccess(settings=settings, usage_recorder=None)


def test_model_for_composes_governed_adapter_over_safe_openrouter() -> None:
    model = _access().model_for("ancoramind-default", _context(_snapshot()))

    assert isinstance(model, SafeOpenRouter)
    assert isinstance(model, GovernedModelMixin)
    assert model.retries == 0
    assert model._governed_route_name == "ancoramind-default"
    assert model._governed_effective_route == "ancoramind-default-r1"
    assert model._governed_revision == 1


def test_model_for_supports_openai_provider() -> None:
    model = _access(provider="openai").model_for("ancoramind-fast", _context(_snapshot()))

    assert isinstance(model, OpenAIChat)
    assert isinstance(model, GovernedModelMixin)
    assert model._governed_route_name == "ancoramind-fast"


def test_model_for_uses_the_runs_snapshot_not_a_newer_one() -> None:
    context = _context(_snapshot(revision=7))

    model = _access().model_for("ancoramind-default", context)

    governed = model
    assert isinstance(governed, GovernedModelMixin)
    assert governed._governed_revision == 7


def test_model_for_fails_closed_on_unknown_route() -> None:
    with pytest.raises(GovernanceViolationError, match="unknown-route"):
        _access().model_for("unknown-route", _context(_snapshot()))


def test_factory_creates_agent_with_snapshot_ceilings_and_zero_retries() -> None:
    snapshot = _snapshot()
    context = _context(snapshot)

    class _FakeAccess:
        def model_for(self, route_name: str, execution_context: ExecutionContext) -> Any:
            return OpenAIChat(id="fake-model")

    factory = GovernedAgentFactory(
        llm_access=_FakeAccess(),
        db=None,
        tools=[],
        instructions=["instr"],
    )

    agent = factory.create_for_run(context)

    assert agent.tool_call_limit == snapshot.config.execution_budget.max_tool_calls == 12
    assert agent.retries == 0
    assert agent.telemetry is False
    assert isinstance(agent.model, OpenAIChat)
    assert agent.id == "ancoramind-governed"
    assert agent.output_schema is AgentReply
    assert agent.use_json_mode is True
    assert agent.parser_model is None
    assert agent.output_model is None


def test_factory_uses_run_snapshot_for_tool_ceiling() -> None:
    base = bootstrap_runtime_configuration()
    modified_config = base.model_copy(
        update={"execution_budget": base.execution_budget.model_copy(update={"max_tool_calls": 3})}
    )
    snapshot = RuntimeConfigSnapshot(
        revision=1,
        checksum=config_checksum(modified_config),
        source="database",
        config=modified_config,
    )
    context = _context(snapshot)

    class _FakeAccess:
        def model_for(self, route_name: str, execution_context: ExecutionContext) -> Any:
            return OpenAIChat(id="fake-model")

    factory = GovernedAgentFactory(
        llm_access=_FakeAccess(),
        db=None,
        tools=[],
        instructions=[],
    )

    assert factory.create_for_run(context).tool_call_limit == 3


def test_model_for_propagates_the_w3c_traceparent_to_the_gateway_request() -> None:
    context = _context(_snapshot())

    model = _access().model_for("ancoramind-default", context)

    assert model.extra_headers == {"traceparent": context.traceparent}


def test_model_for_uses_private_litellm_alias_instead_of_direct_provider() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="must-not-reach-openrouter-directly",
        openrouter_api_key="provider-secret-that-must-not-be-used",
        litellm_proxy_enabled=True,
        litellm_proxy_base_url="http://litellm.railway.internal:4000",
        litellm_proxy_virtual_key="sk-ancoramind-only",
    )
    context = _context(_snapshot())

    model = AgnoLLMAccess(settings=settings, usage_recorder=None).model_for(
        "ancoramind-fast", context
    )

    assert isinstance(model, OpenAILike)
    assert isinstance(model, SafeOpenAILike)
    assert isinstance(model, GovernedModelMixin)
    assert model.id == "ancoramind-fast-r1"
    assert str(model.base_url).rstrip("/") == "http://litellm.railway.internal:4000/v1"
    assert model.api_key == "sk-ancoramind-only"
    assert model._governed_provider_label == "litellm"
    assert model.extra_headers == {"traceparent": context.traceparent}
