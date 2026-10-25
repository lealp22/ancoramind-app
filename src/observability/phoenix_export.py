"""Masked content-trace pipeline for Phoenix (ADR-007 / specs/046 T4).

A pipeline fully separate from the metadata-only Grafana one in ``telemetry.py``:
its own ``TracerProvider`` (never registered as global) and a wrapping
``SpanExporter`` that rebuilds every span from an allowlist, masks every text and
drops the whole span on any doubt (fail-closed per span). Network failures are
swallowed (fail-open): Phoenix is never part of the functional success path.

Content is only accepted from spans whose ``ancora.capture.source`` names a
provenance the capture seam (T6) knows by construction. Nothing here can establish
provenance by itself, so documents, extractions and voice are excluded BEFORE a
span exists; this module is the last line of defence, not the only one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import SpanContext, Status, TraceState
from opentelemetry.util.types import AttributeValue

from src.observability.masking import mask_sensitive

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)

SERVICE = "ancoramind-core"
CAPTURE_SOURCE_ATTRIBUTE = "ancora.capture.source"
# Provenances the capture seam can vouch for by construction (specs/046 "Diseño de
# captura"). Anything else, including voice or document-derived text, is dropped.
CAPTURE_SOURCES = frozenset(
    {"user_text", "final_reply", "proposal_args", "call_metadata", "tool_metadata"}
)

_MESSAGE = re.compile(
    r"llm\.(?:input|output)_messages\.\d+\.message\.(?:role|content|name|tool_call_id|"
    r"tool_calls\.\d+\.tool_call\.(?:id|function\.(?:name|arguments)))"
)
_TEXT_ATTRIBUTES = frozenset({"input.value", "output.value"})
_TOOL_NAME = re.compile(r"propose_[a-z0-9_]+|present_reply")
_PSEUDONYM = re.compile(r"[0-9a-f]{32}")
# Per-tool metadata spans (specs/046 "Visibilidad por tool"): a bare identifier, so a
# name cannot smuggle digits/spaces/punctuation; capture already maps unknown names.
_TOOL_IDENTIFIER = re.compile(r"[a-z][a-z_]{0,63}")
_TOOL_OUTCOMES = frozenset({"ok", "error"})
_TOOL_NUMBERS = frozenset(
    {"ancora.tool.index", "ancora.tool.duration_ms", "ancora.tool.result_chars"}
)
_TOOL_ERROR_MESSAGE = "ancora.tool.error_message"
# Tool error text is a free string written by the tool or a library (it may quote
# values), so it is only accepted on a span that declares ``outcome=error`` and is
# bounded harder than ordinary text.
_MAX_TOOL_ERROR_CHARS = 300
# Exception class names only (never messages), so a failed run is diagnosable.
_ERROR_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_.]{0,99}")
# Schema layer (ADR-007 layer 1): masked by field name whatever the value looks like.
_IDENTIFIERS = {
    "registration": "[MATRICULA]",
    "vin": "[BASTIDOR]",
    "user_id": "[USUARIO]",
    "telegram_user_id": "[USUARIO]",
    "email": "[EMAIL]",
    "phone": "[TELEFONO]",
    "iban": "[IBAN]",
    "dni": "[DNI]",
    "nie": "[NIE]",
}
# A tool payload carrying any of these keys is never exported, not even masked.
_EXCLUDED = frozenset(
    {
        "audio",
        "transcript",
        "transcription",
        "images",
        "image",
        "files",
        "file",
        "document",
        "documents",
        "document_content",
        "ai_extractions",
        "extracted_text",
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "headers",
        "storage_key",
    }
)
_COUNTS = frozenset(
    {"llm.token_count.prompt", "llm.token_count.completion", "llm.token_count.total"}
)
_COSTS = frozenset({"llm.cost.prompt", "llm.cost.completion", "llm.cost.total"})
_KINDS = frozenset({"AGENT", "CHAIN", "LLM", "TOOL"})
_MAX_TEXT = 64_000
_MAX_DEPTH = 20


def _technical_context(context: SpanContext | None) -> SpanContext | None:
    if context is None:
        return None
    # W3C tracestate is another arbitrary-string surface, including on the parent.
    return SpanContext(
        context.trace_id,
        context.span_id,
        context.is_remote,
        trace_flags=context.trace_flags,
        trace_state=TraceState(),
    )


def user_pseudonym(user_id: str, key: bytes) -> str:
    """Domain-separated HMAC of a user id; ``key`` is the dedicated Phoenix key."""
    if len(key) < 32:
        raise ValueError("Pseudonym key too short")
    return hmac.new(key, b"phoenix-user-v1:" + user_id.encode(), hashlib.sha256).hexdigest()[:32]


class MaskedSpanExporter(SpanExporter):
    """Rebuild/sanitize every export surface; fail-closed per span, fail-open on I/O."""

    def __init__(
        self,
        delegate: SpanExporter,
        *,
        project_name: str,
        masker: Callable[[str], str] = mask_sensitive,
    ) -> None:
        self.delegate = delegate
        self.masker = masker
        self._resource = Resource(
            {SERVICE_NAME: SERVICE, "openinference.project.name": project_name}
        )
        self.exported = 0
        self.dropped = 0
        self.failures = 0
        self._table = self._sanitizers()

    def _text(self, value: object) -> str:
        if not isinstance(value, str) or len(value) > _MAX_TEXT:
            raise ValueError("Invalid text projection")
        return self.masker(value)

    def _json_object(self, value: dict[Any, Any], depth: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Non-string key")
            lowered = key.lower()
            if lowered in _EXCLUDED:
                raise ValueError("Excluded content")
            if lowered in _IDENTIFIERS:
                result[key] = _IDENTIFIERS[lowered]
            else:
                result[self._text(key)] = self._json_value(child, depth + 1)
        return result

    def _json_value(self, value: Any, depth: int = 0) -> Any:
        if depth > _MAX_DEPTH:
            raise ValueError("Excessive projection depth")
        if isinstance(value, dict):
            return self._json_object(value, depth)
        if isinstance(value, list):
            return [self._json_value(item, depth + 1) for item in value]
        if isinstance(value, str):
            return self._text(value)
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and math.isfinite(value):
            # Numeric identifiers may occur outside known schema fields too.
            return self._text(str(value))
        raise ValueError("Unsupported projection")

    def _json_text(self, value: object) -> str:
        if not isinstance(value, str) or len(value) > _MAX_TEXT:
            raise ValueError("Invalid JSON projection")
        return json.dumps(self._json_value(json.loads(value)), ensure_ascii=False)

    @staticmethod
    def _number(value: object) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Invalid numeric metadata")
        if not math.isfinite(value) or value < 0:
            raise ValueError("Invalid numeric metadata")
        return value

    @staticmethod
    def _pseudonym(value: object) -> str:
        if not isinstance(value, str) or not _PSEUDONYM.fullmatch(value):
            raise ValueError("User must be pseudonymized before capture")
        return value

    @staticmethod
    def _error_type(value: object) -> str:
        if not isinstance(value, str) or not _ERROR_TYPE.fullmatch(value):
            raise ValueError("Invalid error type")
        return value

    @staticmethod
    def _tool_identifier(value: object) -> str:
        if not isinstance(value, str) or not _TOOL_IDENTIFIER.fullmatch(value):
            raise ValueError("Invalid tool identifier")
        return value

    @staticmethod
    def _tool_outcome(value: object) -> str:
        if not isinstance(value, str) or value not in _TOOL_OUTCOMES:
            raise ValueError("Invalid tool outcome")
        return value

    def _tool_error_message(self, value: object, source: Mapping[str, Any]) -> str:
        if source.get("ancora.tool.outcome") != "error":
            raise ValueError("Error message on a span that did not fail")
        if not isinstance(value, str) or len(value) > _MAX_TOOL_ERROR_CHARS:
            raise ValueError("Invalid tool error message")
        return self._text(value)

    @staticmethod
    def _tool_name(value: object) -> str:
        if not isinstance(value, str) or not _TOOL_NAME.fullmatch(value):
            raise ValueError("Tool outside capture scope")
        return value

    def _sanitizers(self) -> dict[str, Callable[[object, Mapping[str, Any]], AttributeValue]]:
        """Exact-key allowlist: attribute name -> sanitizer. Unlisted keys are dropped."""

        def plain(fn: Callable[[object], AttributeValue]) -> Callable[..., AttributeValue]:
            return lambda value, _source: fn(value)

        table: dict[str, Callable[..., AttributeValue]] = {
            "ancora.correlation_id": plain(lambda v: str(UUID(str(v)))),
            "ancora.interaction_id": plain(lambda v: str(UUID(str(v)))),
            "user.id": plain(self._pseudonym),
            "llm.model_name": plain(self._text),
            "error.type": plain(self._error_type),
            "ancora.tool.name": plain(self._tool_identifier),
            "ancora.tool.outcome": plain(self._tool_outcome),
            _TOOL_ERROR_MESSAGE: self._tool_error_message,
            "tool.name": plain(self._tool_name),
            "tool.parameters": plain(self._json_text),
        }
        for key in _COUNTS | _COSTS | _TOOL_NUMBERS:
            table[key] = plain(self._number)
        for key in _TEXT_ATTRIBUTES:
            table[key] = plain(self._text)
        return table

    def _attribute(
        self, key: str, value: object, source: Mapping[str, Any]
    ) -> AttributeValue | None:
        """Sanitized value for an allowlisted ``key``; ``None`` means not allowlisted."""
        sanitizer = self._table.get(key)
        if sanitizer is not None:
            return sanitizer(value, source)
        if _MESSAGE.fullmatch(key):
            if key.endswith("function.name"):
                return self._tool_name(value)
            if key.endswith("arguments"):
                return self._json_text(value)
            return self._text(value)
        return None

    def _copy(self, span: ReadableSpan) -> ReadableSpan:
        source = span.attributes or {}
        if source.get(CAPTURE_SOURCE_ATTRIBUTE) not in CAPTURE_SOURCES:
            raise ValueError("No trusted capture provenance")
        kind = source.get("openinference.span.kind")
        if kind not in _KINDS:
            raise ValueError("Unknown span kind")
        attributes: dict[str, AttributeValue] = {
            CAPTURE_SOURCE_ATTRIBUTE: str(source[CAPTURE_SOURCE_ATTRIBUTE]),
            "openinference.span.kind": str(kind),
        }
        for key, value in source.items():
            sanitized = self._attribute(key, value, source)
            # Everything not handled above is dropped: this is an allowlist.
            if sanitized is not None:
                attributes[key] = sanitized
        # Name, resource, events, links, scope and status descriptions are also
        # payload surfaces. Rebuild/drop rather than mutate shared SDK spans.
        return ReadableSpan(
            name=f"ancora.{str(kind).lower()}",
            context=_technical_context(span.context),
            parent=_technical_context(span.parent),
            kind=span.kind,
            start_time=span.start_time,
            end_time=span.end_time,
            status=Status(span.status.status_code),
            attributes=attributes,
            resource=self._resource,
            events=(),
            links=(),
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        safe: list[ReadableSpan] = []
        for span in spans:
            try:
                safe.append(self._copy(span))
            except Exception:
                # Never log the exception: its message may quote the rejected content.
                self.dropped += 1
        if not safe:
            return SpanExportResult.SUCCESS
        try:
            result = self.delegate.export(tuple(safe))
        except Exception:
            self.failures += 1
            return SpanExportResult.FAILURE
        if result is SpanExportResult.SUCCESS:
            self.exported += len(safe)
        else:
            self.failures += 1
        return result

    def shutdown(self) -> None:
        try:
            self.delegate.shutdown()
        except Exception:
            self.failures += 1

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        try:
            return bool(self.delegate.force_flush(timeout_millis))
        except Exception:
            self.failures += 1
            return False


class PhoenixTracing:
    """Handle on the isolated provider; owns the pseudonym key, never exposes it."""

    def __init__(
        self,
        provider: TracerProvider,
        exporter: MaskedSpanExporter,
        pseudonym_key: bytes,
    ) -> None:
        self.provider = provider
        self.exporter = exporter
        self._pseudonym_key = pseudonym_key

    def tracer(self) -> Any:
        return self.provider.get_tracer(SERVICE)

    def pseudonym(self, user_id: str) -> str:
        return user_pseudonym(user_id, self._pseudonym_key)

    def shutdown(self) -> None:
        try:
            self.provider.shutdown()
        except Exception:
            logger.debug("Phoenix provider shutdown failed", exc_info=False)


_tracing: PhoenixTracing | None = None


def get_phoenix_tracing() -> PhoenixTracing | None:
    """Active Phoenix pipeline, or ``None`` when disabled/misconfigured/failed."""
    return _tracing


def build_phoenix_tracing(
    settings: Settings,
    *,
    delegate: SpanExporter | None = None,
) -> PhoenixTracing | None:
    """Build the isolated pipeline, or ``None`` if inactive. Never raises.

    ``delegate`` replaces the OTLP exporter in tests. The provider is deliberately
    not registered as the global one, so no instrumentation can feed it by accident.
    """
    if not settings.phoenix_tracing_active:
        return None
    try:
        exporter = MaskedSpanExporter(
            delegate or _otlp_exporter(settings),
            project_name=settings.phoenix_project_name.strip(),
        )
        provider = TracerProvider(resource=Resource({SERVICE_NAME: SERVICE}))
        provider.add_span_processor(BatchSpanProcessor(exporter))
        return PhoenixTracing(
            provider,
            exporter,
            settings.phoenix_user_pseudonym_key.strip().encode(),
        )
    except Exception as exc:
        # Type name only: messages may carry endpoint or credential fragments.
        logger.warning(
            "Phoenix tracing setup failed (%s); continuing without it", type(exc).__name__
        )
        return None


def configure_phoenix_tracing(settings: Settings) -> PhoenixTracing | None:
    """Idempotently activate the pipeline; a no-op while the flag/config is off."""
    global _tracing
    if _tracing is None:
        _tracing = build_phoenix_tracing(settings)
        if _tracing is not None:
            logger.info("AncoraMind Phoenix masked content tracing configured")
    return _tracing


def shutdown_phoenix_tracing() -> None:
    """Flush/shutdown best-effort during application shutdown."""
    global _tracing
    tracing, _tracing = _tracing, None
    if tracing is not None:
        tracing.shutdown()


def _otlp_exporter(settings: Settings) -> SpanExporter:
    """Private-network gRPC exporter, imported lazily so the flag-off path stays light."""
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    endpoint = settings.phoenix_collector_endpoint.strip()
    return OTLPSpanExporter(
        endpoint=endpoint,
        insecure=endpoint.startswith("http://"),
        timeout=settings.otel_exporter_otlp_timeout_seconds,
        headers={"authorization": "Bearer " + settings.phoenix_api_key.strip()},
    )
