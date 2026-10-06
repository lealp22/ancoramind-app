"""Encryption, repository fail-closed and canonical DDL without live inference."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.speech.models import SpeechToTextResult
from src.domain.speech.preparation import SpeechTranscriptCipher
from src.repositories.voice_preparations import VoicePreparationsRepository


def test_transcript_roundtrip_and_no_raw_content():
    cipher = SpeechTranscriptCipher(TelegramPayloadCipher(Fernet.generate_key().decode(), 1))
    result = SpeechToTextResult(
        text="private-canary", duration_seconds="1", call_id=uuid4(), usage_event_id=uuid4()
    )
    ciphertext, version = cipher.encrypt(result)
    assert b"private-canary" not in ciphertext and version == 1
    assert cipher.decrypt(ciphertext) == result
    with pytest.raises(ValueError):
        cipher.decrypt(b"invalid")


async def test_claim_rolls_back_on_db_error_and_never_reports_success():
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        await VoicePreparationsRepository(session).claim(uuid4(), 1, uuid4(), 0)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


async def test_missing_parent_does_not_create_preparation():
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None
    session.execute.return_value = result
    assert await VoicePreparationsRepository(session).claim(uuid4(), 1, uuid4(), 0) is None
    assert session.execute.await_count == 1


def test_migration_bootstrap_ddl_equivalence():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "voice_ddl", root / "migrations/versions/0011_voice_preparation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DDL.strip() in (root / "migrations/init.sql").read_text(encoding="utf-8")
    assert module.down_revision == "0010_pairing_auto_approve"
