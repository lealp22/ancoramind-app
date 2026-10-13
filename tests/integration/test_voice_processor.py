"""T4 PostgreSQL processor path with injected synthetic inspector/STT only."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.interactions.models import (
    TelegramDeliveryCreate,
    TelegramInteractionCreate,
    normalize_telegram_update,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.speech.models import InspectedVoiceAudio, SpeechToTextResult
from src.domain.speech.policy import SpeechBillingPolicy
from src.domain.speech.service import VoicePreparationService, maintain_voice_preparations
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.voice_preparations import VoicePreparationsRepository
from tests.unit.test_governed_interaction_runner import _runner
from tests.unit.test_voice_channel import update

pytestmark = pytest.mark.integration


async def setup(session):
    sessions = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)

    async def factory():
        return sessions()

    cipher = TelegramPayloadCipher(Fernet.generate_key().decode(), 1)
    payload = normalize_telegram_update(update()).model_dump(mode="json")
    encrypted = cipher.encrypt(payload)
    admitted = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=1,
            telegram_update_id=2,
            telegram_message_id=3,
            chat_id=4,
            telegram_user_id=5,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=1,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(),
    )
    inspector = AsyncMock()
    inspector.inspect.return_value = InspectedVoiceAudio(
        content=b"OggSsynthetic", mime_type="audio/ogg", codec="opus", duration_seconds="2"
    )
    stt = AsyncMock()

    async def transcribe(audio, *, execution_context, call_id):
        return SpeechToTextResult(
            text="consulta mis notas", duration_seconds="2", call_id=call_id, usage_event_id=uuid4()
        )

    stt.transcribe.side_effect = transcribe
    service = VoicePreparationService(
        session_factory=factory,
        cipher=cipher,
        inspector=inspector,
        stt=stt,
        download=AsyncMock(return_value=b"OggSsynthetic"),
        billing=SpeechBillingPolicy(
            version="fake", rate_usd_per_second="0", quantum_seconds="1", minimum_seconds="0"
        ),
        logical_route="stt-test",
        effective_route="stt-test-r1",
    )
    runner, agent_factory = _runner()
    sender = AsyncMock()
    sender.send_text.return_value = 900
    processor = InteractionProcessor(
        session_factory=factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        voice_enabled=True,
        voice_preparation=service,
    )
    return factory, service, stt, processor, admitted.interaction, agent_factory


async def test_voice_runs_once_and_cleans_ciphertext(session):
    _, _, stt, processor, interaction, agent_factory = await setup(session)
    assert await processor._run_agent(interaction)
    assert not await processor._run_agent(interaction)
    stt.transcribe.assert_awaited_once()
    assert len(agent_factory.agent.calls) == 1
    call = agent_factory.agent.calls[0]
    assert call["input_text"] == "consulta mis notas"
    assert "files" not in call and "images" not in call
    assert call["context"].budget.model_calls == 1


@pytest.mark.parametrize(
    "scenario", ["yes", "no", "multiple", "late", "unsupported", "expired", "generation"]
)
async def test_voice_consent_uses_presented_proposal_without_agent(session, scenario):
    from datetime import UTC, datetime, timedelta

    from src.domain.actions.models import ConsentPrincipal
    from src.domain.interactions.commands import default_session_id
    from src.repositories.actions import ActionProposalsRepository

    _, _, stt, processor, interaction, agent_factory = await setup(session)
    processor._governed_consent = True
    repo = ActionProposalsRepository(session)
    source = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=1,
            telegram_update_id=100,
            chat_id=4,
            telegram_user_id=5,
            update_type="message",
        ),
        TelegramDeliveryCreate(),
    )
    generation = default_session_id(4)
    await session.execute(
        text("UPDATE ancora.telegram_interactions SET agno_session_id=:generation WHERE id=:id"),
        {
            "generation": "another-generation" if scenario == "generation" else generation,
            "id": source.interaction.id,
        },
    )
    await session.commit()
    if scenario == "generation":
        reset = await TelegramInteractionsRepository(session).admit(
            TelegramInteractionCreate(
                bot_id=1,
                telegram_update_id=101,
                chat_id=4,
                telegram_user_id=5,
                update_type="message",
            ),
            TelegramDeliveryCreate(),
        )
        await session.execute(
            text(
                "UPDATE ancora.telegram_interactions SET agno_session_id=:generation WHERE id=:id"
            ),
            {"generation": generation, "id": reset.interaction.id},
        )
        await session.commit()
    proposal = await repo.create(
        "5",
        "unsupported" if scenario == "unsupported" else "remember_note",
        {"content": "synthetic vocal consent note"},
        source_interaction_id=source.interaction.id,
        bot_id=1,
        chat_id=4,
    )
    ids = [proposal["id"]]
    if scenario == "multiple":
        second = await repo.create(
            "5",
            "remember_note",
            {"content": "second"},
            source_interaction_id=source.interaction.id,
            bot_id=1,
            chat_id=4,
        )
        ids.append(second["id"])
    response_id = uuid4()
    await session.execute(
        text("""INSERT INTO ancora.logical_responses
            (id, interaction_id, response_kind, status)
            VALUES (:id, :interaction, 'agent_final', 'delivered')"""),
        {"id": response_id, "interaction": source.interaction.id},
    )
    presented = (
        interaction.accepted_at + timedelta(seconds=1)
        if scenario == "late"
        else interaction.accepted_at - timedelta(seconds=1)
    )
    await repo.mark_presented(
        ids, principal=ConsentPrincipal("5", 1, 4), response_id=response_id, presented_at=presented
    )
    if scenario == "expired":
        await session.execute(
            text("UPDATE ancora.action_proposals SET expires_at=:expired WHERE id=:id"),
            {"expired": datetime.now(UTC) - timedelta(seconds=1), "id": proposal["id"]},
        )
    await session.commit()

    async def transcribe(audio, *, execution_context, call_id):
        return SpeechToTextResult(
            text="No" if scenario == "no" else "Sí",
            duration_seconds="2",
            call_id=call_id,
            usage_event_id=uuid4(),
        )

    stt.transcribe.side_effect = transcribe
    assert await processor._run_agent(interaction)
    assert not await processor._run_agent(interaction)
    assert not agent_factory.agent.calls
    status = await session.scalar(
        text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": proposal["id"]}
    )
    assert status == (
        "executed"
        if scenario == "yes"
        else "discarded"
        if scenario == "no"
        else "pending_confirmation"
    )
    count = await session.scalar(
        text("SELECT count(*) FROM ancora.notes WHERE user_id=:user AND content=:content"),
        {"user": "5", "content": "synthetic vocal consent note"},
    )
    assert count == (1 if scenario == "yes" else 0)
    prep = await VoicePreparationsRepository(session).get(interaction.id, 5)
    assert prep.transcript_ciphertext is None


async def test_maintenance_skips_active_owner_then_recovers_without_replay(session):
    factory, service, stt, _, interaction, _ = await setup(session)
    async with service.exclusive(interaction.id) as acquired:
        assert acquired
        repo = VoicePreparationsRepository(session)
        await repo.claim(interaction.id, 5, uuid4(), 3)
        assert await maintain_voice_preparations(factory) == 0
        async with service.exclusive(interaction.id) as second:
            assert not second
    assert await maintain_voice_preparations(factory) == 1
    assert await maintain_voice_preparations(factory) == 0
    stt.transcribe.assert_not_awaited()


async def test_cancelled_stt_not_replayed(session):
    factory, service, stt, processor, interaction, agent_factory = await setup(session)
    stt.transcribe.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await processor._run_agent(interaction)
    assert not await processor._run_agent(interaction)
    stt.transcribe.assert_awaited_once()
    assert not agent_factory.agent.calls
    await maintain_voice_preparations(factory)


@pytest.mark.parametrize("failure", ["provider", "call_id", "empty_result", "timeout"])
async def test_stt_errors_after_send_are_ambiguous_and_never_replayed(session, failure):
    _, service, stt, processor, interaction, agent_factory = await setup(session)

    async def fail(audio, *, execution_context, call_id):
        if failure == "provider":
            raise RuntimeError("private-provider-error-canary")
        if failure == "timeout":
            await asyncio.sleep(1)
        if failure == "empty_result":
            return None
        return SpeechToTextResult(
            text="synthetic", duration_seconds="2", call_id=uuid4(), usage_event_id=uuid4()
        )

    service._timeout = 0.05 if failure == "timeout" else 60
    stt.transcribe.side_effect = fail
    assert await processor._run_agent(interaction)
    assert not await processor._run_agent(interaction)
    stt.transcribe.assert_awaited_once()
    assert not agent_factory.agent.calls
    stored = (
        (
            await session.execute(
                text(
                    "SELECT status, error_detail_code FROM ancora.telegram_interactions "
                    "WHERE id = :id AND telegram_user_id = :user_id"
                ),
                {"id": interaction.id, "user_id": 5},
            )
        )
        .mappings()
        .one()
    )
    assert stored["status"] == "completed"
    processor._sender.send_text.assert_awaited_once()
    assert "No he podido entender el audio" in processor._sender.send_text.call_args.args[1]
    assert stored["error_detail_code"] in {"stt_failed", "stt_result_invalid", "stt_timeout"}


async def test_restart_delivers_only_missing_voice_notice(session):
    _, service, stt, processor, interaction, agent_factory = await setup(session)
    await session.execute(
        text(
            "UPDATE ancora.telegram_interactions SET status = 'failed_ambiguous', "
            "error_class = 'VoicePreparationRecovery' WHERE id = :id"
        ),
        {"id": interaction.id},
    )
    await session.commit()
    service.maintain = AsyncMock()
    assert await processor.run_once() == 0
    assert await processor.run_once() == 0
    stt.transcribe.assert_not_awaited()
    assert not agent_factory.agent.calls
    processor._sender.send_text.assert_awaited_once()
    assert processor._sender.send_text.call_args.args[1] == (
        "No he podido entender el audio. Por favor, envía tus indicaciones de nuevo."
    )
    assert (
        await session.scalar(
            text("SELECT count(*) FROM ancora.logical_responses WHERE interaction_id = :id"),
            {"id": interaction.id},
        )
        == 1
    )


async def test_two_processors_cannot_transcribe_same_voice(session):
    _, _, stt, processor, interaction, agent_factory = await setup(session)
    await asyncio.gather(processor._run_agent(interaction), processor._run_agent(interaction))
    stt.transcribe.assert_awaited_once()
    assert len(agent_factory.agent.calls) == 1
