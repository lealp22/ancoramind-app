"""specs/046 T7 + T8: privacy and fail-open of the two pipelines on a REAL governed turn.

A real ``GovernedInteractionRunner`` with the real ``GovernedAgentFactory`` (and its
budget tool hook, which is what emits the Grafana per-tool spans) runs a scripted
model. Two real ``TracerProvider`` instances export into memory: the metadata-only one
that stands in for Grafana, and the Phoenix one built by ``build_phoenix_tracing``.
Canaries enter through every door and the assertions look at what each exporter
actually received, not at the filters in isolation.

T7: no canary reaches the Grafana exporter; masked canaries are the only ones Phoenix
sees; audio/attachments/documents are absent; the LLM request and the persisted data
are untouched (criterion 9).
T8: Phoenix down, a failing masker or a broken provider never changes the reply.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.run import RunContext
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

import src.agent.tool_budget_hooks as hooks_module
import src.observability.telemetry as telemetry_module
from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_interaction_runner import GovernedInteractionRunner
from src.config import Settings
from src.domain.interactions.media import ResolvedTelegramMedia
from src.domain.interactions.reply import AgentReply, InvalidPresentationOutputError
from src.domain.llm_access.models import ExecutionContext
from src.observability.phoenix_export import MaskedSpanExporter, build_phoenix_tracing
from src.observability.telemetry import MetadataTelemetry
from tests.unit.test_governed_interaction_runner import _FakeManager, _snapshot

DNI = "12345678Z"
CARD = "4539 1488 0343 6467"
PHONE = "+34 612 345 678"
IBAN = "ES9121000418450200051332"
PLATE_FIELD = "9999 ZZZ"  # reaches a tool as the `registration` argument
USER_ID = "77001234"
LIST_ID = "0aa839cf-80fe-4593-87c3-2ce6816db448"
ERROR_SECRET = f"vehicle lookup failed for {DNI}"
READ_RESULT_SECRET = "RESULTADO-DE-LECTURA-CONFIDENCIAL"
DOCUMENT_SECRET = "CONTENIDO-DE-DOCUMENTO-CONFIDENCIAL"
ALL_CANARIES = (DNI, CARD, PHONE, IBAN, PLATE_FIELD, ERROR_SECRET)


class _Sink(SpanExporter):
    def __init__(self) -> None:
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Any) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def dump(self) -> str:
        return " ".join(span.to_json() for span in self.spans)


@dataclass
class _ScriptedModel(Model):
    """Replays a fixed list of tool calls, then the terminal ``present_reply``."""

    script: list[tuple[str, dict[str, Any]]] = field(default_factory=list, repr=False)
    requests: list[str] = field(default_factory=list, repr=False)
    step: int = field(default=0, repr=False)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
        yield

    def _parse_provider_response(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _parse_provider_response_delta(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def ainvoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        # What the provider would receive, captured BEFORE any telemetry could matter.
        messages = args[0] if args else kwargs.get("messages", [])
        self.requests.append(" ".join(str(getattr(m, "content", "")) for m in messages))
        if self.step >= len(self.script):
            # Fail fast: repeating the last call forever made a badly scripted run hang
            # until it exhausted memory.
            raise AssertionError("scripted model exhausted: the run did not end on present_reply")
        name, arguments = self.script[self.step]
        self.step += 1
        call = {
            "id": f"call-{self.step}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }
        return ModelResponse(tool_calls=[call])


class _Access:
    def __init__(self, model: Model) -> None:
        self._model = model

    def model_for(self, route_name: str, context: ExecutionContext) -> Model:
        return self._model


# ── real tools, shaped like the registered ones ──────────────────────────────

persisted: list[dict[str, Any]] = []


async def find_vehicle(run_context: RunContext, query: str) -> str:
    """Read tool whose result must never be copied anywhere."""
    return f"{READ_RESULT_SECRET} {query}"


async def get_document(run_context: RunContext, document_id: str) -> str:
    """Document tool: its content is excluded from Phoenix by construction."""
    return f"{DOCUMENT_SECRET} {DNI}"


async def propose_vehicle(
    run_context: RunContext,
    make: str,
    model: str,
    registration: str | None = None,
    nickname: str | None = None,
) -> str:
    """Proposal tool: its arguments are captured, masked, in Phoenix."""
    persisted.append({"registration": registration, "nickname": nickname})
    return "Propuesta creada"


async def list_todo_items(run_context: RunContext, list_id: str) -> str:
    """Read tool that fails with a message quoting data."""
    raise RuntimeError(ERROR_SECRET)


def _present(answer: str) -> tuple[str, dict[str, Any]]:
    return "present_reply", {"answer": answer, "proposal_text": ""}


@dataclass
class _Rig:
    runner: GovernedInteractionRunner
    model: _ScriptedModel
    grafana: _Sink
    phoenix: _Sink
    tracing: Any


def _rig(
    monkeypatch: pytest.MonkeyPatch,
    script: list[tuple[str, dict[str, Any]]],
    *,
    phoenix_on: bool = True,
    phoenix_delegate: SpanExporter | None = None,
) -> _Rig:
    # Grafana side: a real provider/tracer behind the real MetadataTelemetry facade,
    # patched into every module that imported the singleton accessor.
    grafana = _Sink()
    provider = TracerProvider(resource=Resource({"service.name": "ancoramind-core"}))
    provider.add_span_processor(SimpleSpanProcessor(grafana))
    meter = telemetry_module._telemetry._meter
    facade = MetadataTelemetry(provider.get_tracer("grafana-standin"), meter)
    monkeypatch.setattr(telemetry_module, "_telemetry", facade)
    monkeypatch.setattr(hooks_module, "get_telemetry", lambda: facade)
    monkeypatch.setattr("src.agent.governed_interaction_runner.get_telemetry", lambda: facade)

    phoenix = _Sink()
    tracing = None
    if phoenix_on:
        for name, value in {
            "PHOENIX_TRACING_ENABLED": "true",
            "PHOENIX_COLLECTOR_ENDPOINT": "http://phoenix.railway.internal:4317",
            "PHOENIX_API_KEY": "system-key",
            "PHOENIX_USER_PSEUDONYM_KEY": "k" * 32,
        }.items():
            monkeypatch.setenv(name, value)
        tracing = build_phoenix_tracing(
            Settings(_env_file=None), delegate=phoenix_delegate or phoenix
        )
        assert tracing is not None

    model = _ScriptedModel(id="scripted", script=script)
    factory = GovernedAgentFactory(
        llm_access=_Access(model),
        db=None,
        tools=[find_vehicle, get_document, propose_vehicle, list_todo_items],
        instructions=["Synthetic fixture"],
        fingerprint_key="synthetic-fingerprint-key-32-bytes!!",
    )
    runner = GovernedInteractionRunner(
        config_manager=_FakeManager(_snapshot()), factory=factory, phoenix_tracing=tracing
    )
    return _Rig(runner, model, grafana, phoenix, tracing)


async def _turn(rig: _Rig, text: str, **kwargs: Any) -> AgentReply:
    return await rig.runner.run(
        text,
        user_id=USER_ID,
        session_id="synthetic",
        run_id=f"run-{uuid4()}",
        correlation_id=uuid4(),
        telegram_update_id=1,
        **kwargs,
    )


def _flush(rig: _Rig) -> None:
    if rig.tracing is not None:
        rig.tracing.provider.force_flush()


def _without_clock(requests: list[str]) -> list[str]:
    return [re.sub(r"The current time is [^\n]*", "The current time is <now>", r) for r in requests]


@pytest.fixture(autouse=True)
def _reset_persisted() -> None:
    persisted.clear()


# ── T7 · the rig itself is not vacuous ──────────────────────────────────────


async def test_rig_produces_spans_in_both_pipelines(monkeypatch):
    """Guards every assertion below against passing because nothing was exported."""
    rig = _rig(monkeypatch, [("find_vehicle", {"query": "x"}), _present("ok")])
    await _turn(rig, "hola", capture_user_text=True)
    _flush(rig)
    grafana_names = {span.name for span in rig.grafana.spans}
    assert {"agno.agent.run", "ancora.tool.call"} <= grafana_names
    assert {span.attributes["ancora.capture.source"] for span in rig.phoenix.spans} >= {
        "call_metadata",
        "user_text",
        "tool_metadata",
        "final_reply",
    }


# ── T7 · Grafana never receives content ─────────────────────────────────────


async def test_grafana_exporter_receives_no_canary_from_a_full_turn(monkeypatch):
    rig = _rig(
        monkeypatch,
        [
            ("find_vehicle", {"query": CARD}),
            ("list_todo_items", {"list_id": LIST_ID}),
            (
                "propose_vehicle",
                {"make": "Seat", "model": "Ibiza", "registration": PLATE_FIELD, "nickname": PHONE},
            ),
            _present(f"Anotado {IBAN}"),
        ],
    )
    await _turn(rig, f"mi dni es {DNI} y mi tarjeta {CARD}", capture_user_text=True)
    _flush(rig)

    dumped = rig.grafana.dump()
    for secret in (*ALL_CANARIES, READ_RESULT_SECRET, "Anotado", "mi dni es", "Ibiza", "Seat"):
        assert secret not in dumped, f"{secret!r} reached the Grafana exporter"


async def test_grafana_spans_only_carry_allowlisted_attribute_keys(monkeypatch):
    rig = _rig(
        monkeypatch,
        [
            ("find_vehicle", {"query": "x"}),
            ("list_todo_items", {"list_id": LIST_ID}),
            _present("ok"),
        ],
    )
    await _turn(rig, "texto", capture_user_text=True)
    keys = {key for span in rig.grafana.spans for key in (span.attributes or {})}
    assert keys <= telemetry_module.SPAN_ATTRIBUTE_ALLOWLIST
    # None of the Phoenix-only namespaces may exist on the Grafana side.
    assert not {k for k in keys if k.startswith(("input.", "output.", "llm.", "tool.", "user."))}
    assert "ancora.capture.source" not in keys


async def test_a_failed_tool_exposes_only_the_class_name_to_grafana(monkeypatch):
    rig = _rig(monkeypatch, [("list_todo_items", {"list_id": LIST_ID}), _present("ok")])
    await _turn(rig, "texto", capture_user_text=True)
    tool_spans = [s for s in rig.grafana.spans if s.name == "ancora.tool.call"]
    assert tool_spans and tool_spans[0].attributes["error.type"] == "RuntimeError"
    assert ERROR_SECRET not in rig.grafana.dump()
    assert DNI not in rig.grafana.dump()


async def test_the_phoenix_provider_is_not_the_global_one_so_grafana_cannot_see_its_spans(
    monkeypatch,
):
    rig = _rig(monkeypatch, [_present("ok")])
    await _turn(rig, f"dni {DNI}", capture_user_text=True)
    _flush(rig)
    phoenix_trace_ids = {span.context.trace_id for span in rig.phoenix.spans}
    grafana_trace_ids = {span.context.trace_id for span in rig.grafana.spans}
    assert phoenix_trace_ids
    assert not phoenix_trace_ids & grafana_trace_ids


# ── T7 · Phoenix sees masked content and nothing excluded ───────────────────


async def test_phoenix_receives_no_unmasked_canary_from_a_full_turn(monkeypatch):
    rig = _rig(
        monkeypatch,
        [
            ("list_todo_items", {"list_id": LIST_ID}),
            (
                "propose_vehicle",
                {"make": "Seat", "model": "Ibiza", "registration": PLATE_FIELD, "nickname": PHONE},
            ),
            _present(f"Anotado {IBAN}"),
        ],
    )
    await _turn(rig, f"mi dni es {DNI} y mi tarjeta {CARD}", capture_user_text=True)
    _flush(rig)

    dumped = rig.phoenix.dump()
    for canary in (DNI, CARD, PHONE, IBAN, PLATE_FIELD):
        assert canary not in dumped, f"{canary!r} reached the Phoenix exporter unmasked"
    for marker in ("[DNI]", "[TARJETA]", "[TELEFONO]", "[IBAN]", "[MATRICULA]"):
        assert marker in dumped, f"{marker} missing: content was not captured at all"


async def test_phoenix_never_carries_the_raw_user_id(monkeypatch):
    rig = _rig(monkeypatch, [_present("ok")])
    await _turn(rig, "hola", capture_user_text=True)
    _flush(rig)
    assert USER_ID not in rig.phoenix.dump()
    pseudonyms = {span.attributes["user.id"] for span in rig.phoenix.spans}
    assert pseudonyms == {rig.tracing.pseudonym(USER_ID)}


async def test_results_of_read_tools_are_never_captured(monkeypatch):
    rig = _rig(monkeypatch, [("find_vehicle", {"query": "ARG-DE-LECTURA"}), _present("ok")])
    await _turn(rig, "hola", capture_user_text=True)
    _flush(rig)
    dumped = rig.phoenix.dump()
    assert READ_RESULT_SECRET not in dumped
    assert "ARG-DE-LECTURA" not in dumped
    sizes = [s.attributes.get("ancora.tool.result_chars") for s in rig.phoenix.spans]
    assert any(isinstance(size, int) and size > 0 for size in sizes)


async def test_document_content_is_absent_and_the_reply_is_withheld(monkeypatch):
    rig = _rig(
        monkeypatch,
        [
            ("get_document", {"document_id": LIST_ID}),
            _present(f"El documento dice {DOCUMENT_SECRET}"),
        ],
    )
    await _turn(rig, "léeme el documento", capture_user_text=True)
    _flush(rig)
    dumped = rig.phoenix.dump()
    assert DOCUMENT_SECRET not in dumped
    assert "El documento dice" not in dumped
    assert DNI not in dumped
    sources = {s.attributes["ancora.capture.source"] for s in rig.phoenix.spans}
    assert "final_reply" not in sources
    assert "get_document" in dumped  # the call itself stays visible as metadata


async def test_a_voice_turn_sends_no_user_text_to_phoenix(monkeypatch):
    rig = _rig(monkeypatch, [_present("ok")])
    await _turn(rig, f"transcripción de voz con {DNI}")  # capture_user_text defaults to False
    _flush(rig)
    sources = {s.attributes["ancora.capture.source"] for s in rig.phoenix.spans}
    assert "user_text" not in sources
    assert "transcripción" not in rig.phoenix.dump()
    assert DNI not in rig.phoenix.dump()


async def test_attachment_bytes_and_filename_never_reach_either_pipeline(monkeypatch):
    rig = _rig(monkeypatch, [_present(f"Resumen {DOCUMENT_SECRET}")])

    async def ingest(*_args: Any, **_kwargs: Any) -> str:
        return ""

    monkeypatch.setattr(
        "src.agent.governed_interaction_runner.ingest_resolved_telegram_media", ingest
    )
    media = (
        ResolvedTelegramMedia(
            content=b"BYTES-CONFIDENCIALES",
            filename="factura-maria.pdf",
            mime_type="application/pdf",
            is_image=False,
        ),
    )
    await _turn(rig, "guarda esto", capture_user_text=True, media=media)
    _flush(rig)
    for sink in (rig.grafana, rig.phoenix):
        dumped = sink.dump()
        assert "BYTES-CONFIDENCIALES" not in dumped
        assert "factura-maria" not in dumped
    assert DOCUMENT_SECRET not in rig.phoenix.dump()
    assert "final_reply" not in {s.attributes["ancora.capture.source"] for s in rig.phoenix.spans}


async def test_a_failed_tool_exports_its_message_masked_to_phoenix_only(monkeypatch):
    rig = _rig(monkeypatch, [("list_todo_items", {"list_id": LIST_ID}), _present("ok")])
    await _turn(rig, "texto", capture_user_text=True)
    _flush(rig)
    errors = [
        s.attributes["ancora.tool.error_message"]
        for s in rig.phoenix.spans
        if "ancora.tool.error_message" in (s.attributes or {})
    ]
    assert errors == ["vehicle lookup failed for [DNI]"]
    assert DNI not in rig.phoenix.dump()
    assert "ancora.tool.error_message" not in " ".join(
        key for span in rig.grafana.spans for key in (span.attributes or {})
    )


# ── T7 · criterion 9: masking never alters what the LLM or the database get ──


async def test_masking_does_not_alter_the_llm_request_or_what_is_persisted(monkeypatch):
    script = [
        ("propose_vehicle", {"make": "Seat", "model": "Ibiza", "registration": PLATE_FIELD}),
        _present("ok"),
    ]
    on = _rig(monkeypatch, script, phoenix_on=True)
    await _turn(on, f"mi dni es {DNI}", capture_user_text=True)
    persisted_with_phoenix = list(persisted)
    requests_with_phoenix = list(on.model.requests)

    persisted.clear()
    off = _rig(monkeypatch, script, phoenix_on=False)
    await _turn(off, f"mi dni es {DNI}", capture_user_text=True)

    assert persisted_with_phoenix == list(persisted) == [
        {"registration": PLATE_FIELD, "nickname": None}
    ]
    # Agno stamps the current time into the system prompt; it is the only legitimate
    # difference between two runs of the same script.
    assert _without_clock(requests_with_phoenix) == _without_clock(off.model.requests)
    # The model still saw the real value; masking is telemetry-only.
    assert any(DNI in request for request in on.model.requests)
    assert all("[DNI]" not in request for request in on.model.requests)


async def test_phoenix_off_exports_nothing_and_changes_nothing_for_grafana(monkeypatch):
    rig = _rig(monkeypatch, [("find_vehicle", {"query": "x"}), _present("ok")], phoenix_on=False)
    reply = await _turn(rig, f"dni {DNI}", capture_user_text=True)
    assert reply == AgentReply(answer="ok", proposal_text="")
    assert rig.phoenix.spans == []
    assert {"agno.agent.run", "ancora.tool.call"} <= {s.name for s in rig.grafana.spans}


# ── T8 · fail-open ──────────────────────────────────────────────────────────


class _DownDelegate(SpanExporter):
    """Phoenix unreachable: raises on export, shutdown and flush."""

    def __init__(self) -> None:
        self.calls = 0

    def export(self, spans: Any) -> SpanExportResult:
        self.calls += 1
        raise ConnectionError("phoenix.railway.internal unreachable")

    def shutdown(self) -> None:
        raise ConnectionError("down")

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        raise ConnectionError("down")


class _FailureResult(SpanExporter):
    def export(self, spans: Any) -> SpanExportResult:
        return SpanExportResult.FAILURE


SCRIPT = [("find_vehicle", {"query": "x"}), _present("respuesta estable")]
EXPECTED = AgentReply(answer="respuesta estable", proposal_text="")


async def test_phoenix_down_does_not_change_the_reply(monkeypatch):
    down = _DownDelegate()
    rig = _rig(monkeypatch, SCRIPT, phoenix_delegate=down)
    assert await _turn(rig, "hola", capture_user_text=True) == EXPECTED
    _flush(rig)
    assert down.calls >= 1  # the export really was attempted and failed


async def test_phoenix_down_does_not_retry_or_accumulate(monkeypatch):
    down = _DownDelegate()
    rig = _rig(monkeypatch, SCRIPT, phoenix_delegate=down)
    await _turn(rig, "hola", capture_user_text=True)
    _flush(rig)
    calls_after_first = down.calls
    # The scripted model is single-use; a fresh script gives the same second turn.
    rig.model.step = 0
    await _turn(rig, "otra", capture_user_text=True)
    _flush(rig)
    # One batch per turn at most: failures are not re-queued or retried.
    assert down.calls - calls_after_first <= calls_after_first


async def test_phoenix_returning_failure_does_not_change_the_reply(monkeypatch):
    rig = _rig(monkeypatch, SCRIPT, phoenix_delegate=_FailureResult())
    assert await _turn(rig, "hola", capture_user_text=True) == EXPECTED
    _flush(rig)


async def test_a_masker_that_raises_drops_spans_but_never_the_reply(monkeypatch):
    rig = _rig(monkeypatch, SCRIPT)

    def broken(_text: str) -> str:
        raise ValueError(f"mask failure quoting {DNI}")

    rig.tracing.exporter.masker = broken
    assert await _turn(rig, f"dni {DNI}", capture_user_text=True) == EXPECTED
    _flush(rig)
    assert rig.tracing.exporter.dropped > 0
    # Fail-closed: every span that carries text is dropped. Tool-metadata spans hold no
    # free text, never reach the masker and may still go out; nothing else may.
    sources = {s.attributes["ancora.capture.source"] for s in rig.phoenix.spans}
    assert sources <= {"tool_metadata"}
    assert DNI not in rig.phoenix.dump()


async def test_a_broken_provider_does_not_change_the_reply(monkeypatch):
    rig = _rig(monkeypatch, SCRIPT)

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("provider broken")

    monkeypatch.setattr(rig.tracing.provider, "get_tracer", explode)
    assert await _turn(rig, "hola", capture_user_text=True) == EXPECTED


async def test_a_shut_down_provider_does_not_change_the_reply(monkeypatch):
    rig = _rig(monkeypatch, SCRIPT)
    rig.tracing.shutdown()
    assert await _turn(rig, "hola", capture_user_text=True) == EXPECTED


async def test_phoenix_failure_does_not_change_the_failure_of_a_failed_turn(monkeypatch):
    """Agno swallows a model exception and returns a run without a presentation, which
    the runner reports as ``InvalidPresentationOutputError``. That outcome must be the
    same with Phoenix down, and the failed turn must still be diagnosable."""

    async def failing(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError(f"model unavailable for {DNI}")

    outcomes = []
    for delegate in (None, _DownDelegate()):
        rig = _rig(monkeypatch, SCRIPT, phoenix_on=delegate is not None, phoenix_delegate=delegate)
        monkeypatch.setattr(rig.model, "ainvoke", failing)
        with pytest.raises(InvalidPresentationOutputError) as raised:
            await _turn(rig, "hola", capture_user_text=True)
        outcomes.append(str(raised.value))
        if delegate is not None:
            _flush(rig)
    assert outcomes[0] == outcomes[1]


async def test_a_failed_turn_is_diagnosable_in_phoenix_without_the_exception_text(monkeypatch):
    rig = _rig(monkeypatch, SCRIPT)

    async def failing(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError(f"model unavailable for {DNI}")

    monkeypatch.setattr(rig.model, "ainvoke", failing)
    with pytest.raises(InvalidPresentationOutputError):
        await _turn(rig, f"dni {DNI}", capture_user_text=True)
    _flush(rig)
    roots = [
        s for s in rig.phoenix.spans if s.attributes["ancora.capture.source"] == "call_metadata"
    ]
    assert roots[0].attributes["error.type"] == "InvalidPresentationOutputError"
    assert "user_text" in {s.attributes["ancora.capture.source"] for s in rig.phoenix.spans}
    assert "model unavailable" not in rig.phoenix.dump()
    assert DNI not in rig.phoenix.dump()


async def test_grafana_still_exports_when_phoenix_is_down(monkeypatch):
    rig = _rig(monkeypatch, SCRIPT, phoenix_delegate=_DownDelegate())
    await _turn(rig, "hola", capture_user_text=True)
    _flush(rig)
    assert {"agno.agent.run", "ancora.tool.call"} <= {s.name for s in rig.grafana.spans}


def test_masked_span_exporter_is_the_only_door_to_the_phoenix_delegate(monkeypatch):
    rig = _rig(monkeypatch, [_present("ok")])
    assert isinstance(rig.tracing.exporter, MaskedSpanExporter)
    processors = rig.tracing.provider._active_span_processor._span_processors
    assert [type(p.span_exporter) for p in processors if hasattr(p, "span_exporter")] == [
        MaskedSpanExporter
    ]
