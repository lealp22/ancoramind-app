"""specs/046 T4: masked Phoenix exporter and isolated provider."""

from __future__ import annotations

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceState

from src.config import Settings
from src.observability import phoenix_export
from src.observability.phoenix_export import (
    CAPTURE_SOURCES,
    MaskedSpanExporter,
    build_phoenix_tracing,
    user_pseudonym,
)

CANARIES = [
    "12345678Z",
    "X1234567L",
    "4539 1488 0343 6467",
    "ES9121000418450200051332",
    "1234 BCD",
    "WVWZZZ1JZXW000001",
    "synthetic@example.com",
    "+34 612 345 678",
    "ghp_abcdefghijklmnop1234",
]


def _span(source: str = "user_text", **attributes):
    return ReadableSpan(
        name=" ".join(CANARIES),
        attributes={
            "ancora.capture.source": source,
            "openinference.span.kind": "LLM",
            **attributes,
        },
        resource=Resource({"private": " ".join(CANARIES)}),
        events=[Event(" ".join(CANARIES), {"private": CANARIES[0]})],
        status=Status(StatusCode.ERROR, " ".join(CANARIES)),
    )


def _delegate():
    delegate = Mock(spec=SpanExporter)
    delegate.export.return_value = SpanExportResult.SUCCESS
    return delegate


def _exporter(delegate=None, **kwargs):
    return MaskedSpanExporter(delegate or _delegate(), project_name="ancoramind", **kwargs)


def _settings(monkeypatch, **overrides) -> Settings:
    values = {
        "PHOENIX_TRACING_ENABLED": "true",
        "PHOENIX_COLLECTOR_ENDPOINT": "http://phoenix.railway.internal:4317",
        "PHOENIX_API_KEY": "system-key",
        "PHOENIX_USER_PSEUDONYM_KEY": "k" * 32,
        **overrides,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


@pytest.mark.parametrize("canary", CANARIES)
def test_canaries_and_every_other_surface_are_sanitized_without_mutating_source(canary):
    delegate = _delegate()
    original = _span(
        **{
            "llm.input_messages.0.message.content": canary,
            "input.value": canary,
            "unknown": canary,
            "llm.prompt": canary,
        }
    )
    assert _exporter(delegate).export([original]) is SpanExportResult.SUCCESS
    copied = delegate.export.call_args.args[0][0]
    assert canary not in copied.to_json()
    assert canary in original.to_json()
    assert copied.events == () and copied.links == ()
    assert copied.status.description is None
    assert "unknown" not in copied.attributes and "llm.prompt" not in copied.attributes
    assert copied.name == "ancora.llm"


def test_output_resource_is_rebuilt_with_project_and_no_source_resource_content():
    delegate = _delegate()
    _exporter(delegate).export([_span()])
    copied = delegate.export.call_args.args[0][0]
    assert copied.resource.attributes["openinference.project.name"] == "ancoramind"
    assert "private" not in copied.resource.attributes


@pytest.mark.parametrize("source", sorted(CAPTURE_SOURCES))
def test_every_trusted_provenance_is_exported_with_its_label(source):
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export([_span(source)])
    assert delegate.export.call_args.args[0][0].attributes["ancora.capture.source"] == source
    assert exporter.exported == 1 and exporter.dropped == 0


@pytest.mark.parametrize(
    "source",
    ["voice_text", "document", "attachment", "history", "untrusted_results", "synthetic_text", ""],
)
def test_untrusted_or_unknown_provenance_never_reaches_the_delegate(source):
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export([_span(source, **{"llm.input_messages.0.message.content": "CANARY"})])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


def test_span_without_provenance_is_dropped():
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export(
        [ReadableSpan("x", attributes={"openinference.span.kind": "LLM", "input.value": "CANARY"})]
    )
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


def test_schema_masking_does_not_depend_on_pattern_and_ids_survive():
    delegate = _delegate()
    correlation = str(uuid4())
    span = _span(
        "proposal_args",
        **{
            "tool.parameters": json.dumps(
                {"registration": "unrecognizable", "vin": 7, "nested": {"email": "short"}}
            ),
            "ancora.correlation_id": correlation,
        },
    )
    _exporter(delegate).export([span])
    copied = delegate.export.call_args.args[0][0]
    assert copied.attributes["ancora.correlation_id"] == correlation
    assert json.loads(copied.attributes["tool.parameters"]) == {
        "registration": "[MATRICULA]",
        "vin": "[BASTIDOR]",
        "nested": {"email": "[EMAIL]"},
    }


@pytest.mark.parametrize(
    "field",
    ["audio", "transcript", "document_content", "ai_extractions", "files", "authorization"],
)
def test_excluded_payload_drops_entire_span(field):
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export([_span("proposal_args", **{"tool.parameters": json.dumps({field: "C"})})])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


@pytest.mark.parametrize("name", ["propose_note", "propose_todo_item_complete", "present_reply"])
def test_allowed_tool_names_pass(name):
    delegate = _delegate()
    _exporter(delegate).export([_span("proposal_args", **{"tool.name": name})])
    assert delegate.export.call_args.args[0][0].attributes["tool.name"] == name


@pytest.mark.parametrize(
    "name", ["get_document", "list_pending_proposals", "execute_note", "propose_", "PROPOSE_x"]
)
def test_tool_names_outside_scope_drop_the_span(name):
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export([_span("proposal_args", **{"tool.name": name})])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


@pytest.mark.parametrize(
    "attributes",
    [
        {"tool.parameters": "not json"},
        {"user.id": "123"},
        {"user.id": "12345678Z"},
        {"llm.token_count.prompt": float("nan")},
        {"llm.token_count.prompt": True},
        {"llm.cost.total": -1.0},
        {"ancora.correlation_id": "not-a-uuid"},
        {"openinference.span.kind": "UNKNOWN"},
    ],
)
def test_invalid_metadata_drops_the_span(attributes):
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export([_span(**attributes)])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


def test_oversized_text_is_dropped_not_truncated():
    delegate = _delegate()
    exporter = _exporter(delegate)
    exporter.export([_span(**{"llm.input_messages.0.message.content": "a" * 64_001})])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


def test_mask_failure_is_per_span_and_never_delegates_raw_content():
    delegate = _delegate()

    def broken(text):
        if text == "break":
            raise ValueError("secret exception detail")
        return text

    exporter = _exporter(delegate, masker=broken)
    exporter.export([_span(**{"llm.model_name": "break"}), _span()])
    assert len(delegate.export.call_args.args[0]) == 1
    assert exporter.dropped == 1


def test_delegate_failures_do_not_propagate_or_retry():
    delegate = _delegate()
    delegate.export.side_effect = RuntimeError("private network error")
    delegate.shutdown.side_effect = RuntimeError()
    delegate.force_flush.side_effect = RuntimeError()
    exporter = _exporter(delegate)
    assert exporter.export([_span()]) is SpanExportResult.FAILURE
    delegate.export.assert_called_once()
    exporter.shutdown()
    assert exporter.force_flush() is False
    assert exporter.failures == 3


def test_tracestate_parent_links_and_scope_cannot_leak_untrusted_content():
    context = SpanContext(1, 2, False, trace_state=TraceState([("vendor", "private-canary")]))
    original = ReadableSpan(
        "private-canary",
        context=context,
        parent=context,
        attributes={"ancora.capture.source": "user_text", "openinference.span.kind": "LLM"},
        links=[Link(context, {"secret": "private-canary"})],
        instrumentation_scope=InstrumentationScope("private-canary", attributes={"k": "private"}),
    )
    delegate = _delegate()
    _exporter(delegate).export([original])
    copied = delegate.export.call_args.args[0][0]
    assert copied.context.trace_id == context.trace_id
    assert copied.parent.span_id == context.span_id
    assert not copied.context.trace_state and not copied.parent.trace_state
    assert "private-canary" not in copied.to_json()
    assert original.context.trace_state["vendor"] == "private-canary"


def test_pseudonym_has_own_domain_key_and_never_contains_user_id():
    value = user_pseudonym("synthetic-user", b"a" * 32)
    assert len(value) == 32 and value == user_pseudonym("synthetic-user", b"a" * 32)
    assert value != user_pseudonym("synthetic-user", b"b" * 32)
    assert value != user_pseudonym("other", b"a" * 32)
    assert "synthetic-user" not in value
    with pytest.raises(ValueError):
        user_pseudonym("synthetic-user", b"short")


# ── provider factory ────────────────────────────────────────────────────────


def test_flag_off_builds_nothing(monkeypatch):
    settings = _settings(monkeypatch, PHOENIX_TRACING_ENABLED="false")
    assert build_phoenix_tracing(settings) is None


@pytest.mark.parametrize(
    "missing", ["PHOENIX_COLLECTOR_ENDPOINT", "PHOENIX_API_KEY", "PHOENIX_USER_PSEUDONYM_KEY"]
)
def test_incomplete_config_builds_nothing_even_with_flag_on(monkeypatch, missing):
    settings = _settings(monkeypatch, **{missing: ""})
    assert build_phoenix_tracing(settings) is None


def test_flag_off_never_imports_or_creates_the_otlp_exporter(monkeypatch):
    called = Mock()
    monkeypatch.setattr(phoenix_export, "_otlp_exporter", called)
    build_phoenix_tracing(_settings(monkeypatch, PHOENIX_TRACING_ENABLED="false"))
    called.assert_not_called()


def test_setup_failure_is_swallowed_and_does_not_log_secrets(monkeypatch, caplog):
    def boom(_settings):
        raise RuntimeError("system-key leaked in message")

    monkeypatch.setattr(phoenix_export, "_otlp_exporter", boom)
    with caplog.at_level("DEBUG"):
        assert build_phoenix_tracing(_settings(monkeypatch)) is None
    # Inspect records, not caplog.text: the JSON formatter other tests install is global.
    messages = [record.getMessage() for record in caplog.records]
    assert any("RuntimeError" in message for message in messages)
    assert not any("system-key" in message for message in messages)
    assert all(record.exc_info is None for record in caplog.records)


def test_provider_is_isolated_from_the_global_one_and_exports_masked(monkeypatch):
    global_before = trace.get_tracer_provider()
    delegate = _delegate()
    tracing = build_phoenix_tracing(_settings(monkeypatch), delegate=delegate)
    assert tracing is not None
    assert trace.get_tracer_provider() is global_before
    assert tracing.provider is not global_before
    with tracing.tracer().start_as_current_span(
        "raw name 12345678Z",
        attributes={
            "ancora.capture.source": "user_text",
            "openinference.span.kind": "LLM",
            "input.value": "mi dni es 12345678Z",
            "user.id": tracing.pseudonym("42"),
        },
    ):
        pass
    tracing.provider.force_flush()
    exported = delegate.export.call_args.args[0][0]
    assert exported.attributes["input.value"] == "mi dni es [DNI]"
    assert exported.attributes["user.id"] == user_pseudonym("42", b"k" * 32)
    assert "12345678Z" not in exported.to_json()
    tracing.shutdown()


def test_spans_on_the_global_provider_never_reach_phoenix(monkeypatch):
    delegate = _delegate()
    tracing = build_phoenix_tracing(_settings(monkeypatch), delegate=delegate)
    assert tracing is not None
    with trace.get_tracer("other").start_as_current_span("not-ours"):
        pass
    tracing.provider.force_flush()
    delegate.export.assert_not_called()
    tracing.shutdown()


def test_configure_is_idempotent_and_shutdown_resets(monkeypatch):
    monkeypatch.setattr(phoenix_export, "_tracing", None)
    monkeypatch.setattr(phoenix_export, "_otlp_exporter", lambda _s: _delegate())
    settings = _settings(monkeypatch)
    first = phoenix_export.configure_phoenix_tracing(settings)
    assert first is not None
    assert phoenix_export.configure_phoenix_tracing(settings) is first
    assert phoenix_export.get_phoenix_tracing() is first
    phoenix_export.shutdown_phoenix_tracing()
    assert phoenix_export.get_phoenix_tracing() is None
    phoenix_export.shutdown_phoenix_tracing()  # second call is harmless


def test_configure_with_flag_off_leaves_no_state(monkeypatch):
    monkeypatch.setattr(phoenix_export, "_tracing", None)
    settings = _settings(monkeypatch, PHOENIX_TRACING_ENABLED="false")
    assert phoenix_export.configure_phoenix_tracing(settings) is None
    assert phoenix_export.get_phoenix_tracing() is None
