"""Unit tests for the physical BL-8 eval executor (specs/018 T6).

Uses a scripted, in-memory Agno `Model` — the same pattern already proven in
`tests/unit/test_tool_budget_hooks.py` (`_ScriptedToolModel`) — wired through
a fake `LLMAccess`. No network call, no credentials, no cost: this is the T6
wiring test, not T7 (real LLM execution, separately gated).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse

from src.agent.eval_physical_executor import GovernedPhysicalEvalExecutor
from src.agent.evals import EvalCase, EvalExecutionRequest
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.models import ExecutionContext


@dataclass
class _ScriptedModel(Model):
    """Deterministic in-memory provider: returns each entry of `turns` in order."""

    turns: tuple[ModelResponse, ...] = ()
    calls: int = field(default=0, repr=False)

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
        turn = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        return turn


def _tool_call_turn(call_id: str, name: str, arguments: str) -> ModelResponse:
    return ModelResponse(
        tool_calls=[
            {
                "type": "function",
                "id": call_id,
                "function": {"name": name, "arguments": arguments},
            }
        ]
    )


@dataclass
class _FakeLLMAccess:
    """Returns the same scripted model regardless of route/context."""

    model: Model

    def model_for(self, route_name: str, execution_context: ExecutionContext) -> Model:
        return self.model


def _case(
    *,
    input_text: str,
    synthetic_context: dict[str, object] | None = None,
    required_tool: str | None = None,
) -> EvalCase:
    return EvalCase(
        case_id="eval-physical-executor-test",
        category="tool_selection",
        input_text=input_text,
        synthetic_context=synthetic_context or {},
        expected_outcome="tool_call",
        required_tool=required_tool,
        forbidden_tools=frozenset(),
        requires_user_confirmation=False,
        response_criteria=(),
    )


async def test_tool_call_is_observed_as_tool_call_outcome() -> None:
    model = _ScriptedModel(
        id="eval-test",
        turns=(
            _tool_call_turn("call-1", "search_notes", "{}"),
            ModelResponse(
                content=AgentReply(
                    answer="Aquí tienes tu nota.", proposal_text=""
                ).model_dump_json()
            ),
        ),
    )
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model=model))
    request = EvalExecutionRequest(
        case=_case(input_text="¿Qué apunté sobre mi coche?"),
        logical_route="ancoramind-default",
        config_revision=0,
    )

    observation = await executor.execute(request)

    assert observation.outcome == "tool_call"
    assert observation.tool_names == ("search_notes",)
    assert observation.requires_user_confirmation is False
    assert observation.response_text == "Aquí tienes tu nota."


async def test_propose_tool_call_requires_user_confirmation() -> None:
    model = _ScriptedModel(
        id="eval-test",
        turns=(
            _tool_call_turn(
                "call-1",
                "propose_reminder",
                '{"title": "Llamar al dentista", "trigger_at": "2026-01-01T10:00:00"}',
            ),
            ModelResponse(content=AgentReply(answer="", proposal_text="").model_dump_json()),
        ),
    )
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model=model))
    request = EvalExecutionRequest(
        case=_case(input_text="Recuérdame llamar al dentista mañana a las 10."),
        logical_route="ancoramind-default",
        config_revision=0,
    )

    observation = await executor.execute(request)

    assert observation.outcome == "tool_call"
    assert observation.tool_names == ("propose_reminder",)
    assert observation.requires_user_confirmation is True


async def test_legacy_confirmation_case_is_rejected_before_inference() -> None:
    model = _ScriptedModel(
        id="eval-test",
        turns=(
            _tool_call_turn(
                "call-1",
                "execute_vehicle",
                '{"proposal_id": "synthetic-vehicle-proposal"}',
            ),
            ModelResponse(
                content=AgentReply(
                    answer="Vehículo registrado.", proposal_text=""
                ).model_dump_json()
            ),
        ),
    )
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model=model))
    request = EvalExecutionRequest(
        case=_case(
            input_text="Sí, confirma.",
            synthetic_context={
                "pending_proposal": {
                    "id": "synthetic-vehicle-proposal",
                    "tool_name": "create_vehicle",
                }
            },
            required_tool="execute_vehicle",
        ),
        logical_route="ancoramind-default",
        config_revision=0,
    )

    with pytest.raises(ValueError, match="deterministic consent harness"):
        await executor.execute(request)
    assert model.calls == 0


async def test_no_tool_call_is_a_distinct_sentinel_not_clarify_or_safe_response() -> None:
    """Known T6 scope limit: clarify vs safe_response needs a semantic judge (T8)."""
    model = _ScriptedModel(
        id="eval-test",
        turns=(
            ModelResponse(
                content=AgentReply(
                    answer="No tengo esa información.", proposal_text=""
                ).model_dump_json()
            ),
        ),
    )
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model=model))
    request = EvalExecutionRequest(
        case=_case(input_text="¿Qué es una lista de tareas?"),
        logical_route="ancoramind-default",
        config_revision=0,
    )

    observation = await executor.execute(request)

    assert observation.outcome == "no_tool_call"
    assert observation.outcome not in ("clarify", "safe_response")
    assert observation.tool_names == ()
    assert observation.requires_user_confirmation is False
