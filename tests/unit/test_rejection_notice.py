"""BL-52 eligibility is deterministic, non-enumerating and denied by default."""

from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from src.config import Settings
from src.domain.interactions.admission import TelegramAdmissionPolicy
from src.domain.interactions.commands import with_pilot_notice
from src.domain.interactions.models import (
    InteractionStatus,
    NormalizedTelegramUpdate,
    TelegramAdmissionLimits,
)
from src.domain.interactions.pairing import PairingRedemption, PairingRedemptionStatus
from src.domain.interactions.pairing_service import TelegramPairingService
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.rejection_notice import ACCESS_DENIED_REPLY, permits_access_notice
from src.domain.interactions.service import (
    PAIRING_AUTO_APPROVED_REPLY,
    PAIRING_PENDING_REPLY,
    PAIRING_UNAVAILABLE_REPLY,
    TelegramInteractionService,
)
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


def test_pilot_notice_url_is_empty_by_default(monkeypatch):
    monkeypatch.delenv("PILOT_NOTICE_URL", raising=False)
    assert Settings(_env_file=None, app_env="development").pilot_notice_url == ""


@pytest.mark.parametrize(
    "url",
    ["http://example.org/terms", "ftp://example.org/terms", "example.org/terms", "https://a b"],
)
def test_pilot_notice_url_rejects_non_https_or_whitespace(url):
    with pytest.raises(ValueError, match="PILOT_NOTICE_URL"):
        Settings(_env_file=None, app_env="development", pilot_notice_url=url)


def test_pilot_notice_url_accepts_https():
    settings = Settings(
        _env_file=None, app_env="development", pilot_notice_url="https://example.org/terms"
    )
    assert settings.pilot_notice_url == "https://example.org/terms"


_PAIR_UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 2,
        "chat": {"id": 7, "type": "private"},
        "from": {"id": 7},
        "text": "/pair " + "A" * 40,
    },
}
_LIMITS = TelegramAdmissionLimits(
    user_burst=5,
    burst_window_seconds=10,
    user_requests_per_minute=10,
    user_requests_per_hour=120,
    pending_global=20,
    queued_per_chat=5,
)


@pytest.mark.parametrize(
    ("status", "base_reply"),
    [
        (PairingRedemptionStatus.PENDING, PAIRING_PENDING_REPLY),
        (PairingRedemptionStatus.ALREADY_PENDING, PAIRING_PENDING_REPLY),
        (PairingRedemptionStatus.AUTO_APPROVED, PAIRING_AUTO_APPROVED_REPLY),
        (PairingRedemptionStatus.INVALID, PAIRING_UNAVAILABLE_REPLY),
        (PairingRedemptionStatus.EXPIRED, PAIRING_UNAVAILABLE_REPLY),
    ],
)
@pytest.mark.parametrize("pilot_url", [None, "https://example.org/terms"])
async def test_pair_reply_carries_pilot_notice_only_on_access_outcomes(
    status, base_reply, pilot_url
):
    repo = AsyncMock(spec=TelegramInteractionsRepository)
    pairing_repo = AsyncMock(spec=TelegramPairingRepository)
    pairing_repo.has_active_authorization.return_value = False
    pairing_service = AsyncMock(spec=TelegramPairingService)
    pairing_service.redeem_code.return_value = PairingRedemption(status=status)
    cipher = TelegramPayloadCipher(Fernet.generate_key().decode(), 1)
    service = TelegramInteractionService(
        repo,
        cipher,
        pairing_repository=pairing_repo,
        pairing_service=pairing_service,
        pairing_enabled=True,
        pilot_notice_url=pilot_url,
    )

    await service.admit_update(
        bot_id=9,
        railway_request_id=None,
        update=_PAIR_UPDATE,
        limits=_LIMITS,
        policy=TelegramAdmissionPolicy({999}),
    )

    ciphertext = repo.admit_with_limits.await_args.kwargs["deterministic_reply_ciphertext"]
    sent = cipher.decrypt(ciphertext)
    unavailable = base_reply == PAIRING_UNAVAILABLE_REPLY
    expected = (
        base_reply if pilot_url is None or unavailable else with_pilot_notice(base_reply, pilot_url)
    )
    assert sent == {"content": expected}
    if unavailable:
        assert "Condiciones" not in expected


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
