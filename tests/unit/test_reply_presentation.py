"""Real governed Agent/SDK loop over synthetic HTTP, without network or DB."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from agno.run.agent import RunOutput, ToolExecution

from src.agent.ancora_agent import SafeOpenAILike
from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_model import build_governed_model
from src.agent.instructions import assemble_instructions
from src.agent.reply_presentation import reply_from_run
from src.domain.interactions.reply import AgentReply, InvalidPresentationOutputError
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import ExecutionBudget, ExecutionContext
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


def _context() -> ExecutionContext:
    config = bootstrap_runtime_configuration()
    snapshot = RuntimeConfigSnapshot(
        revision=1, checksum=config_checksum(config), source="bootstrap", config=config
    )
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=1,
        agno_run_id="synthetic",
        agno_session_id="synthetic",
        config=snapshot,
        budget=ExecutionBudget.from_config(
            config.execution_budget, started_at_monotonic=time.monotonic()
        ),
    )


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{name}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


@pytest.mark.parametrize(
    "scenario", ["lists", "items", "proposal", "greeting", "mixed", "trivial", "not_found", "error"]
)
async def test_sdk_loop_uses_native_tools_then_terminal_presentation(scenario: str) -> None:
    executed: list[str] = []

    async def list_todo_lists() -> str:
        """Return synthetic lists without a database."""
        executed.append("list_todo_lists")
        if scenario == "not_found":
            return "No tienes listas TODO todavía."
        if scenario == "error":
            return "Error interno al procesar la operación."
        return 'Datos recuperados: {"records":[{"id":"synthetic-list","name":"Casas"}]}'

    async def list_todo_items(list_id: str) -> str:
        """Return synthetic tasks for the resolved list."""
        assert list_id == "synthetic-list"
        executed.append("list_todo_items")
        return "Comprar café — pendiente."

    async def propose_todo_list(name: str) -> str:
        """Simulate proposal persistence, never create a canonical list."""
        assert name == "Casa"
        executed.append("propose_todo_list")
        return "Propuesta persistida en el store sintético."

    async def propose_todo_item(list_id: str, title: str) -> str:
        """Simulate an audited trivial mutation."""
        assert list_id == "synthetic-list" and title == "Comprar café"
        executed.append("propose_todo_item")
        return "Tarea añadida y auditada."

    terminal = {
        "lists": {"answer": "Casas.", "proposal_text": ""},
        "items": {"answer": "Comprar café — pendiente.", "proposal_text": ""},
        "proposal": {"answer": "", "proposal_text": "Propuesta creada."},
        "greeting": {"answer": "Hola.", "proposal_text": ""},
        "mixed": {"answer": "Casas.", "proposal_text": "Propuesta creada."},
        "trivial": {"answer": "Tarea añadida y auditada.", "proposal_text": ""},
        "not_found": {"answer": "No tienes listas TODO todavía.", "proposal_text": ""},
        "error": {"answer": "Error interno al procesar la operación.", "proposal_text": ""},
    }[scenario]
    sequence = {
        "lists": [_call("list_todo_lists", {})],
        "items": [
            _call("list_todo_lists", {}),
            _call("list_todo_items", {"list_id": "synthetic-list"}),
        ],
        "proposal": [_call("propose_todo_list", {"name": "Casa"})],
        "greeting": [],
        "mixed": [_call("list_todo_lists", {}), _call("propose_todo_list", {"name": "Casa"})],
        "trivial": [
            _call("list_todo_lists", {}),
            _call("propose_todo_item", {"list_id": "synthetic-list", "title": "Comprar café"}),
        ],
        "not_found": [_call("list_todo_lists", {})],
        "error": [_call("list_todo_lists", {})],
    }[scenario]
    sequence.append(_call("present_reply", terminal))
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "response_format" not in body
        assert body["tool_choice"] == "required"
        names = {item["function"]["name"] for item in body["tools"]}
        assert "present_reply" in names and not any(name.startswith("execute_") for name in names)
        presentation = next(
            item["function"]
            for item in body["tools"]
            if item["function"]["name"] == "present_reply"
        )
        assert set(presentation["parameters"]["properties"]) == {"answer", "proposal_text"}
        assert "exactly once, as the last tool call" in presentation["description"]
        system = next(item["content"] for item in body["messages"] if item["role"] == "system")
        assert "Start your response with" not in system
        assert "json.loads()" not in system
        if requests:
            prior = sequence[len(requests) - 1]["tool_calls"][0]
            assert any(
                item["role"] == "tool" and item["tool_call_id"] == prior["id"]
                for item in body["messages"]
            )
        assert len(requests) < len(sequence), "Unexpected inference after terminal tool"
        message = sequence[len(requests)]
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": "synthetic",
                "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    recorder = AsyncMock()
    context = _context()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        model = build_governed_model(
            SafeOpenAILike,
            {
                "id": "synthetic",
                "api_key": "synthetic-not-a-secret",
                "base_url": "https://synthetic.invalid/v1",
                "http_client": client,
            },
            recorder=recorder,
            route_name="ancoramind-default",
            effective_route="synthetic",
            revision=1,
            provider_label="synthetic",
        )

        class FakeAccess:
            def model_for(self, route_name: str, execution_context: ExecutionContext) -> Any:
                return model

        factory = GovernedAgentFactory(
            llm_access=FakeAccess(),
            db=None,
            tools=[list_todo_lists, list_todo_items, propose_todo_list, propose_todo_item],
            instructions=assemble_instructions(),
            fingerprint_key="synthetic-fingerprint-key",
        )
        with execution_context_scope(context):
            output = await factory.create_for_run(context).arun("Petición sintética", stream=False)
    assert reply_from_run(output) == AgentReply(**terminal)
    expected = [item["tool_calls"][0]["function"]["name"] for item in sequence]
    assert executed == expected[:-1]
    assert len(requests) == context.budget.model_calls == recorder.await_count == len(sequence)
    assert context.budget.tool_calls == len(sequence)  # presentation consumes the same budget


@pytest.mark.parametrize(
    "text",
    [
        "Necesito localizar tu lista Casas. Déjame ver tus listas.",
        "Déjame consultar tus listas de tareas.",
        "He creado una propuesta para Casa. Confirma si quieres guardarla.",
        '{"answer":"","proposal_text":""}',
    ],
)
def test_premature_completion_cannot_be_used_as_terminal_tool_result(text: str) -> None:
    with pytest.raises(InvalidPresentationOutputError, match="invalid presentation output"):
        reply_from_run(RunOutput(content=text))


@pytest.mark.parametrize(
    "executions",
    [
        [
            ToolExecution(
                tool_name="present_reply",
                result='{"answer":"hola","proposal_text":""}',
                tool_call_error=True,
            )
        ],
        [ToolExecution(tool_name="present_reply", result=None)],
        [ToolExecution(tool_name="present_reply", result='{"answer":"","proposal_text":""}')],
        [
            ToolExecution(tool_name="present_reply", result='{"answer":"hola","proposal_text":""}'),
            ToolExecution(tool_name="list_todo_lists", result="Casas"),
        ],
        [ToolExecution(tool_name="present_reply", result='{"answer":"hola","proposal_text":""}')]
        * 2,
    ],
)
def test_failed_empty_duplicate_or_nonterminal_presentations_are_rejected(executions) -> None:
    with pytest.raises(ValueError):
        reply_from_run(RunOutput(tools=executions))
