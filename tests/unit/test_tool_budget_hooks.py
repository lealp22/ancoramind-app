"""Unit tests for the T8 tool budget hook and tool-call fingerprints."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import pytest
from agno.agent import Agent
from agno.exceptions import StopAgentRun
from agno.models.base import Model
from agno.models.response import ModelResponse

from src.agent.tool_budget_hooks import build_budget_tool_hook
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.fingerprints import (
    canonical_tool_call_json,
    compute_tool_fingerprint,
    derive_fingerprint_key,
)
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

KEY = "unit-test-fingerprint-key"


class _ScriptedToolModel(Model):
    """Minimal real Agno provider for testing async tool-hook integration."""

    provider_calls = 0

    def invoke(self, *args: Any, **kwargs: Any) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError
        yield  # pragma: no cover

    def _parse_provider_response(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def _parse_provider_response_delta(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke(self, messages: Any = None, **kwargs: Any) -> ModelResponse:
        type(self).provider_calls += 1
        if type(self).provider_calls == 1:
            return ModelResponse(
                tool_calls=[
                    {
                        "type": "function",
                        "id": "call-1",
                        "function": {"name": "echo", "arguments": '{"value":"hola"}'},
                    }
                ]
            )
        return ModelResponse(content="listo")


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


def test_fingerprint_is_stable_and_argument_order_insensitive() -> None:
    first = compute_tool_fingerprint(KEY, "search_notes", {"query": "hola", "limit": 5})
    second = compute_tool_fingerprint(KEY, "search_notes", {"limit": 5, "query": "hola"})
    other = compute_tool_fingerprint(KEY, "search_notes", {"query": "hola", "limit": 6})

    assert first == second
    assert first != other
    assert len(first) == 32


def test_fingerprint_differs_per_key_and_tool() -> None:
    assert compute_tool_fingerprint(KEY, "t", {}) != compute_tool_fingerprint("k2", "t", {})
    assert compute_tool_fingerprint(KEY, "a", {}) != compute_tool_fingerprint(KEY, "b", {})


def test_derived_key_is_deterministic_and_requires_material() -> None:
    derived = derive_fingerprint_key("secret")
    assert derived is not None
    assert derive_fingerprint_key("secret") == derived
    assert derive_fingerprint_key(None) is None
    assert derive_fingerprint_key("") is None


def test_canonical_json_is_deterministic() -> None:
    assert canonical_tool_call_json("t", {"a": 1, "b": [1, 2]}) == canonical_tool_call_json(
        "t", {"b": [1, 2], "a": 1}
    )


async def test_hook_records_success_and_blocks_identical_repeat() -> None:
    hook = build_budget_tool_hook(KEY)
    context = _context()
    calls: list[str] = []

    def tool(**kwargs: Any) -> str:
        calls.append(kwargs["q"])
        return "ok"

    with execution_context_scope(context):
        first = await hook(name="search_notes", func=tool, args={"q": "hola"})
        with pytest.raises(StopAgentRun) as exc_info:
            await hook(name="search_notes", func=tool, args={"q": "hola"})
        assert "max_same_tool_args_after_success" in str(exc_info.value)
        await hook(name="search_notes", func=tool, args={"q": "otra"})

    assert first == "ok"
    assert calls == ["hola", "otra"]
    assert context.budget.tool_calls == 2
    assert (
        context.budget.successful_tool_fingerprints[
            compute_tool_fingerprint(KEY, "search_notes", {"q": "hola"})
        ]
        == 1
    )


async def test_hook_blocks_tool_before_execution_on_violation() -> None:
    hook = build_budget_tool_hook(KEY)
    context = _context()
    context.budget.max_tool_calls = 1
    executed: list[int] = []

    def tool(**kwargs: Any) -> int:
        executed.append(1)
        return len(executed)

    with execution_context_scope(context):
        await hook(name="t", func=tool, args={})
        with pytest.raises(StopAgentRun):
            await hook(name="t", func=tool, args={})

    assert executed == [1]


async def test_hook_failure_keeps_one_retry_then_blocks() -> None:
    hook = build_budget_tool_hook(KEY)
    context = _context()
    attempts: list[int] = []

    def failing_tool(**kwargs: Any) -> None:
        attempts.append(1)
        raise RuntimeError("tool boom")

    with execution_context_scope(context):
        for _ in range(2):
            with pytest.raises(RuntimeError, match="tool boom"):
                await hook(name="t", func=failing_tool, args={"a": 1})
        with pytest.raises(StopAgentRun):
            await hook(name="t", func=failing_tool, args={"a": 1})

    assert len(attempts) == 2
    assert context.budget.tool_calls == 2


async def test_hook_fails_closed_without_governed_context() -> None:
    hook = build_budget_tool_hook(KEY)

    with pytest.raises(GovernanceViolationError):
        await hook(name="t", func=lambda **kw: None, args={})


async def test_real_agno_agent_awaits_hook_for_async_tool() -> None:
    """Protect against regressions in the Agno 2.9.0 hook integration contract."""
    _ScriptedToolModel.provider_calls = 0
    context = _context()
    executions: list[str] = []

    async def echo(value: str = "") -> str:
        await asyncio.sleep(0)
        executions.append(value)
        return f"eco:{value}"

    with execution_context_scope(context):
        agent = Agent(
            id="tool-hook-contract",
            model=_ScriptedToolModel(id="scripted"),
            tools=[echo],
            tool_call_limit=12,
            retries=0,
            tool_hooks=[build_budget_tool_hook(KEY)],
            markdown=False,
            add_datetime_to_context=False,
            add_history_to_context=False,
        )
        output = await agent.arun("usa echo", stream=False)

    assert output.content == "listo"
    assert executions == ["hola"]
    assert context.budget.tool_calls == 1
    assert len(context.budget.successful_tool_fingerprints) == 1


async def test_real_agno_agent_stops_repeated_tool_loop_without_third_model_call() -> None:
    """StopAgentRun prevents an identical-tool loop from amplifying inference."""

    class _LoopingToolModel(_ScriptedToolModel):
        provider_calls = 0

        async def ainvoke(self, messages: Any = None, **kwargs: Any) -> ModelResponse:
            type(self).provider_calls += 1
            return ModelResponse(
                tool_calls=[
                    {
                        "type": "function",
                        "id": f"call-{type(self).provider_calls}",
                        "function": {"name": "echo", "arguments": '{"value":"hola"}'},
                    }
                ]
            )

    context = _context()
    executions: list[str] = []

    async def echo(value: str = "") -> str:
        executions.append(value)
        return f"eco:{value}"

    with execution_context_scope(context):
        agent = Agent(
            id="tool-loop-contract",
            model=_LoopingToolModel(id="looping"),
            tools=[echo],
            tool_call_limit=12,
            retries=0,
            tool_hooks=[build_budget_tool_hook(KEY)],
            markdown=False,
            add_datetime_to_context=False,
            add_history_to_context=False,
        )
        await agent.arun("repite echo", stream=False)

    assert _LoopingToolModel.provider_calls == 2
    assert executions == ["hola"]
    assert context.budget.tool_calls == 1
