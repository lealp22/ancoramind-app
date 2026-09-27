"""PostgreSQL persistence for governed Telegram pairing invitations (BL-24)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.pairing import (
    PairingInvitation,
    PairingRequest,
)


class TelegramPairingRepository:
    """Persist invitation and request state using parameterized, auditable SQL."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_invitation(
        self,
        *,
        code_hash: str,
        max_uses: int,
        expires_at: datetime,
        created_by: str,
        reason: str,
    ) -> PairingInvitation:
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    INSERT INTO ancora.telegram_pairing_invitations (
                        code_hash, status, max_uses, use_count, expires_at, created_by,
                        reason, created_at
                    ) VALUES (
                        :code_hash, 'active', :max_uses, 0, :expires_at, :created_by, :reason, :now
                    )
                    RETURNING id, status, max_uses, use_count, expires_at, created_by,
                        reason, created_at,
                        revoked_by, revoked_reason, revoked_at
                """),
                {
                    "code_hash": code_hash,
                    "max_uses": max_uses,
                    "expires_at": expires_at,
                    "created_by": created_by,
                    "reason": reason,
                    "now": now,
                },
            )
            row = result.fetchone()
            if row is None:  # pragma: no cover - INSERT RETURNING always returns a row
                raise RuntimeError("Pairing invitation insert did not return a row")
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return PairingInvitation.model_validate(row, from_attributes=True)

    async def revoke_invitation(
        self,
        invitation_id: UUID,
        *,
        actor: str,
        reason: str,
    ) -> PairingInvitation | None:
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_pairing_invitations
                    SET status = 'revoked', revoked_by = :actor, revoked_reason = :reason,
                        revoked_at = :now
                    WHERE id = :id AND status = 'active'
                    RETURNING id, status, max_uses, use_count, expires_at, created_by,
                        reason, created_at,
                        revoked_by, revoked_reason, revoked_at
                """),
                {"id": invitation_id, "actor": actor, "reason": reason, "now": now},
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return PairingInvitation.model_validate(row, from_attributes=True) if row else None

    async def approve_request(
        self,
        request_id: UUID,
        *,
        actor: str,
        reason: str,
    ) -> PairingRequest | None:
        """Approve once and create the durable authorization in the same transaction."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_pairing_requests
                    SET status = 'approved', decided_by = :actor, decision_reason = :reason,
                        decided_at = :now
                    WHERE id = :id AND status = 'pending'
                    RETURNING id, invitation_id, telegram_user_id, status, requested_at,
                        decided_by, decision_reason, decided_at
                """),
                {"id": request_id, "actor": actor, "reason": reason, "now": now},
            )
            row = result.fetchone()
            if row is not None:
                await self._session.execute(
                    text("""
                        INSERT INTO ancora.telegram_pairing_authorizations (
                            telegram_user_id, request_id, status, authorized_by, reason,
                            authorized_at
                        ) VALUES (:telegram_user_id, :request_id, 'active', :actor, :reason, :now)
                        ON CONFLICT (telegram_user_id) DO UPDATE
                        SET request_id = EXCLUDED.request_id,
                            status = 'active',
                            authorized_by = EXCLUDED.authorized_by,
                            reason = EXCLUDED.reason, authorized_at = EXCLUDED.authorized_at,
                            revoked_by = NULL, revoked_reason = NULL, revoked_at = NULL
                    """),
                    {
                        "telegram_user_id": row.telegram_user_id,
                        "request_id": row.id,
                        "actor": actor,
                        "reason": reason,
                        "now": now,
                    },
                )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return PairingRequest.model_validate(row, from_attributes=True) if row else None

    async def revoke_authorization(
        self,
        telegram_user_id: int,
        *,
        actor: str,
        reason: str,
    ) -> bool:
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_pairing_authorizations
                    SET status = 'revoked', revoked_by = :actor, revoked_reason = :reason,
                        revoked_at = :now
                    WHERE telegram_user_id = :telegram_user_id AND status = 'active'
                    RETURNING telegram_user_id
                """),
                {
                    "telegram_user_id": telegram_user_id,
                    "actor": actor,
                    "reason": reason,
                    "now": now,
                },
            )
            changed = result.fetchone() is not None
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return changed
