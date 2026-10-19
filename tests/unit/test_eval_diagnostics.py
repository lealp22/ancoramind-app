"""Terminal failure reasons without provider I/O, rejected prose or relaxed consent."""

import json

import pytest
from agno.run.agent import RunOutput, ToolExecution
from agno.run.base import RunStatus
from pydantic import ValidationError

from src.agent.eval_diagnostics import (
    safe_error_class,
    safe_terminal_diagnostic,
    terminal_diagnostic,
)
from src.agent.reply_presentation import reply_from_run

PRIVATE = "PRIVATE_RESPONSE_OR_ARGUMENT_MUST_NOT_BE_EXPORTED"


def terminal(**changes):
    return ToolExecution(**{
        "tool_name": "present_reply", "tool_args": {"answer": PRIVATE},
        "result": '{"answer":"synthetic","proposal_text":""}', **changes,
    })


@pytest.mark.parametrize("tools,reason", [
    ([], "missing_terminal"), ([terminal(), terminal()], "multiple_terminals"),
    ([terminal(), ToolExecution(tool_name=PRIVATE, result=PRIVATE)], "terminal_not_last"),
    ([terminal(tool_call_error=True, result=PRIVATE)], "terminal_tool_error"),
    ([terminal(result=None)], "terminal_result_not_string"),
    ([terminal(result=PRIVATE)], "invalid_terminal_payload"),
    ([terminal(result='{"answer":"","proposal_text":""}')], "invalid_terminal_payload"),
])
def test_rejected_variants_have_fixed_diagnostics_and_still_reject(tools, reason):
    output = RunOutput(tools=tools, content=PRIVATE, status=RunStatus.completed)
    with pytest.raises((ValueError, ValidationError)):
        reply_from_run(output)
    value = terminal_diagnostic(output)
    assert value.reason == reason
    assert value.tool_execution_count == len(tools)
    assert value.run_status == "COMPLETED"
    assert PRIVATE not in value.model_dump_json()
    assert safe_terminal_diagnostic(value.model_dump()) == value.model_dump()


def test_failed_runtime_is_a_fact_not_attributed_to_model_or_provider():
    value = terminal_diagnostic(RunOutput(content=PRIVATE, status=RunStatus.error))
    assert value.run_status == "ERROR" and value.reason == "missing_terminal"
    assert PRIVATE not in value.model_dump_json()


@pytest.mark.parametrize("change", [
    {"reason": PRIVATE}, {"presentation_count": "0"}, {"presentation_count": -1},
    {"tool_execution_count": True}, {"run_status": PRIVATE}, {"extra": PRIVATE},
])
def test_malformed_stored_diagnostic_never_leaks(change):
    value = terminal_diagnostic(RunOutput()).model_dump()
    value.update(change)
    assert safe_terminal_diagnostic(value) is None


@pytest.mark.parametrize("value", [None, {}, [], PRIVATE, "InvalidPresentationOutputError"])
def test_public_error_class_is_allowlisted(value):
    assert PRIVATE not in json.dumps(safe_error_class(value))
    if value is None:
        assert safe_error_class(value) is None
    elif value == "InvalidPresentationOutputError":
        assert safe_error_class(value) == value
    else:
        assert safe_error_class(value) == "OtherError"
