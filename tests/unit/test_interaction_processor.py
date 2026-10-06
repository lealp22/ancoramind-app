"""Unit tests for T5 interaction processor invariants and response chunking."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

import src.domain.interactions.processor as processor_module
from src.domain.interactions.commands import (
    HELP_REPLY,
    NEW_SESSION_REPLY,
)
from src.domain.interactions.media import ResolvedTelegramMedia
from src.domain.interactions.models import InteractionStatus, TelegramInteraction
from src.domain.interactions.outbox import split_telegram_message
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor, TelegramSendError
from src.domain.llm_access.cost_governance import CostGovernanceError
from src.domain.llm_access.models import ExecutionBudgetExceededError
from src.repositories.interactions import TelegramInteractionsRepository


def _interaction(status: InteractionStatus = InteractionStatus.ACCEPTED) -> TelegramInteraction:
    return TelegramInteraction.model_validate(
        {
            "id": str(uuid4()),
            "bot_id": 1,
            "telegram_update_id": 2,
            "telegram_message_id": 3,
            "chat_id": 4,
            "telegram_user_id": 5,
            "update_type": "message",
            "status": status,
            "received_at": "2026-09-13T00:00:00Z",
            "accepted_at": "2026-09-13T00:00:00Z",
            "updated_at": "2026-09-13T00:00:00Z",
        }
    )


def test_split_telegram_message_is_deterministic_and_prefers_word_boundary() -> None:
    content = "uno dos tres cuatro"

    assert split_telegram_message(content, limit=10) == ["uno dos", "tres", "cuatro"]
    assert split_telegram_message("abcdefgh", limit=3) == ["abc", "def", "gh"]
    assert split_telegram_message("") == [""]


def test_split_telegram_message_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        split_telegram_message("content", limit=0)


async def test_agent_failure_after_claim_is_marked_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt({"text": "hola"})
    accepted = interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})
    runner = AsyncMock()
    runner.run.side_effect = RuntimeError("model crashed")
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    runner.run.assert_awaited_once()
    assert runner.run.await_args.kwargs["telegram_update_id"] == 2
    assert runner.run.await_args.kwargs["telegram_message_id"] == 3
    sender.send_text.assert_not_awaited()
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="AgentRunError",
        error_detail_code="agent_run_failed_after_claim",
    )


async def test_budget_exhaustion_after_claim_records_the_budget_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    runner = AsyncMock()
    runner.run.side_effect = ExecutionBudgetExceededError(
        "max_model_calls", "logical model-call ceiling"
    )
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_AMBIGUOUS,
        error_class="ExecutionBudgetExceededError",
        error_detail_code="max_model_calls",
    )


async def test_cost_hard_stop_is_controlled_and_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    repo.claim_agent_start_with_run_id.return_value = interaction.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    runner = AsyncMock()
    runner.run.side_effect = CostGovernanceError(
        "daily_budget_exhausted", "today spend exhausted the daily budget"
    )
    sender = AsyncMock()
    sender.send_typing.return_value = None

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is True
    runner.run.assert_awaited_once()
    sender.send_text.assert_not_awaited()
    repo.update_status.assert_awaited_once_with(
        accepted.id,
        InteractionStatus.FAILED_CONTROLLED,
        error_class="CostGovernanceError",
        error_detail_code="daily_budget_exhausted",
    )


async def test_definitive_telegram_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction(InteractionStatus.RESPONSE_READY)
    response_id = uuid4()
    response = AsyncMock()
    response.id = response_id
    response.content_ciphertext = (
        TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
        .encrypt({"content": "respuesta"})
        .ciphertext
    )
    response.chunk_count = 1
    delivery = AsyncMock()
    delivery.id = uuid4()
    delivery.chunk_index = 0
    delivery.status = "pending"
    claimed = AsyncMock()
    claimed.id = delivery.id
    claimed.chunk_index = 0

    repo.claim_delivery_start.return_value = response
    repo.list_response_deliveries.return_value = [delivery]
    repo.claim_response_chunk.return_value = claimed
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    response.content_ciphertext = cipher.encrypt({"content": "respuesta"}).ciphertext
    runner = AsyncMock()
    sender = AsyncMock()
    sender.send_typing.return_value = None
    sender.send_text.side_effect = TelegramSendError("bad request", definitive=True)

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._deliver_response(interaction) is True
    sender.send_text.assert_awaited_once_with(4, "respuesta")
    repo.fail_response_delivery.assert_awaited_once_with(
        interaction.id,
        response_id,
        delivery.id,
        status=InteractionStatus.FAILED_DEFINITIVE,
        error_class="TelegramSendError",
    )


async def test_processor_refreshes_typing_while_agent_run_is_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt({"text": "hola"})
    accepted = interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    release_runner = asyncio.Event()
    typing_sent = asyncio.Event()

    class SlowRunner:
        async def run(
            self,
            input_text: str,
            *,
            user_id: str,
            session_id: str,
            run_id: str,
            correlation_id: UUID,
            telegram_update_id: int,
            telegram_message_id: int | None = None,
            media=(),
            provenance=None,
        ) -> str:
            assert input_text == "hola"
            assert user_id == "5"
            assert session_id == "tg:ancoramind:4"
            assert run_id
            assert correlation_id == accepted.id
            assert telegram_update_id == 2
            assert telegram_message_id == 3
            assert media == ()
            await release_runner.wait()
            return "respuesta final"

    sender = AsyncMock()

    async def mark_typing(chat_id: int) -> None:
        assert chat_id == 4
        typing_sent.set()

    sender.send_typing.side_effect = mark_typing

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=SlowRunner(),
        sender=sender,
        typing_refresh_seconds=0.01,
    )
    task = asyncio.create_task(processor._run_agent(accepted))
    await asyncio.wait_for(typing_sent.wait(), timeout=0.2)
    release_runner.set()
    await task

    assert sender.send_typing.await_count >= 1


async def test_processor_resolves_attachment_after_claim_and_passes_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    encrypted = cipher.encrypt(
        {
            "text": None,
            "attachments": [{"kind": "photo", "file_id": "opaque-file-id"}],
        }
    )
    accepted = interaction.model_copy(update={"payload_ciphertext": encrypted.ciphertext})
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    resolver = AsyncMock()
    resolved = ResolvedTelegramMedia(
        content=b"\xff\xd8\xffJPEG",
        filename="telegram-document.jpg",
        mime_type="image/jpeg",
        is_image=True,
    )
    resolver.resolve.return_value = resolved
    runner = AsyncMock()
    runner.run.return_value = "📄 archivado"
    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        media_resolver=resolver,
    )

    assert await processor._run_agent(accepted) is False
    repo.claim_agent_start_with_run_id.assert_awaited_once()
    resolver.resolve.assert_awaited_once()
    assert runner.run.await_args.kwargs["media"] == (resolved,)
    assert "analyze_document" in runner.run.await_args.args[0]


async def test_command_is_answered_deterministically_without_an_agent_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/help"}).ciphertext}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.claim_command_reply.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    runner = AsyncMock()
    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
    )

    assert await processor._run_agent(accepted) is False

    runner.run.assert_not_awaited()
    sender.send_typing.assert_not_awaited()
    kwargs = repo.claim_command_reply.await_args.kwargs
    assert kwargs["agno_session_id"] is None
    assert kwargs["content_length"] == len(HELP_REPLY)
    assert kwargs["chunk_count"] == 1
    assert cipher.decrypt(kwargs["content_ciphertext"]) == {"content": HELP_REPLY}


async def test_new_command_opens_the_next_conversation_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/new"}).ciphertext}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.current_session_id.return_value = "tg:ancoramind:4"
    repo.claim_command_reply.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
    )

    assert await processor._run_agent(accepted) is False

    kwargs = repo.claim_command_reply.await_args.kwargs
    assert kwargs["agno_session_id"] == "tg:ancoramind:4:1"
    assert cipher.decrypt(kwargs["content_ciphertext"]) == {"content": NEW_SESSION_REPLY}


async def test_a_replayed_command_never_answers_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/new"}).ciphertext}
    )
    repo.claim_command_reply.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    sender = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=AsyncMock(),
        sender=sender,
    )

    assert await processor._run_agent(accepted) is False

    repo.claim_delivery_start.assert_not_awaited()
    sender.send_text.assert_not_awaited()


async def test_leading_slash_text_that_is_not_a_command_reaches_the_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "/home/user/notas.txt"}).ciphertext}
    )
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    runner = AsyncMock()
    runner.run.return_value = "ok"

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=AsyncMock(),
    )

    assert await processor._run_agent(accepted) is False

    runner.run.assert_awaited_once()
    assert runner.run.await_args.args[0] == "/home/user/notas.txt"
    repo.claim_command_reply.assert_not_awaited()


async def test_agent_run_reuses_the_stored_conversation_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    interaction = _interaction()
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1)
    accepted = interaction.model_copy(
        update={"payload_ciphertext": cipher.encrypt({"text": "hola"}).ciphertext}
    )
    repo.current_session_id.return_value = "tg:ancoramind:4:3"
    repo.claim_agent_start_with_run_id.return_value = accepted.model_copy(
        update={"status": InteractionStatus.AGENT_STARTED}
    )
    response = AsyncMock()
    response.id = uuid4()
    repo.persist_response_ready.return_value = response
    repo.claim_delivery_start.return_value = None
    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    runner = AsyncMock()
    runner.run.return_value = "ok"

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=cipher,
        agent_runner=runner,
        sender=AsyncMock(),
    )

    assert await processor._run_agent(accepted) is False

    assert runner.run.await_args.kwargs["session_id"] == "tg:ancoramind:4:3"
    assert repo.claim_agent_start_with_run_id.await_args.args[2] == "tg:ancoramind:4:3"


async def test_same_chat_is_processed_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    first = _interaction()
    second = first.model_copy(update={"id": uuid4(), "telegram_update_id": 3})
    calls: list[UUID] = []

    async def fake_run_agent(interaction: TelegramInteraction) -> bool:
        calls.append(interaction.id)
        return True

    monkeypatch.setattr(processor_module, "TelegramInteractionsRepository", lambda _: repo)

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    processor = InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
    )
    monkeypatch.setattr(processor, "_run_agent", fake_run_agent)

    assert await processor._process_chat_queue([first, second]) == 2
    assert calls == [first.id, second.id]


def _consent_processor(
    monkeypatch: pytest.MonkeyPatch, actions_repo: AsyncMock
) -> InteractionProcessor:
    session = AsyncMock()

    async def session_factory() -> AsyncSession:
        return cast(AsyncSession, session)

    monkeypatch.setattr(processor_module, "ActionProposalsRepository", lambda _: actions_repo)
    executor = AsyncMock()

    async def execute(proposal, *, user_id):
        assert user_id == "5"
        return f"✅ Confirmado y ejecutado ({proposal.id})."

    executor.execute.side_effect = execute
    monkeypatch.setattr(processor_module, "ProposalExecutor", lambda *args, **kwargs: executor)
    return InteractionProcessor(
        session_factory=session_factory,
        payload_cipher=TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), key_version=1),
        agent_runner=AsyncMock(),
        sender=AsyncMock(),
        governed_consent=True,
    )


class TestConsentInput:
    """specs/023 T4.3: resolving Sí/No before the Agent, with mocked repositories."""

    async def test_non_consent_text_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        processor = _consent_processor(monkeypatch, AsyncMock())
        assert await processor._handle_consent_input(_interaction(), "hola, qué tal") is None

    async def test_bare_si_with_no_pending_proposals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        actions = AsyncMock()
        actions.list_confirmable.return_value = []
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), "Sí")

        assert reply == "No tienes ninguna propuesta pendiente de confirmar."
        actions.claim_confirmation.assert_not_awaited()

    async def test_bare_si_with_several_pending_asks_to_pick(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = uuid4(), uuid4()
        actions = AsyncMock()
        actions.list_confirmable.return_value = [a, b]
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), "Sí")

        assert str(a) in reply and str(b) in reply
        actions.claim_confirmation.assert_not_awaited()

    async def test_bare_si_with_exactly_one_pending_claims_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domain.actions.models import ClaimedProposal, ConsentClaimResult

        proposal_id = uuid4()
        actions = AsyncMock()
        actions.list_confirmable.return_value = [proposal_id]
        actions.claim_confirmation.return_value = ConsentClaimResult(
            claimed=ClaimedProposal(
                id=proposal_id,
                tool_name="create_reminder",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        )
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), "Sí")

        assert str(proposal_id) in reply
        actions.claim_confirmation.assert_awaited_once()

    async def test_si_with_uuid_claims_that_proposal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domain.actions.models import ClaimedProposal, ConsentClaimResult

        proposal_id = uuid4()
        actions = AsyncMock()
        actions.claim_confirmation.return_value = ConsentClaimResult(
            claimed=ClaimedProposal(
                id=proposal_id,
                tool_name="create_reminder",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        )
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"Sí {proposal_id}")

        assert str(proposal_id) in reply
        actions.list_confirmable.assert_not_awaited()

    async def test_rejection_reasons_produce_distinct_fixed_replies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domain.actions.models import ConsentClaimResult, ConsentRejection

        proposal_id = uuid4()
        cases = (
            (ConsentRejection.NOT_FOUND, "no encontré"),
            (ConsentRejection.EXPIRED, "caducó"),
            (ConsentRejection.INTERACTION_ALREADY_USED, "ya has confirmado"),
            (ConsentRejection.NOT_PENDING, "ya no está pendiente"),
        )
        for rejection, expected_snippet in cases:
            actions = AsyncMock()
            actions.claim_confirmation.return_value = ConsentClaimResult(rejection=rejection)
            processor = _consent_processor(monkeypatch, actions)
            reply = await processor._handle_consent_input(_interaction(), f"Sí {proposal_id}")
            assert expected_snippet in reply.lower()

    async def test_confirm_button_claims_without_touching_discard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domain.actions.models import ClaimedProposal, ConsentClaimResult

        proposal_id = uuid4()
        actions = AsyncMock()
        actions.claim_confirmation.return_value = ConsentClaimResult(
            claimed=ClaimedProposal(
                id=proposal_id,
                tool_name="create_reminder",
                payload={},
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
        )
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"c:{proposal_id}")

        assert str(proposal_id) in reply
        actions.discard_proposal.assert_not_awaited()

    async def test_discard_button_discards_without_claiming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        actions = AsyncMock()
        actions.discard_proposal.return_value = True
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"d:{uuid4()}")

        assert reply == "❌ Propuesta descartada."
        actions.claim_confirmation.assert_not_awaited()

    async def test_discard_button_on_already_resolved_proposal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        actions = AsyncMock()
        actions.discard_proposal.return_value = False
        processor = _consent_processor(monkeypatch, actions)

        reply = await processor._handle_consent_input(_interaction(), f"d:{uuid4()}")

        assert reply == "Esa propuesta ya no está pendiente."

    async def test_malformed_callback_like_text_is_not_consent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        actions = AsyncMock()
        processor = _consent_processor(monkeypatch, actions)

        for raw in ("c:not-a-uuid", "x:" + str(uuid4()), "c:" + str(uuid4()) + " extra"):
            assert await processor._handle_consent_input(_interaction(), raw) is None
        actions.claim_confirmation.assert_not_awaited()
        actions.discard_proposal.assert_not_awaited()
