"""BL-52: denied admission stays denied while a bounded secondary outbox replies."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from src.domain.interactions.pairing import hash_pairing_code
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.processor import InteractionProcessor, TelegramSendError
from src.domain.interactions.rejection_notice import (
    ACCESS_DENIED_REPLY,
    ACCESS_DENIED_RESPONSE_KIND,
    NOTICE_GLOBAL_PER_MINUTE,
)
from src.repositories.database import get_session
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.pairing import TelegramPairingRepository
from tests.integration.test_telegram_admission_endpoint import (
    _app,
    _create_pairing_invitation,
    _post,
    _settings,
    _update,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def setup_notice(session):
    settings = _settings(_env_file=None, telegram_access_notice_enabled=True)
    runner = AsyncMock()
    runner.run.side_effect = AssertionError("A rejected user must never reach the Agent")
    sender = AsyncMock()
    sender.send_text.return_value = 400
    processor = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=TelegramPayloadCipher(
            settings.telegram_payload_encryption_key, settings.telegram_payload_key_version
        ),
        agent_runner=runner,
        sender=sender,
        access_notice_enabled=True,
    )
    return _app(settings), settings, processor, runner, sender


def _message(update_id=1, user_id=1601, **kwargs):
    return _update(update_id, user_id=user_id, chat_id=user_id, **kwargs)


async def _notice_count(session):
    return (
        await session.execute(
            text("SELECT count(*) FROM ancora.logical_responses WHERE response_kind=:kind"),
            {"kind": ACCESS_DENIED_RESPONSE_KIND},
        )
    ).scalar_one()


async def test_rejected_message_has_one_notice_no_payload_and_no_agent(session, setup_notice):
    app, settings, processor, runner, sender = setup_notice
    payload = _message(text_value="private data must not be echoed or stored")
    first = await _post(app, payload)
    duplicate = await _post(app, payload)
    assert first.json()["status"] == duplicate.json()["status"] == "rejected"
    assert duplicate.json()["duplicate"] is True
    assert await _notice_count(session) == 1
    # A restart before claim can safely pick up the unsent outbox.
    assert await processor.recover_once() == 0
    assert await processor.run_once() == 1
    assert await processor.run_once() == 0
    assert (await _post(app, payload)).json()["duplicate"] is True
    assert await processor.run_once() == 0
    sender.send_text.assert_awaited_once_with(1601, ACCESS_DENIED_REPLY)
    runner.run.assert_not_awaited()
    row = (
        await session.execute(
            text("""
        SELECT status, accepted_at, agent_started_at, payload_ciphertext,
            error_detail_code, model_call_count, gateway_request_count, tool_call_count
        FROM ancora.telegram_interactions WHERE id=:id
    """),
            {"id": first.json()["correlation_id"]},
        )
    ).one()
    assert row.status == "rejected" and row.error_detail_code == "user_not_allowlisted"
    assert row.accepted_at is row.agent_started_at is row.payload_ciphertext is None
    assert row.model_call_count == row.gateway_request_count == row.tool_call_count == 0
    stored = await session.execute(text("SELECT content_ciphertext FROM ancora.logical_responses"))
    cipher = TelegramPayloadCipher(
        settings.telegram_payload_encryption_key, settings.telegram_payload_key_version
    )
    assert cipher.decrypt(stored.scalar_one()) == {"content": ACCESS_DENIED_REPLY}
    usage = await session.execute(text("SELECT count(*) FROM ancora.llm_usage_events"))
    assert usage.scalar_one() == 0


async def test_cooldown_is_durable_per_user_under_concurrent_updates(session, setup_notice):
    app, _, processor, _, sender = setup_notice
    results = await asyncio.gather(*(_post(app, _message(n)) for n in range(1, 9)))
    assert all(r.json()["status"] == "rejected" for r in results)
    assert await _notice_count(session) == 1
    await processor.run_once()
    assert (await _post(app, _message(9))).json()["status"] == "rejected"
    assert await processor.run_once() == 0
    sender.send_text.assert_awaited_once()
    # Advance only the local reservation fixture, not a production clock.
    await session.execute(
        text("UPDATE ancora.logical_responses SET created_at=:past"),
        {"past": datetime.now(tz=UTC) - timedelta(minutes=6)},
    )
    await session.commit()
    await _post(app, _message(10))
    assert await _notice_count(session) == 2


async def test_global_rate_and_pending_caps_survive_distinct_users(session, setup_notice):
    app, _, processor, _, sender = setup_notice
    for n in range(NOTICE_GLOBAL_PER_MINUTE + 3):
        await _post(app, _message(n + 1, user_id=1601 + n))
    assert await _notice_count(session) == NOTICE_GLOBAL_PER_MINUTE
    # Rate window passes, pending capacity must still prevent a new reservation.
    await session.execute(
        text("UPDATE ancora.logical_responses SET created_at=:past"),
        {"past": datetime.now(tz=UTC) - timedelta(seconds=65)},
    )
    await session.commit()
    await _post(app, _message(50, user_id=1701))
    assert await _notice_count(session) == NOTICE_GLOBAL_PER_MINUTE
    assert await processor.run_once() == NOTICE_GLOBAL_PER_MINUTE
    assert sender.send_text.await_count == NOTICE_GLOBAL_PER_MINUTE


async def test_global_quota_counts_delivered_not_only_pending_notices(session, setup_notice):
    app, _, processor, _, sender = setup_notice
    for n in range(NOTICE_GLOBAL_PER_MINUTE):
        await _post(app, _message(n + 1, user_id=1601 + n))
    assert await processor.run_once() == NOTICE_GLOBAL_PER_MINUTE
    await _post(app, _message(50, user_id=1701))
    assert await _notice_count(session) == NOTICE_GLOBAL_PER_MINUTE
    assert await processor.run_once() == 0
    assert sender.send_text.await_count == NOTICE_GLOBAL_PER_MINUTE


@pytest.mark.parametrize("case", ["flag_off", "group", "callback", "edit", "identity", "secret"])
async def test_ineligible_updates_never_notify(session, setup_notice, case):
    app, settings, processor, _, sender = setup_notice
    update = _message()
    secret = "webhook-secret"
    if case == "flag_off":
        app = _app(settings.model_copy(update={"telegram_access_notice_enabled": False}))
    elif case == "group":
        update["message"]["chat"]["type"] = "group"
    elif case == "identity":
        del update["message"]["from"]
    elif case == "secret":
        secret = "wrong"
    elif case == "edit":
        update["edited_message"] = update.pop("message")
    else:
        message = update.pop("message")
        update["callback_query"] = {
            "id": "opaque",
            "from": message["from"],
            "message": message,
            "data": "consent:yes:untrusted",
        }
    result = await _post(app, update, secret=secret)
    assert result.status_code == (403 if case == "secret" else 200)
    assert await _notice_count(session) == 0
    assert await processor.run_once() == 0
    sender.send_text.assert_not_awaited()


@pytest.mark.parametrize("definitive", [False, True])
async def test_failed_send_never_replays_or_reopens_admission(session, setup_notice, definitive):
    app, _, processor, runner, sender = setup_notice
    sender.send_text.side_effect = TelegramSendError("bounded failure", definitive=definitive)
    payload = _message()
    await _post(app, payload)
    assert await processor.run_once() == 1
    assert await processor.recover_once() == 0
    await _post(app, payload)
    await _post(app, _message(2))
    assert await processor.run_once() == 0
    sender.send_text.assert_awaited_once()
    runner.run.assert_not_awaited()
    states = await session.execute(text("SELECT DISTINCT status FROM ancora.telegram_interactions"))
    assert states.scalars().all() == ["rejected"]


async def test_crash_after_claim_expires_without_resend(session, setup_notice):
    app, _, processor, _, sender = setup_notice
    await _post(app, _message())
    repo = TelegramInteractionsRepository(session)
    notices = await repo.list_access_notices()
    assert len(notices) == 1
    _, delivery_id = notices[0]
    assert await repo.claim_access_notice(delivery_id)
    assert not await repo.claim_access_notice(delivery_id)
    assert await processor.recover_once() == 0
    assert await processor.run_once() == 0
    sender.send_text.assert_not_awaited()
    result = await session.execute(text("SELECT status FROM ancora.logical_responses"))
    assert result.scalar_one() == "failed"


async def test_notice_expiry_and_processor_off_do_not_deliver(session, setup_notice):
    app, settings, processor, _, sender = setup_notice
    await _post(app, _message())
    off = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=TelegramPayloadCipher(
            settings.telegram_payload_encryption_key, settings.telegram_payload_key_version
        ),
        agent_runner=AsyncMock(),
        sender=sender,
    )
    assert await off.run_once() == 0
    await session.execute(
        text("UPDATE ancora.logical_responses SET created_at=:past"),
        {"past": datetime.now(tz=UTC) - timedelta(minutes=6)},
    )
    await session.commit()
    assert await processor.run_once() == 0
    sender.send_text.assert_not_awaited()
    result = await session.execute(text("SELECT status FROM ancora.logical_responses"))
    assert result.scalar_one() == "expired"


@pytest.mark.parametrize("state", ["pending", "revoked"])
async def test_notice_is_identical_for_pending_and_revoked_users(session, setup_notice, state):
    app, _, processor, _, sender = setup_notice
    code = "local-test-invitation-with-sufficient-length"
    await _create_pairing_invitation(session, code)
    repo = TelegramPairingRepository(session)
    redemption = await repo.redeem_invitation(
        code_hash=hash_pairing_code(code, "pairing-pepper"),
        telegram_user_id=1601,
    )
    assert redemption.request is not None
    if state == "revoked":
        await repo.approve_request(redemption.request.id, actor="test", reason="local")
        await repo.revoke_authorization(1601, actor="test", reason="local")
    # Pairing OFF must not alter durable authorization or announce code validity.
    assert (await _post(app, _message())).json()["status"] == "rejected"
    assert await processor.run_once() == 1
    sender.send_text.assert_awaited_once_with(1601, ACCESS_DENIED_REPLY)


async def test_granted_authorization_cancels_queued_stale_notice(session, setup_notice):
    app, _, processor, _, sender = setup_notice
    await _post(app, _message())
    code = "local-test-invitation-with-sufficient-length"
    await _create_pairing_invitation(session, code)
    repo = TelegramPairingRepository(session)
    redemption = await repo.redeem_invitation(
        code_hash=hash_pairing_code(code, "pairing-pepper"),
        telegram_user_id=1601,
    )
    await repo.approve_request(redemption.request.id, actor="test", reason="local")
    assert await processor.run_once() == 0
    sender.send_text.assert_not_awaited()


async def test_authorized_rate_limit_rejection_does_not_emit_access_notice(session, setup_notice):
    _, settings, processor, _, sender = setup_notice
    app = _app(settings.model_copy(update={"telegram_admission_user_burst": 1}))
    # The technical user is admitted once; the second update is rejected for rate.
    await _post(app, _message(1, user_id=999, text_value="/help"))
    second = await _post(app, _message(2, user_id=999, text_value="/help"))
    assert second.json()["status"] == "rejected"
    assert await _notice_count(session) == 0
    assert await processor.run_once() == 1  # Only the authorized /help response.
    assert sender.send_text.await_args.args[1] != ACCESS_DENIED_REPLY


async def test_two_concurrent_processors_send_one_notice(session, setup_notice):
    app, settings, first, _, sender = setup_notice
    await _post(app, _message())
    second = InteractionProcessor(
        session_factory=get_session,
        payload_cipher=TelegramPayloadCipher(
            settings.telegram_payload_encryption_key, settings.telegram_payload_key_version
        ),
        agent_runner=AsyncMock(),
        sender=sender,
        access_notice_enabled=True,
    )
    await asyncio.gather(first.run_once(), second.run_once())
    sender.send_text.assert_awaited_once_with(1601, ACCESS_DENIED_REPLY)


async def test_outbox_failure_rolls_back_notice_and_admission_together(
    session, setup_notice, monkeypatch
):
    app, _, processor, _, sender = setup_notice
    from sqlalchemy.exc import SQLAlchemyError

    original = TelegramInteractionsRepository._create_pending_response

    async def fail_after_insert(self, **kwargs):
        await original(self, **kwargs)
        raise SQLAlchemyError("synthetic local outbox persistence failure")

    monkeypatch.setattr(
        TelegramInteractionsRepository, "_create_pending_response", fail_after_insert
    )
    result = await _post(app, _message())
    assert result.status_code == 503
    assert await _notice_count(session) == 0
    count = await session.execute(text("SELECT count(*) FROM ancora.telegram_interactions"))
    assert count.scalar_one() == 0
    assert await processor.run_once() == 0
    sender.send_text.assert_not_awaited()
