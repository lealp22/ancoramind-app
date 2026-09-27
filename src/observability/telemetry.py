"""Privacy-preserving OpenTelemetry and JSON logging facade (specs/013 T10).

Only allowlisted technical metadata can enter spans, metrics and logs. Prompts,
messages, responses, document content, tool arguments/results and exception
messages are deliberately excluded. Export failures are swallowed: telemetry is
never part of the functional success path.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode, use_span

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.trace import Tracer

    from src.config import Settings
    from src.domain.llm_access.models import ExecutionContext

logger = logging.getLogger(__name__)

SERVICE = "ancoramind-core"
_LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar("ancoramind_log_context", default=None)

# IDs may be span/log attributes for correlation, but are excluded from metric
# labels to prevent unbounded cardinality. All other keys are technical enums,
# bounded status codes, counters, routes or revision numbers.
SPAN_ATTRIBUTE_ALLOWLIST = frozenset(
    {
        "ancora.correlation_id",
        "ancora.interaction_id",
        "agno.run_id",
        "agno.session_id",
        "telegram.update_id",
        "telegram.message_id",
        "railway.request_id",
        "runtime_config.revision",
        "ancora.route",
        "ancora.effective_route",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "ancora.status",
        "error.type",
        "ancora.budget.limit",
        "ancora.delivery.status",
        "ancora.admission.status",
        "ancora.command",
        "ancora.duplicate",
        "ancora.queue.status",
        "ancora.queue.scope",
        "ancora.tool.name",
        "ancora.tool.outcome",
        "ancora.health.component",
        "ancora.health.status",
        "ancora.circuit.state",
        "http.response.status_code",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.total_tokens",
        "gen_ai.usage.estimated_cost_usd",
        "gen_ai.usage.actual_cost_usd",
    }
)
METRIC_ATTRIBUTE_ALLOWLIST = SPAN_ATTRIBUTE_ALLOWLIST - {
    "ancora.correlation_id",
    "ancora.interaction_id",
    "agno.run_id",
    "agno.session_id",
    "telegram.update_id",
    "telegram.message_id",
    "railway.request_id",
}
LOG_ATTRIBUTE_ALLOWLIST = SPAN_ATTRIBUTE_ALLOWLIST


def filter_telemetry_attributes(
    attributes: Mapping[str, object] | None,
    *,
    metric: bool = False,
) -> dict[str, str | bool | int | float]:
    allowed = METRIC_ATTRIBUTE_ALLOWLIST if metric else SPAN_ATTRIBUTE_ALLOWLIST
    if not attributes:
        return {}
    filtered: dict[str, str | bool | int | float] = {}
    for key, value in attributes.items():
        if key not in allowed or value is None:
            continue
        if isinstance(value, (str, bool, int, float)):
            filtered[key] = value
    return filtered


class MetadataOnlyJsonFormatter(logging.Formatter):
    """Render only log templates plus explicitly allowlisted context metadata."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            # Intentionally do not call getMessage() or serialize record.msg:
            # either can contain a dynamic f-string, positional private content
            # or a provider exception. The logger name + level + allowlisted
            # metadata are the structured operational event.
            "event": "application_log",
        }
        for key, value in (_LOG_CONTEXT.get() or {}).items():
            if key in LOG_ATTRIBUTE_ALLOWLIST:
                payload[key] = value
        record_attributes = getattr(record, "ancora_attributes", None)
        if isinstance(record_attributes, Mapping):
            payload.update(filter_telemetry_attributes(record_attributes))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@contextmanager
def log_context_scope(attributes: Mapping[str, object]) -> Iterator[None]:
    """Attach allowlisted correlation metadata to structured logs in this scope."""
    current = dict(_LOG_CONTEXT.get() or {})
    current.update(
        {key: str(value) for key, value in filter_telemetry_attributes(attributes).items()}
    )
    token: Token[dict[str, str] | None] = _LOG_CONTEXT.set(current)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def telemetry_attributes_from_execution_context(context: ExecutionContext) -> dict[str, object]:
    """Return the fixed, content-free telemetry attributes for one governed run."""
    return {
        "ancora.correlation_id": str(context.correlation_id),
        "telegram.update_id": context.telegram_update_id,
        "telegram.message_id": context.telegram_message_id,
        "agno.run_id": context.agno_run_id,
        "agno.session_id": context.agno_session_id,
        "railway.request_id": context.railway_request_id,
        "runtime_config.revision": context.config.revision,
    }


class MetadataTelemetry:
    """Small OTel facade that only accepts metadata allowed by this module."""

    def __init__(self, tracer: Tracer, meter: Meter) -> None:
        self._tracer = tracer
        self._meter = meter
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._gauges: dict[str, Any] = {}
        self._gauge_values: dict[
            tuple[str, tuple[tuple[str, str | bool | int | float], ...]], float
        ] = {}

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, object] | None = None,
        *,
        enabled: bool = True,
    ) -> Iterator[Any]:
        """Create a metadata-only span; instrumentation errors never propagate."""
        if not enabled:
            yield trace.get_current_span()
            return
        try:
            span = self._tracer.start_span(name, attributes=filter_telemetry_attributes(attributes))
        except Exception:  # pragma: no cover - exporter/provider failures are environment-specific
            logger.debug("Observability span failed", exc_info=False)
            yield trace.get_current_span()
            return
        try:
            with use_span(span, end_on_exit=False):
                yield span
        finally:
            try:
                span.end()
            except Exception:  # pragma: no cover - exporter/provider failures
                logger.debug("Observability span end failed", exc_info=False)

    def counter(
        self,
        name: str,
        value: int | float = 1,
        attributes: Mapping[str, object] | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        """Record a bounded-cardinality counter without affecting the caller."""
        if not enabled:
            return
        try:
            counter = self._counters.setdefault(name, self._meter.create_counter(name))
            counter.add(value, attributes=filter_telemetry_attributes(attributes, metric=True))
        except Exception:  # pragma: no cover - exporter/provider failures are environment-specific
            logger.debug("Observability counter failed", exc_info=False)

    def duration_ms(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, object] | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        """Record a bounded-cardinality duration histogram in milliseconds."""
        if not enabled:
            return
        try:
            histogram = self._histograms.setdefault(
                name,
                self._meter.create_histogram(name, unit="ms"),
            )
            histogram.record(
                max(0.0, value),
                attributes=filter_telemetry_attributes(attributes, metric=True),
            )
        except Exception:  # pragma: no cover - exporter/provider failures are environment-specific
            logger.debug("Observability histogram failed", exc_info=False)

    def gauge(
        self,
        name: str,
        value: int | float,
        attributes: Mapping[str, object] | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        """Record an absolute bounded value through an UpDownCounter delta safely."""
        if not enabled:
            return
        try:
            filtered = filter_telemetry_attributes(attributes, metric=True)
            series = (name, tuple(sorted(filtered.items())))
            previous = self._gauge_values.get(series, 0.0)
            target = float(value)
            delta = target - previous
            if delta:
                gauge = self._gauges.setdefault(name, self._meter.create_up_down_counter(name))
                gauge.add(delta, attributes=filtered)
            self._gauge_values[series] = target
        except Exception:  # pragma: no cover - exporter/provider failures are environment-specific
            logger.debug("Observability gauge failed", exc_info=False)

    @staticmethod
    def mark_error(span: Any, error_type: str) -> None:
        """Mark a span failed without recording exception text or stack traces."""
        try:
            span.set_attribute("error.type", error_type)
            span.set_status(Status(StatusCode.ERROR))
        except Exception:  # pragma: no cover - no-op span/provider behavior
            pass


_telemetry = MetadataTelemetry(trace.get_tracer(SERVICE), metrics.get_meter(SERVICE))
_providers: tuple[TracerProvider, MeterProvider] | None = None


def get_telemetry() -> MetadataTelemetry:
    """Return the active telemetry facade (a safe no-op proxy before setup)."""
    return _telemetry


def configure_observability(settings: Settings) -> MetadataTelemetry:
    """Configure JSON logging and optional OTLP export without blocking startup."""
    global _telemetry, _providers
    os.environ["AGNO_TELEMETRY"] = "false"
    _configure_json_logging(settings.log_level, settings.observability_json_logs)
    if _providers is not None:
        return _telemetry
    resource = Resource.create(
        {
            SERVICE_NAME: SERVICE,
            SERVICE_VERSION: "0.1.0",
            "deployment.environment": settings.app_env,
        }
    )
    try:
        tracer_provider = TracerProvider(resource=resource)
        if settings.otel_exporter_otlp_endpoint:
            meter_provider = _attach_otlp_exporters(tracer_provider, resource, settings)
        else:
            meter_provider = MeterProvider(resource=resource)
        _telemetry = MetadataTelemetry(
            tracer_provider.get_tracer(SERVICE),
            meter_provider.get_meter(SERVICE),
        )
        _providers = (tracer_provider, meter_provider)
        logger.info("AncoraMind metadata-only observability configured")
    except Exception:
        # Keep a no-op proxy and continue: observability is explicitly fail-open.
        logger.warning("AncoraMind observability setup failed; continuing without OTLP export")
    return _telemetry


def shutdown_observability() -> None:
    """Flush/shutdown providers best-effort during application shutdown."""
    if _providers is None:
        return
    for provider in _providers:
        try:
            provider.shutdown()
        except Exception:  # pragma: no cover - exporter/provider failures are environment-specific
            logger.debug("Observability provider shutdown failed", exc_info=False)


def _attach_otlp_exporters(
    tracer_provider: TracerProvider,
    resource: Resource,
    settings: Settings,
) -> MeterProvider:
    """Attach private-Collector exporters lazily so local no-export startup stays light."""
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    span_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=settings.otel_exporter_otlp_insecure,
        timeout=settings.otel_exporter_otlp_timeout_seconds,
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_otlp_insecure,
            timeout=settings.otel_exporter_otlp_timeout_seconds,
        ),
        export_interval_millis=settings.otel_export_interval_millis,
    )
    return MeterProvider(resource=resource, metric_readers=[metric_reader])


def _configure_json_logging(log_level: str, enabled: bool) -> None:
    if not enabled:
        return
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        handler.setFormatter(MetadataOnlyJsonFormatter())
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
