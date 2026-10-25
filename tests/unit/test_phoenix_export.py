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


def test_flag_on_with_incomplete_config_warns_with_names_only(monkeypatch, caplog):
    settings = _settings(
        monkeypatch, PHOENIX_API_KEY="", PHOENIX_COLLECTOR_ENDPOINT="phoenix.railway.internal"
    )
    with caplog.at_level("WARNING"):
        assert build_phoenix_tracing(settings) is None
    # Inspect records, not caplog.text: other tests install a metadata-only formatter.
    messages = [record.getMessage() for record in caplog.records]
    warning = next(m for m in messages if "enabled but inactive" in m)
    assert "PHOENIX_API_KEY" in warning
    assert "PHOENIX_COLLECTOR_ENDPOINT" in warning
    assert "PHOENIX_USER_PSEUDONYM_KEY" not in warning  # it was set, so not reported
    assert "phoenix.railway.internal" not in warning  # names only, never values


def test_flag_off_logs_nothing_about_phoenix(monkeypatch, caplog):
    settings = _settings(monkeypatch, PHOENIX_TRACING_ENABLED="false", PHOENIX_API_KEY="")
    with caplog.at_level("DEBUG"):
        assert build_phoenix_tracing(settings) is None
    assert not [r for r in caplog.records if "hoenix" in r.getMessage()]


def test_the_missing_settings_warning_never_contains_a_secret_value(monkeypatch, caplog):
    secret = "super-secret-system-key-value"
    settings = _settings(monkeypatch, PHOENIX_USER_PSEUDONYM_KEY="short", PHOENIX_API_KEY=secret)
    with caplog.at_level("WARNING"):
        build_phoenix_tracing(settings)
    assert secret not in " ".join(r.getMessage() for r in caplog.records)
    assert "short" not in " ".join(r.getMessage() for r in caplog.records)


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


def test_real_otlp_exporter_is_built_for_the_private_grpc_endpoint(monkeypatch):
    """The only code that builds the production exporter; no other test constructs it."""
    settings = _settings(monkeypatch, PHOENIX_API_KEY="secret-system-key-value")
    exporter = phoenix_export._otlp_exporter(settings)
    try:
        assert exporter._endpoint == "phoenix.railway.internal:4317"
        assert exporter._insecure is True  # plain http on the private network
        assert exporter._timeout == settings.otel_exporter_otlp_timeout_seconds
        assert dict(exporter._headers)["authorization"] == "Bearer secret-system-key-value"
    finally:
        exporter.shutdown()


def test_an_https_endpoint_uses_a_secure_channel(monkeypatch):
    """Documents the library's behaviour, not a guard of ours: gRPC derives TLS from the
    URL scheme, so an ``https://`` endpoint is secure whatever ``insecure=`` says. What
    our line must get right is the opposite case, covered by the private-network test
    above: ``http://`` must be plain text, or the Railway-internal link would try TLS."""
    settings = _settings(monkeypatch, PHOENIX_COLLECTOR_ENDPOINT="https://phoenix.example.com:4317")
    exporter = phoenix_export._otlp_exporter(settings)
    try:
        assert exporter._insecure is False
    finally:
        exporter.shutdown()


def test_the_api_key_is_only_ever_sent_as_a_bearer_header_and_never_logged(monkeypatch, caplog):
    secret = "secret-system-key-value"
    settings = _settings(monkeypatch, PHOENIX_API_KEY=secret)
    with caplog.at_level("DEBUG"):
        tracing = build_phoenix_tracing(settings)
    assert tracing is not None
    assert secret not in " ".join(record.getMessage() for record in caplog.records)
    assert secret not in repr(tracing.exporter)
    tracing.shutdown()


@pytest.mark.parametrize(
    "arguments",
    [
        json.dumps(
            {"notes": ["uno", "dni 12345678Z", {"anidado": "tarjeta 4539 1488 0343 6467"}]}
        ),
        json.dumps({"notes": [[["profundo 12345678Z"]]]}),
    ],
)
def test_lists_and_nested_values_are_masked_recursively(arguments):
    projected = _exporter()._json_text(arguments)
    assert "12345678Z" not in projected
    assert "4539 1488 0343 6467" not in projected


def test_numbers_outside_known_fields_still_go_through_the_numeric_safety_net():
    projected = json.loads(_exporter()._json_text(json.dumps({"extra": 612345678901})))
    assert projected["extra"] != 612345678901
    assert "612345678901" not in json.dumps(projected)


def test_booleans_and_nulls_pass_through_unchanged():
    projected = json.loads(_exporter()._json_text(json.dumps({"extra": [True, False, None]})))
    assert projected == {"extra": [True, False, None]}


def test_an_excessively_deep_payload_is_rejected_not_truncated():
    deep: object = "x"
    for _ in range(30):
        deep = [deep]
    with pytest.raises(ValueError, match="depth"):
        _exporter()._json_value(deep)


@pytest.mark.parametrize("bad", [{1: "numeric key"}, {"a": object()}, {"a": float("inf")}])
def test_unsupported_payload_shapes_raise_instead_of_leaking(bad):
    with pytest.raises(ValueError):
        _exporter()._json_value(bad)


def test_oversized_json_arguments_are_rejected_before_parsing():
    with pytest.raises(ValueError):
        _exporter()._json_text("[" + "0," * 40_000 + "0]")


def test_provider_shutdown_failure_is_swallowed(monkeypatch):
    tracing = build_phoenix_tracing(_settings(monkeypatch), delegate=_delegate())
    assert tracing is not None
    monkeypatch.setattr(tracing.provider, "shutdown", Mock(side_effect=RuntimeError("boom")))
    tracing.shutdown()  # must not raise


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
