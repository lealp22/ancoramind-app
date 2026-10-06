"""Canonical mutations and terminal audit share one real PostgreSQL transaction."""

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.actions.executor import ProposalExecutor
from src.domain.actions.models import ClaimedProposal
from src.domain.documents.models import DocumentCreate
from src.repositories.actions import ActionProposalsRepository
from src.repositories.documents import DocumentsRepository
from tests.integration.test_voice_processor import setup

pytestmark = pytest.mark.integration


async def claimed(session, tool, payload):
    row = await ActionProposalsRepository(session).create("5", tool, payload)
    confirming = uuid4()
    await session.execute(
        text(
            "INSERT INTO ancora.telegram_interactions "
            "(id,bot_id,telegram_update_id,telegram_user_id,update_type,status) "
            "VALUES (:id,1,:update,5,'message','accepted')"
        ),
        {"id": confirming, "update": confirming.int % 1000000000000},
    )
    # The executor independently verifies persisted evidence; claim resolver is
    # tested separately. No generated production IDs are used.
    await session.execute(
        text(
            "UPDATE ancora.action_proposals SET status='confirmed', "
            "confirming_interaction_id=:confirmation WHERE id=:id"
        ),
        {"confirmation": confirming, "id": UUID(row["id"])},
    )
    await session.commit()
    return ClaimedProposal(UUID(row["id"]), tool, payload, None, confirming)


def executor(session, **kwargs):
    sessions = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)

    async def factory():
        return sessions()

    return ProposalExecutor(factory, **kwargs)


async def run(session, tool, payload):
    proposal = await claimed(session, tool, payload)
    reply = await executor(session).execute(proposal, user_id="5")
    assert "✅" in reply
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": proposal.id}
        )
        == "executed"
    )
    assert "✅" not in await executor(session).execute(proposal, user_id="5")


async def test_all_canonical_capabilities(session):
    await run(session, "remember_note", {"content": "synthetic"})
    await run(
        session, "register_vehicle", {"make": "Test", "model": "Synthetic", "registration": "TEST1"}
    )
    vehicle = str(await session.scalar(text("SELECT id FROM ancora.vehicles WHERE user_id='5'")))
    await run(
        session,
        "register_vehicle_maintenance",
        {
            "vehicle_id": vehicle,
            "date": "2026-10-06",
            "description": "synthetic",
            "cost_amount": "12.50",
            "cost_currency": "EUR",
        },
    )
    await run(
        session,
        "create_reminder",
        {"title": "synthetic", "trigger_at": "2026-11-06T10:00:00+00:00"},
    )
    reminder = str(
        await session.scalar(text("SELECT id FROM ancora.reminders WHERE user_id='5' LIMIT 1"))
    )
    await run(session, "snooze_reminder", {"reminder_id": reminder, "minutes": 10})
    await run(
        session,
        "create_calendar_event",
        {
            "title": "synthetic",
            "start_at": "2026-11-06T10:00:00+00:00",
            "with_reminder": True,
            "reminder_lead_minutes": 10,
            "recurrence_frequency": "weekly",
            "recurrence_interval": 1,
        },
    )
    await run(session, "create_todo_list", {"name": "source"})
    source = str(
        await session.scalar(
            text("SELECT id FROM ancora.todo_lists WHERE name='source' AND user_id='5'")
        )
    )
    await run(session, "rename_todo_list", {"list_id": source, "name": "renamed"})
    await run(session, "create_todo_list", {"name": "target"})
    target = str(
        await session.scalar(
            text("SELECT id FROM ancora.todo_lists WHERE name='target' AND user_id='5'")
        )
    )
    await run(session, "create_todo_item", {"list_id": source, "title": "synthetic"})
    item = str(
        await session.scalar(
            text("SELECT id FROM ancora.todo_items WHERE list_id=:id"), {"id": UUID(source)}
        )
    )
    await run(
        session, "update_todo_item", {"item_id": item, "title": "updated", "priority": "high"}
    )
    await run(session, "set_todo_item_status", {"item_id": item, "status": "done"})
    await run(session, "move_todo_item", {"item_id": item, "target_list_id": target})
    await run(session, "delete_todo_item", {"item_id": item})
    await run(session, "delete_todo_list", {"list_id": source})
    await run(session, "delete_todo_list", {"list_id": target})


async def test_linked_reminder_failure_rolls_back_event_and_audits(session):
    proposal = await claimed(
        session,
        "create_calendar_event",
        {
            "title": "synthetic rollback",
            "start_at": "2026-11-06T10:00:00+00:00",
            "with_reminder": True,
            "reminder_lead_minutes": -1,
        },
    )
    assert "✅" not in await executor(session).execute(proposal, user_id="5")
    assert (
        await session.scalar(text("SELECT count(*) FROM ancora.calendar_events WHERE user_id='5'"))
        == 0
    )
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": proposal.id}
        )
        == "failed_definitive"
    )


async def test_foreign_list_is_not_mutated(session):
    await session.execute(
        text("INSERT INTO ancora.todo_lists (user_id,name) VALUES ('other','foreign')")
    )
    await session.commit()
    foreign = str(
        await session.scalar(text("SELECT id FROM ancora.todo_lists WHERE user_id='other'"))
    )
    proposal = await claimed(session, "delete_todo_list", {"list_id": foreign})
    assert "✅" not in await executor(session).execute(proposal, user_id="5")
    assert (
        await session.scalar(text("SELECT count(*) FROM ancora.todo_lists WHERE user_id='other'"))
        == 1
    )


async def test_concurrent_executors_and_tampered_claim(session):
    proposal = await claimed(session, "remember_note", {"content": "single synthetic write"})
    service = executor(session)
    replies = await asyncio.gather(
        service.execute(proposal, user_id="5"), service.execute(proposal, user_id="5")
    )
    assert sum("✅" in reply for reply in replies) == 1
    assert await session.scalar(text("SELECT count(*) FROM ancora.notes WHERE user_id='5'")) == 1
    foreign = await claimed(session, "remember_note", {"content": "tampered"})
    forged = ClaimedProposal(
        foreign.id,
        foreign.tool_name,
        {"content": "forged"},
        None,
        foreign.confirming_interaction_id,
    )
    assert "✅" not in await service.execute(forged, user_id="5")
    assert "✅" not in await service.execute(foreign, user_id="other")
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": foreign.id}
        )
        == "confirmed"
    )


@pytest.mark.parametrize("failure", [False, True])
async def test_document_external_intent_is_durable_and_never_replayed(session, failure):
    doc = await DocumentsRepository(session).create(
        "5",
        DocumentCreate(
            storage_key="synthetic-key",
            original_filename="test.txt",
            mime_type="text/plain",
            size_bytes=2,
        ),
    )
    proposal = await claimed(session, "delete_document", {"document_id": str(doc.id)})
    storage = AsyncMock()

    async def delete(key):
        assert key == "synthetic-key"
        assert (
            await session.scalar(
                text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": proposal.id}
            )
            == "executing"
        )
        if failure:
            raise RuntimeError("private storage canary")

    storage.delete.side_effect = delete
    service = executor(session, storage=storage)
    reply = await service.execute(proposal, user_id="5")
    assert ("✅" in reply) is not failure
    assert await session.scalar(
        text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": proposal.id}
    ) == ("failed_ambiguous" if failure else "executed")
    await service.execute(proposal, user_id="5")
    storage.delete.assert_awaited_once()


@pytest.mark.parametrize(
    "attack", ["text", "call", "origin", "expired", "chat", "user", "bot", "tampered"]
)
async def test_adversarial_voice_evidence_never_consumes_proposal(session, attack):
    from src.domain.actions.models import ConsentPrincipal
    from src.domain.interactions.commands import default_session_id

    factory, service, stt, processor, interaction, agent = await setup(session)
    processor._governed_consent = True
    # Populate a real, encrypted preparation without running the Agent.
    context = await processor._agent_runner.prepare_execution_context(
        session_id=default_session_id(4),
        run_id=str(uuid4()),
        correlation_id=interaction.id,
        telegram_update_id=2,
        telegram_message_id=3,
    )
    from src.domain.speech.models import SpeechToTextResult

    stt.transcribe.side_effect = None

    async def transcribe(audio, *, execution_context, call_id):
        return SpeechToTextResult(
            text="sí", duration_seconds="2", call_id=call_id, usage_event_id=uuid4()
        )

    stt.transcribe.side_effect = transcribe
    from src.domain.interactions.models import TelegramAttachment

    attachment = TelegramAttachment.model_validate(
        processor._payload_cipher.decrypt(interaction.payload_ciphertext)["attachments"][0]
    )
    async with service.exclusive(interaction.id):
        assert await service.prepare(interaction, attachment, context=context) == "sí"
    # Reuse this accepted row as proposal source solely for adversarial resolver tests.
    await session.execute(
        text("UPDATE ancora.telegram_interactions SET agno_session_id=:generation WHERE id=:id"),
        {"generation": default_session_id(4), "id": interaction.id},
    )
    repo = ActionProposalsRepository(session)
    row = await repo.create(
        "5",
        "remember_note",
        {"content": "synthetic"},
        source_interaction_id=interaction.id,
        bot_id=1,
        chat_id=4,
    )
    response_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO ancora.logical_responses "
            "(id,interaction_id,response_kind,status) "
            "VALUES (:id,:interaction,'agent_final','delivered')"
        ),
        {"id": response_id, "interaction": interaction.id},
    )
    await repo.mark_presented(
        [UUID(row["id"])],
        principal=ConsentPrincipal("5", 1, 4),
        response_id=response_id,
        presented_at=interaction.accepted_at,
    )
    if attack == "tampered":
        await session.execute(
            text("UPDATE ancora.action_proposals SET payload='{}'::jsonb WHERE id=:id"),
            {"id": UUID(row["id"])},
        )
    if attack == "expired":
        await session.execute(
            text(
                "UPDATE ancora.voice_preparations "
                "SET transcript_expires_at=now()-interval '1 second' WHERE interaction_id=:id"
            ),
            {"id": interaction.id},
        )
    if attack == "call":
        await session.execute(
            text("UPDATE ancora.voice_preparations SET call_id=:call WHERE interaction_id=:id"),
            {"call": uuid4(), "id": interaction.id},
        )
    if attack == "origin":
        payload = processor._payload_cipher.decrypt(interaction.payload_ciphertext)
        payload["voice_message_kind"] = "forwarded"
        interaction = interaction.model_copy(
            update={"payload_ciphertext": processor._payload_cipher.encrypt(payload).ciphertext}
        )
    if attack in {"chat", "user", "bot"}:
        key = {"chat": "chat_id", "user": "telegram_user_id", "bot": "bot_id"}[attack]
        interaction = interaction.model_copy(update={key: 999})
    await session.commit()
    reply = await processor._handle_voice_consent(
        interaction, "sí por favor" if attack == "text" else "sí", default_session_id(4)
    )
    assert "✅" not in reply
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"), {"id": UUID(row["id"])}
        )
        == "pending_confirmation"
    )
    assert not agent.agent.calls
