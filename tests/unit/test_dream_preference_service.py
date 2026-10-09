"""Unit tests for DreamPreferenceService (specs/029 T5) — mocked repository."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from src.domain.dream.preferences import DreamPreferenceService
from src.security.user_context import UserContext

_USER = UserContext(user_id="452022640")


async def test_list_preferences_delegates_to_the_repository():
    repo = AsyncMock()
    repo.list_active.return_value = ["sentinel"]

    result = await DreamPreferenceService(repo).list_preferences(_USER)

    assert result == ["sentinel"]
    repo.list_active.assert_awaited_once_with(user_id="452022640")


async def test_forget_with_candidate_id_calls_forget_one():
    repo = AsyncMock()
    repo.forget_one.return_value = True
    candidate_id = uuid4()

    result = await DreamPreferenceService(repo).forget(_USER, candidate_id)

    assert result is True
    repo.forget_one.assert_awaited_once_with("452022640", candidate_id)
    repo.forget_all.assert_not_awaited()


async def test_forget_with_candidate_id_returns_false_when_not_found():
    repo = AsyncMock()
    repo.forget_one.return_value = False

    result = await DreamPreferenceService(repo).forget(_USER, uuid4())

    assert result is False


async def test_forget_without_candidate_id_calls_forget_all():
    repo = AsyncMock()
    repo.forget_all.return_value = 5

    result = await DreamPreferenceService(repo).forget(_USER, None)

    assert result == 5
    repo.forget_all.assert_awaited_once_with("452022640")
    repo.forget_one.assert_not_awaited()


async def test_forget_without_candidate_id_zero_is_not_a_bool_false():
    """A deliberate type distinction: int 0 (nothing to forget) must never be
    confused with bool False (a specific id that was not found/owned)."""
    repo = AsyncMock()
    repo.forget_all.return_value = 0

    result = await DreamPreferenceService(repo).forget(_USER, None)

    assert result == 0
    assert result is not False
