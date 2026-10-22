"""BL-49: stored proposal -> Core presentation with user-scoped canonical data."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.actions.models import payload_hash
from src.domain.interactions.models import TelegramInteraction
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.interactions.reply import AgentReply
from src.domain.reminders.models import ReminderCreate
from src.notifications.markup import markdown_to_telegram_html
from src.repositories.actions import ActionProposalsRepository
from src.repositories.reminders import RemindersRepository

pytestmark = pytest.mark.integration


async def _source(session):
    result = await session.execute(
        text(
            "INSERT INTO ancora.telegram_interactions "
            "(bot_id,telegram_update_id,telegram_user_id,chat_id,update_type,status) "
            "VALUES (1,101,5,5,'message','accepted') RETURNING *"
        )
    )
    interaction = TelegramInteraction.model_validate(dict(result.mappings().one()))
    await session.commit()
    return interaction


def _processor(session):
    sessions = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)

    async def factory():
        return sessions()

    return InteractionProcessor(
        session_factory=factory,
        payload_cipher=TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
        governed_consent=True,
    )


@pytest.mark.parametrize("target", ["owned", "other_user", "missing"])
async def test_snooze_presentation_only_reads_own_target_and_preserves_proposal(session, target):
    interaction = await _source(session)
    repository = RemindersRepository(session)
    own = await repository.create(
        "5", ReminderCreate(title="Seguro propio", trigger_at=datetime(2026, 11, 1, tzinfo=UTC))
    )
    other = await repository.create(
        "6", ReminderCreate(title="SECRETO ajeno", trigger_at=datetime(2026, 11, 1, tzinfo=UTC))
    )
    reminder_id = {"owned": own.id, "other_user": other.id, "missing": uuid4()}[target]
    payload = {"reminder_id": str(reminder_id), "minutes": 90}
    proposal = await ActionProposalsRepository(session).create(
        "5", "snooze_reminder", payload,
        source_interaction_id=interaction.id, bot_id=1, chat_id=5,
    )
    processor = _processor(session)
    content = await processor._append_proposal_blocks(
        interaction, AgentReply(answer="Lectura independiente.", proposal_text="Título del LLM"),
    )
    expected_title = "Seguro propio" if target == "owned" else "No disponible"
    assert f"Recordatorio: {expected_title}" in content
    assert "SECRETO ajeno" not in content
    assert "Título del LLM" not in content
    assert str(reminder_id) not in content
    assert "Aplazamiento: 1 h 30 min desde la confirmación" in content
    assert content.count("Pulsa ✅ Sí") == 1
    assert content.startswith("Lectura independiente.")
    buttons = await processor._pending_proposal_buttons(interaction)
    assert buttons[0][0].callback_data == f"c:{proposal['id']}"
    stored = (
        await session.execute(
            text("SELECT payload,payload_hash,status FROM ancora.action_proposals WHERE id=:id"),
            {"id": UUID(proposal["id"])},
        )
    ).one()
    assert stored.payload == payload
    assert stored.payload_hash == payload_hash("snooze_reminder", payload)
    assert stored.status == "pending_confirmation"
    assert await session.scalar(text("SELECT count(*) FROM ancora.reminders")) == 2
    processor._agent_runner.run.assert_not_awaited()
    processor._sender.send_text.assert_not_awaited()


async def test_calendar_persisted_payload_reaches_html_with_recurrence_and_reminder(session):
    interaction = await _source(session)
    payload = {
        "title": "Clase <sintética>",
        "start_at": "2026-11-01T10:00:00+00:00",
        "end_at": "2026-11-01T11:00:00+00:00",
        "recurrence_frequency": "weekly",
        "recurrence_interval": 2,
        "recurrence_until": "2026-12-31T23:59:59+00:00",
        "with_reminder": True,
        "reminder_lead_minutes": 0,
    }
    proposal = await ActionProposalsRepository(session).create(
        "5", "create_calendar_event", payload,
        source_interaction_id=interaction.id, bot_id=1, chat_id=5,
    )
    processor = _processor(session)
    content = await processor._append_proposal_blocks(
        interaction, AgentReply(answer="", proposal_text="Narración que se descarta"),
    )
    html = markdown_to_telegram_html(content)
    assert "Clase &lt;sintética&gt;" in html
    assert "Repetición: cada 2 semanas" in html
    assert "Inicio: 2026-11-01 11:00 (Europe/Madrid, UTC+01:00)" in html
    assert "Fin: 2026-11-01 12:00 (Europe/Madrid, UTC+01:00)" in html
    assert "Repetir hasta (inclusive): 2027-01-01 00:59:59 (Europe/Madrid, UTC+01:00)" in html
    assert "Aviso: sí" in html
    assert "Antelación: al inicio" in html
    assert "Narración" not in html
    stored = (
        await session.execute(
            text("SELECT payload,payload_hash,status FROM ancora.action_proposals WHERE id=:id"),
            {"id": UUID(proposal["id"])},
        )
    ).one()
    assert stored.payload == payload
    assert stored.payload_hash == payload_hash("create_calendar_event", payload)
    assert stored.status == "pending_confirmation"
    assert await session.scalar(text("SELECT count(*) FROM ancora.calendar_events")) == 0
    assert await session.scalar(text("SELECT count(*) FROM ancora.reminders")) == 0
    processor._agent_runner.run.assert_not_awaited()
    processor._sender.send_text.assert_not_awaited()
