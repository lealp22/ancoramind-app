"""Unit tests for the context-compaction adapter (BL-34, 2026-10-12).

Same scripted-model pattern as tests/unit/test_dream_access.py — a real
Agno Model subclass with ainvoke scripted in memory, never a network call.
"""

from __future__ import annotations

from typing import Any

from agno.models.base import Model
from agno.models.response import ModelResponse

from src.agent.context_compaction_access import GovernedContextCompactionAdapter
from src.domain.context_policy.session_summary import SessionExchange
from src.domain.llm_access.models import ExecutionContext
from src.domain.runtime_config.models import (
    RuntimeConfigSnapshot,
    RuntimeConfiguration,
    bootstrap_runtime_configuration,
    config_checksum,
)
from src.domain.runtime_config.service import RuntimeConfigManager


class _ScriptedModel(Model):
    """Minimal real Agno provider returning one scripted text response."""

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


def _manager(revision: int = 3) -> _FakeManager:
    config = bootstrap_runtime_configuration()
    return _FakeManager(
        RuntimeConfigSnapshot(
            revision=revision,
            checksum=config_checksum(config),
            source="database",
            config=config,
        )
    )


def _exchanges() -> tuple[SessionExchange, ...]:
    return (
        SessionExchange(
            interaction_id="1", user_text="¿Qué apunté del coche?", assistant_text="Nada todavía."
        ),
        SessionExchange(
            interaction_id="2", user_text="Anota el cambio de aceite.", assistant_text="Hecho."
        ),
    )


async def test_summarize_returns_the_scripted_text() -> None:
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = None
    _ScriptedModel.response_content = "El usuario registró un cambio de aceite."
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    llm_access = _FakeLLMAccess(model)
    manager = _manager(revision=3)
    adapter = GovernedContextCompactionAdapter(llm_access=llm_access, config_manager=manager)

    outcome = await adapter.summarize(_exchanges())

    assert llm_access.calls[0][0] == "ancoramind-context-compaction"
    assert llm_access.calls[0][1].config.revision == 3
    assert outcome.status == "completed"
    assert outcome.summary_text == "El usuario registró un cambio de aceite."


async def test_summarize_maps_inference_failure_to_controlled_outcome() -> None:
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = RuntimeError("provider exploded")
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    adapter = GovernedContextCompactionAdapter(
        llm_access=_FakeLLMAccess(model), config_manager=_manager()
    )

    outcome = await adapter.summarize(_exchanges())

    assert outcome.status == "failed"
    # Agno's own Agent.arun() swallows the provider exception internally and
    # returns an ERROR-status RunOutput rather than raising (same behaviour
    # test_dream_access.py documents for GovernedDreamConsolidationAdapter).
    assert outcome.error_class == "AgentRunError"
    assert outcome.summary_text is None


async def test_summarize_maps_empty_content_to_controlled_outcome() -> None:
    _ScriptedModel.ainvoke_calls = 0
    _ScriptedModel.raise_on_ainvoke = None
    _ScriptedModel.response_content = "   "
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    adapter = GovernedContextCompactionAdapter(
        llm_access=_FakeLLMAccess(model), config_manager=_manager()
    )

    outcome = await adapter.summarize(_exchanges())

    assert outcome.status == "failed"
    assert outcome.error_class == "InvalidCompactionContent"


async def test_summarize_fails_closed_when_route_is_missing() -> None:
    _ScriptedModel.ainvoke_calls = 0
    model = _ScriptedModel(id="test/model", provider="OpenRouter")
    llm_access = _FakeLLMAccess(model)
    config = bootstrap_runtime_configuration()
    payload = config.model_dump(mode="json", by_alias=True)
    del payload["routing"]["routes"]["ancoramind-context-compaction"]
    stripped = RuntimeConfiguration.model_validate(payload)
    manager = _FakeManager(
        RuntimeConfigSnapshot(
            revision=1, checksum=config_checksum(stripped), source="database", config=stripped
        )
    )
    adapter = GovernedContextCompactionAdapter(llm_access=llm_access, config_manager=manager)

    outcome = await adapter.summarize(_exchanges())

    assert outcome.status == "failed"
    assert outcome.error_class == "CompactionRouteUnavailable"
    assert llm_access.calls == []
    assert _ScriptedModel.ainvoke_calls == 0
