"""Unit tests for InteractionProcessor._handle_voice_consent (BL-26 V27/V29/V30).

V25/V26/V28 (admission-vs-presentation races, generation changes mid-STT,
concurrent "Sí") are integration-level — they depend on real PostgreSQL
locking inside ActionProposalsRepository.resolve_voice_consent and are not
covered here. These tests cover what *is* unit-testable at the processor
layer: the guards that run before any claim is even attempted.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

import src.domain.interactions.processor as processor_module
from src.domain.actions.models import ConsentClaimResult, ConsentRejection
from src.domain.interactions.models import InteractionStatus, TelegramInteraction
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.speech.models import SpeechToTextResult
from src.domain.speech.preparation import (
    PreparationStatus,
    SpeechTranscriptCipher,
    VoicePreparation,
)
from src.repositories.actions import ActionProposalsRepository
from src.repositories.voice_preparations import VoicePreparationsRepository


def _interaction(**overrides: object) -> TelegramInteraction:
    base = {
        "id": str(uuid4()),
        "bot_id": 1,
        "telegram_update_id": 2,
        "telegram_message_id": 3,
        "chat_id": 4,
        "telegram_user_id": 5,
        "update_type": "message",
        "status": InteractionStatus.AGENT_STARTED,
        "received_at": "2026-09-13T00:00:00Z",
        "accepted_at": "2026-09-13T00:00:00Z",
        "updated_at": "2026-09-13T00:00:00Z",
    }
    base.update(overrides)
    return TelegramInteraction.model_validate(base)


def _preparation(*, call_id: UUID, transcript_ciphertext: bytes) -> VoicePreparation:
    return VoicePreparation(
        interaction_id=uuid4(),
        user_id=5,
        owner_token=uuid4(),
        status=PreparationStatus.TRANSCRIBED,
        config_revision=1,
        call_id=call_id,
        transcript_ciphertext=transcript_ciphertext,
        transcript_key_version=1,
        claimed_at="2026-09-13T00:00:00Z",
        updated_at="2026-09-13T00:00:00Z",
    )


class _Harness:
    """Builds a processor + original payload + matching voice preparation."""

    def __init__(self) -> None:
        self.cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
        self.call_id = uuid4()
        self.text = "Sí"

    def transcript_ciphertext(
        self, *, text: str | None = None, call_id: UUID | None = None
    ) -> bytes:
        result = SpeechToTextResult(
            text=text if text is not None else self.text,
            duration_seconds=2,
            call_id=call_id if call_id is not None else self.call_id,
            usage_event_id=uuid4(),
        )
        ciphertext, _ = SpeechTranscriptCipher(self.cipher).encrypt(result)
        return ciphertext

    def original_payload_ciphertext(self, **overrides: object) -> bytes:
        payload: dict[str, object] = {
            "text": None,
            "voice_message_kind": "original",
            "attachments": [{"kind": "voice", "file_id": "opaque-file-id"}],
        }
        payload.update(overrides)
        return self.cipher.encrypt(payload).ciphertext

    def processor(self, *, governed_consent: bool = True) -> InteractionProcessor:
        return InteractionProcessor(
            session_factory=self._session_factory,
            payload_cipher=self.cipher,
            agent_runner=AsyncMock(),
            sender=AsyncMock(),
            governed_consent=governed_consent,
        )

    async def _session_factory(self) -> AsyncSession:
        return cast(AsyncSession, AsyncMock())


@pytest.fixture
def harness() -> _Harness:
    return _Harness()


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    prep_repo: AsyncMock,
    actions_repo: AsyncMock,
) -> None:
    monkeypatch.setattr(
        "src.repositories.voice_preparations.VoicePreparationsRepository",
        lambda _session: prep_repo,
    )
    monkeypatch.setattr(
        processor_module, "ActionProposalsRepository", lambda _session: actions_repo
    )


async def test_v29_disabled_governed_consent_never_touches_any_repository(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consent-off is checked before VoicePreparationsRepository is even constructed."""
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor(governed_consent=False)
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "no está habilitada" in reply
    prep_repo.get.assert_not_awaited()
    actions_repo.resolve_voice_consent.assert_not_awaited()


async def test_v29_executor_unavailable_reports_without_discarding_the_proposal(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext()
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    actions_repo.resolve_voice_consent.return_value = (None, "voice_executor_unavailable")
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "no tiene ejecutor determinista" in reply
    actions_repo.resolve_voice_consent.assert_awaited_once()


@pytest.mark.parametrize(
    "overrides",
    [
        {"voice_message_kind": "forwarded"},
        {"voice_message_kind": "edited"},
        {"voice_message_kind": "mixed"},
    ],
)
async def test_v27_forwarded_edited_or_mixed_voice_never_reaches_the_claim(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, overrides: dict[str, object]
) -> None:
    """A forwarded/edited/mixed voice message is never treated as fresh consent."""
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext()
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(
        payload_ciphertext=harness.original_payload_ciphertext(**overrides)
    )

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "No pude verificar" in reply
    actions_repo.resolve_voice_consent.assert_not_awaited()


async def test_v27_voice_mixed_with_written_text_never_reaches_the_claim(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A voice note combined with written text in the same update is not pure consent."""
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext()
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(
        payload_ciphertext=harness.original_payload_ciphertext(text="también borra esto")
    )

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "No pude verificar" in reply
    actions_repo.resolve_voice_consent.assert_not_awaited()


@pytest.mark.parametrize(
    "attachments",
    [
        [],
        [{"kind": "voice", "file_id": "a"}, {"kind": "voice", "file_id": "b"}],
        [{"kind": "photo", "file_id": "a"}],
    ],
)
async def test_v30_payload_without_exactly_one_voice_attachment_is_rejected(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch, attachments: list[dict[str, str]]
) -> None:
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext()
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(
        payload_ciphertext=harness.original_payload_ciphertext(attachments=attachments)
    )

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "No pude verificar" in reply
    actions_repo.resolve_voice_consent.assert_not_awaited()


async def test_v30_transcript_text_mismatch_is_rejected(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The processor re-decrypts the durable transcript rather than trusting the
    text argument — a stale/tampered call can never pass as fresh consent."""
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext(text="No")
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, "Sí", "session-id")

    assert "No pude verificar" in reply
    actions_repo.resolve_voice_consent.assert_not_awaited()


async def test_v30_call_id_mismatch_is_rejected(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=uuid4(),  # different from the transcript's own call_id below
        transcript_ciphertext=harness.transcript_ciphertext(call_id=uuid4()),
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "No pude verificar" in reply
    actions_repo.resolve_voice_consent.assert_not_awaited()


async def test_v30_no_preparation_found_is_rejected(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BL-32-style evidence check: no durable preparation, no consent."""
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = None
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "No pude verificar" in reply
    actions_repo.resolve_voice_consent.assert_not_awaited()


async def test_no_single_confirmable_proposal_is_reported_without_executing(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext()
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    actions_repo.resolve_voice_consent.return_value = (None, None)
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "No hay una única propuesta vigente" in reply


async def test_rejected_claim_reports_the_rejection_reason(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext()
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    actions_repo.resolve_voice_consent.return_value = (
        ConsentClaimResult(rejection=ConsentRejection.EXPIRED),
        None,
    )
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, harness.text, "session-id")

    assert "caducó" in reply


async def test_discard_confirmed_claim_replies_without_executing(
    harness: _Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spoken "No" discards the proposal — never routes to execution."""
    from src.domain.actions.models import ClaimedProposal

    prep_repo = AsyncMock(spec=VoicePreparationsRepository)
    prep_repo.get.return_value = _preparation(
        call_id=harness.call_id, transcript_ciphertext=harness.transcript_ciphertext(text="No")
    )
    actions_repo = AsyncMock(spec=ActionProposalsRepository)
    actions_repo.resolve_voice_consent.return_value = (
        ConsentClaimResult(
            claimed=ClaimedProposal(
                id=uuid4(),
                tool_name="execute_note",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        ),
        None,
    )
    _patch_repos(monkeypatch, prep_repo=prep_repo, actions_repo=actions_repo)
    processor = harness.processor()
    interaction = _interaction(payload_ciphertext=harness.original_payload_ciphertext())

    reply = await processor._handle_voice_consent(interaction, "No", "session-id")

    assert reply == "❌ Propuesta descartada."
