"""BL-54: real Agno schemas/adapters, synthetic recurrence inputs, no inference."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from agno.run import RunContext
from agno.tools.function import Function, FunctionCall

from src.agent.instructions import assemble_instructions, load_prompt
from src.agent.tools import calendar, reminders
from src.agent.tools.validation import INVALID_RECURRENCE
from src.domain.shared.recurrence import recurrence_rule_from_flat, recurrence_rule_to_flat
from src.repositories.actions import ActionProposalsRepository

TOOLS = [
    pytest.param(calendar, calendar.propose_calendar_event, "start_at", id="calendar"),
    pytest.param(reminders, reminders.propose_reminder, "trigger_at", id="reminder"),
]
ANCHOR = "2026-11-01T10:00:00+01:00"
UNTIL = "2026-11-15T10:00:00+01:00"


def _context() -> RunContext:
    return RunContext(run_id="synthetic-bl54", session_id="synthetic-bl54", user_id="synthetic")


def _arguments(time_key, **changes):
    return {
        "title": "Synthetic BL54",
        time_key: ANCHOR,
        "recurrence_frequency": "weekly",
        "recurrence_interval": 2,
        "recurrence_until": UNTIL,
        **changes,
    }


@pytest.mark.parametrize("module,tool,time_key", TOOLS)
def test_real_agno_schema_requires_aware_until_and_bounded_interval(module, tool, time_key):
    function = Function.from_callable(tool)
    properties = function.parameters["properties"]
    until_description = " ".join(properties["recurrence_until"]["description"].split())
    assert "inclusive" in until_description.lower()
    assert "timezone-aware ISO 8601 datetime" in until_description
    assert "not a date-only or naive value" in until_description
    assert "2026-11-15T10:00:00+01:00" in until_description
    assert "explicit offset" in until_description
    assert "Ask for clarification" in until_description
    assert "1-365" in properties["recurrence_interval"]["description"]
    assert "run_context" not in properties
    assert properties["recurrence_until"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert function.parameters["required"] == ["title", time_key]


def test_loaded_calendar_prompt_matches_until_validation_without_inventing_timezone():
    prompt = load_prompt("skills/calendar.md")
    assert prompt in assemble_instructions()
    assert "timezone-aware ISO 8601 datetime" in prompt
    assert "Do not reduce it to a date" in prompt
    assert "ask for clarification in natural language" in prompt
    assert "Do not invent midnight or UTC" in prompt
    assert "with that end date" not in prompt


def test_reminder_asset_matches_same_contract_without_changing_assembly():
    prompt = load_prompt("skills/reminders.md")
    assert "timezone-aware ISO 8601 datetime" in prompt
    assert "Do not invent midnight or UTC" in prompt
    assert len(assemble_instructions()) == 10


@pytest.mark.parametrize("module,tool,time_key", TOOLS)
@pytest.mark.parametrize(
    "changes",
    [
        {"recurrence_until": "2026-11-15"},
        {"recurrence_until": "2026-11-15T10:00:00"},
        {"recurrence_until": "not-an-iso-datetime"},
        {"recurrence_interval": 0},
        {"recurrence_interval": 366},
        {"recurrence_frequency": "UNTRUSTED-frequency-<script>"},
    ],
    ids=["date-only", "naive", "invalid-datetime", "interval-zero", "interval-large", "frequency"],
)
async def test_invalid_recurrence_has_safe_complete_guidance_before_io(
    monkeypatch, module, tool, time_key, changes, caplog
):
    factory = AsyncMock(side_effect=AssertionError("must reject before DB access"))
    monkeypatch.setattr(module, "_get_actions_repo", factory)
    reply = await tool(_context(), **_arguments(time_key, **changes))
    assert "Regla de recurrencia no válida" in reply
    assert reply == INVALID_RECURRENCE
    assert "intervalo" in reply
    assert "1 y 365" in reply
    assert "fecha-hora ISO 8601 con zona explícita" in reply
    assert "No se ha creado ninguna propuesta" in reply
    assert "UNTRUSTED" not in reply + caplog.text
    assert "<script>" not in reply + caplog.text
    assert "frecuencia=" not in reply
    factory.assert_not_awaited()


@pytest.mark.parametrize("module,tool,time_key", TOOLS)
@pytest.mark.parametrize("through_agno", [False, True], ids=["direct", "agno"])
@pytest.mark.parametrize(
    "until", [UNTIL, "2026-11-15T09:00:00Z", "2026-11-15T09:00:00+00:00"]
)
async def test_aware_until_survives_adapter_and_round_trip(
    monkeypatch, module, tool, time_key, through_agno, until
):
    repo = AsyncMock(spec=ActionProposalsRepository)
    repo.create.return_value = {"id": "11111111-1111-1111-1111-111111111111"}
    monkeypatch.setattr(module, "_get_actions_repo", AsyncMock(return_value=repo))
    arguments = _arguments(time_key, recurrence_until=until)
    if through_agno:
        function = Function.from_callable(tool)
        function._run_context = _context()
        function.process_entrypoint()
        call = FunctionCall(function=function, arguments=arguments)
        outcome = await call.aexecute()
        assert outcome.status == "success"
        reply = outcome.result
    else:
        reply = await tool(_context(), **arguments)
    assert "Propuesta" in reply
    repo.create.assert_awaited_once()
    payload = repo.create.await_args.kwargs["payload"]
    assert repo.create.await_args.kwargs["user_id"] == "synthetic"
    assert payload[time_key] == ANCHOR
    assert payload["recurrence_until"] == datetime.fromisoformat(until).isoformat()
    rebuilt = recurrence_rule_from_flat(
        payload["recurrence_frequency"], payload["recurrence_interval"], payload["recurrence_until"]
    )
    assert rebuilt.until == datetime.fromisoformat(until)
    assert recurrence_rule_to_flat(rebuilt)["recurrence_until"] == payload["recurrence_until"]
    repo.confirm_or_use_confirmed.assert_not_awaited()
    repo.mark_executed.assert_not_awaited()


@pytest.mark.parametrize("module,tool,time_key", TOOLS)
@pytest.mark.parametrize(
    "frequency,interval,until",
    [("weekly", 1, None), ("weekly", 365, UNTIL), (None, 0, "ignored-invalid-bound")],
)
async def test_recurrence_bounds_and_no_frequency_behavior_are_unchanged(
    monkeypatch, module, tool, time_key, frequency, interval, until
):
    repo = AsyncMock(spec=ActionProposalsRepository)
    repo.create.return_value = {"id": "11111111-1111-1111-1111-111111111111"}
    monkeypatch.setattr(module, "_get_actions_repo", AsyncMock(return_value=repo))
    await tool(
        _context(), **_arguments(
            time_key, recurrence_frequency=frequency,
            recurrence_interval=interval, recurrence_until=until,
        ),
    )
    repo.create.assert_awaited_once()
    payload = repo.create.await_args.kwargs["payload"]
    assert payload["recurrence_frequency"] == frequency
    assert payload["recurrence_interval"] == (interval if frequency else None)
    assert payload["recurrence_until"] == (until if frequency else None)


@pytest.mark.parametrize("frequency", ["daily", "weekly", "monthly", "yearly"])
@pytest.mark.parametrize("until", ["2026-11-15", "2026-11-15T10:00:00"])
def test_parser_still_rejects_missing_timezone_for_all_frequencies(frequency, until):
    with pytest.raises(ValueError, match="timezone-aware"):
        recurrence_rule_from_flat(frequency, 2, until)


@pytest.mark.parametrize("module,tool,time_key", TOOLS)
async def test_agno_returns_validation_guidance_without_proposal_or_retry(
    monkeypatch, module, tool, time_key
):
    factory = AsyncMock(side_effect=AssertionError("must not open a DB session"))
    monkeypatch.setattr(module, "_get_actions_repo", factory)
    function = Function.from_callable(tool)
    function._run_context = _context()
    function.process_entrypoint()
    call = FunctionCall(
        function=function, arguments=_arguments(time_key, recurrence_until="2026-11-15")
    )
    result = await call.aexecute()
    # Agno success means the adapter returned, not a proposal or canonical write.
    assert result.status == "success"
    assert result.result == INVALID_RECURRENCE
    factory.assert_not_awaited()
