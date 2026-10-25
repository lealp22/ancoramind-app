"""specs/046 T6: provenance-gated capture seam for masked Phoenix traces."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from agno.run.agent import RunOutput, ToolExecution
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from src.agent.governed_interaction_runner import GovernedInteractionRunner
from src.config import Settings
from src.domain.interactions.reply import AgentReply
from src.observability.phoenix_capture import (
    SAFE_READ_TOOLS,
    ToolCallRecord,
    TurnRecord,
    bounded_tool_error,
    capture_turn,
    model_content_allowed,
)
from src.observability.phoenix_export import PhoenixTracing, build_phoenix_tracing
from tests.unit.test_governed_interaction_runner import _FakeFactory, _FakeManager
from tests.unit.test_governed_interaction_runner import _snapshot as _runtime_snapshot

DNI = "12345678Z"


class _Sink(SpanExporter):
    def __init__(self) -> None:
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Any) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS


def _tracing(monkeypatch: pytest.MonkeyPatch) -> tuple[PhoenixTracing, _Sink]:
    for name, value in {
        "PHOENIX_TRACING_ENABLED": "true",
        "PHOENIX_COLLECTOR_ENDPOINT": "http://phoenix.railway.internal:4317",
        "PHOENIX_API_KEY": "system-key",
        "PHOENIX_USER_PSEUDONYM_KEY": "k" * 32,
    }.items():
        monkeypatch.setenv(name, value)
    sink = _Sink()
    tracing = build_phoenix_tracing(Settings(_env_file=None), delegate=sink)
    assert tracing is not None
    return tracing, sink


def _record(**overrides: Any) -> TurnRecord:
    now = time.time_ns()
    values: dict[str, Any] = {
        "correlation_id": uuid4(),
        "user_id": "5551234",
        "started_ns": now,
        "ended_ns": now + 1_000_000,
        "route": "ancoramind-default-r4",
        "user_text": "apunta una nota",
        "answer": "Hecho",
        "proposal_text": "",
        "tool_calls": (ToolCallRecord("propose_note", {"content": "comprar pan"}),),
    }
    values.update(overrides)
    return TurnRecord(**values)


def _by_source(sink: _Sink) -> dict[str, list[ReadableSpan]]:
    grouped: dict[str, list[ReadableSpan]] = {}
    for span in sink.spans:
        grouped.setdefault(str(span.attributes["ancora.capture.source"]), []).append(span)
    return grouped


def _flush(tracing: PhoenixTracing) -> None:
    tracing.provider.force_flush()


def _assert_no_model_content(sink: _Sink) -> None:
    """Typed text and metadata may be present; model-generated content must not be."""
    sources = set(_by_source(sink))
    assert {"call_metadata", "user_text"} <= sources
    assert not sources & {"final_reply", "proposal_args"}


# ── policy ──────────────────────────────────────────────────────────────────


def test_typed_note_turn_captures_all_four_sources(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    record = _record()
    capture_turn(tracing, record)
    _flush(tracing)
    grouped = _by_source(sink)
    assert set(grouped) == {
        "call_metadata",
        "user_text",
        "tool_metadata",
        "final_reply",
        "proposal_args",
    }
    assert grouped["user_text"][0].attributes["input.value"] == "apunta una nota"
    assert grouped["final_reply"][0].attributes["output.value"] == "Hecho"
    assert json.loads(grouped["proposal_args"][0].attributes["tool.parameters"]) == {
        "content": "comprar pan"
    }
    tracing.shutdown()


def test_all_spans_share_one_trace_correlation_and_pseudonym_but_never_the_raw_user_id(
    monkeypatch,
):
    tracing, sink = _tracing(monkeypatch)
    record = _record()
    capture_turn(tracing, record)
    _flush(tracing)
    assert len({span.context.trace_id for span in sink.spans}) == 1
    for span in sink.spans:
        assert span.attributes["ancora.correlation_id"] == str(record.correlation_id)
        assert span.attributes["ancora.interaction_id"] == str(record.correlation_id)
        assert span.attributes["user.id"] == tracing.pseudonym("5551234")
        assert "5551234" not in span.to_json()
    root = _by_source(sink)["call_metadata"][0]
    assert root.parent is None
    assert all(span.parent is not None for span in sink.spans if span is not root)
    tracing.shutdown()


def test_voice_or_synthesized_text_is_never_captured(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(tracing, _record(user_text=None))
    _flush(tracing)
    grouped = _by_source(sink)
    assert "user_text" not in grouped
    assert "input.value" not in json.dumps([span.to_json() for span in sink.spans])
    tracing.shutdown()


@pytest.mark.parametrize(
    "tool",
    [
        "get_document",
        "search_documents",
        "search_documents_semantically",
        "analyze_document",
        "export_document",
        "search_web",
        "propose_document_delete",
        "some_future_tool",
    ],
)
def test_turn_with_document_or_unknown_tools_keeps_only_user_text_and_metadata(
    monkeypatch, tool
):
    tracing, sink = _tracing(monkeypatch)
    record = _record(
        answer=f"El documento dice {DNI}", tool_calls=(ToolCallRecord(tool, {"document_id": "1"}),)
    )
    assert model_content_allowed(record) is False
    capture_turn(tracing, record)
    _flush(tracing)
    _assert_no_model_content(sink)
    assert "El documento dice" not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


def test_turn_with_attachments_never_captures_model_generated_content(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(tracing, _record(had_media=True, answer="Resumen del PDF"))
    _flush(tracing)
    _assert_no_model_content(sink)
    tracing.shutdown()


@pytest.mark.parametrize("tool", sorted(SAFE_READ_TOOLS))
def test_known_safe_read_tools_do_not_block_model_content(tool):
    record = _record(tool_calls=(ToolCallRecord(tool, {}), ToolCallRecord("present_reply", {})))
    assert model_content_allowed(record) is True


def test_read_tool_arguments_are_never_captured(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    record = _record(
        tool_calls=(
            ToolCallRecord("find_vehicle", {"query": "SECRET-READ-ARG"}),
            ToolCallRecord("propose_note", {"content": "ok"}),
        )
    )
    capture_turn(tracing, record)
    _flush(tracing)
    assert len(_by_source(sink)["proposal_args"]) == 1
    assert "SECRET-READ-ARG" not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


def test_failed_turn_still_exports_metadata_with_error_class_only(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    failed = _record(
        answer=None, proposal_text=None, tool_calls=(), error_type="InvalidPresentationOutputError"
    )
    capture_turn(tracing, failed)
    _flush(tracing)
    root = _by_source(sink)["call_metadata"][0]
    assert root.attributes["error.type"] == "InvalidPresentationOutputError"
    assert root.status.status_code is trace.StatusCode.ERROR
    _assert_no_model_content(sink)
    tracing.shutdown()


def test_canaries_are_masked_in_user_text_reply_and_proposal_args(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            user_text=f"mi dni es {DNI}",
            answer=f"Anotado {DNI}",
            tool_calls=(
                ToolCallRecord("propose_note", {"content": f"dni {DNI}", "registration": "zz"}),
            ),
        ),
    )
    _flush(tracing)
    dumped = " ".join(span.to_json() for span in sink.spans)
    assert DNI not in dumped
    assert "[DNI]" in dumped
    assert "[MATRICULA]" in dumped
    tracing.shutdown()


def test_metrics_and_cost_are_exported_as_numbers_only(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing, _record(input_tokens=10, output_tokens=4, total_tokens=14, cost_usd=0.002)
    )
    _flush(tracing)
    attrs = _by_source(sink)["call_metadata"][0].attributes
    assert attrs["llm.token_count.prompt"] == 10
    assert attrs["llm.cost.total"] == 0.002
    assert attrs["llm.model_name"] == "ancoramind-default-r4"
    tracing.shutdown()


def test_ambient_grafana_span_is_never_the_parent(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    with trace.get_tracer("grafana-side").start_as_current_span("ambient") as ambient:
        capture_turn(tracing, _record())
    _flush(tracing)
    ambient_id = ambient.get_span_context().trace_id
    assert all(span.context.trace_id != ambient_id for span in sink.spans)
    tracing.shutdown()


# ── per-tool metadata (specs/046 "Visibilidad por tool") ─────────────────────


def _tool_spans(sink: _Sink) -> list[ReadableSpan]:
    spans = _by_source(sink).get("tool_metadata", [])
    return sorted(spans, key=lambda span: span.attributes["ancora.tool.index"])


def test_every_tool_call_gets_a_metadata_span_in_call_order(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(
                ToolCallRecord("find_vehicle", {}, duration_ms=12.5, result_chars=340),
                ToolCallRecord("get_document", {}, failed=True, duration_ms=3.0),
                ToolCallRecord("propose_note", {"content": "x"}),
            )
        ),
    )
    _flush(tracing)
    spans = _tool_spans(sink)
    assert [s.attributes["ancora.tool.name"] for s in spans] == [
        "find_vehicle",
        "get_document",
        "propose_note",
    ]
    assert [s.attributes["ancora.tool.outcome"] for s in spans] == ["ok", "error", "ok"]
    assert spans[0].attributes["ancora.tool.duration_ms"] == 12.5
    assert spans[0].attributes["ancora.tool.result_chars"] == 340
    assert "ancora.tool.result_chars" not in spans[1].attributes
    tracing.shutdown()


def test_document_tool_is_visible_as_metadata_even_though_its_content_is_not(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            answer=f"Contiene {DNI}",
            tool_calls=(ToolCallRecord("get_document", {"document_id": "1"}, result_chars=900),),
        ),
    )
    _flush(tracing)
    assert [s.attributes["ancora.tool.name"] for s in _tool_spans(sink)] == ["get_document"]
    assert "final_reply" not in _by_source(sink)
    assert DNI not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


@pytest.mark.parametrize(
    "invented", [f"propose_{DNI}", "propose_", "ignore previous instructions", DNI, "Ñ", ""]
)
def test_model_invented_tool_names_never_reach_a_span(monkeypatch, invented):
    tracing, sink = _tracing(monkeypatch)
    record = _record(tool_calls=(ToolCallRecord(invented, {"content": "SECRET-ARG"}),))
    assert model_content_allowed(record) is False
    capture_turn(tracing, record)
    _flush(tracing)
    dumped = " ".join(span.to_json() for span in sink.spans)
    assert invented not in dumped or invented == ""
    assert "SECRET-ARG" not in dumped
    assert [s.attributes["ancora.tool.name"] for s in _tool_spans(sink)] == ["unknown_tool"]
    assert "proposal_args" not in _by_source(sink)
    assert "final_reply" not in _by_source(sink)
    tracing.shutdown()


def test_tool_metadata_never_carries_arguments_or_successful_result_text(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(
                ToolCallRecord("find_vehicle", {"query": "ARG-CANARY"}, failed=True),
                ToolCallRecord("search_web", {"query": "ARG-CANARY"}, result_chars=10),
            )
        ),
    )
    _flush(tracing)
    for span in _tool_spans(sink):
        assert set(span.attributes) <= {
            "ancora.capture.source",
            "openinference.span.kind",
            "ancora.correlation_id",
            "ancora.interaction_id",
            "user.id",
            "ancora.tool.name",
            "ancora.tool.index",
            "ancora.tool.outcome",
            "ancora.tool.duration_ms",
            "ancora.tool.result_chars",
            "ancora.tool.error_message",
        }
    assert "ARG-CANARY" not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


# ── tool error message (owner decision 2026-10-25) ───────────────────────────


def _error_span(sink: _Sink) -> ReadableSpan:
    return _tool_spans(sink)[0]


def test_failed_tool_exports_its_error_message_masked(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(
                ToolCallRecord(
                    "find_vehicle",
                    {},
                    failed=True,
                    error_message=f"db failed for user {DNI} at host secret-host",
                ),
            )
        ),
    )
    _flush(tracing)
    attrs = _error_span(sink).attributes
    assert attrs["ancora.tool.outcome"] == "error"
    assert attrs["ancora.tool.error_message"] == "db failed for user [DNI] at host secret-host"
    assert DNI not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


def test_successful_tool_never_carries_a_message_even_if_one_is_supplied(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(ToolCallRecord("find_vehicle", {}, failed=False, error_message="LEAK"),)
        ),
    )
    _flush(tracing)
    assert "ancora.tool.error_message" not in _error_span(sink).attributes
    assert "LEAK" not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


def test_error_message_of_an_unregistered_tool_is_never_exported(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(ToolCallRecord("made_up", {}, failed=True, error_message="LEAK detail"),)
        ),
    )
    _flush(tracing)
    attrs = _error_span(sink).attributes
    assert attrs["ancora.tool.name"] == "unknown_tool"
    assert "ancora.tool.error_message" not in attrs
    tracing.shutdown()


def test_error_message_is_exported_even_when_model_content_is_excluded(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(
                ToolCallRecord("get_document", {}, failed=True, error_message="timeout"),
            )
        ),
    )
    _flush(tracing)
    assert _error_span(sink).attributes["ancora.tool.error_message"] == "timeout"
    _assert_no_model_content(sink)
    tracing.shutdown()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   \n  ", None),
        ("simple", "simple"),
        ("first\nsecond line with 12345678Z", "first"),
        (
            "1 validation error for propose_x\namount\n  bad [type=int, input_value='SECRET', ...]",
            "1 validation error for propose_x",
        ),
        ("bad value [type=int, input_value='SECRET', input_type=str]", "bad value [type=int,"),
        ("input_value='only a value'", None),
        ("x" * 1000, "x" * 300),
    ],
)
def test_bounded_tool_error_keeps_first_line_cuts_quoted_values_and_caps_length(raw, expected):
    assert bounded_tool_error(raw) == expected


def test_error_message_carrying_a_quoted_argument_never_reaches_a_span(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    pydantic_style = (
        "1 validation error for propose_note\ncontent\n"
        "  Input should be a valid string [type=string_type, input_value=Segredo-Ana-Lopez, "
        "input_type=int]"
    )
    capture_turn(
        tracing,
        _record(
            tool_calls=(
                ToolCallRecord(
                    "propose_note",
                    {},
                    failed=True,
                    error_message=bounded_tool_error(pydantic_style),
                ),
            )
        ),
    )
    _flush(tracing)
    dumped = " ".join(span.to_json() for span in sink.spans)
    assert "Segredo-Ana-Lopez" not in dumped
    assert "validation error for propose_note" in dumped
    tracing.shutdown()


def test_known_limit_unrecognised_text_in_an_error_is_not_masked(monkeypatch):
    """Documents the residual risk: the masker detects formats, not names or hosts."""
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing,
        _record(
            tool_calls=(
                ToolCallRecord(
                    "find_vehicle", {}, failed=True, error_message="no vehicle for Maria Lopez"
                ),
            )
        ),
    )
    _flush(tracing)
    assert _error_span(sink).attributes["ancora.tool.error_message"] == (
        "no vehicle for Maria Lopez"
    )
    tracing.shutdown()


def test_exporter_rejects_an_error_message_on_a_span_that_did_not_fail():
    from src.observability.phoenix_export import MaskedSpanExporter

    sink = _Sink()
    exporter = MaskedSpanExporter(sink, project_name="ancoramind")
    span = ReadableSpan(
        "x",
        attributes={
            "ancora.capture.source": "tool_metadata",
            "openinference.span.kind": "TOOL",
            "ancora.tool.name": "find_vehicle",
            "ancora.tool.outcome": "ok",
            "ancora.tool.error_message": "LEAK",
        },
    )
    exporter.export([span])
    assert sink.spans == [] and exporter.dropped == 1


def test_exporter_rejects_an_oversized_error_message():
    from src.observability.phoenix_export import MaskedSpanExporter

    sink = _Sink()
    exporter = MaskedSpanExporter(sink, project_name="ancoramind")
    span = ReadableSpan(
        "x",
        attributes={
            "ancora.capture.source": "tool_metadata",
            "openinference.span.kind": "TOOL",
            "ancora.tool.name": "find_vehicle",
            "ancora.tool.outcome": "error",
            "ancora.tool.error_message": "x" * 301,
        },
    )
    exporter.export([span])
    assert sink.spans == [] and exporter.dropped == 1


def test_runner_keeps_the_error_text_of_a_failed_call_but_not_a_successful_result():
    from agno.metrics import ToolCallMetrics

    from src.agent.governed_interaction_runner import _tool_call_record

    failed = _tool_call_record(
        ToolExecution(
            tool_name="find_vehicle",
            result=f"db failed for user {DNI}\ntraceback line",
            tool_call_error=True,
            metrics=ToolCallMetrics(duration=0.1),
        )
    )
    ok = _tool_call_record(
        ToolExecution(tool_name="find_vehicle", result="Coche SECRET-RESULT", tool_call_error=False)
    )
    assert failed.error_message == f"db failed for user {DNI}"
    assert ok.error_message is None
    assert "SECRET-RESULT" not in repr(ok)


@pytest.mark.parametrize(
    "attributes",
    [
        {"ancora.tool.name": "Not A Tool"},
        {"ancora.tool.name": "tool12"},
        {"ancora.tool.name": DNI},
        {"ancora.tool.outcome": "maybe"},
        {"ancora.tool.duration_ms": -1.0},
        {"ancora.tool.result_chars": float("inf")},
    ],
)
def test_exporter_drops_tool_spans_with_invalid_metadata(attributes):
    delegate = _Sink()
    from src.observability.phoenix_export import MaskedSpanExporter

    exporter = MaskedSpanExporter(delegate, project_name="ancoramind")
    span = ReadableSpan(
        "x",
        attributes={
            "ancora.capture.source": "tool_metadata",
            "openinference.span.kind": "TOOL",
            **attributes,
        },
    )
    exporter.export([span])
    assert delegate.spans == [] and exporter.dropped == 1


def test_registry_matches_every_propose_tool_defined_in_the_code():
    import re
    from pathlib import Path

    from src.observability.phoenix_capture import PROPOSE_TOOLS

    defined = set()
    for path in Path("src/agent/tools").glob("*.py"):
        defined |= set(re.findall(r"^async def (propose_\w+)\(", path.read_text("utf-8"), re.M))
    assert defined == set(PROPOSE_TOOLS), (
        "Classify new propose_* tools in phoenix_capture.PROPOSE_TOOLS "
        f"(missing: {defined - PROPOSE_TOOLS}, stale: {PROPOSE_TOOLS - defined})"
    )


def test_runner_builds_tool_metadata_from_real_executions_without_result_text(monkeypatch):
    from agno.metrics import ToolCallMetrics

    from src.agent.governed_interaction_runner import _tool_call_record

    result = f"Coche con matrícula {DNI}"
    ok = _tool_call_record(
        ToolExecution(
            tool_name="find_vehicle",
            tool_args={"query": "ARG-CANARY"},
            result=result,
            tool_call_error=False,
            metrics=ToolCallMetrics(duration=0.25),
        )
    )
    assert ok.args == {}
    assert ok.failed is False
    assert ok.duration_ms == 250
    assert ok.result_chars == len(result)
    assert ok.error_message is None
    assert DNI not in repr(ok)
    assert "ARG-CANARY" not in repr(ok)


# ── fail-open ───────────────────────────────────────────────────────────────


def test_inactive_pipeline_is_a_no_op():
    capture_turn(None, _record())


def test_unserializable_proposal_args_abort_capture_without_raising(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    capture_turn(
        tracing, _record(tool_calls=(ToolCallRecord("propose_note", {"content": object()}),))
    )
    _flush(tracing)
    # user text was already emitted; the offending proposal_args span never existed.
    assert "proposal_args" not in _by_source(sink)
    tracing.shutdown()


def test_broken_tracer_never_raises(monkeypatch):
    broken = Mock(spec=PhoenixTracing)
    broken.tracer.side_effect = RuntimeError(f"leaks {DNI}")
    capture_turn(broken, _record())


# ── runner integration ──────────────────────────────────────────────────────


def _runner(monkeypatch, tracing):
    factory = _FakeFactory()
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_runtime_snapshot()),
        factory=factory,
        phoenix_tracing=tracing,
    )
    return runner, factory


async def _run(runner, text="hola", **kwargs):
    return await runner.run(
        text,
        user_id="88",
        session_id="s",
        run_id="r",
        correlation_id=uuid4(),
        telegram_update_id=1,
        **kwargs,
    )


async def test_runner_default_captures_no_user_text(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    runner, _ = _runner(monkeypatch, tracing)
    reply = await _run(runner, f"mi dni {DNI}")
    _flush(tracing)
    assert reply == AgentReply(answer="respuesta gobernada", proposal_text="")
    grouped = _by_source(sink)
    assert "user_text" not in grouped
    assert grouped["final_reply"][0].attributes["output.value"] == "respuesta gobernada"
    tracing.shutdown()


async def test_runner_captures_typed_text_masked_when_caller_vouches_for_it(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    runner, _ = _runner(monkeypatch, tracing)
    await _run(runner, f"mi dni {DNI}", capture_user_text=True)
    _flush(tracing)
    assert _by_source(sink)["user_text"][0].attributes["input.value"] == "mi dni [DNI]"
    tracing.shutdown()


async def test_runner_without_phoenix_behaves_exactly_as_before():
    runner, factory = _runner(None, None)
    reply = await _run(runner, capture_user_text=True)
    assert reply == AgentReply(answer="respuesta gobernada", proposal_text="")
    assert len(factory.agent.calls) == 1


async def test_runner_tracing_failure_never_changes_the_reply(monkeypatch):
    broken = Mock(spec=PhoenixTracing)
    broken.tracer.side_effect = RuntimeError("phoenix down")
    broken.pseudonym.side_effect = RuntimeError("phoenix down")
    runner, _ = _runner(monkeypatch, broken)
    reply = await _run(runner, capture_user_text=True)
    assert reply == AgentReply(answer="respuesta gobernada", proposal_text="")


async def test_runner_failed_run_exports_error_class_and_reraises_original(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    runner, factory = _runner(monkeypatch, tracing)

    async def boom(*_args, **_kwargs):
        raise ValueError(f"secret {DNI}")

    factory.agent.arun = boom
    with pytest.raises(ValueError, match="secret"):
        await _run(runner, capture_user_text=True)
    _flush(tracing)
    root = _by_source(sink)["call_metadata"][0]
    assert root.attributes["error.type"] == "ValueError"
    assert DNI not in " ".join(span.to_json() for span in sink.spans)
    assert "final_reply" not in _by_source(sink)
    tracing.shutdown()


async def test_runner_invalid_presentation_is_diagnosable_without_model_content(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    runner, factory = _runner(monkeypatch, tracing)

    async def no_presentation(*_args, **_kwargs):
        return RunOutput(tools=[ToolExecution(tool_name="search_notes", tool_args={"q": "x"})])

    factory.agent.arun = no_presentation
    with pytest.raises(ValueError, match="invalid presentation output"):
        await _run(runner, capture_user_text=True)
    _flush(tracing)
    root = _by_source(sink)["call_metadata"][0]
    assert root.attributes["error.type"] == "InvalidPresentationOutputError"
    assert "user_text" in _by_source(sink)
    tracing.shutdown()


async def test_runner_captures_propose_args_from_the_real_tool_executions(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    runner, factory = _runner(monkeypatch, tracing)

    reply = AgentReply(answer="Propuesta lista", proposal_text="x")

    async def with_proposal(*_args, **_kwargs):
        return RunOutput(
            tools=[
                ToolExecution(tool_name="search_notes", tool_args={"query": "READ-ARG"}),
                ToolExecution(tool_name="propose_note", tool_args={"content": "pan"}),
                ToolExecution(tool_name="present_reply", result=reply.model_dump_json()),
            ]
        )

    factory.agent.arun = with_proposal
    await _run(runner, capture_user_text=True)
    _flush(tracing)
    grouped = _by_source(sink)
    args = json.loads(grouped["proposal_args"][0].attributes["tool.parameters"])
    assert args == {"content": "pan"}
    assert "READ-ARG" not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


async def test_runner_turn_with_document_tool_drops_reply_even_though_reply_is_valid(monkeypatch):
    tracing, sink = _tracing(monkeypatch)
    runner, factory = _runner(monkeypatch, tracing)

    reply = AgentReply(answer=f"Contiene {DNI}", proposal_text="")

    async def reads_document(*_args, **_kwargs):
        return RunOutput(
            tools=[
                ToolExecution(tool_name="get_document", tool_args={"document_id": "1"}),
                ToolExecution(tool_name="present_reply", result=reply.model_dump_json()),
            ]
        )

    factory.agent.arun = reads_document
    await _run(runner, capture_user_text=True)
    _flush(tracing)
    assert "final_reply" not in _by_source(sink)
    assert DNI not in " ".join(span.to_json() for span in sink.spans)
    tracing.shutdown()


async def test_runner_attachments_disable_model_content(monkeypatch):
    from src.domain.interactions.media import ResolvedTelegramMedia

    tracing, sink = _tracing(monkeypatch)
    runner, _ = _runner(monkeypatch, tracing)
    monkeypatch.setattr(
        "src.agent.governed_interaction_runner.ingest_resolved_telegram_media",
        _async_return(""),
    )
    media = (Mock(spec=ResolvedTelegramMedia),)
    await _run(runner, capture_user_text=True, media=media)
    _flush(tracing)
    assert "final_reply" not in _by_source(sink)
    tracing.shutdown()


def _async_return(value):
    async def inner(*_args, **_kwargs):
        return value

    return inner
