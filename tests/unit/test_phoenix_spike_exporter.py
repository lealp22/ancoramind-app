"""Synthetic-only exporter proof; importing this never connects the application."""

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceState

from scripts.phoenix_spike.exporter import SyntheticMaskedExporter, user_pseudonym

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


def _span(**attributes):
    return ReadableSpan(
        name=" ".join(CANARIES),
        attributes={
            "ancora.capture.source": "synthetic_text",
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


@pytest.mark.parametrize("canary", CANARIES)
def test_canaries_and_every_other_surface_are_sanitized_without_mutating_source(canary):
    delegate = _delegate()
    original = _span(
        **{"llm.input_messages.0.message.content": canary, "input.value": canary, "unknown": canary}
    )
    exporter = SyntheticMaskedExporter(delegate)
    assert exporter.export([original]) is SpanExportResult.SUCCESS
    copied = delegate.export.call_args.args[0][0]
    assert canary not in copied.to_json()
    assert canary in original.to_json()
    assert copied.events == () and copied.links == ()
    assert copied.status.description is None
    assert "input.value" not in copied.attributes
    assert copied.name == "phoenix.synthetic.llm"


def test_schema_masking_does_not_depend_on_pattern_and_ids_survive():
    delegate = _delegate()
    correlation = str(uuid4())
    span = _span(
        **{
            "tool.parameters": json.dumps(
                {"registration": "unrecognizable", "vin": 7, "nested": {"email": "short"}}
            ),
            "ancora.correlation_id": correlation,
        }
    )
    SyntheticMaskedExporter(delegate).export([span])
    copied = delegate.export.call_args.args[0][0]
    assert copied.attributes["ancora.correlation_id"] == correlation
    args = json.loads(copied.attributes["tool.parameters"])
    assert args == {
        "registration": "[MATRICULA]",
        "vin": "[BASTIDOR]",
        "nested": {"email": "[EMAIL]"},
    }


@pytest.mark.parametrize(
    "field",
    [
        "audio",
        "transcript",
        "document_content",
        "ai_extractions",
        "files",
        "authorization",
        "api_key",
    ],
)
def test_excluded_payload_drops_entire_span(field):
    delegate = _delegate()
    exporter = SyntheticMaskedExporter(delegate)
    exporter.export([_span(**{"tool.parameters": json.dumps({field: "CANARY"})})])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


@pytest.mark.parametrize(
    "attributes",
    [
        {"ancora.capture.source": "real_text"},
        {"ancora.capture.source": ""},
        {"tool.name": "get_document"},
        {"tool.parameters": "not json"},
        {"user.id": "123"},
        {"llm.token_count.prompt": float("nan")},
    ],
)
def test_invalid_or_non_synthetic_span_is_not_exported(attributes):
    delegate = _delegate()
    exporter = SyntheticMaskedExporter(delegate)
    exporter.export([_span(**attributes)])
    delegate.export.assert_not_called()
    assert exporter.dropped == 1


def test_mask_failure_is_per_span_and_never_delegates_raw_content():
    delegate = _delegate()

    def broken(text):
        if text == "break":
            raise ValueError("secret exception detail")
        return text

    exporter = SyntheticMaskedExporter(delegate, broken)
    exporter.export([_span(**{"llm.model_name": "break"}), _span()])
    assert len(delegate.export.call_args.args[0]) == 1
    assert exporter.dropped == 1


def test_delegate_failures_do_not_propagate_or_retry():
    delegate = _delegate()
    delegate.export.side_effect = RuntimeError("private network error")
    delegate.shutdown.side_effect = RuntimeError()
    delegate.force_flush.side_effect = RuntimeError()
    exporter = SyntheticMaskedExporter(delegate)
    assert exporter.export([_span()]) is SpanExportResult.FAILURE
    delegate.export.assert_called_once()
    exporter.shutdown()
    assert exporter.force_flush() is False


def test_pseudonym_has_own_domain_key_and_never_contains_user_id():
    value = user_pseudonym("synthetic-user", b"a" * 32)
    assert len(value) == 32 and value == user_pseudonym("synthetic-user", b"a" * 32)
    assert value != user_pseudonym("synthetic-user", b"b" * 32)
    assert value != user_pseudonym("other", b"a" * 32)
    with pytest.raises(ValueError):
        user_pseudonym("synthetic-user", b"short")


def test_tracestate_parent_links_and_scope_cannot_leak_untrusted_content():
    context = SpanContext(1, 2, False, trace_state=TraceState([("vendor", "private-canary")]))
    original = ReadableSpan(
        "private-canary", context=context, parent=context,
        attributes={"ancora.capture.source": "synthetic_text", "openinference.span.kind": "LLM"},
        links=[Link(context, {"secret": "private-canary"})],
        instrumentation_scope=InstrumentationScope("private-canary", attributes={"key": "private"}),
    )
    delegate = _delegate()
    SyntheticMaskedExporter(delegate).export([original])
    copied = delegate.export.call_args.args[0][0]
    assert copied.context.trace_id == context.trace_id
    assert copied.parent.span_id == context.span_id
    assert not copied.context.trace_state and not copied.parent.trace_state
    assert "private-canary" not in copied.to_json()
    assert original.context.trace_state["vendor"] == "private-canary"
