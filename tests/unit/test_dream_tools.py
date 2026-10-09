"""Unit tests for Dream preference tools (specs/029 T5) — mocked service/repo,
same style as test_note_tools.py / test_document_tools.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

from agno.run import RunContext

from src.agent.tools import dream as dream_tools
from src.domain.dream.models import DreamCandidateSnapshot, DreamCandidateStatus, DreamCategory


def _context() -> RunContext:
    return RunContext(run_id="dream-test", session_id="tg:test:1", user_id="452022640")


def _snapshot(**overrides: object) -> DreamCandidateSnapshot:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "category": DreamCategory.TONE_LENGTH,
        "key": "response_length",
        "value": "corto",
        "status": DreamCandidateStatus.ACTIVE,
        "evidence_count": 1,
        "confidence": 0.9,
    }
    defaults.update(overrides)
    return DreamCandidateSnapshot.model_validate(defaults)


async def test_list_my_preferences_with_none_saved(monkeypatch):
    service = AsyncMock()
    service.list_preferences.return_value = []

    async def get_service():
        return service

    monkeypatch.setattr(dream_tools, "_get_preference_service", get_service)

    response = await dream_tools.list_my_preferences(_context())

    assert "No tengo ninguna preferencia" in response


async def test_list_my_preferences_wraps_results_as_untrusted_data(monkeypatch):
    candidate = _snapshot(value="respuestas cortas, sin rodeos")
    service = AsyncMock()
    service.list_preferences.return_value = [candidate]

    async def get_service():
        return service

    monkeypatch.setattr(dream_tools, "_get_preference_service", get_service)

    response = await dream_tools.list_my_preferences(_context())

    data = json.loads(response.split("\n", 1)[1])
    assert data["trust"] == "untrusted_data"
    assert data["source"] == "list_my_preferences"
    assert data["records"][0] == {
        "source": "dream_preference",
        "id": str(candidate.id),
        "category": "tone_length",
        "key": "response_length",
        "value": "respuestas cortas, sin rodeos",
        "value_truncated": False,
        "confidence": 0.9,
    }
    service.list_preferences.assert_awaited_once()
    assert service.list_preferences.await_args.args[0].user_id == "452022640"


async def test_propose_preference_forget_with_candidate_id(monkeypatch):
    actions = AsyncMock()
    actions.create.return_value = {"id": "11111111-1111-1111-1111-111111111111"}

    async def get_actions_repo():
        return actions

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)
    candidate_id = str(uuid4())

    response = await dream_tools.propose_preference_forget(_context(), candidate_id)

    actions.create.assert_awaited_once_with(
        user_id="452022640",
        tool_name="forget_dream_preference",
        payload={"candidate_id": candidate_id},
    )
    assert "11111111-1111-1111-1111-111111111111" in response
    assert candidate_id in response
    assert "confirmas" in response.lower()


async def test_propose_preference_forget_without_candidate_id_means_all(monkeypatch):
    actions = AsyncMock()
    actions.create.return_value = {"id": "proposal-1"}

    async def get_actions_repo():
        return actions

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)

    response = await dream_tools.propose_preference_forget(_context())

    actions.create.assert_awaited_once_with(
        user_id="452022640",
        tool_name="forget_dream_preference",
        payload={"candidate_id": None},
    )
    assert "todas" in response.lower()


async def test_propose_preference_forget_rejects_invalid_id_without_a_proposal(monkeypatch):
    actions = AsyncMock()

    async def get_actions_repo():
        return actions

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)

    response = await dream_tools.propose_preference_forget(_context(), "not-a-uuid")

    actions.create.assert_not_awaited()
    assert "no válido" in response.lower()


async def test_execute_preference_forget_forgets_one(monkeypatch):
    candidate_id = str(uuid4())
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {"payload": {"candidate_id": candidate_id}}
    service = AsyncMock()
    service.forget.return_value = True

    async def get_actions_repo():
        return actions

    async def get_service():
        return service

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)
    monkeypatch.setattr(dream_tools, "_get_preference_service", get_service)

    response = await dream_tools.execute_preference_forget(_context(), "proposal-1")

    actions.confirm_or_use_confirmed.assert_awaited_once_with("452022640", "proposal-1")
    service.forget.assert_awaited_once()
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-1")
    assert "olvidada" in response.lower()


async def test_execute_preference_forget_forgets_all(monkeypatch):
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {"payload": {"candidate_id": None}}
    service = AsyncMock()
    service.forget.return_value = 3

    async def get_actions_repo():
        return actions

    async def get_service():
        return service

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)
    monkeypatch.setattr(dream_tools, "_get_preference_service", get_service)

    response = await dream_tools.execute_preference_forget(_context(), "proposal-1")

    service.forget.assert_awaited_once()
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-1")
    assert "3" in response


async def test_execute_preference_forget_one_not_found_does_not_mark_executed(monkeypatch):
    candidate_id = str(uuid4())
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {"payload": {"candidate_id": candidate_id}}
    service = AsyncMock()
    service.forget.return_value = False

    async def get_actions_repo():
        return actions

    async def get_service():
        return service

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)
    monkeypatch.setattr(dream_tools, "_get_preference_service", get_service)

    response = await dream_tools.execute_preference_forget(_context(), "proposal-1")

    actions.mark_executed.assert_not_awaited()
    assert "no encontré" in response.lower()


async def test_execute_preference_forget_without_a_pending_proposal_does_not_forget(monkeypatch):
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = None
    service = AsyncMock()

    async def get_actions_repo():
        return actions

    async def get_service():
        return service

    monkeypatch.setattr(dream_tools, "_get_actions_repo", get_actions_repo)
    monkeypatch.setattr(dream_tools, "_get_preference_service", get_service)

    response = await dream_tools.execute_preference_forget(_context(), "proposal-1")

    service.forget.assert_not_awaited()
    assert "no está pendiente" in response
