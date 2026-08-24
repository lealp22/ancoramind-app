"""Unit tests for Notes domain models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.notes.models import Note, NoteCreate


class TestNoteCreate:
    def test_valid_note(self):
        data = NoteCreate(content="La plaza del garaje es la 42")
        assert data.content == "La plaza del garaje es la 42"

    def test_empty_content_fails(self):
        with pytest.raises(ValidationError):
            NoteCreate(content="")

    def test_too_long_content_fails(self):
        with pytest.raises(ValidationError):
            NoteCreate(content="x" * 5001)


class TestNote:
    def test_valid_note_from_attributes(self):
        note_id = uuid4()
        now = datetime.now(tz=timezone.utc)
        note = Note(
            id=note_id,
            user_id="user-1",
            content="test content",
            created_at=now,
            updated_at=now,
        )
        assert note.id == note_id
        assert note.user_id == "user-1"
        assert note.content == "test content"