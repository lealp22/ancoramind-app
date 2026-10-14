"""Tests for BL-8/specs/018 T6b's isolated Core consent eval executor."""

from __future__ import annotations

import inspect
from dataclasses import replace
from uuid import UUID

import pytest

import src.agent.eval_core_consent_executor as core_executor_module
from src.agent.eval_core_consent_executor import CoreConsentEvalExecutor, SyntheticConsentStore
from src.agent.evals import (
    EvalCase,
    EvalExecutionRequest,
    execute_cases,
    load_eval_cases,
    metadata_report,
)
from src.domain.actions.models import ConsentPrincipal, ProposalStatus

_VEHICLE_ID = "11111111-1111-1111-1111-111111111111"
_REMINDER_ID = "22222222-2222-2222-2222-222222222222"


def test_core_consent_harness_has_no_repository_or_production_executor_imports() -> None:
    import_lines = [
        line
        for line in inspect.getsource(core_executor_module).splitlines()
        if line.startswith(("import ", "from "))
    ]

    for line in import_lines:
        assert "src.repositories" not in line
        assert "sqlalchemy" not in line
        assert "src.domain.actions.executor" not in line
        assert "src.domain.actions.trivial_executor" not in line


def _case(*, input_text: str, context: dict[str, object]) -> EvalCase:
    return EvalCase(
        case_id="confirmation.synthetic",
        category="confirmation",
        input_text=input_text,
        synthetic_context=context,
        expected_outcome="confirm_pending_action",
        required_tool="create_reminder",
        forbidden_tools=frozenset({"propose_reminder"}),
        requires_user_confirmation=False,
        response_criteria=(),
    )


def _request(*, input_text: str, context: dict[str, object]) -> EvalExecutionRequest:
    return EvalExecutionRequest(
        case=_case(input_text=input_text, context=context),
        logical_route="core-consent-eval",
        config_revision=0,
    )


async def test_core_executor_executes_the_one_presented_proposal_for_bare_si() -> None:
    observation = await CoreConsentEvalExecutor().execute(
        _request(
            input_text="Sí",
            context={"pending_proposal": {"id": _REMINDER_ID, "tool_name": "create_reminder"}},
        )
    )

    assert observation.outcome == "confirm_pending_action"
    assert observation.tool_names == ("create_reminder",)
    assert observation.requires_user_confirmation is False


@pytest.mark.parametrize(
    ("context", "input_text"),
    [
        ({}, "Sí"),
        (
            {
                "pending_proposals": [
                    {"id": _VEHICLE_ID, "tool_name": "register_vehicle"},
                    {"id": _REMINDER_ID, "tool_name": "create_reminder"},
                ]
            },
            "Sí",
        ),
        (
            {
                "pending_proposal": {
                    "id": _REMINDER_ID,
                    "tool_name": "create_reminder",
                    "presented": False,
                }
            },
            f"Sí {_REMINDER_ID}",
        ),
        (
            {
                "pending_proposal": {
                    "id": _REMINDER_ID,
                    "tool_name": "create_reminder",
                    "expired": True,
                }
            },
            f"Sí {_REMINDER_ID}",
        ),
        (
            {
                "pending_proposal": {
                    "id": _REMINDER_ID,
                    "tool_name": "create_reminder",
                    "chat_id": 9902,
                }
            },
            f"Sí {_REMINDER_ID}",
        ),
    ],
)
async def test_core_executor_never_executes_ineligible_or_ambiguous_confirmation(
    context: dict[str, object], input_text: str
) -> None:
    observation = await CoreConsentEvalExecutor().execute(
        _request(input_text=input_text, context=context)
    )

    assert observation.outcome == "safe_response"
    assert observation.tool_names == ()
    assert observation.requires_user_confirmation is False


async def test_discard_callback_is_terminal_without_a_logical_mutation() -> None:
    store = SyntheticConsentStore.from_context(
        {"pending_proposal": {"id": _VEHICLE_ID, "tool_name": "register_vehicle"}}
    )
    assert store.status_for_test(UUID(_VEHICLE_ID)) is ProposalStatus.PENDING_CONFIRMATION

    discarded = store.discard(
        UUID(_VEHICLE_ID),
        ConsentPrincipal(user_id="eval-synthetic-user", bot_id=8801, chat_id=9901),
    )

    assert discarded is True
    assert store.status_for_test(UUID(_VEHICLE_ID)) is ProposalStatus.DISCARDED


async def test_expired_claim_marks_only_the_per_case_synthetic_store_terminal() -> None:
    store = SyntheticConsentStore.from_context(
        {
            "pending_proposal": {
                "id": _REMINDER_ID,
                "tool_name": "create_reminder",
                "expired": True,
            }
        }
    )

    action, rejection = store.claim_and_execute(
        UUID(_REMINDER_ID),
        principal=ConsentPrincipal(user_id="eval-synthetic-user", bot_id=8801, chat_id=9901),
    )

    assert action is None
    assert rejection is not None and rejection.value == "expired"
    assert store.status_for_test(UUID(_REMINDER_ID)) is ProposalStatus.EXPIRED


async def test_confirmation_catalog_executes_through_core_harness_and_reports_metadata_only() -> (
    None
):
    cases = load_eval_cases(categories={"confirmation"})

    results = await execute_cases(
        cases,
        executor=CoreConsentEvalExecutor(),
        logical_route="core-consent-eval",
        config_revision=0,
    )
    report = metadata_report(results)

    assert len(results) == 7
    assert all(result.passed for result in results)
    assert report["passed_count"] == 7
    serialized = str(report)
    assert "Sí" not in serialized
    assert _VEHICLE_ID not in serialized


async def test_core_executor_rejects_non_confirmation_cases() -> None:
    request = _request(input_text="Sí", context={})
    non_confirmation = replace(request.case, category="security")

    with pytest.raises(ValueError, match="only accepts confirmation"):
        await CoreConsentEvalExecutor().execute(
            EvalExecutionRequest(
                case=non_confirmation,
                logical_route=request.logical_route,
                config_revision=request.config_revision,
            )
        )


async def test_write_trivial_has_an_immediate_synthetic_effect_without_confirmation() -> None:
    observation = await CoreConsentEvalExecutor().execute(
        _request(
            input_text="Añade comprar leche a Ensayo.",
            context={"trivial_mutation": "create_todo_item"},
        )
    )

    assert observation.outcome == "tool_call"
    assert observation.tool_names == ("create_todo_item",)
    assert observation.requires_user_confirmation is False
