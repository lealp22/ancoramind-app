"""PostgreSQL integration tests for T5 processor, recovery and response outbox."""

from __future__ import annotations

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.models import (
    TelegramDeliveryCreate,
    TelegramInteractionCreate,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor
from src.domain.interactions.reply import AgentReply
from src.repositories.database import get_session
from src.repositories.interactions import TelegramInteractionsRepository

pytestmark = pytest.mark.integration


class FakeRunner:
    def __init__(self, content: str = "Respuesta final") -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def run(self, input_text: str, **kwargs: object) -> str:
        self.calls.append({"input_text": input_text, **kwargs})
        if self.error:
            raise self.error
        return self.content


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.button_rows: list[object] = []
        self.next_message_id = 100

    async def send_text(self, chat_id: int, text: str, *, button_rows=None) -> int:
        self.calls.append((chat_id, text))
        self.button_rows.append(button_rows)
        self.next_message_id += 1
        return self.next_message_id

    async def send_typing(self, chat_id: int) -> None:
        return None


def _cipher() -> TelegramPayloadCipher:
    return TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)


async def _accepted_interaction(
    session: AsyncSession,
    cipher: TelegramPayloadCipher,
    update_id: int,
) -> UUID:
    encrypted = cipher.encrypt({"update_id": update_id, "text": "Hola procesador"})
    result = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=41,
            telegram_update_id=update_id,
            telegram_message_id=update_id + 1,
            chat_id=77,
            telegram_user_id=88,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(railway_request_id=f"delivery-{update_id}", http_status=200),
    )
    return result.interaction.id


async def test_processor_persists_outbox_before_confirmed_chunk_delivery(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _accepted_interaction(session, cipher, update_id=501)
    runner = FakeRunner(content="respuesta " * 600)
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        global_concurrency=2,
    )

    assert await processor.run_once() == 1

    interaction = (
        await session.execute(
            text("""
                SELECT status, agno_run_id, agno_session_id, payload_ciphertext
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert interaction.status == "completed"
    assert interaction.agno_run_id is not None
    assert interaction.agno_session_id == "tg:ancoramind:77"
    assert interaction.payload_ciphertext is None
    response = (
        await session.execute(
            text("""
                SELECT id, status, content_ciphertext, content_key_version, chunk_count
                FROM ancora.logical_responses
                WHERE interaction_id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert response.status == "completed"
    assert response.content_ciphertext is not None
    assert response.content_key_version == 1
    assert b"respuesta" not in response.content_ciphertext
    assert response.chunk_count == len(sender.calls)
    deliveries = (
        await session.execute(
            text("""
                SELECT status, telegram_message_id
                FROM ancora.telegram_response_deliveries
                WHERE logical_response_id = :id
                ORDER BY chunk_index
            """),
            {"id": response.id},
        )
    ).fetchall()
    assert all(row.status == "completed" for row in deliveries)
    assert all(row.telegram_message_id is not None for row in deliveries)
    assert len(runner.calls) == 1


async def test_processor_does_not_replay_agent_after_post_claim_failure(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    interaction_id = await _accepted_interaction(session, cipher, update_id=502)
    runner = FakeRunner()
    runner.error = RuntimeError("agent failure")
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor.run_once() == 1
    assert await processor.run_once() == 0

    row = (
        await session.execute(
            text("""
                SELECT status, error_class, error_detail_code
                FROM ancora.telegram_interactions
                WHERE id = :id
            """),
            {"id": interaction_id},
        )
    ).one()
    assert row.status == "failed_ambiguous"
    assert row.error_class == "AgentRunError"
    assert row.error_detail_code == "agent_run_failed_after_claim"
    assert len(runner.calls) == 1
    assert sender.calls == []


async def test_recovery_marks_inflight_ambiguous_but_delivers_response_ready(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    agent_started_id = await _accepted_interaction(session, cipher, update_id=503)
    delivery_started_id = await _accepted_interaction(session, cipher, update_id=505)
    response_ready_id = await _accepted_interaction(session, cipher, update_id=504)
    repository = TelegramInteractionsRepository(session)
    assert await repository.claim_agent_start_with_run_id(
        agent_started_id,
        "run-503",
        "tg:ancoramind:77",
    )
    assert await repository.claim_agent_start_with_run_id(
        delivery_started_id,
        "run-505",
        "tg:ancoramind:77",
    )
    assert await repository.claim_agent_start_with_run_id(
        response_ready_id, "run-504", "tg:ancoramind:77"
    )
    response_payload = cipher.encrypt({"content": "respuesta recuperable"})
    assert await repository.persist_response_ready(
        response_ready_id,
        content_ciphertext=response_payload.ciphertext,
        content_key_version=response_payload.key_version,
        content_length=len("respuesta recuperable"),
        chunk_count=1,
    )
    delivery_payload = cipher.encrypt({"content": "respuesta no reenviable"})
    assert await repository.persist_response_ready(
        delivery_started_id,
        content_ciphertext=delivery_payload.ciphertext,
        content_key_version=delivery_payload.key_version,
        content_length=len("respuesta no reenviable"),
        chunk_count=1,
    )
    assert await repository.claim_delivery_start(delivery_started_id)

    runner = FakeRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor.recover_once() == 2
    assert await processor.run_once() == 1

    rows = (
        await session.execute(
            text("""
                SELECT id, status, error_detail_code
                FROM ancora.telegram_interactions
                WHERE id IN (:agent_started_id, :response_ready_id, :delivery_started_id)
                ORDER BY telegram_update_id
            """),
            {
                "agent_started_id": agent_started_id,
                "response_ready_id": response_ready_id,
                "delivery_started_id": delivery_started_id,
            },
        )
    ).fetchall()
    assert rows[0].id == agent_started_id
    assert rows[0].status == "failed_ambiguous"
    assert rows[0].error_detail_code == "restart_after_agent_started"
    assert rows[1].id == response_ready_id
    assert rows[1].status == "completed"
    assert rows[2].id == delivery_started_id
    assert rows[2].status == "failed_ambiguous"
    assert rows[2].error_detail_code == "restart_during_delivery"
    assert runner.calls == []
    assert sender.calls == [(77, "respuesta recuperable")]


class ProposingRunner:
    """Simulates a propose_* tool creating a proposal during the Agent run."""

    def __init__(self) -> None:
        self.proposal_id: UUID | None = None

    async def run(self, input_text: str, **kwargs: object) -> AgentReply:
        from src.domain.llm_access.context import execution_context_scope
        from src.repositories.actions import ActionProposalsRepository

        provenance = kwargs["provenance"]
        session = await get_session()
        try:
            repo = ActionProposalsRepository(session)
            if provenance is not None:
                context = _fake_context(provenance)
                with execution_context_scope(context):
                    proposal = await repo.create(
                        "88",
                        "create_reminder",
                        {"title": "ITV", "trigger_at": "2026-10-20T09:00:00"},
                    )
            else:
                proposal = await repo.create(
                    "88", "create_reminder", {"title": "ITV", "trigger_at": "x"}
                )
            await session.commit()
        finally:
            await session.close()
        self.proposal_id = UUID(proposal["id"])
        return AgentReply(answer="", proposal_text="Voy a crear el recordatorio.")


def _fake_context(provenance: object) -> object:
    from uuid import uuid4

    from src.domain.llm_access.models import ExecutionBudget, ExecutionContext
    from src.domain.runtime_config.models import (
        RuntimeConfigSnapshot,
        bootstrap_runtime_configuration,
        config_checksum,
    )

    config = bootstrap_runtime_configuration()
    snapshot = RuntimeConfigSnapshot(
        revision=0, checksum=config_checksum(config), config=config, source="bootstrap"
    )
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=1,
        agno_run_id="run-1",
        agno_session_id="tg:ancoramind:77",
        config=snapshot,
        budget=ExecutionBudget.from_config(config.execution_budget, started_at_monotonic=0.0),
        provenance=provenance,  # type: ignore[arg-type]
    )


async def _accepted_callback(
    session: AsyncSession,
    cipher: TelegramPayloadCipher,
    update_id: int,
    *,
    callback_data: str,
) -> UUID:
    encrypted = cipher.encrypt({"update_id": update_id, "text": callback_data})
    result = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=41,
            telegram_update_id=update_id,
            telegram_message_id=1,
            chat_id=77,
            telegram_user_id=88,
            update_type="callback_query",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(railway_request_id=f"delivery-{update_id}", http_status=200),
    )
    return result.interaction.id


async def _accepted_command_interaction(
    session: AsyncSession,
    cipher: TelegramPayloadCipher,
    update_id: int,
    *,
    command: str = "/new",
) -> UUID:
    encrypted = cipher.encrypt({"update_id": update_id, "text": command})
    result = await TelegramInteractionsRepository(session).admit(
        TelegramInteractionCreate(
            bot_id=41,
            telegram_update_id=update_id,
            telegram_message_id=update_id + 1,
            chat_id=77,
            telegram_user_id=88,
            update_type="message",
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        ),
        TelegramDeliveryCreate(railway_request_id=f"delivery-{update_id}", http_status=200),
    )
    return result.interaction.id


async def test_new_command_discards_pending_proposals_of_the_chat(
    session: AsyncSession,
) -> None:
    """specs/023 T4.8 + consent-design.md: /new invalidates pending proposals."""
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=701)
    runner = ProposingRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )

    assert await processor.run_once() == 1
    assert runner.proposal_id is not None

    await _accepted_command_interaction(session, cipher, update_id=702, command="/new")
    assert await processor.run_once() == 1

    status = (
        await session.execute(
            text("SELECT status FROM ancora.action_proposals WHERE id = :id"),
            {"id": runner.proposal_id},
        )
    ).scalar_one()
    assert status == "discarded"


async def test_governed_consent_button_claims_the_proposal_it_presented(
    session: AsyncSession,
) -> None:
    """specs/023 T4.3-T4.4: end-to-end — propose, present with buttons, confirm."""
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=601)
    runner = ProposingRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )

    assert await processor.run_once() == 1

    assert runner.proposal_id is not None
    assert sender.calls, "the Agent reply must have been delivered"
    final_chunk_text = sender.calls[-1][1]
    assert str(runner.proposal_id) not in final_chunk_text
    assert "ID:" not in final_chunk_text
    assert sender.button_rows[-1] is not None
    yes_button, no_button = sender.button_rows[-1][0]
    assert yes_button.callback_data == f"c:{runner.proposal_id}"
    assert no_button.callback_data == f"d:{runner.proposal_id}"

    presented = (
        await session.execute(
            text("SELECT presented_at FROM ancora.action_proposals WHERE id = :id"),
            {"id": runner.proposal_id},
        )
    ).scalar_one()
    assert presented is not None

    await _accepted_callback(session, cipher, update_id=602, callback_data=yes_button.callback_data)
    assert await processor.run_once() == 1

    status = (
        await session.execute(
            text("SELECT status FROM ancora.action_proposals WHERE id = :id"),
            {"id": runner.proposal_id},
        )
    ).scalar_one()
    assert status == "executed"
    confirm_reply = sender.calls[-1][1]
    assert "✅" in confirm_reply
    assert (
        await session.scalar(text("SELECT count(*) FROM ancora.reminders WHERE user_id='88'")) == 1
    )
