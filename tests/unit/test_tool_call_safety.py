"""BL-16 contract at the direct-provider and governed Gateway boundaries."""

from __future__ import annotations

import copy
import json
import time
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from agno.models.base import MessageData, Model
from agno.models.message import Message
from agno.models.openai import OpenAIChat
from agno.models.response import ModelResponse
from agno.tools.function import Function
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)

from src.agent.ancora_agent import create_model
from src.agent.governed_model import GovernanceStreamingOrSyncError
from src.agent.llm_access import AgnoLLMAccess
from src.config import Settings
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionBudgetExceededError,
    ExecutionContext,
    GovernanceViolationError,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


@pytest.fixture(params=["openrouter", "openai-like"])
def safe_model(request: pytest.FixtureRequest) -> Model:
    return create_model(
        provider=request.param,
        model_id="synthetic-model",
        api_key="synthetic-key",
        base_url="http://gateway.invalid/v1",
    )


def _valid_call() -> dict[str, Any]:
    return {
        "id": "valid-call",
        "type": "function",
        "function": {"name": "echo", "arguments": '{"value":"synthetic-value"}'},
    }


def _context() -> ExecutionContext:
    config = bootstrap_runtime_configuration()
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=10,
        agno_run_id="synthetic-run",
        agno_session_id="synthetic-session",
        config=RuntimeConfigSnapshot(
            revision=1, checksum=config_checksum(config), source="bootstrap", config=config
        ),
        budget=ExecutionBudget.from_config(
            config.execution_budget, started_at_monotonic=time.monotonic()
        ),
    )


@pytest.fixture(params=[False, True], ids=["direct-openrouter", "private-gateway"])
def governed_case(request: pytest.FixtureRequest) -> tuple[Model, ExecutionContext, AsyncMock]:
    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        llm_model="synthetic-model",
        openrouter_api_key="synthetic-provider-key",
        litellm_proxy_enabled=request.param,
        litellm_proxy_base_url="http://gateway.invalid:4000",
        litellm_proxy_virtual_key="synthetic-virtual-key",
    )
    context = _context()
    recorder = AsyncMock()
    model = AgnoLLMAccess(settings=settings, usage_recorder=recorder).model_for(
        "ancoramind-default", context
    )
    return model, context, recorder


@pytest.mark.parametrize("calls", [None, []])
def test_no_calls_preserves_content_without_warning(safe_model, calls, caplog):
    response = ModelResponse(content="Synthetic reply")
    response.tool_calls = calls
    populated = safe_model._populate_assistant_message(Message(role="assistant"), response)

    assert populated.content == "Synthetic reply"
    assert populated.tool_calls is None
    assert response.tool_calls is None
    assert not caplog.records


@pytest.mark.parametrize(
    "malformed",
    [
        {},
        {"id": "id-only"},
        {"type": "function", "function": None},
        {"type": "function", "function": {}},
        {"type": "function", "function": {"name": ""}},
        {"type": "function", "function": {"name": "  "}},
        {"type": "function", "function": {"name": 123}},
        {"type": "other", "function": {"name": "echo"}},
    ],
)
def test_malformed_entries_are_dropped_and_valid_calls_preserved(safe_model, malformed):
    valid = _valid_call()
    response = ModelResponse(tool_calls=[malformed, copy.deepcopy(valid)])

    populated = safe_model._populate_assistant_message(Message(role="assistant"), response)

    assert populated.tool_calls == [valid]
    assert response.tool_calls == [valid]


def test_valid_calls_without_id_keep_agno_id_generation_and_order(safe_model):
    first = _valid_call()
    del first["id"]
    second = _valid_call()
    second["id"] = "second-call"
    response = ModelResponse(tool_calls=[first, second])

    populated = safe_model._populate_assistant_message(Message(role="assistant"), response)

    assert len(populated.tool_calls) == 2
    assert populated.tool_calls[0]["id"]
    assert populated.tool_calls[0]["function"] == _valid_call()["function"]
    assert populated.tool_calls[1] == second


def test_filter_does_not_parse_or_rewrite_arguments(safe_model):
    calls = [_valid_call(), _valid_call()]
    calls[0]["function"]["arguments"] = "{invalid-json"
    del calls[1]["function"]["arguments"]
    expected = copy.deepcopy(calls)

    populated = safe_model._populate_assistant_message(
        Message(role="assistant"), ModelResponse(tool_calls=calls)
    )

    assert populated.tool_calls == expected


def test_streaming_filters_only_after_fragment_consolidation(safe_model):
    data = MessageData(
        response_content="Synthetic reply",
        response_tool_calls=[
            ChoiceDeltaToolCall(index=0, id="empty-call"),
            ChoiceDeltaToolCall(index=1, id="valid-call", type="function"),
            ChoiceDeltaToolCall(
                index=1,
                function=ChoiceDeltaToolCallFunction(name="echo", arguments='{"value":'),
            ),
            ChoiceDeltaToolCall(
                index=1,
                function=ChoiceDeltaToolCallFunction(arguments='"synthetic-value"}'),
            ),
        ],
    )
    assistant = Message(role="assistant")

    safe_model._populate_assistant_message_from_stream_data(assistant, data)

    assert assistant.content == "Synthetic reply"
    assert assistant.tool_calls == [_valid_call()]


@pytest.mark.parametrize("streaming", [False, True])
def test_warning_never_contains_tool_name_arguments_or_content(safe_model, caplog, streaming):
    response = ModelResponse(
        content="sensitive-content-marker",
        tool_calls=[
            {
                "id": "sensitive-id-marker",
                "function": {
                    "name": "sensitive-name-marker",
                    "arguments": "sensitive-arguments-marker",
                },
            },
            _valid_call(),
        ],
    )

    if streaming:
        safe_model._populate_assistant_message_from_stream_data(
            Message(role="assistant"),
            MessageData(
                response_content=response.content,
                response_tool_calls=[
                    ChoiceDeltaToolCall(
                        index=0,
                        id="sensitive-id-marker",
                        function=ChoiceDeltaToolCallFunction(
                            name="sensitive-name-marker", arguments="sensitive-arguments-marker"
                        ),
                    ),
                ],
            ),
        )
    else:
        safe_model._populate_assistant_message(Message(role="assistant"), response)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    # Full-suite app imports install the metadata-only JSON formatter. Check
    # the underlying record too: redaction must not hide a leaking log call.
    message = caplog.records[0].getMessage()
    assert "Dropped 1 malformed" in message
    assert "sensitive-" not in message + caplog.text
    assert "synthetic-value" not in message + caplog.text


async def test_legacy_async_stream_stops_after_only_malformed_calls(safe_model, monkeypatch):
    requests = 0

    async def invoke_stream(**kwargs):
        nonlocal requests
        requests += 1
        assert requests == 1, "Unexpected extra streaming model turn"
        yield ModelResponse(
            content="Synthetic reply", tool_calls=[ChoiceDeltaToolCall(index=0, id="id-only")]
        )

    monkeypatch.setattr(safe_model, "ainvoke_stream", invoke_stream)
    messages = [Message(role="user", content="Synthetic input")]

    async for _ in safe_model.aresponse_stream(messages=messages, tools=[]):
        pass

    assert requests == 1
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "Synthetic reply"
    assert messages[-1].tool_calls is None


async def test_governed_only_malformed_calls_stop_without_another_turn(governed_case, monkeypatch):
    model, context, recorder = governed_case
    provider = AsyncMock(return_value=ModelResponse(content="Synthetic reply", tool_calls=[{}]))
    monkeypatch.setattr(OpenAIChat, "ainvoke", provider)
    messages = [Message(role="user", content="Synthetic input")]

    with execution_context_scope(context):
        response = await model.aresponse(messages=messages, tools=[])

    assert response.content == "Synthetic reply"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].tool_calls is None
    assert provider.await_count == 1
    assert context.budget.model_calls == context.budget.gateway_requests == 1
    recorder.assert_awaited_once()
    assert recorder.call_args.args[0].status == "completed"
    assert model.retries == 0


async def test_governed_valid_call_executes_once_and_next_turn_receives_clean_history(
    governed_case, monkeypatch
):
    model, context, recorder = governed_case
    executed = []
    second_turn = []

    def echo(value: str) -> str:
        """Echo a synthetic value without external effects."""
        executed.append(value)
        return value

    calls = 0

    async def invoke(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(tool_calls=[{}, {"id": "id-only"}, _valid_call()])
        assert calls == 2, "Unexpected extra model turn"
        second_turn.extend(copy.deepcopy(kwargs["messages"]))
        return ModelResponse(content="Synthetic final reply")

    monkeypatch.setattr(OpenAIChat, "ainvoke", invoke)
    messages = [Message(role="user", content="Synthetic input")]

    with execution_context_scope(context):
        response = await model.aresponse(messages=messages, tools=[Function.from_callable(echo)])

    assert response.content == "Synthetic final reply"
    assert executed == ["synthetic-value"]
    assert calls == context.budget.model_calls == context.budget.gateway_requests == 2
    assert recorder.await_count == 2
    assert all(call.args[0].status == "completed" for call in recorder.call_args_list)
    assert [message.role for message in second_turn] == ["user", "assistant", "tool"]
    assert second_turn[1].tool_calls == [_valid_call()]
    assert second_turn[2].tool_call_id == "valid-call"
    assert [tc for msg in messages for tc in (msg.tool_calls or [])] == [_valid_call()]


async def test_governed_safety_does_not_bypass_context_or_budget(governed_case, monkeypatch):
    model, context, recorder = governed_case
    provider = AsyncMock()
    monkeypatch.setattr(OpenAIChat, "ainvoke", provider)

    with pytest.raises(GovernanceViolationError):
        await model.ainvoke(messages=[])
    context.budget.max_model_calls = 0
    with execution_context_scope(context), pytest.raises(ExecutionBudgetExceededError):
        await model.ainvoke(messages=[])

    provider.assert_not_awaited()
    recorder.assert_not_awaited()


async def test_governed_safety_does_not_enable_sync_or_streaming(governed_case):
    model, _, _ = governed_case

    with pytest.raises(GovernanceStreamingOrSyncError):
        model.invoke(messages=[])
    with pytest.raises(GovernanceStreamingOrSyncError):
        model.invoke_stream(messages=[])
    with pytest.raises(GovernanceStreamingOrSyncError):
        await model.ainvoke_stream(messages=[])


@pytest.mark.parametrize("with_valid_call", [False, True], ids=["only-empty", "empty-and-valid"])
async def test_governed_http_boundary_parses_malformed_calls_without_polluting_replay(
    governed_case, with_valid_call
):
    """Exercise the real SDK/parser and Agno loop without opening a socket."""
    model, context, recorder = governed_case
    requests = []
    executed = []
    valid = _valid_call()
    # OpenRouter rewrites IDs to its 40-character format on outgoing replay.
    valid["id"] = "call_" + "a" * 35

    def echo(value: str) -> str:
        """Echo a synthetic value without external effects."""
        executed.append(value)
        return value

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/chat/completions"
        assert request.url.host == "gateway.invalid"
        assert request.headers["authorization"] == f"Bearer {model.api_key}"
        assert body["model"] == model.id
        if len(requests) == 1:
            message = {"role": "assistant", "content": "Synthetic reply", "tool_calls": [{}]}
            if with_valid_call:
                message["tool_calls"].append(valid)
            reason = "tool_calls"
        else:
            assert with_valid_call and len(requests) == 2, "Unexpected extra HTTP request"
            assistant = next(msg for msg in body["messages"] if msg["role"] == "assistant")
            assert assistant["tool_calls"] == [valid]
            tools = [msg for msg in body["messages"] if msg["role"] == "tool"]
            assert len(tools) == 1 and tools[0]["tool_call_id"] == valid["id"]
            message = {"role": "assistant", "content": "Synthetic final reply"}
            reason = "stop"
        return httpx.Response(
            200,
            json={
                "id": "synthetic-completion",
                "object": "chat.completion",
                "created": 0,
                "model": model.id,
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client,
        AsyncOpenAI(
            api_key=model.api_key,
            base_url="http://gateway.invalid/v1",
            http_client=http_client,
            max_retries=0,
        ) as client,
    ):
        model.async_client = client
        with execution_context_scope(context):
            await model.aresponse(
                messages=[Message(role="user", content="Synthetic input")],
                tools=[Function.from_callable(echo)],
            )

    expected = 2 if with_valid_call else 1
    assert len(requests) == expected
    assert context.budget.model_calls == context.budget.gateway_requests == expected
    assert executed == (["synthetic-value"] if with_valid_call else [])
    assert recorder.await_count == expected
    assert all(call.args[0].status == "completed" for call in recorder.call_args_list)
