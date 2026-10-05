"""Operator use cases for governed Telegram evaluator pairing (BL-24)."""

from __future__ import annotations

from uuid import UUID

from src.domain.interactions.pairing import (
    IssuedPairingInvitation,
    PairingInvitation,
    PairingInvitationCreate,
    PairingRedemption,
    PairingRequest,
    generate_pairing_code,
    hash_pairing_code,
    invitation_expiry,
)
from src.repositories.pairing import TelegramPairingRepository


class TelegramPairingService:
    """Create and administer pairing state; no Telegram/Agno dependency."""

    def __init__(self, repository: TelegramPairingRepository, *, code_pepper: str):
        self._repository = repository
        self._code_pepper = code_pepper

    async def issue_invitation(
        self,
        invitation: PairingInvitationCreate,
        *,
        actor: str,
    ) -> IssuedPairingInvitation:
        code = generate_pairing_code()
        persisted = await self._repository.create_invitation(
            code_hash=hash_pairing_code(code, self._code_pepper),
            max_uses=invitation.max_uses,
            expires_at=invitation_expiry(invitation.expires_in_minutes),
            created_by=actor,
            reason=invitation.reason,
            auto_approve=invitation.auto_approve,
        )
        return IssuedPairingInvitation(invitation=persisted, code=code)

    async def revoke_invitation(
        self, invitation_id: str, *, actor: str, reason: str
    ) -> PairingInvitation | None:
        return await self._repository.revoke_invitation(
            UUID(invitation_id), actor=actor, reason=reason.strip()
        )

    async def approve_request(
        self, request_id: str, *, actor: str, reason: str
    ) -> PairingRequest | None:
        return await self._repository.approve_request(
            UUID(request_id), actor=actor, reason=reason.strip()
        )

    async def redeem_code(self, code: str, *, telegram_user_id: int) -> PairingRedemption:
        """Request pairing through a code; this does not authorize Agent access."""
        return await self._repository.redeem_invitation(
            code_hash=hash_pairing_code(code, self._code_pepper),
            telegram_user_id=telegram_user_id,
        )

    async def list_pending_requests(self, limit: int = 100) -> list[PairingRequest]:
        """Return the bounded pending queue for an authenticated operator."""
        return await self._repository.list_pending_requests(limit)

    async def list_invitations(self, limit: int = 100) -> list[PairingInvitation]:
        """Return the most recent invitations for an authenticated operator."""
        return await self._repository.list_invitations(limit)

    async def reject_request(
        self,
        request_id: str,
        *,
        actor: str,
        reason: str,
    ) -> PairingRequest | None:
        return await self._repository.reject_request(
            UUID(request_id), actor=actor, reason=reason.strip()
        )

    async def revoke_authorization(
        self,
        telegram_user_id: int,
        *,
        actor: str,
        reason: str,
    ) -> bool:
        return await self._repository.revoke_authorization(
            telegram_user_id,
            actor=actor,
            reason=reason.strip(),
        )
