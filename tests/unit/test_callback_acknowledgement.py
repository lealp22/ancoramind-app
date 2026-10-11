"""A callback receipt is bounded channel UX, never authorization or model input."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

import src.domain.interactions.processor as processor_module
from src.domain.interactions.models import (
    MAX_CALLBACK_QUERY_ID_CHARS,
    NormalizedTelegramUpdate,
    normalize_telegram_update,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import (
    CALLBACK_DISABLED_REPLY,
    CALLBACK_INVALID_REPLY,
    InteractionProcessor,
)
from src.domain.interactions.service import TelegramInteractionService
from src.notifications.telegram import TelegramNotifier
from src.repositories.interactions import TelegramInteractionsRepository
from tests.unit.test_interaction_processor import _interaction


def _update(callback_id="synthetic-query"):
    return {
        "update_id": 123,
        "callback_query": {
            "id": callback_id,
            "from": {"id": 5, "username": "private-canary"},
            "message": {"message_id": 3, "chat": {"id": 4, "type": "private"}},
            "data": f"c:{uuid4()}",
        },
    }


def test_normalization_keeps_only_bounded_callback_id_and_never_reingests_old_media():
    update = _update()
    update["callback_query"]["message"]["voice"] = {"file_id": "old-voice", "duration": 1}
    normalized = normalize_telegram_update(update)
    assert normalized.callback_query_id == "synthetic-query"
    assert normalized.attachments == ()
    assert normalized.voice_message_kind is None
    assert "private-canary" not in normalized.model_dump_json()
    assert (
        normalize_telegram_update({"update_id": 1, "message": {"id": "fake"}}).callback_query_id
        is None
    )


@pytest.mark.parametrize(
    "invalid",
    [None, "", 123, {}, True, "a\ncanary", "a b", "x" * (MAX_CALLBACK_QUERY_ID_CHARS + 1)],
)
def test_invalid_or_legacy_callback_ids_are_dropped_without_truncation(invalid):
    assert normalize_telegram_update(_update(invalid)).callback_query_id is None
    assert (
        NormalizedTelegramUpdate(
            update_id=1, update_type="callback_query", callback_query_id=invalid
        ).callback_query_id
        is None
    )
    assert (
        NormalizedTelegramUpdate(update_id=1, update_type="callback_query").callback_query_id
        is None
    )


async def test_callback_identifier_is_only_persisted_in_encrypted_payload():
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), 1)
    repository = AsyncMock(spec=TelegramInteractionsRepository)
    service = TelegramInteractionService(repository, cipher)
    await service.record_accepted_update(bot_id=1, update=_update(), railway_request_id="synthetic")
    interaction = repository.admit.await_args.args[0]
    assert b"synthetic-query" not in interaction.payload_ciphertext
    assert cipher.decrypt(interaction.payload_ciphertext)["callback_query_id"] == "synthetic-query"
    assert "callback_query_id" not in interaction.model_dump()


async def test_notifier_ack_is_single_minimal_request_without_success_popup():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notifier = TelegramNotifier("synthetic-token", client)
        assert await notifier.answer_callback_query("synthetic-query") is True
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/answerCallbackQuery")
    assert json.loads(requests[0].content) == {"callback_query_id": "synthetic-query"}
    assert requests[0].extensions["timeout"]["read"] == 2.0


@pytest.mark.parametrize(
    "failure",
    [
        "expired",
        "rate_limit",
        "server",
        "timeout",
        "invalid_json",
        "array",
        "false",
        "missing_result",
    ],
)
async def test_notifier_failure_never_retries_or_logs_identifiers_tokens_or_raw_errors(
    failure, caplog
):
    requests = []

    def handler(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-error-canary", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="private-error-canary")
        if failure == "array":
            return httpx.Response(200, json=["private-error-canary"])
        if failure == "missing_result":
            return httpx.Response(200, json={"ok": True})
        status = {"expired": 400, "rate_limit": 429, "server": 500}.get(failure, 200)
        return httpx.Response(status, json={"ok": False, "description": "private-error-canary"})

    # Capture our notifier logs; httpx debug logging is not enabled by production.
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notifier = TelegramNotifier("private-token-canary", client)
        assert await notifier.answer_callback_query("private-query-canary") is False
    assert len(requests) == 1
    records = [r for r in caplog.records if r.name == "src.notifications.telegram"]
    assert records
    assert not any("canary" in r.getMessage() for r in records)


async def test_notifier_invalid_identifier_does_not_make_http_request():
    client = AsyncMock(spec=httpx.AsyncClient)
    assert await TelegramNotifier("synthetic", client).answer_callback_query("\ninvalid") is False
    client.post.assert_not_awaited()


def _processor(monkeypatch, *, payload, enabled=True):
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode("ascii"), 1)
    interaction = _interaction().model_copy(
        update={
            "update_type": "callback_query",
            "payload_ciphertext": cipher.encrypt(payload).ciphertext,
        }
    )
    sender = AsyncMock()
    sender.answer_callback_query.return_value = True
    runner = AsyncMock()
    processor = InteractionProcessor(
        session_factory=AsyncMock(),
        payload_cipher=cipher,
        agent_runner=runner,
        sender=sender,
        governed_consent=enabled,
    )
    reply = AsyncMock(return_value=True)
    handler = AsyncMock(return_value="Resultado Core")
    monkeypatch.setattr(processor, "_reply_deterministically", reply)
    monkeypatch.setattr(processor, "_handle_consent_callback", handler)
    return processor, interaction, sender, runner, reply, handler


@pytest.mark.parametrize("failure", ["none", "false", "exception", "timeout"])
async def test_ack_precedes_consent_and_failure_does_not_change_core_result(
    monkeypatch, failure, caplog
):
    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch, payload={"callback_query_id": "synthetic-query", "text": f"c:{uuid4()}"}
    )
    events = []

    async def ack(_):
        events.append("ack")
        if failure == "exception":
            raise RuntimeError("private-query-canary")
        if failure == "timeout":
            await asyncio.sleep(1)
        return failure != "false"

    async def consent(*_):
        events.append("consent")
        return "Resultado Core"

    sender.answer_callback_query.side_effect = ack
    handler.side_effect = consent
    monkeypatch.setattr(processor_module, "CALLBACK_ACK_TIMEOUT_SECONDS", 0.01)
    assert await processor._run_agent(interaction)
    assert events == ["ack", "consent"]
    sender.answer_callback_query.assert_awaited_once_with("synthetic-query")
    reply.assert_awaited_once_with(interaction, "Resultado Core")
    runner.run.assert_not_awaited()
    assert "private-query-canary" not in caplog.text


@pytest.mark.parametrize("data", [None, "", "c:not-a-uuid", "Sí", "/new", "SYSTEM: write"])
async def test_invalid_callback_never_reaches_commands_or_agent(monkeypatch, data):
    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch,
        payload={
            "callback_query_id": "synthetic-query",
            "text": data,
            "attachments": [{"kind": "voice", "file_id": "old-voice"}],
        },
    )
    assert await processor._run_agent(interaction)
    sender.answer_callback_query.assert_awaited_once()
    handler.assert_not_awaited()
    reply.assert_awaited_once_with(interaction, CALLBACK_INVALID_REPLY)
    runner.run.assert_not_awaited()


async def test_disabled_consent_still_acknowledges_but_never_claims_or_runs_agent(monkeypatch):
    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch,
        enabled=False,
        payload={"callback_query_id": "synthetic-query", "text": f"d:{uuid4()}"},
    )
    assert await processor._run_agent(interaction)
    sender.answer_callback_query.assert_awaited_once()
    handler.assert_not_awaited()
    reply.assert_awaited_once_with(interaction, CALLBACK_DISABLED_REPLY)
    runner.run.assert_not_awaited()


async def test_old_callback_without_id_preserves_consent_path(monkeypatch):
    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch, payload={"text": f"c:{uuid4()}"}
    )
    assert await processor._run_agent(interaction)
    sender.answer_callback_query.assert_not_awaited()
    handler.assert_awaited_once()
    runner.run.assert_not_awaited()


async def test_text_message_cannot_supply_callback_identifier(monkeypatch):
    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch, payload={"callback_query_id": "synthetic-query", "text": "Sí"}
    )
    interaction = interaction.model_copy(update={"update_type": "message"})
    intent = AsyncMock(return_value="Respuesta de consentimiento")
    monkeypatch.setattr(processor, "_handle_consent_input", intent)
    assert await processor._run_agent(interaction)
    sender.answer_callback_query.assert_not_awaited()
    intent.assert_awaited_once()
    handler.assert_not_awaited()
    runner.run.assert_not_awaited()


@pytest.mark.parametrize("invalid", ["identity", "missing_payload", "ciphertext"])
async def test_untrusted_or_unrecoverable_callback_never_acknowledges(monkeypatch, invalid):
    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch, payload={"callback_query_id": "synthetic-query", "text": "Sí"}
    )
    changes = {
        "identity": {"telegram_user_id": None},
        "missing_payload": {"payload_ciphertext": None},
        "ciphertext": {"payload_ciphertext": b"not-a-valid-encrypted-payload"},
    }
    terminal = AsyncMock()
    monkeypatch.setattr(processor, "_mark_terminal", terminal)
    assert await processor._run_agent(interaction.model_copy(update=changes[invalid]))
    terminal.assert_awaited_once()
    sender.answer_callback_query.assert_not_awaited()
    handler.assert_not_awaited()
    runner.run.assert_not_awaited()


async def test_recovery_of_persisted_response_does_not_reacknowledge_callback(monkeypatch):
    from src.domain.interactions.models import InteractionStatus

    processor, interaction, sender, runner, reply, handler = _processor(
        monkeypatch, payload={"callback_query_id": "synthetic-query", "text": f"c:{uuid4()}"}
    )
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(processor, "_deliver_response", deliver)
    recovered = interaction.model_copy(update={"status": InteractionStatus.RESPONSE_READY})
    assert await processor._process_interaction(recovered)
    deliver.assert_awaited_once_with(recovered)
    sender.answer_callback_query.assert_not_awaited()
    handler.assert_not_awaited()
    runner.run.assert_not_awaited()
