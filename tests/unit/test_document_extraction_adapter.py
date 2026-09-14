"""Unit tests for the T9 Agno document extraction adapter."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse

from src.agent.document_extraction import AgnoDocumentExtractionAdapter
from src.domain.documents.schemas import GenericDocumentExtraction
from src.domain.llm_access.context import execution_context_scope
from src.domain.llm_access.models import (
    ExecutionBudget,
    ExecutionContext,
    GovernanceViolationError,
    generate_traceparent,
)
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)


class _ScriptedExtractionModel(Model):
    """Minimal real Agno provider returning one structured extraction."""

    ainvoke_calls = 0
    response_content: Any = None
    raise_on_ainvoke: BaseException | None = None

    def invoke(self, *args: Any, **kwargs: Any) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError
        yield  # pragma: no cover

    def _parse_provider_response(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def _parse_provider_response_delta(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def ainvoke(self, messages: Any = None, **kwargs: Any) -> ModelResponse:
        type(self).ainvoke_calls += 1
        if type(self).raise_on_ainvoke is not None:
            raise type(self).raise_on_ainvoke
        return ModelResponse(content=type(self).response_content)


class _FakeLLMAccess:
    def __init__(self, model: Model):
        self._model = model
        self.calls: list[tuple[str, ExecutionContext]] = []

    def model_for(self, route_name: str, execution_context: ExecutionContext) -> Model:
        self.calls.append((route_name, execution_context))
        return self._model


def _context() -> ExecutionContext:
    config = bootstrap_runtime_configuration()
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=10,
        agno_run_id="run-1",
        agno_session_id="tg:ancoramind:77",
        config=RuntimeConfigSnapshot(
            revision=1,
            checksum=config_checksum(config),
            source="database",
            config=config,
        ),
        budget=ExecutionBudget.from_config(
            config.execution_budget,
            started_at_monotonic=time.monotonic(),
        ),
        traceparent=generate_traceparent(),
    )


def _adapter(
    model: Model,
    *,
    standalone_model: Model | None = None,
) -> AgnoDocumentExtractionAdapter:
    return AgnoDocumentExtractionAdapter(
        llm_access=_FakeLLMAccess(model),
        standalone_llm_access=(
            _FakeLLMAccess(standalone_model) if standalone_model is not None else None
        ),
    )


def _access_of(
    adapter: AgnoDocumentExtractionAdapter,
    *,
    standalone: bool = False,
) -> _FakeLLMAccess:
    return adapter._standalone_llm_access if standalone else adapter._llm_access  # noqa: SLF001


async def test_extract_inside_governed_run_shares_the_run_context() -> None:
    _ScriptedExtractionModel.ainvoke_calls = 0
    _ScriptedExtractionModel.response_content = (
        '{"document_type": "invoice", "summary": "Factura de taller", "confidence": 0.8}'
    )
    _ScriptedExtractionModel.raise_on_ainvoke = None
    model = _ScriptedExtractionModel(id="test/model", provider="OpenRouter")
    adapter = _adapter(model)
    context = _context()

    with execution_context_scope(context):
        outcome = await adapter.extract("prompt", GenericDocumentExtraction)

    access = _access_of(adapter)
    assert access.calls[0][0] == "ancoramind-default"
    assert access.calls[0][1] is context
    assert outcome.status == "completed"
    assert isinstance(outcome.extraction, GenericDocumentExtraction)
    assert outcome.extraction.document_type == "invoice"
    assert outcome.provider == "OpenRouter"
    assert outcome.model == "test/model"
    assert _ScriptedExtractionModel.ainvoke_calls == 1


async def test_extract_outside_governed_run_uses_standalone_frontier() -> None:
    _ScriptedExtractionModel.ainvoke_calls = 0
    _ScriptedExtractionModel.response_content = '{"document_type": "invoice"}'
    _ScriptedExtractionModel.raise_on_ainvoke = None
    model = _ScriptedExtractionModel(id="test/model", provider="OpenRouter")
    adapter = _adapter(_ScriptedExtractionModel(id="unused"), standalone_model=model)

    outcome = await adapter.extract("prompt", GenericDocumentExtraction)

    assert _access_of(adapter).calls == []
    standalone_access = _access_of(adapter, standalone=True)
    assert standalone_access.calls[0][0] == "ancoramind-default"
    assert standalone_access.calls[0][1].config.source == "bootstrap"
    assert outcome.status == "completed"
    assert outcome.extraction is not None
    assert outcome.provider == "OpenRouter"


async def test_extract_without_context_or_standalone_frontier_fails_closed() -> None:
    model = _ScriptedExtractionModel(id="test/model", provider="OpenRouter")
    adapter = _adapter(model)

    with pytest.raises(GovernanceViolationError):
        await adapter.extract("prompt", GenericDocumentExtraction)


async def test_extract_maps_inference_failure_to_controlled_outcome() -> None:
    _ScriptedExtractionModel.ainvoke_calls = 0
    _ScriptedExtractionModel.raise_on_ainvoke = RuntimeError("provider exploded")
    model = _ScriptedExtractionModel(id="test/model", provider="OpenRouter")
    adapter = _adapter(model)
    context = _context()

    with execution_context_scope(context):
        outcome = await adapter.extract("prompt", GenericDocumentExtraction)

    assert outcome.status == "failed"
    assert outcome.error_class == "AgentRunError"
    assert outcome.extraction is None
    assert outcome.provider == "OpenRouter"


async def test_extract_maps_invalid_content_to_controlled_outcome() -> None:
    _ScriptedExtractionModel.ainvoke_calls = 0
    _ScriptedExtractionModel.raise_on_ainvoke = None
    _ScriptedExtractionModel.response_content = '{"confidence": "not-a-number"}'
    model = _ScriptedExtractionModel(id="test/model", provider="OpenRouter")
    adapter = _adapter(model)
    context = _context()

    with execution_context_scope(context):
        outcome = await adapter.extract("prompt", GenericDocumentExtraction)

    assert outcome.status == "failed"
    assert outcome.error_class == "InvalidExtractionContent"
    assert outcome.extraction is None


async def test_extract_inside_governed_run_consumes_the_shared_budget() -> None:
    """Acceptance P: the extraction call counts against the run's own budget."""
    from src.agent.governed_model import build_governed_model

    _ScriptedExtractionModel.ainvoke_calls = 0
    _ScriptedExtractionModel.response_content = '{"document_type": "invoice"}'
    _ScriptedExtractionModel.raise_on_ainvoke = None
    governed_model = build_governed_model(
        _ScriptedExtractionModel,
        {"id": "test/model", "provider": "OpenRouter"},
        recorder=None,
        route_name="ancoramind-default",
        effective_route="ancoramind-default-r1",
        revision=1,
    )
    adapter = _adapter(governed_model)
    context = _context()

    with execution_context_scope(context):
        outcome = await adapter.extract("prompt", GenericDocumentExtraction)

    assert outcome.status == "completed"
    assert outcome.extraction is not None
    assert context.budget.model_calls == 1
    assert context.budget.gateway_requests == 1
