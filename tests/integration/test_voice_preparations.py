"""T3 real PostgreSQL exclusivity, encrypted results and no replay recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.interactions.models import (
    InteractionStatus,
    TelegramDeliveryCreate,
    TelegramInteractionCreate,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.speech.models import SpeechToTextResult, ValidatedVoiceAudio
from src.domain.speech.policy import SpeechBillingPolicy
from src.domain.speech.preparation import SpeechTranscriptCipher
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.voice_preparations import VoicePreparationsRepository

pytestmark = pytest.mark.integration


async def admitted(session):
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode(), 1)
    encrypted = cipher.encrypt({"attachments": [{"kind": "voice", "file_id": "synthetic"}]})
    result = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=10,
            telegram_update_id=20,
            chat_id=30,
            telegram_user_id=40,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=1,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(),
    )
    return result.interaction.id, SpeechTranscriptCipher(cipher)


async def transcribing(repo, interaction_id, owner):
    await repo.claim(interaction_id, 40, owner, 0)
    await repo.mark_downloaded(interaction_id, 40, owner)
    call_id = uuid4()
    audio = ValidatedVoiceAudio(content=b"OggSsynthetic", duration_seconds="2")
    tariff = SpeechBillingPolicy(
        version="test", rate_usd_per_second="0.01", quantum_seconds="1", minimum_seconds="0"
    )
    assert (
        await repo.start_transcription(
            interaction_id,
            40,
            owner,
            call_id=call_id,
            logical_route="ancoramind-stt",
            effective_route="ancoramind-stt-r1",
            audio=audio,
            estimate=tariff.estimate(2),
        )
        is not None
    )
    return call_id


async def test_concurrent_claims_and_user_owner_isolation(session):
    interaction_id, _ = await admitted(session)
    sessions = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)

    async def claim():
        async with sessions() as db:
            return await VoicePreparationsRepository(db).claim(interaction_id, 40, uuid4(), 0)

    claims = await asyncio.gather(*(claim() for _ in range(20)))
    assert sum(item is not None for item in claims) == 1
    repo = VoicePreparationsRepository(session)
    assert await repo.get(interaction_id, 41) is None
    assert await repo.mark_downloaded(interaction_id, 40, uuid4()) is None
    with pytest.raises(Exception, match="voice preparation incomplete"):
        await TelegramInteractionsRepository(session).claim_agent_start(interaction_id)


async def test_result_encrypted_immutable_and_cleared_on_terminal(session):
    interaction_id, cipher = await admitted(session)
    owner = uuid4()
    repo = VoicePreparationsRepository(session)
    call_id = await transcribing(repo, interaction_id, owner)
    result = SpeechToTextResult(
        text="canary-private-transcript",
        duration_seconds="2",
        call_id=call_id,
        usage_event_id=uuid4(),
    )
    row = await repo.persist_transcript(interaction_id, 40, owner, result=result, cipher=cipher)
    assert row is not None and row.transcript_ciphertext is not None
    assert b"canary-private" not in row.transcript_ciphertext
    assert cipher.decrypt(row.transcript_ciphertext) == result
    assert (
        await repo.persist_transcript(interaction_id, 40, owner, result=result, cipher=cipher)
        is None
    )
    assert (
        await TelegramInteractionsRepository(session).claim_agent_start(interaction_id) is not None
    )
    await TelegramInteractionsRepository(session).update_status(
        interaction_id, InteractionStatus.COMPLETED
    )
    assert (await repo.get(interaction_id, 40)).transcript_ciphertext is None


@pytest.mark.parametrize(
    "stage,expected",
    [
        ("preparing", "failed_controlled"),
        ("downloaded", "failed_controlled"),
        ("transcribing", "failed_ambiguous"),
        ("transcribed", "failed_ambiguous"),
    ],
)
async def test_recovery_never_requeues_or_retranscribes(session, stage, expected):
    interaction_id, cipher = await admitted(session)
    owner = uuid4()
    repo = VoicePreparationsRepository(session)
    if stage in {"transcribing", "transcribed"}:
        call_id = await transcribing(repo, interaction_id, owner)
        if stage == "transcribed":
            await repo.persist_transcript(
                interaction_id,
                40,
                owner,
                result=SpeechToTextResult(
                    text="Sí", duration_seconds="2", call_id=call_id, usage_event_id=uuid4()
                ),
                cipher=cipher,
            )
    else:
        await repo.claim(interaction_id, 40, owner, 0)
        if stage == "downloaded":
            await repo.mark_downloaded(interaction_id, 40, owner)
    cutoff = datetime.now(UTC) + timedelta(seconds=1)
    assert await repo.recover_abandoned(user_id=40, owner_token=uuid4(), updated_before=cutoff) == 0
    assert await repo.recover_abandoned(user_id=40, owner_token=owner, updated_before=cutoff) == 1
    assert await repo.recover_abandoned(user_id=40, owner_token=owner, updated_before=cutoff) == 0
    assert (await repo.get(interaction_id, 40)).status.value == expected
    assert await repo.claim(interaction_id, 40, uuid4(), 0) is None
    assert await TelegramInteractionsRepository(session).claim_agent_start(interaction_id) is None


@pytest.mark.parametrize(
    "stage,ambiguous,expected",
    [
        ("preparing", False, "failed_controlled"),
        ("downloaded", False, "failed_controlled"),
        ("preparing", True, "failed_ambiguous"),
        ("transcribing", False, "failed_ambiguous"),
    ],
)
async def test_close_failed_closes_only_own_unfinished_row(session, stage, ambiguous, expected):
    interaction_id, _ = await admitted(session)
    owner = uuid4()
    repo = VoicePreparationsRepository(session)
    if stage == "transcribing":
        await transcribing(repo, interaction_id, owner)
    else:
        await repo.claim(interaction_id, 40, owner, 0)
        if stage == "downloaded":
            await repo.mark_downloaded(interaction_id, 40, owner)
    # Another owner or another user can never close it.
    assert await repo.close_failed(interaction_id, 40, uuid4(), ambiguous=ambiguous) is None
    assert await repo.close_failed(interaction_id, 41, owner, ambiguous=ambiguous) is None
    closed = await repo.close_failed(interaction_id, 40, owner, ambiguous=ambiguous)
    assert closed is not None and closed.status.value == expected
    # Terminal rows are never reopened, requeued or re-closed.
    assert await repo.close_failed(interaction_id, 40, owner, ambiguous=ambiguous) is None
    assert await repo.mark_downloaded(interaction_id, 40, owner) is None
    assert await repo.claim(interaction_id, 40, uuid4(), 0) is None


async def test_close_failed_does_not_touch_a_transcribed_row(session):
    interaction_id, cipher = await admitted(session)
    owner = uuid4()
    repo = VoicePreparationsRepository(session)
    call_id = await transcribing(repo, interaction_id, owner)
    await repo.persist_transcript(
        interaction_id,
        40,
        owner,
        result=SpeechToTextResult(
            text="Sí", duration_seconds="2", call_id=call_id, usage_event_id=uuid4()
        ),
        cipher=cipher,
    )
    assert await repo.close_failed(interaction_id, 40, owner, ambiguous=True) is None
    row = await repo.get(interaction_id, 40)
    assert row.status.value == "transcribed" and row.transcript_ciphertext is not None


async def test_expiry_purges_ciphertext_without_removing_audit(session):
    interaction_id, cipher = await admitted(session)
    owner = uuid4()
    repo = VoicePreparationsRepository(session)
    call_id = await transcribing(repo, interaction_id, owner)
    await repo.persist_transcript(
        interaction_id,
        40,
        owner,
        result=SpeechToTextResult(
            text="test", duration_seconds="2", call_id=call_id, usage_event_id=uuid4()
        ),
        cipher=cipher,
    )
    assert (
        await repo.purge_expired_transcripts(user_id=40, now=datetime.now(UTC) + timedelta(days=2))
        == 1
    )
    row = await repo.get(interaction_id, 40)
    assert row.call_id == call_id and row.transcript_ciphertext is None
    columns = (
        (
            await session.execute(
                text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='ancora' AND table_name='voice_preparations'
    """)
            )
        )
        .scalars()
        .all()
    )
    assert "audio" not in columns and "content" not in columns


async def test_agent_winning_first_blocks_preparation(session):
    interaction_id, _ = await admitted(session)
    assert (
        await TelegramInteractionsRepository(session).claim_agent_start(interaction_id) is not None
    )
    assert await VoicePreparationsRepository(session).claim(interaction_id, 40, uuid4(), 0) is None


async def test_transcription_requires_matching_call_and_cannot_skip_stage(session):
    interaction_id, cipher = await admitted(session)
    owner = uuid4()
    repo = VoicePreparationsRepository(session)
    await repo.claim(interaction_id, 40, owner, 0)
    result = SpeechToTextResult(
        text="Sí", duration_seconds="2", call_id=uuid4(), usage_event_id=uuid4()
    )
    assert (
        await repo.persist_transcript(interaction_id, 40, owner, result=result, cipher=cipher)
        is None
    )
    await repo.mark_downloaded(interaction_id, 40, owner)
    audio = ValidatedVoiceAudio(content=b"OggSsynthetic", duration_seconds="2")
    tariff = SpeechBillingPolicy(
        version="test", rate_usd_per_second="0.01", quantum_seconds="1", minimum_seconds="0"
    )
    await repo.start_transcription(
        interaction_id,
        40,
        owner,
        call_id=uuid4(),
        logical_route="ancoramind-stt",
        effective_route="ancoramind-stt-r1",
        audio=audio,
        estimate=tariff.estimate(2),
    )
    assert (
        await repo.persist_transcript(interaction_id, 40, owner, result=result, cipher=cipher)
        is None
    )
