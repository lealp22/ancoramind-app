"""Manual capture seam for masked Phoenix traces (ADR-007 / specs/046 T6).

Provenance is known by construction at the caller (``GovernedInteractionRunner.run``)
and this module only turns an already-classified ``TurnRecord`` into spans. It never
inspects text to guess where it came from: if the provenance is not certain the
field is simply not part of the record.

What is captured, each under its own ``ancora.capture.source``:

* ``call_metadata``: ids, pseudonymous user, route, tokens, cost, error class name.
  Always, also for failed runs (the ``InvalidPresentationOutputError`` case).
* ``user_text``: the text the user typed (never voice, never synthesized text).
* ``final_reply`` / ``proposal_args``: model-generated content, only when the turn
  could not have surfaced document-derived content (see ``model_content_allowed``).

Never captured: audio, transcripts, attachments, tool read results, history,
compaction summaries, and the extraction/Dream/compaction/eval routes (those never
reach the runner). Capture is fail-open: no error here can reach the Agent.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from opentelemetry.context import Context
from opentelemetry.trace import SpanKind, Status, StatusCode, set_span_in_context

from src.observability.phoenix_export import CAPTURE_SOURCE_ATTRIBUTE, PhoenixTracing

logger = logging.getLogger(__name__)

# Read tools whose results are the user's own canonical records or free text. A turn
# that used ONLY these (plus propose_* and present_reply) may expose model-generated
# content. Everything else is excluded by default, so a newly registered tool is
# never captured until someone classifies it here:
#   search_documents*, get_document, analyze_document, export_document -> document
#   content or extractions (ADR-007 exclusion);
#   search_web -> third-party content, not the user's data.
SAFE_READ_TOOLS = frozenset(
    {
        "search_notes",
        "list_todo_lists",
        "list_todo_items",
        "list_reminders",
        "check_calendar",
        "list_pending_proposals",
        "find_vehicle",
        "get_vehicle_summary",
        "get_vehicle_maintenance_history",
    }
)
_PRESENT_REPLY = "present_reply"
# Registered tools whose results can carry document or third-party content. They are
# known by name (so their calls are visible as metadata) but never unlock model content.
CONTENT_TOOLS = frozenset(
    {
        "search_documents",
        "search_documents_semantically",
        "get_document",
        "analyze_document",
        "export_document",
        "search_web",
        # Not registered in main.py today. Its result is what the system inferred
        # about the user, not their own records: not in SAFE_READ_TOOLS until the
        # owner decides.
        "list_my_preferences",
    }
)
# Every ``propose_*`` tool defined under ``src/agent/tools``; a drift test fails when
# a new one is added without being listed here.
PROPOSE_TOOLS = frozenset(
    {
        "propose_note",
        "propose_document_delete",
        "propose_preference_forget",
        "propose_vehicle",
        "propose_vehicle_maintenance",
        "propose_reminder",
        "propose_reminder_snooze",
        "propose_calendar_event",
        "propose_todo_list",
        "propose_todo_list_rename",
        "propose_todo_list_delete",
        "propose_todo_item",
        "propose_todo_item_update",
        "propose_todo_item_complete",
        "propose_todo_item_reopen",
        "propose_todo_item_move",
        "propose_todo_item_delete",
    }
)
# Proposing a document deletion names a document: its filename is untrusted metadata.
_EXCLUDED_PROPOSALS = frozenset({"propose_document_delete"})
KNOWN_TOOLS = SAFE_READ_TOOLS | CONTENT_TOOLS | PROPOSE_TOOLS | {_PRESENT_REPLY}
UNKNOWN_TOOL = "unknown_tool"


MAX_TOOL_ERROR_CHARS = 300
# Pydantic validation errors quote the received value after this marker.
_QUOTED_VALUE_MARKER = "input_value="


def bounded_tool_error(message: str | None) -> str | None:
    """First line of a tool error, cut before any quoted argument value, bounded.

    Tool error text is a free string produced by the tool or a library and may quote
    data (Pydantic's ``input_value=...``, SQL fragments, hostnames). Only the first
    line is kept, then cut at the quoted-value marker. The exporter masks what is
    left; this limits how much unrecognised text can reach a span in the first place.
    """
    if not message or not message.strip():
        return None
    first = message.strip().splitlines()[0]
    cut = first.find(_QUOTED_VALUE_MARKER)
    if cut != -1:
        first = first[:cut]
    first = first.strip()
    return first[:MAX_TOOL_ERROR_CHARS] or None


def public_tool_name(name: str) -> str:
    """The tool name as it may appear in a span.

    The model chooses tool names, so an unregistered one (a hallucinated or injected
    string) must never reach a span verbatim.
    """
    return name if name in KNOWN_TOOLS else UNKNOWN_TOOL


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: Mapping[str, object]
    failed: bool = False
    duration_ms: float | None = None
    result_chars: int | None = None
    """Size of the result only; the result itself is never carried."""
    error_message: str | None = None
    """Bounded error text, set only when ``failed`` (see ``bounded_tool_error``)."""


@dataclass(frozen=True)
class TurnRecord:
    """One Agent turn, with provenance decided by the caller."""

    correlation_id: UUID
    user_id: str
    started_ns: int
    ended_ns: int
    route: str
    user_text: str | None = None
    """Only text the user typed; ``None`` for voice or synthesized text."""
    answer: str | None = None
    proposal_text: str | None = None
    tool_calls: Sequence[ToolCallRecord] = ()
    had_media: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    error_type: str | None = None


def model_content_allowed(record: TurnRecord) -> bool:
    """Whether model-generated text of this turn may be captured.

    Fail-safe: any attachment, or any tool outside the known-safe sets, means the
    reply could restate document-derived content, so none of it is captured.
    """
    if record.had_media:
        return False
    for call in record.tool_calls:
        name = call.name
        if name == _PRESENT_REPLY or name in SAFE_READ_TOOLS:
            continue
        # Registered names only: a made-up ``propose_*`` string unlocks nothing.
        if name in PROPOSE_TOOLS and name not in _EXCLUDED_PROPOSALS:
            continue
        return False
    return True


def capture_turn(tracing: PhoenixTracing | None, record: TurnRecord) -> None:
    """Emit the spans of one turn. Never raises; a no-op when Phoenix is inactive."""
    if tracing is None:
        return
    try:
        _emit(tracing, record)
    except Exception as exc:
        # Type name only: the message may quote the content being captured.
        logger.debug("Phoenix capture failed (%s)", type(exc).__name__)


def _common(tracing: PhoenixTracing, record: TurnRecord, source: str) -> dict[str, Any]:
    return {
        CAPTURE_SOURCE_ATTRIBUTE: source,
        "ancora.correlation_id": str(record.correlation_id),
        "ancora.interaction_id": str(record.correlation_id),
        # Every span of a trace carries the same pseudonym: per-user deletion works
        # by trace (specs/046 spike Q9).
        "user.id": tracing.pseudonym(record.user_id),
    }


def _root_attributes(tracing: PhoenixTracing, record: TurnRecord) -> dict[str, Any]:
    attributes = _common(tracing, record, "call_metadata")
    attributes["openinference.span.kind"] = "AGENT"
    attributes["llm.model_name"] = record.route
    for key, value in (
        ("llm.token_count.prompt", record.input_tokens),
        ("llm.token_count.completion", record.output_tokens),
        ("llm.token_count.total", record.total_tokens),
        ("llm.cost.total", record.cost_usd),
        ("error.type", record.error_type),
    ):
        if value is not None:
            attributes[key] = value
    return attributes


def _emit(tracing: PhoenixTracing, record: TurnRecord) -> None:
    tracer = tracing.tracer()
    # An explicit empty Context starts a new trace: the ambient current span belongs
    # to the metadata-only Grafana provider and must not become our parent.
    root = tracer.start_span(
        "agent.turn",
        context=Context(),
        kind=SpanKind.INTERNAL,
        attributes=_root_attributes(tracing, record),
        start_time=record.started_ns,
    )
    if record.error_type is not None:
        root.set_status(Status(StatusCode.ERROR))
    parent = set_span_in_context(root)

    def child(source: str, kind: str, extra: Mapping[str, Any]) -> None:
        attributes = _common(tracing, record, source)
        attributes["openinference.span.kind"] = kind
        attributes.update(extra)
        span = tracer.start_span(
            f"agent.{source}", context=parent, attributes=attributes, start_time=record.ended_ns
        )
        span.end(end_time=record.ended_ns)

    try:
        if record.user_text is not None:
            child("user_text", "CHAIN", {"input.value": record.user_text})
        _emit_tool_metadata(child, record)
        if model_content_allowed(record):
            _emit_model_content(child, record)
    finally:
        root.end(end_time=record.ended_ns)


def _emit_tool_metadata(child: Any, record: TurnRecord) -> None:
    """One metadata-only span per tool call, in call order (specs/046 "Visibilidad por tool").

    Name (registry-checked), outcome, duration and result size; for a failed call
    also its bounded, masked error message (owner decision 2026-10-25). Never
    arguments or successful results: those can carry document or third-party content.
    """
    for index, call in enumerate(record.tool_calls):
        attributes: dict[str, Any] = {
            "ancora.tool.name": public_tool_name(call.name),
            "ancora.tool.index": index,
            "ancora.tool.outcome": "error" if call.failed else "ok",
        }
        if call.duration_ms is not None:
            attributes["ancora.tool.duration_ms"] = call.duration_ms
        if call.result_chars is not None:
            attributes["ancora.tool.result_chars"] = call.result_chars
        # Only for a failed call, and only for a registered tool: the text of an
        # error can quote data, and ``unknown_tool`` is already an anomaly marker.
        if call.failed and call.error_message and public_tool_name(call.name) != UNKNOWN_TOOL:
            attributes["ancora.tool.error_message"] = call.error_message
        child("tool_metadata", "TOOL", attributes)


def _emit_model_content(child: Any, record: TurnRecord) -> None:
    if record.answer is not None or record.proposal_text is not None:
        reply = "\n\n".join(
            part.strip() for part in (record.answer, record.proposal_text) if part and part.strip()
        )
        child("final_reply", "CHAIN", {"output.value": reply})
    for call in record.tool_calls:
        if call.name in PROPOSE_TOOLS and call.name not in _EXCLUDED_PROPOSALS:
            # json.dumps without ``default``: a non-serializable argument aborts this
            # capture rather than being stringified into a span.
            child(
                "proposal_args",
                "TOOL",
                {"tool.name": call.name, "tool.parameters": json.dumps(call.args)},
            )
