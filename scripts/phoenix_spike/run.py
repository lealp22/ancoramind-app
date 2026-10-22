"""Run the isolated compatibility spike with a scripted HTTP transport, no LLM.

Usage: python -m scripts.phoenix_spike.run
Requires the optional spike requirements, not application dependencies. Prints
only version/attribute names/counters/measurements, never recorded span content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import tracemalloc
from importlib.metadata import version
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from scripts.phoenix_spike.exporter import SyntheticMaskedExporter, user_pseudonym
from src.agent.ancora_agent import SafeOpenAILike
from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.governed_model import build_governed_model
from src.agent.instructions import assemble_instructions
from src.agent.reply_presentation import reply_from_run
from src.domain.interactions.reply import AgentReply
from src.domain.llm_access.context import current_execution_context, execution_context_scope
from src.domain.llm_access.models import ExecutionBudget, ExecutionContext, InteractionProvenance
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


class Inventory(SpanExporter):
    def __init__(self):
        self.keys: set[str] = set()
        self.count = 0
        self.last: list[ReadableSpan] = []

    def export(self, spans):
        self.keys.update(key for span in spans for key in (span.attributes or {}))
        self.count += len(spans)
        self.last = list(spans)
        return SpanExportResult.SUCCESS


class Unavailable(SpanExporter):
    def export(self, spans):
        raise ConnectionError("Synthetic sink unavailable")


class SyntheticScope(SpanProcessor):
    """Only attached inside this standalone, synthetic-only process."""

    def __init__(self):
        self.keys: set[str] = set()
        self.spans: list[ReadableSpan] = []
        self.pseudonym = user_pseudonym("spike-synthetic-user", os.urandom(32))

    def on_start(self, span: Span, parent_context=None):
        span.set_attribute("ancora.capture.source", "synthetic_text")
        context = current_execution_context()
        span.set_attribute("ancora.correlation_id", str(context.correlation_id))
        span.set_attribute("ancora.interaction_id", str(context.provenance.interaction_id))
        span.set_attribute("user.id", self.pseudonym)

    def on_end(self, span: ReadableSpan):
        self.keys.update((span.attributes or {}).keys())
        # Keep only one run for assertions, not the benchmark's full corpus.
        self.spans.append(span)


async def one_run() -> tuple[int, list[str]]:
    config = bootstrap_runtime_configuration()
    context = ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=1,
        agno_run_id="synthetic",
        agno_session_id="synthetic",
        provenance=InteractionProvenance(interaction_id=uuid4(), bot_id=1, chat_id=1),
        config=RuntimeConfigSnapshot(
            revision=1,
            checksum=config_checksum(config),
            source="bootstrap",
            config=config,
        ),
        budget=ExecutionBudget.from_config(
            config.execution_budget,
            started_at_monotonic=time.monotonic(),
        ),
    )
    calls = 0
    executed = []

    async def lookup_synthetic() -> str:
        """Return a synthetic value without database or network."""
        executed.append("lookup_synthetic")
        return "DNI sintético 12345678Z"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        body = json.loads(request.content)
        assert body["tool_choice"] == "required"
        assert "response_format" not in body
        assert "12345678Z" in json.dumps(body), "Telemetry must not mask model input"
        name = "lookup_synthetic" if calls == 0 else "present_reply"
        arguments = {} if calls == 0 else {"answer": "DNI sintético 12345678Z", "proposal_text": ""}
        calls += 1
        assert calls <= 2
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": "ancoramind-default-r4",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"synthetic-{calls}",
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        model = build_governed_model(
            SafeOpenAILike,
            {
                "id": "ancoramind-default-r4",
                "api_key": "synthetic-not-a-secret",
                "base_url": "https://synthetic.invalid/v1",
                "http_client": client,
                "max_retries": 0,
            },
            recorder=AsyncMock(),
            route_name="ancoramind-default",
            effective_route="ancoramind-default-r4",
            revision=1,
            provider_label="synthetic",
        )

        class Access:
            def model_for(self, *_: Any) -> Any:
                return model

        factory = GovernedAgentFactory(
            llm_access=Access(),
            db=None,
            tools=[lookup_synthetic],
            instructions=assemble_instructions(),
            fingerprint_key="synthetic-fingerprint",
        )
        with execution_context_scope(context):
            output = await factory.create_for_run(context).arun("Consulta sintética 12345678Z")
        assert reply_from_run(output) == AgentReply(
            answer="DNI sintético 12345678Z",
            proposal_text="",
        )
        assert executed == ["lookup_synthetic"]
        return calls, [item.tool_name for item in output.tools]


async def benchmark(count: int, scope: SyntheticScope | None = None) -> dict[str, float]:
    tracemalloc.start()
    start = time.perf_counter()
    for _ in range(count):
        if scope:
            scope.spans.clear()
        await one_run()
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "runs": count,
        "mean_ms": round(elapsed * 1000 / count, 3),
        "peak_mib": round(
            peak / 1024**2,
            3,
        ),
    }


async def main() -> None:
    # Optional dependency intentionally imported only in this standalone spike.
    from openinference.instrumentation.agno import AgnoInstrumentor

    os.environ["AGNO_TELEMETRY"] = "false"
    logging.getLogger("agno").setLevel(logging.ERROR)
    global_before = trace.get_tracer_provider()
    await one_run()  # Warm imports/client/schema caches before measuring either side.
    baseline = await benchmark(50)
    collector_sink, phoenix_sink = Inventory(), Inventory()
    collector = TracerProvider(resource=Resource({"service.name": "metadata-spike"}))
    collector.add_span_processor(SimpleSpanProcessor(collector_sink))
    phoenix = TracerProvider(resource=Resource({"service.name": "phoenix-spike"}))
    scope = SyntheticScope()
    wrapper = SyntheticMaskedExporter(phoenix_sink)
    phoenix.add_span_processor(scope)
    phoenix.add_span_processor(SimpleSpanProcessor(wrapper))
    instrumentor = AgnoInstrumentor()
    try:
        instrumentor.instrument(tracer_provider=phoenix)
        with collector.get_tracer("metadata-spike").start_as_current_span("metadata.only"):
            requests, tools = await one_run()
        assert collector_sink.count == 1
        assert not collector_sink.keys
        assert phoenix_sink.count > 0
        assert trace.get_tracer_provider() is global_before
        assert any("present_reply" in span.to_json() for span in scope.spans)
        assert len({span.attributes["ancora.correlation_id"] for span in scope.spans}) == 1
        assert len({span.attributes["ancora.interaction_id"] for span in scope.spans}) == 1
        assert all("12345678Z" not in span.to_json() for span in phoenix_sink.last)
        wrapper.delegate = Unavailable()
        outage_calls, outage_tools = await one_run()
        assert outage_calls == 2 and outage_tools == tools
        assert wrapper.failures > 0
        wrapper.delegate = phoenix_sink
        measured = await benchmark(50, scope)
        summary = {
            "versions": {
                name: version(name)
                for name in [
                    "agno",
                    "openinference-instrumentation-agno",
                    "openinference-instrumentation",
                    "openinference-semantic-conventions",
                    "opentelemetry-sdk",
                ]
            },
            "scripted_requests_per_run": requests,
            "executed_tools": tools,
            "global_provider_unchanged": trace.get_tracer_provider() is global_before,
            "collector_spans": collector_sink.count,
            "single_run_correlation_preserved": True,
            "synthetic_sink_outage_agent_reply_unchanged": True,
            "raw_attribute_names": sorted(scope.keys),
            "safe_attribute_names": sorted(phoenix_sink.keys),
            "exported_spans": wrapper.exported,
            "dropped_spans": wrapper.dropped,
            "baseline": baseline,
            "instrumented": measured,
        }
        print(json.dumps(summary, indent=2))
    finally:
        instrumentor.uninstrument()
        phoenix.shutdown()
        collector.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
