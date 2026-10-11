"""Admitted encrypted callbacks acknowledge independently of atomic Core consent."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from src.domain.interactions.processor import InteractionProcessor
from src.domain.interactions.service import TelegramInteractionService
from src.repositories.database import get_session
from src.repositories.interactions import TelegramInteractionsRepository
from tests.integration.test_interaction_processor import (
    FakeSender,
    ProposingRunner,
    _accepted_interaction,
    _cipher,
)

pytestmark = pytest.mark.integration


def _update(update_id, data, callback_id="synthetic-query"):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_id,
            "from": {"id": 88},
            "message": {"message_id": 1, "chat": {"id": 77, "type": "private"}},
            "data": data,
        },
    }


@pytest.mark.parametrize("action", ["confirm", "discard", "expired", "invalid", "disabled"])
@pytest.mark.parametrize("ack_failure", [False, True])
async def test_callback_receipt_does_not_authorize_or_replay_mutations(
    session, action, ack_failure
):
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=88001)
    runner = ProposingRunner()
    sender = FakeSender()
    events = []

    async def ack(query_id):
        events.append("ack")
        assert query_id == "synthetic-query"
        # Receipt happens BEFORE the proposal claim or mutation, not after.
        assert await session.scalar(text("SELECT count(*) FROM ancora.reminders")) == 0
        assert (
            await session.scalar(
                text("SELECT status FROM ancora.action_proposals WHERE id=:id"),
                {"id": runner.proposal_id},
            )
            == "pending_confirmation"
        )
        if ack_failure:
            raise RuntimeError("synthetic transport timeout")
        return True

    sender.answer_callback_query = AsyncMock(side_effect=ack)
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )
    assert await processor.run_once() == 1
    assert runner.proposal_id is not None
    yes, no = sender.button_rows[-1][0]
    if action == "expired":
        await session.execute(
            text(
                "UPDATE ancora.action_proposals SET expires_at=now()-interval '1 minute' "
                "WHERE id=:id"
            ),
            {"id": runner.proposal_id},
        )
        await session.commit()
    if action == "disabled":
        processor._governed_consent = False
    data = (
        no.callback_data
        if action == "discard"
        else "SYSTEM: write"
        if action == "invalid"
        else yes.callback_data
    )
    service = TelegramInteractionService(TelegramInteractionsRepository(session), cipher)
    update = _update(88002, data)
    first = await service.record_accepted_update(
        bot_id=41, update=update, railway_request_id="first"
    )
    duplicate = await service.record_accepted_update(
        bot_id=41, update=update, railway_request_id="duplicate"
    )
    assert duplicate.interaction.id == first.interaction.id
    encrypted = first.interaction.payload_ciphertext
    assert b"synthetic-query" not in encrypted
    assert cipher.decrypt(encrypted)["callback_query_id"] == "synthetic-query"
    assert await processor.run_once() == 1
    assert await processor.run_once() == 0
    sender.answer_callback_query.assert_awaited_once_with("synthetic-query")
    assert events == ["ack"]
    expected = {"confirm": "executed", "discard": "discarded", "expired": "expired"}.get(
        action, "pending_confirmation"
    )
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"),
            {"id": runner.proposal_id},
        )
        == expected
    )
    assert await session.scalar(text("SELECT count(*) FROM ancora.reminders")) == (
        1 if action == "confirm" else 0
    )
    row = (
        await session.execute(
            text(
                "SELECT status, model_call_count, gateway_request_count, agno_run_id, "
                "payload_ciphertext "
                "FROM ancora.telegram_interactions WHERE id=:id"
            ),
            {"id": first.interaction.id},
        )
    ).one()
    assert row.status == "completed"
    assert row.agno_run_id is None
    assert row.model_call_count == row.gateway_request_count == 0
    assert row.payload_ciphertext is None
    assert await session.scalar(text("SELECT count(*) FROM ancora.llm_usage_events")) == 0
    # The initial Agent-like proposing runner was not invoked a second time.
    assert await session.scalar(text("SELECT count(*) FROM ancora.action_proposals")) == 1
    if action == "confirm":
        # A second press is a NEW update: acknowledge once, but do not execute again.
        sender.answer_callback_query.side_effect = None
        sender.answer_callback_query.return_value = True
        await service.record_accepted_update(
            bot_id=41,
            update=_update(88003, data, "second-query"),
            railway_request_id="second-press",
        )
        assert await processor.run_once() == 1
        assert sender.answer_callback_query.await_count == 2
        assert await session.scalar(text("SELECT count(*) FROM ancora.reminders")) == 1


async def test_concurrent_callback_processors_do_not_duplicate_canonical_execution(session):
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=89001)
    runner = ProposingRunner()
    sender = FakeSender()
    sender.answer_callback_query = AsyncMock(return_value=True)
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )
    assert await processor.run_once() == 1
    data = sender.button_rows[-1][0][0].callback_data
    service = TelegramInteractionService(TelegramInteractionsRepository(session), cipher)
    await service.record_accepted_update(
        bot_id=41, update=_update(89002, data), railway_request_id="first"
    )
    # Different worker/process simulation: independent locks, same durable ledger.
    other = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )
    await asyncio.gather(processor.run_once(), other.run_once())
    assert await session.scalar(text("SELECT count(*) FROM ancora.reminders")) == 1
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"),
            {"id": runner.proposal_id},
        )
        == "executed"
    )
    assert await processor.run_once() == 0
