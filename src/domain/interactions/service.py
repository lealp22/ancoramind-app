"""Use cases for durable interaction admission and recovery primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.interactions.admission import TelegramAdmissionPolicy
from src.domain.interactions.commands import parse_telegram_pairing_command
from src.domain.interactions.models import (
    InteractionStatus,
    TelegramAdmissionLimits,
    TelegramAdmissionResult,
    TelegramDeliveryCreate,
    TelegramInteraction,
    TelegramInteractionCreate,
    normalize_telegram_update,
)
from src.domain.interactions.pairing import PairingRedemptionStatus
from src.domain.interactions.pairing_service import TelegramPairingService
from src.domain.interactions.payloads import TelegramPayloadCipher
from src.domain.interactions.rejection_notice import ACCESS_DENIED_REPLY, permits_access_notice
from src.repositories.interactions import TelegramInteractionsRepository
from src.repositories.pairing import TelegramPairingRepository

PAIRING_PENDING_REPLY = (
    "✅ Solicitud de acceso recibida. Un operador la revisará antes de activar el acceso."
)
PAIRING_AUTO_APPROVED_REPLY = "✅ Acceso concedido. Ya puedes escribir con normalidad."
PAIRING_UNAVAILABLE_REPLY = (
    "No se pudo procesar la solicitud de acceso. Verifica el código y solicita ayuda al operador."
)


class TelegramInteractionService:
    """Domain service for ledger invariants; HTTP admission belongs to T4."""

    def __init__(
        self,
        repository: TelegramInteractionsRepository,
        payload_cipher: TelegramPayloadCipher,
        pairing_repository: TelegramPairingRepository | None = None,
        pairing_service: TelegramPairingService | None = None,
        pairing_enabled: bool = False,
        access_notice_enabled: bool = False,
    ):
        self._repository = repository
        self._payload_cipher = payload_cipher
        self._pairing_repository = pairing_repository
        self._pairing_service = pairing_service
        self._pairing_enabled = pairing_enabled
        self._access_notice_enabled = access_notice_enabled

    async def record_accepted_update(
        self,
        *,
        bot_id: int,
        update: dict[str, Any],
        railway_request_id: str | None,
        http_status: int = 200,
    ) -> TelegramAdmissionResult:
        """Normalize/encrypt an accepted update and atomically ledger its delivery."""
        normalized = normalize_telegram_update(update)
        encrypted = self._payload_cipher.encrypt(normalized.model_dump(mode="json"))
        interaction = TelegramInteractionCreate(
            bot_id=bot_id,
            telegram_update_id=normalized.update_id,
            telegram_message_id=normalized.message_id,
            chat_id=normalized.chat_id,
            telegram_user_id=normalized.telegram_user_id,
            update_type=normalized.update_type,
            payload_ciphertext=encrypted.ciphertext,
            payload_key_version=encrypted.key_version,
            payload_fingerprint=encrypted.fingerprint,
        )
        return await self._repository.admit(
            interaction,
            TelegramDeliveryCreate(
                railway_request_id=railway_request_id,
                http_status=http_status,
                delivery_status="durable",
            ),
        )

    async def admit_update(
        self,
        *,
        bot_id: int,
        update: dict[str, Any],
        railway_request_id: str | None,
        limits: TelegramAdmissionLimits,
        policy: TelegramAdmissionPolicy,
        http_status: int = 200,
    ) -> TelegramAdmissionResult:
        """Apply deterministic policy then atomically persist durable admission."""
        normalized = normalize_telegram_update(update)
        pairing_command = (
            parse_telegram_pairing_command(normalized.text)
            if self._pairing_enabled
            else None
        )
        has_active_authorization = False
        if (
            normalized.chat_type == "private"
            and normalized.telegram_user_id is not None
            and not policy.is_technical_allowlisted(normalized.telegram_user_id)
        ):
            if self._pairing_repository is None:
                raise RuntimeError("Pairing authorization repository is required")
            has_active_authorization = await self._pairing_repository.has_active_authorization(
                normalized.telegram_user_id
            )
        decision = policy.evaluate(
            normalized,
            has_active_authorization=has_active_authorization,
            permits_pairing=pairing_command is not None,
        )
        pairing_reply: str | None = None
        if pairing_command is not None and decision.status is InteractionStatus.ACCEPTED:
            if self._pairing_service is None or normalized.telegram_user_id is None:
                raise RuntimeError("Pairing redemption service is required")
            redemption = await self._pairing_service.redeem_code(
                pairing_command.code,
                telegram_user_id=normalized.telegram_user_id,
            )
            pairing_reply = (
                PAIRING_AUTO_APPROVED_REPLY
                if redemption.status is PairingRedemptionStatus.AUTO_APPROVED
                else PAIRING_PENDING_REPLY
                if redemption.status
                in {PairingRedemptionStatus.PENDING, PairingRedemptionStatus.ALREADY_PENDING}
                else PAIRING_UNAVAILABLE_REPLY
            )
            # Never write the raw credential to the encrypted interaction payload.
            normalized = normalized.model_copy(update={"text": "/pair"})
        encrypted = (
            self._payload_cipher.encrypt(normalized.model_dump(mode="json"))
            if decision.status is InteractionStatus.ACCEPTED
            else None
        )
        interaction = TelegramInteractionCreate(
            bot_id=bot_id,
            telegram_update_id=normalized.update_id,
            telegram_message_id=normalized.message_id,
            chat_id=normalized.chat_id,
            telegram_user_id=normalized.telegram_user_id,
            update_type=normalized.update_type,
            status=decision.status,
            payload_ciphertext=encrypted.ciphertext if encrypted else None,
            payload_key_version=encrypted.key_version if encrypted else None,
            payload_fingerprint=encrypted.fingerprint if encrypted else None,
            error_class="admission_rejected"
            if decision.status is InteractionStatus.REJECTED
            else None,
            error_detail_code=decision.error_detail_code,
        )
        reply = self._payload_cipher.encrypt({"content": pairing_reply}) if pairing_reply else None
        notice = (
            self._payload_cipher.encrypt({"content": ACCESS_DENIED_REPLY})
            if self._access_notice_enabled
            and permits_access_notice(normalized, decision.status, decision.error_detail_code)
            else None
        )
        return await self._repository.admit_with_limits(
            interaction,
            TelegramDeliveryCreate(
                railway_request_id=railway_request_id,
                http_status=http_status,
                delivery_status="received",
            ),
            limits,
            deterministic_reply_ciphertext=reply.ciphertext if reply else None,
            deterministic_reply_key_version=reply.key_version if reply else None,
            deterministic_reply_length=len(pairing_reply) if pairing_reply else None,
            deterministic_reply_chunk_count=1 if pairing_reply else None,
            access_notice_ciphertext=notice.ciphertext if notice else None,
            access_notice_key_version=notice.key_version if notice else None,
        )

    async def claim_agent_start(self, correlation_id: UUID) -> TelegramInteraction | None:
        """Claim an accepted interaction exactly once for future T5 processing."""
        return await self._repository.claim_agent_start(correlation_id)

    async def mark_terminal(
        self,
        correlation_id: UUID,
        status: InteractionStatus,
        *,
        error_class: str | None = None,
        error_detail_code: str | None = None,
    ) -> TelegramInteraction | None:
        """Persist a terminal state and enforce its payload-retention policy."""
        if status not in {
            InteractionStatus.IGNORED,
            InteractionStatus.REJECTED,
            InteractionStatus.COMPLETED,
            InteractionStatus.FAILED_CONTROLLED,
            InteractionStatus.FAILED_DEFINITIVE,
            InteractionStatus.FAILED_AMBIGUOUS,
        }:
            raise ValueError("mark_terminal requires a terminal interaction status")
        return await self._repository.update_status(
            correlation_id,
            status,
            error_class=error_class,
            error_detail_code=error_detail_code,
        )

    async def purge_expired_payloads(self, now: datetime | None = None) -> int:
        """Purge expired failed-ambiguous payloads while preserving audit metadata."""
        return await self._repository.purge_expired_payloads(now)
