"""BL-52 eligibility is deterministic, non-enumerating and denied by default."""

from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from src.config import Settings
from src.domain.interactions.admission import TelegramAdmissionPolicy
from src.domain.interactions.models import (
    InteractionStatus,
    NormalizedTelegramUpdate,
    TelegramAdmissionLimits,
)
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.rejection_notice import ACCESS_DENIED_REPLY, permits_access_notice
from src.domain.interactions.service import TelegramInteractionService
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.pairing import TelegramPairingRepository


@pytest.mark.parametrize(
    "overrides",
    [
        {"chat_type": "group"},
        {"chat_id": None},
        {"telegram_user_id": None},
        {"telegram_user_id": -1, "chat_id": -1},
        {"chat_id": 8},
        {"message_id": None},
        {"message_id": 0},
        {"update_type": "callback_query"},
        {"update_type": "edited_message"},
        {"update_type": "unsupported"},
    ],
)
def test_notice_requires_private_new_message_and_complete_matching_identity(overrides):
    update = NormalizedTelegramUpdate.model_validate(
        {
            "update_id": 1,
            "update_type": "message",
            "message_id": 2,
            "telegram_user_id": 7,
            "chat_id": 7,
            "chat_type": "private",
            **overrides,
        }
    )
    assert not permits_access_notice(update, InteractionStatus.REJECTED, "user_not_allowlisted")


@pytest.mark.parametrize(
    "status,reason",
    [
        (InteractionStatus.ACCEPTED, None),
        (InteractionStatus.IGNORED, "unsupported_update"),
        (InteractionStatus.REJECTED, "user_burst_exceeded"),
        (InteractionStatus.REJECTED, "missing_telegram_user_id"),
    ],
)
def test_other_rejections_do_not_create_notification(status, reason):
    update = NormalizedTelegramUpdate(
        update_id=1,
        update_type="message",
        message_id=2,
        telegram_user_id=7,
        chat_id=7,
        chat_type="private",
    )
    assert not permits_access_notice(update, status, reason)


def test_notice_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ACCESS_NOTICE_ENABLED", raising=False)
    assert not Settings(_env_file=None, app_env="development").telegram_access_notice_enabled


@pytest.mark.parametrize("enabled", [False, True])
async def test_service_only_encrypts_fixed_notice_not_rejected_content(enabled):
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    pairing = AsyncMock(spec=TelegramPairingRepository)
    pairing.has_active_authorization.return_value = False
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode(), 1)
    service = TelegramInteractionService(
        repo,
        cipher,
        pairing_repository=pairing,
        access_notice_enabled=enabled,
    )
    await service.admit_update(
        bot_id=9,
        railway_request_id=None,
        update={
            "update_id": 1,
            "message": {
                "message_id": 2,
                "chat": {"id": 7, "type": "private"},
                "from": {"id": 7},
                "text": "untrusted private text",
            },
        },
        limits=TelegramAdmissionLimits(
            user_burst=5,
            burst_window_seconds=10,
            user_requests_per_minute=10,
            user_requests_per_hour=120,
            pending_global=20,
            queued_per_chat=5,
        ),
        policy=TelegramAdmissionPolicy({999}),
    )
    interaction = repo.admit_with_limits.await_args.args[0]
    assert interaction.status is InteractionStatus.REJECTED
    assert interaction.payload_ciphertext is None
    notice = repo.admit_with_limits.await_args.kwargs["access_notice_ciphertext"]
    if enabled:
        assert cipher.decrypt(notice) == {"content": ACCESS_DENIED_REPLY}
    else:
        assert notice is None
