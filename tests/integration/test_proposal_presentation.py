"""Persisted presentation/consent boundaries, without LLM or Telegram I/O.

specs/036 AC2/AC3/AC6/AC9: the real processor, repositories and Core executor
run on isolated PostgreSQL. Scripted replies do not validate model semantics.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import ConsentPrincipal, payload_hash
from src.domain.actions.trivial_executor import TrivialExecutor
from src.domain.interactions.processor import InteractionProcessor, TelegramSendError
from src.domain.interactions.reply import AgentReply, InvalidPresentationOutputError
from src.domain.llm_access.models import InteractionProvenance
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from tests.integration.test_interaction_processor import (
    FakeSender,
    _accepted_callback,
    _accepted_command_interaction,
    _accepted_interaction,
    _cipher,
)

pytestmark = pytest.mark.integration


class ScriptedProposalRunner:
    def __init__(self, *, count: int = 1, answer: str = "Consulta independiente.") -> None:
        self.count = count
        self.answer = answer
        self.calls = 0
        self.ids: list[UUID] = []
        self.invalid_terminal = False

    async def run(self, input_text: str, **kwargs: object) -> AgentReply:
        self.calls += 1
        provenance = kwargs["provenance"]
        assert provenance is None or isinstance(provenance, InteractionProvenance)
        session = await get_session()
        try:
            for index in range(self.count):
                proposal = await ActionProposalsRepository(session).create(
                    "88",
                    "create_reminder",
                    {"title": f"Sintético {index}", "trigger_at": "2099-10-20T09:00:00+00:00"},
                    source_interaction_id=provenance.interaction_id if provenance else None,
                    bot_id=provenance.bot_id if provenance else None,
                    chat_id=provenance.chat_id if provenance else None,
                )
                self.ids.append(UUID(proposal["id"]))
        finally:
            await session.close()
        if self.invalid_terminal:
            raise InvalidPresentationOutputError("scripted invalid terminal presentation")
        return AgentReply(answer=self.answer, proposal_text="Narración reemplazable. ¿Confirmas?")


async def _proposals(session: AsyncSession):
    return (
        await session.execute(
            text("""
                SELECT id, status, payload, payload_hash, presented_at,
                       presented_response_id, expires_at, confirming_interaction_id
                FROM ancora.action_proposals WHERE user_id = :uid ORDER BY created_at, id
            """),
            {"uid": "88"},
        )
    ).all()


async def _reminder_count(session: AsyncSession) -> int:
    return await session.scalar(
        text("SELECT count(*) FROM ancora.reminders WHERE user_id = :uid"), {"uid": "88"}
    )


async def test_mixed_multiple_proposals_require_individual_consent_and_allow_explicit_reproposal(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    source_id = await _accepted_interaction(session, cipher, update_id=810)
    runner = ScriptedProposalRunner(count=2)
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )

    assert await processor.run_once() == 1
    delivered = sender.calls[-1][1]
    assert delivered.startswith(runner.answer)
    assert delivered.count("📋 **Propuesta**") == 2
    assert delivered.count("Pulsa ✅ Sí") == 2
    assert "Narración reemplazable" not in delivered
    assert "¿Confirmas?" not in delivered
    assert [pair[0].callback_data for pair in sender.button_rows[-1]] == [
        f"c:{pid}" for pid in runner.ids
    ]
    assert [pair[1].callback_data for pair in sender.button_rows[-1]] == [
        f"d:{pid}" for pid in runner.ids
    ]
    rows = await _proposals(session)
    assert len(rows) == 2
    response_id = await session.scalar(
        text("SELECT id FROM ancora.logical_responses WHERE interaction_id = :id"),
        {"id": source_id},
    )
    for row in rows:
        assert row.status == "pending_confirmation"
        assert row.presented_at is not None and row.expires_at > row.presented_at
        assert row.presented_response_id == response_id
        assert row.payload_hash == payload_hash("create_reminder", row.payload)
    assert await _reminder_count(session) == 0

    await _accepted_command_interaction(session, cipher, 811, command="Sí")
    assert await processor.run_once() == 1
    assert "varias propuestas" in sender.calls[-1][1]
    assert await _reminder_count(session) == 0
    assert all(row.confirming_interaction_id is None for row in await _proposals(session))

    first, second = runner.ids
    await _accepted_callback(session, cipher, 812, callback_data=f"c:{first}")
    assert await processor.run_once() == 1
    assert await _reminder_count(session) == 1
    assert (
        await session.scalar(
            text("SELECT title FROM ancora.reminders WHERE user_id = :uid"), {"uid": "88"}
        )
        == "Sintético 0"
    )
    await _accepted_callback(session, cipher, 813, callback_data=f"c:{first}")
    assert await processor.run_once() == 1
    assert await _reminder_count(session) == 1

    await _accepted_callback(session, cipher, 814, callback_data=f"d:{second}")
    assert await processor.run_once() == 1
    assert "descartada" in sender.calls[-1][1]
    assert runner.calls == 1  # Control events never invoke the Agent.
    statuses = {row.id: row.status for row in await _proposals(session)}
    assert statuses == {first: "executed", second: "discarded"}

    # Simulate an explicit new domain request, not a replay of the rejected run.
    await _accepted_interaction(session, cipher, update_id=815)
    assert await processor.run_once() == 1
    assert runner.calls == 2
    rows = await _proposals(session)
    assert len(rows) == 4
    assert {row.id: row.status for row in rows[:2]} == statuses
    assert all(row.status == "pending_confirmation" for row in rows[2:])
    assert not set(runner.ids[:2]) & set(runner.ids[2:])
    assert rows[1].payload == rows[3].payload
    assert await _reminder_count(session) == 1


@pytest.mark.parametrize("definitive", [False, True])
@pytest.mark.parametrize("failed_chunk", [0, 1])
async def test_failed_or_partial_delivery_never_opens_consent_or_replays_agent(
    session: AsyncSession,
    definitive: bool,
    failed_chunk: int,
) -> None:
    class FailingSender(FakeSender):
        async def send_text(self, chat_id: int, text: str, *, button_rows=None) -> int:
            message_id = await super().send_text(chat_id, text, button_rows=button_rows)
            if len(self.calls) == failed_chunk + 1:
                raise TelegramSendError("scripted delivery failure", definitive=definitive)
            return message_id

    cipher = _cipher()
    source_id = await _accepted_interaction(session, cipher, update_id=820)
    runner = ScriptedProposalRunner(answer="Consulta independiente. " * 200)
    sender = FailingSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )

    assert await processor.run_once() == 1
    assert len(sender.calls) == failed_chunk + 1
    assert all(buttons is None for buttons in sender.button_rows[:1])
    assert await processor.recover_once() == 0
    assert await processor.run_once() == 0
    assert runner.calls == 1
    assert len(sender.calls) == failed_chunk + 1
    expected = "failed_definitive" if definitive else "failed_ambiguous"
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.telegram_interactions WHERE id = :id"),
            {"id": source_id},
        )
        == expected
    )
    (row,) = await _proposals(session)
    assert row.status == "pending_confirmation"
    assert row.presented_at is None and row.expires_at is None
    assert row.presented_response_id is None and row.confirming_interaction_id is None
    assert (
        await ActionProposalsRepository(session).list_confirmable(
            ConsentPrincipal(user_id="88", bot_id=41, chat_id=77)
        )
        == []
    )

    # Even a forged callback with the persisted ID cannot authorize an unseen proposal.
    await _accepted_callback(session, cipher, 821, callback_data=f"c:{row.id}")
    assert await processor.run_once() == 1
    assert "✅" not in sender.calls[-1][1]
    assert await _reminder_count(session) == 0
    assert runner.calls == 1
    assert (await _proposals(session))[0].confirming_interaction_id is None


async def test_consent_off_preserves_read_answer_without_fictitious_presentation(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    await _accepted_interaction(session, cipher, update_id=830)
    runner = ScriptedProposalRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=False,
    )
    assert await processor.run_once() == 1
    assert sender.calls == [(77, runner.answer)]
    assert sender.button_rows == [None]
    (row,) = await _proposals(session)
    assert row.presented_at is None and row.presented_response_id is None
    await _accepted_callback(session, cipher, 831, callback_data=f"c:{row.id}")
    assert await processor.run_once() == 1
    assert "no está habilitada" in sender.calls[-1][1]
    assert sender.button_rows[-1] is None
    assert await _reminder_count(session) == 0
    assert runner.calls == 1


async def test_invalid_terminal_after_proposal_never_presents_it_via_failure_notice(
    session: AsyncSession,
) -> None:
    cipher = _cipher()
    source_id = await _accepted_interaction(session, cipher, update_id=840)
    runner = ScriptedProposalRunner()
    runner.invalid_terminal = True
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )
    assert await processor.run_once() == 1
    assert await processor.run_once() == 0
    assert runner.calls == 1 and len(sender.calls) == 1
    assert "no reintentaré automáticamente" in sender.calls[0][1]
    assert sender.button_rows == [None]
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.telegram_interactions WHERE id = :id"),
            {"id": source_id},
        )
        == "failed_ambiguous"
    )
    assert (
        await session.execute(
            text(
                "SELECT response_kind, status FROM ancora.logical_responses "
                "WHERE interaction_id = :id"
            ),
            {"id": source_id},
        )
    ).all() == [("failure_notice", "delivered")]
    (row,) = await _proposals(session)
    assert row.presented_at is None and row.presented_response_id is None
    await _accepted_callback(session, cipher, 841, callback_data=f"c:{row.id}")
    assert await processor.run_once() == 1
    assert await _reminder_count(session) == 0
    assert runner.calls == 1
    assert (await _proposals(session))[0].confirming_interaction_id is None


async def test_invalid_terminal_after_trivial_write_preserves_effect_and_never_replays(
    session: AsyncSession,
) -> None:
    class TrivialWritingRunner:
        calls = 0

        async def run(self, input_text: str, **kwargs: object) -> AgentReply:
            self.calls += 1
            reply = await TrivialExecutor(get_session).execute(
                "remember_note", {"content": "Nota sintética ya persistida"}, "88"
            )
            assert "✅" in reply
            raise InvalidPresentationOutputError("scripted invalid terminal presentation")

    cipher = _cipher()
    source_id = await _accepted_interaction(session, cipher, update_id=850)
    runner = TrivialWritingRunner()
    sender = FakeSender()
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=True,
    )
    assert await processor.run_once() == 1
    assert await processor.recover_once() == 0
    assert await processor.run_once() == 0
    assert runner.calls == 1 and len(sender.calls) == 1
    assert "consulta primero su estado" in sender.calls[0][1]
    assert sender.button_rows == [None]
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.telegram_interactions WHERE id = :id"),
            {"id": source_id},
        )
        == "failed_ambiguous"
    )
    assert (
        await session.scalar(
            text("SELECT count(*) FROM ancora.notes WHERE user_id = :uid"), {"uid": "88"}
        )
        == 1
    )
    (row,) = await _proposals(session)
    assert row.status == "executed" and row.confirming_interaction_id is None
    assert row.presented_at is None and row.presented_response_id is None
