"""Unit tests for the Dream consolidation adapter (specs/029 T3)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agno.models.base import Model
from agno.models.response import ModelResponse

from src.agent.dream_access import GovernedDreamConsolidationAdapter
from src.domain.dream.models import DreamCandidateSnapshot, DreamCandidateStatus, DreamCategory
from src.domain.dream.ports import DreamBatch
from src.domain.llm_access.models import ExecutionContext
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    bootstrap_runtime_configuration,
    config_checksum,
)
from src.domain.runtime_config.service import RuntimeConfigManager


class _ScriptedModel(Model):
    """Minimal real Agno provider returning one structured consolidation batch."""

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


class _FakeManager(RuntimeConfigManager):
    def __init__(self, snapshot: RuntimeConfigSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> RuntimeConfigSnapshot:
        return self._snapshot


def _manager(revision: int = 7) -> _FakeManager:
    config = bootstrap_runtime_configuration()
    return _FakeManager(
        RuntimeConfigSnapshot(
            revision=revision,
            checksum=config_checksum(config),
            source="database",
            config=config,
        )
    )


def _batch() -> DreamBatch:
    return DreamBatch(
        user_id="42",
        transcripts=("usuario: prefiero respuestas cortas\nagent: entendido",),
        existing=(
            DreamCandidateSnapshot(
                id=uuid4(),
                category=DreamCategory.TONE_LENGTH,
                key="response_length",
                value="normal",
                status=DreamCandidateStatus.ACTIVE,
                evidence_count=1,
                confidence=0.8,
            ),
        ),
        cursor_interaction_id=uuid4(),
    )


async def test_consolidate_builds_context_from_the_live_activated_snapshot():
    """Dream must use the real activated config, never a hardcoded bootstrap one."""
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = None
    _ScriptedModel.response_content = '{"proposals": []}'
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    llm_access = _FakeLLMAccess(model)
    manager = _manager(revision=7)
    adapter = GovernedDreamConsolidationAdapter(llm_access=llm_access, config_manager=manager)

    outcome = await adapter.consolidate(_batch())

    assert llm_access.calls[0][0] == "ancoramind-dream"
    assert llm_access.calls[0][1].config.revision == 7
    assert outcome.status == "completed"
    assert outcome.batch is not None
    assert outcome.batch.proposals == []
    assert outcome.provider == "OpenRouter"
    assert outcome.model == "test/model"


async def test_consolidate_returns_proposals_from_structured_output():
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = None
    _ScriptedModel.response_content = (
        '{"proposals": [{"category": "tone_length", "key": "response_length", '
        '"value": "corto", "confidence": 0.9, "source": "explicit"}]}'
    )
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    adapter = GovernedDreamConsolidationAdapter(
        llm_access=_FakeLLMAccess(model), config_manager=_manager()
    )

    outcome = await adapter.consolidate(_batch())

    assert outcome.status == "completed"
    assert outcome.batch is not None
    [proposal] = outcome.batch.proposals
    assert proposal.key == "response_length"
    assert proposal.value == "corto"


async def test_consolidate_maps_inference_failure_to_controlled_outcome():
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = RuntimeError("provider exploded")
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    adapter = GovernedDreamConsolidationAdapter(
        llm_access=_FakeLLMAccess(model), config_manager=_manager()
    )

    outcome = await adapter.consolidate(_batch())

    assert outcome.status == "failed"
    assert outcome.error_class == "AgentRunError"  # bounded class marker only
    assert outcome.batch is None


async def test_consolidate_maps_invalid_content_to_controlled_outcome():
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = None
    _ScriptedModel.response_content = '{"not_proposals": []}'
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    adapter = GovernedDreamConsolidationAdapter(
        llm_access=_FakeLLMAccess(model), config_manager=_manager()
    )

    outcome = await adapter.consolidate(_batch())

    assert outcome.status == "failed"
    assert outcome.error_class == "InvalidConsolidationContent"
    assert outcome.batch is None


async def test_consolidate_fails_closed_when_route_is_missing():
    _ScriptedModel.ainvoke_calls = 0
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    llm_access = _FakeLLMAccess(model)
    config = bootstrap_runtime_configuration()
    payload = config.model_dump(mode="json", by_alias=True)
    del payload["routing"]["routes"]["ancoramind-dream"]
    from src.domain.runtime_config.models import RuntimeConfiguration

    stripped = RuntimeConfiguration.model_validate(payload)
    manager = _FakeManager(
        RuntimeConfigSnapshot(
            revision=1, checksum=config_checksum(stripped), source="database", config=stripped
        )
    )
    adapter = GovernedDreamConsolidationAdapter(llm_access=llm_access, config_manager=manager)

    outcome = await adapter.consolidate(_batch())

    assert outcome.status == "failed"
    assert outcome.error_class == "DreamRouteUnavailable"
    assert llm_access.calls == []
    assert _ScriptedModel.ainvoke_calls == 0


async def test_consolidate_opens_its_own_execution_context_scope() -> None:
    """Regression: a real governed model must never be called context-less.

    ``GovernedModelMixin.ainvoke`` reads the active context via a
    contextvar, not a parameter — without the adapter opening
    ``execution_context_scope`` itself, this would raise
    ``GovernanceViolationError`` the moment a real governed model (as
    opposed to the raw ``_ScriptedModel`` the other tests use) is wired in.
    """
    from src.agent.governed_model import build_governed_model

    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = None
    _ScriptedModel.response_content = '{"proposals": []}'
    governed_model = build_governed_model(
        _ScriptedModel,
        {"id": "test/model", "provider": "OpenRouter"},
        recorder=None,
        route_name="ancoramind-dream",
        effective_route="ancoramind-dream-r1",
        revision=1,
    )
    llm_access = _FakeLLMAccess(governed_model)
    adapter = GovernedDreamConsolidationAdapter(llm_access=llm_access, config_manager=_manager())

    # No execution_context_scope opened here on purpose — the adapter must
    # open its own, exactly like src/agent/document_extraction.py does.
    # Before the fix, GovernedModelMixin.ainvoke's call to
    # current_execution_context() would raise GovernanceViolationError here.
    outcome = await adapter.consolidate(_batch())

    assert outcome.status == "completed"
    # The call actually reached the governed model and consumed its budget —
    # not just skipped past a silently-swallowed error.
    assert llm_access.calls[0][1].budget.model_calls == 1
