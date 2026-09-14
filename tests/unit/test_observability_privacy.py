"""T10 regression tests for metadata-only, fail-open observability."""

from __future__ import annotations

import io
import json
import logging

import pytest

import src.observability.telemetry as telemetry_module
from src.config import Settings
from src.observability.telemetry import (
    MetadataOnlyJsonFormatter,
    MetadataTelemetry,
    filter_telemetry_attributes,
    log_context_scope,
)


class _FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.ended = False

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def set_status(self, status: object) -> None:
        self.status = status

    def end(self) -> None:
        self.ended = True


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_span(self, name: str, attributes: dict[str, object]) -> _FakeSpan:
        del name
        span = _FakeSpan()
        span.attributes.update(attributes)
        self.spans.append(span)
        return span


class _FakeMeter:
    def create_counter(self, name: str) -> object:
        del name
        return object()

    def create_histogram(self, name: str, unit: str) -> object:
        del name, unit
        return object()


def test_allowlist_removes_all_content_bearing_attributes_and_metric_ids() -> None:
    private_content = "mensaje privado / prompt / respuesta / argumento"
    attributes = {
        "ancora.correlation_id": "correlation-1",
        "ancora.route": "ancoramind-default",
        "gen_ai.prompt": private_content,
        "message.content": private_content,
        "ancora.tool.arguments": private_content,
        "ancora.tool.result": private_content,
        "custom.untrusted": private_content,
    }

    span_attributes = filter_telemetry_attributes(attributes)
    metric_attributes = filter_telemetry_attributes(attributes, metric=True)

    assert span_attributes == {
        "ancora.correlation_id": "correlation-1",
        "ancora.route": "ancoramind-default",
    }
    assert metric_attributes == {"ancora.route": "ancoramind-default"}
    assert private_content not in json.dumps(span_attributes)
    assert private_content not in json.dumps(metric_attributes)


def test_json_logging_never_interpolates_positional_private_arguments() -> None:
    private_content = "texto personal que nunca debe exportarse"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(MetadataOnlyJsonFormatter())
    logger = logging.getLogger("test.observability.privacy")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with log_context_scope(
        {
            "ancora.correlation_id": "correlation-1",
            "message.content": private_content,
        }
    ):
        logger.info("Provider failed: %s", private_content)

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "application_log"
    assert payload["ancora.correlation_id"] == "correlation-1"
    assert private_content not in stream.getvalue()
    assert "message.content" not in payload


def test_span_context_does_not_swallow_the_instrumented_business_exception() -> None:
    telemetry = MetadataTelemetry(_FakeTracer(), _FakeMeter())

    with (
        pytest.raises(RuntimeError, match="business failure"),
        telemetry.span("test.span", {"message.content": "secret"}),
    ):
        raise RuntimeError("business failure")


def test_span_uses_only_allowlisted_metadata_and_ends_on_error() -> None:
    tracer = _FakeTracer()
    telemetry = MetadataTelemetry(tracer, _FakeMeter())

    with telemetry.span(
        "test.span",
        {"ancora.route": "ancoramind-default", "message.content": "secret"},
    ) as span:
        telemetry.mark_error(span, "RuntimeError")

    assert tracer.spans[0].attributes["ancora.route"] == "ancoramind-default"
    assert tracer.spans[0].attributes["error.type"] == "RuntimeError"
    assert "message.content" not in tracer.spans[0].attributes
    assert tracer.spans[0].ended is True


def test_observability_setup_is_fail_open_when_otlp_exporter_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry_module._providers = None  # noqa: SLF001
    monkeypatch.setattr(
        telemetry_module,
        "_attach_otlp_exporters",
        lambda *args: (_ for _ in ()).throw(RuntimeError("collector unavailable")),
    )

    telemetry = telemetry_module.configure_observability(
        Settings(otel_exporter_otlp_endpoint="http://collector.internal:4317")
    )

    assert isinstance(telemetry, MetadataTelemetry)
