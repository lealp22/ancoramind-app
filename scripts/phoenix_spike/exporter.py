"""Experimental ADR-007 boundary; NOT a production capture authorization.

Only spans explicitly marked synthetic may carry content. Every other span is
dropped. No network, provider registration, settings, retries or application hooks
live here. Generic OpenInference content cannot establish its own provenance.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import SpanContext, Status, TraceState
from opentelemetry.util.types import AttributeValue

from src.observability.masking import mask_sensitive

_MESSAGE = re.compile(
    r"llm\.(?:input|output)_messages\.\d+\.message\.(?:role|content|name|tool_call_id|"
    r"tool_calls\.\d+\.tool_call\.(?:id|function\.(?:name|arguments)))"
)
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
_TOOLS = frozenset({"lookup_synthetic", "present_reply", "propose_vehicle"})
_KINDS = frozenset({"AGENT", "CHAIN", "LLM", "TOOL"})
_MAX_TEXT = 64_000


def _technical_context(context: SpanContext | None) -> SpanContext | None:
    if context is None:
        return None
    # W3C tracestate is another arbitrary-string surface, including on parent.
    return SpanContext(
        context.trace_id, context.span_id, context.is_remote,
        trace_flags=context.trace_flags, trace_state=TraceState(),
    )


def user_pseudonym(user_id: str, key: bytes) -> str:
    """Domain-separated HMAC; caller owns a dedicated key, never persisted here."""
    if len(key) < 32:
        raise ValueError("Pseudonym key too short")
    return hmac.new(key, b"phoenix-user-v1:" + user_id.encode(), hashlib.sha256).hexdigest()[:32]


class SyntheticMaskedExporter(SpanExporter):
    """Copy/sanitize every export surface, fail-closed per span and fail-open on I/O.

    Marker and bounded synthetic tool registry are deliberately NOT a production
    policy. Changing this to accept real content requires ADR-007 and a trusted
    capture seam excluding documents/voice BEFORE instrumentation.
    """

    def __init__(self, delegate: SpanExporter, masker: Callable[[str], str] = mask_sensitive):
        self.delegate = delegate
        self.masker = masker
        self.exported = 0
        self.dropped = 0
        self.failures = 0

    def _text(self, value: object) -> str:
        if not isinstance(value, str) or len(value) > _MAX_TEXT:
            raise ValueError("Invalid text projection")
        return self.masker(value)

    def _json_value(self, value: Any, depth: int = 0) -> Any:
        if depth > 20:
            raise ValueError("Excessive projection depth")
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if key.lower() in _EXCLUDED:
                    raise ValueError("Excluded content")
                if key.lower() in _IDENTIFIERS:
                    result[key] = _IDENTIFIERS[key.lower()]
                else:
                    result[self._text(key)] = self._json_value(child, depth + 1)
            return result
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

    def _copy(self, span: ReadableSpan) -> ReadableSpan:
        source = span.attributes or {}
        if source.get("ancora.capture.source") != "synthetic_text":
            raise ValueError("No trusted synthetic provenance")
        kind = source.get("openinference.span.kind")
        if kind not in _KINDS:
            raise ValueError("Unknown span kind")
        attributes: dict[str, AttributeValue] = {"openinference.span.kind": str(kind)}
        for key, value in source.items():
            if key in {"ancora.correlation_id", "ancora.interaction_id"}:
                attributes[key] = str(UUID(str(value)))
            elif key == "user.id":
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
                    raise ValueError("User must be pseudonymized before capture")
                attributes[key] = value
            elif key in _COUNTS | _COSTS:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Invalid numeric metadata")
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid numeric metadata")
                attributes[key] = value
            elif key == "llm.model_name":
                attributes[key] = self._text(value)
            elif key == "tool.name" or (_MESSAGE.fullmatch(key) and key.endswith("function.name")):
                if value not in _TOOLS:
                    raise ValueError("Tool outside synthetic scope")
                attributes[key] = str(value)
            elif key == "tool.parameters" or (
                _MESSAGE.fullmatch(key) and key.endswith("arguments")
            ):
                parsed = json.loads(self._text_input(value))
                attributes[key] = json.dumps(self._json_value(parsed), ensure_ascii=False)
            elif _MESSAGE.fullmatch(key):
                attributes[key] = self._text(value)
        # Name, resource, events, links, scope and status descriptions are also
        # payload surfaces. Rebuild/drop rather than mutate shared SDK spans.
        return ReadableSpan(
            name=f"phoenix.synthetic.{str(kind).lower()}",
            context=_technical_context(span.context),
            parent=_technical_context(span.parent),
            kind=span.kind,
            start_time=span.start_time,
            end_time=span.end_time,
            status=Status(span.status.status_code),
            attributes=attributes,
            resource=Resource(
                {
                    "service.name": "ancoramind-phoenix-spike",
                    "openinference.project.name": "spike",
                }
            ),
            events=(),
            links=(),
        )

    @staticmethod
    def _text_input(value: object) -> str:
        if not isinstance(value, str) or len(value) > _MAX_TEXT:
            raise ValueError("Invalid JSON projection")
        return value

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        safe = []
        for span in spans:
            try:
                safe.append(self._copy(span))
            except Exception:
                self.dropped += 1
        if not safe:
            return SpanExportResult.SUCCESS
        try:
            result = self.delegate.export(tuple(safe))
            if result is SpanExportResult.SUCCESS:
                self.exported += len(safe)
            else:
                self.failures += 1
            return result
        except Exception:
            self.failures += 1
            return SpanExportResult.FAILURE

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
