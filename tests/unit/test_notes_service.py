"""Unit tests for Notes domain service (with mocked repository)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domain.notes.models import Note, NoteCreate
from src.domain.notes.service import NotesService
from src.repositories.notes import NotesRepository
from src.security.user_context import UserContext


@pytest.fixture
def user_ctx():
    return UserContext(user_id="test-user-1")


@pytest.fixture
def mock_repo():
    repo = AsyncMock(spec=NotesRepository)
    return repo


@pytest.fixture
def service(mock_repo):
    return NotesService(mock_repo)


class TestNotesService:
    async def test_remember_creates_note(self, service, mock_repo, user_ctx):
        """remember() should create a note via the repository."""
        note_id = uuid4()
        now = datetime.now(tz=timezone.utc)
        expected = Note(
            id=note_id,
            user_id="test-user-1",
            content="La plaza 42",
            created_at=now,
            updated_at=now,
        )
        mock_repo.create.return_value = expected

        result = await service.remember(user_ctx, "La plaza 42")

        assert result == expected
        mock_repo.create.assert_awaited_once()
        call_args = mock_repo.create.call_args
        assert call_args.kwargs["user_id"] == "test-user-1"
        assert call_args.kwargs["data"].content == "La plaza 42"

    async def test_search_returns_notes(self, service, mock_repo, user_ctx):
        """search() should return notes from the repository."""
        note_id = uuid4()
        now = datetime.now(tz=timezone.utc)
        expected = [
            Note(
                id=note_id,
                user_id="test-user-1",
                content="test",
                created_at=now,
                updated_at=now,
            )
        ]
        mock_repo.search.return_value = expected

        result = await service.search(user_ctx, "plaza")

        assert result == expected
        mock_repo.search.assert_awaited_once_with(
            user_id="test-user-1",
            query="plaza",
        )

    async def test_search_without_query(self, service, mock_repo, user_ctx):
        """search(None) should pass None to repository."""
        mock_repo.search.return_value = []

        result = await service.search(user_ctx, query=None)

        assert result == []
        mock_repo.search.assert_awaited_once_with(
            user_id="test-user-1",
            query=None,
        )

    async def test_remember_uses_trusted_user_context(self, service, mock_repo):
        """The service MUST use the user_id from UserContext, never from LLM."""
        ctx = UserContext(user_id="trusted-user-from-channel")
        mock_repo.create.return_value = Note(
            id=uuid4(),
            user_id="trusted-user-from-channel",
            content="ok",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )

        await service.remember(ctx, "content")

        call_args = mock_repo.create.call_args
        assert call_args.kwargs["user_id"] == "trusted-user-from-channel"