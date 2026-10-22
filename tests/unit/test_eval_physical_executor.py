"""Unit tests for the physical BL-8 eval executor (specs/018 T6).

Uses a scripted, in-memory Agno `Model` — the same pattern already proven in
`tests/unit/test_tool_budget_hooks.py` (`_ScriptedToolModel`) — wired through
a fake `LLMAccess`. No network call, no credentials, no cost: this is the T6
wiring test, not T7 (real LLM execution, separately gated).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.run.agent import RunOutput, ToolExecution
from agno.run.base import RunStatus

from src.agent.eval_physical_executor import GovernedPhysicalEvalExecutor, eval_snapshot_fingerprint
from src.agent.evals import EvalCase, EvalExecutionRequest, evaluate_observation
from src.domain.interactions.reply import AgentReply, InvalidPresentationOutputError
from src.domain.llm_access.models import ExecutionContext
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


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


@pytest.mark.parametrize("tools,reason", [
    (None, "missing_terminal"),
    ([ToolExecution(tool_name="present_reply", result="PRIVATE_INVALID_JSON")],
     "invalid_terminal_payload"),
    ([ToolExecution(tool_name="present_reply", tool_call_error=True, result="PRIVATE_ERROR")],
     "terminal_tool_error"),
])
async def test_missing_terminal_preserves_only_fixed_diagnostic_not_model_content(
    monkeypatch, tools, reason,
):
    from agno.agent import Agent

    output = RunOutput(content="PRIVATE_RESPONSE_MUST_NOT_BE_EXPORTED", tools=tools,
                       status=RunStatus.error)
    arun = AsyncMock(return_value=output)
    monkeypatch.setattr(Agent, "arun", arun)
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(_ScriptedModel(id="eval")))
    with pytest.raises(InvalidPresentationOutputError) as error:
        await executor.execute(EvalExecutionRequest(
            _case(input_text="Synthetic"), "ancoramind-default", 0,
        ))
    assert error.value.diagnostic.reason == reason
    assert error.value.diagnostic.presentation_count == (1 if tools else 0)
    assert error.value.diagnostic.run_status == "ERROR"
    assert "PRIVATE" not in str(error.value) + repr(error.value.diagnostic)
    assert arun.await_count == 1


async def test_mixed_read_proposal_scripted_success_preserves_both_parts():
    from pathlib import Path

    from src.agent.eval_campaign import EvalCampaignPlan

    folder = Path(__file__).resolve().parents[2] / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text(),
    )
    case = plan.validate_snapshot(snapshot)[1]
    list_id = "11111111-1111-1111-1111-111111111111"
    reply = AgentReply(answer="Revisar recibos: completada.", proposal_text="Propuesta preparada.")
    model = _ScriptedModel(id="eval-test", turns=(
        _tool_call_turn("lists", "list_todo_lists", "{}"),
        _tool_call_turn("items", "list_todo_items", '{"list_id":"' + list_id + '"}'),
        _tool_call_turn("propose", "propose_todo_item", '{"list_id":"' + list_id
                        + '","title":"Revisar póliza","priority":"high"}'),
        _tool_call_turn("reply", "present_reply", reply.model_dump_json()),
    ))
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model), snapshot=snapshot,
                                          budget=plan.budget)
    request = EvalExecutionRequest(case, plan.logical_route, snapshot.revision)
    observed = await executor.execute(request)
    assert evaluate_observation(request, observed).passed
    assert observed.reply == reply
    assert observed.tool_names == ("list_todo_lists", "list_todo_items", "propose_todo_item")
    assert observed.proposals[0]["created_this_run"] is True
    assert reply.answer in observed.delivered_text and "Prioridad: alta" in observed.delivered_text
    assert model.calls == 4


@pytest.mark.parametrize("extra,created", [("", False),
                                          (',"priority":"high","due_date":"2026-11-20"', True)])
async def test_proposal_verdict_depends_on_state_not_function_name(extra, created):
    from dataclasses import replace
    case = replace(_case(input_text="Synthetic", required_tool="propose_todo_item"),
                   requires_user_confirmation=True)
    model = _ScriptedModel(id="eval-test", turns=(
        _tool_call_turn("one", "propose_todo_item",
                        '{"list_id":"synthetic-list","title":"Revisar póliza"' + extra + '}'),
        _tool_call_turn("reply", "present_reply", AgentReply(
            answer="", proposal_text="Propuesta creada.",
        ).model_dump_json()),
    ))
    request = EvalExecutionRequest(case, "ancoramind-default", 0)
    observed = await GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model)).execute(request)
    assert bool(observed.proposals) is created
    assert evaluate_observation(request, observed).passed is created
    assert bool(observed.delivered_text) is created
    if created:
        assert observed.proposals[0]["payload"]["priority"] == "high"
        assert "2026-11-20" in observed.delivered_text
        assert "alta" in observed.delivered_text
    assert observed.tool_trace[0]["name"] == "propose_todo_item"


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
            _tool_call_turn(
                "reply-1",
                "present_reply",
                AgentReply(answer="Aquí tienes tu nota.", proposal_text="").model_dump_json(),
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


async def test_explicit_snapshot_identity_and_narrow_budget_are_used() -> None:
    config = bootstrap_runtime_configuration()
    snapshot = RuntimeConfigSnapshot(
        revision=8, source="database", checksum=config_checksum(config), config=config
    )
    model = _ScriptedModel(
        id="synthetic",
        turns=(_tool_call_turn(
            "reply", "present_reply",
            AgentReply(answer="Respuesta sintética.", proposal_text="").model_dump_json()
        ),),
    )
    budget = config.execution_budget.model_copy(update={"max_output_tokens": 128})
    executor = GovernedPhysicalEvalExecutor(
        llm_access=_FakeLLMAccess(model=model), snapshot=snapshot, budget=budget
    )
    request = EvalExecutionRequest(
        case=_case(input_text="Pregunta sintética"),
        logical_route="ancoramind-default", config_revision=8,
    )
    assert (await executor.execute(request)).response_text == "Respuesta sintética."
    assert model.max_tokens == 128
    first = executor._build_execution_context()
    second = executor._build_execution_context()
    assert first.config.checksum == snapshot.checksum
    assert first.config.revision == 8
    assert first.budget.max_model_calls == budget.max_model_calls
    assert first.budget is not second.budget
    assert first.correlation_id != second.correlation_id
    assert first.provenance is None


async def test_revision_mismatch_rejected_before_model_resolution() -> None:
    model = _ScriptedModel(id="synthetic")
    executor = GovernedPhysicalEvalExecutor(llm_access=_FakeLLMAccess(model=model))
    with pytest.raises(ValueError, match="revision_mismatch"):
        await executor.execute(EvalExecutionRequest(
            case=_case(input_text="Pregunta sintética"),
            logical_route="ancoramind-default", config_revision=8,
        ))
    assert model.calls == 0


def test_bad_fingerprint_or_expanded_budget_is_rejected() -> None:
    config = bootstrap_runtime_configuration()
    snapshot = RuntimeConfigSnapshot(
        revision=8, source="database", checksum=config_checksum(config), config=config
    )
    access = _FakeLLMAccess(model=_ScriptedModel(id="synthetic"))
    with pytest.raises(ValueError, match="fingerprint_mismatch"):
        GovernedPhysicalEvalExecutor(
            llm_access=access, snapshot=snapshot.model_copy(update={"checksum": "0" * 64}),
            snapshot_fingerprint=eval_snapshot_fingerprint(snapshot),
        )
    with pytest.raises(ValueError, match="may_not_expand"):
        GovernedPhysicalEvalExecutor(
            llm_access=access, snapshot=snapshot,
            budget=config.execution_budget.model_copy(update={"max_output_tokens": 32768}),
        )


async def test_propose_tool_call_requires_user_confirmation() -> None:
    model = _ScriptedModel(
        id="eval-test",
        turns=(
            _tool_call_turn(
                "call-1",
                "propose_reminder",
                '{"title": "Llamar al dentista", "trigger_at": "2026-01-01T10:00:00"}',
            ),
            _tool_call_turn(
                "reply-1",
                "present_reply",
                AgentReply(answer="", proposal_text="Propuesta creada.").model_dump_json(),
            ),
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
            _tool_call_turn(
                "reply-1",
                "present_reply",
                AgentReply(answer="No tengo esa información.", proposal_text="").model_dump_json(),
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
