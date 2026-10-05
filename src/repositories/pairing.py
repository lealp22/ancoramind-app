"""PostgreSQL persistence for governed Telegram pairing invitations (BL-24)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.pairing import (
    PairingInvitation,
    PairingRedemption,
    PairingRedemptionStatus,
    PairingRequest,
)


class TelegramPairingRepository:
    """Persist invitation and request state using parameterized, auditable SQL."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def has_active_authorization(self, telegram_user_id: int) -> bool:
        """Return whether a user is currently authorized for a new admission.

        This is deliberately a fresh database read on every non-technical
        admission, so an operator revocation takes effect on the next update.
        Callers must fail closed if this query cannot complete.
        """
        result = await self._session.execute(
            text("""
                SELECT 1
                FROM ancora.telegram_pairing_authorizations
                WHERE telegram_user_id = :telegram_user_id AND status = 'active'
            """),
            {"telegram_user_id": telegram_user_id},
        )
        return result.fetchone() is not None

    async def redeem_invitation(
        self,
        *,
        code_hash: str,
        telegram_user_id: int,
    ) -> PairingRedemption:
        """Atomically create one pending request without persisting the raw code.

        The user advisory lock serializes redemption across distinct invitations,
        while ``FOR UPDATE`` serializes consumption of one invitation's capacity.
        This deliberately returns typed metadata only; the channel adapter decides
        later which fixed user-facing reply is safe to disclose.
        """
        now = datetime.now(tz=UTC)
        try:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:telegram_user_id)"),
                {"telegram_user_id": telegram_user_id},
            )
            pending = await self._session.execute(
                text("""
                    SELECT id, invitation_id, telegram_user_id, status, requested_at,
                        decided_by, decision_reason, decided_at
                    FROM ancora.telegram_pairing_requests
                    WHERE telegram_user_id = :telegram_user_id AND status = 'pending'
                    FOR UPDATE
                """),
                {"telegram_user_id": telegram_user_id},
            )
            pending_row = pending.fetchone()
            if pending_row is not None:
                await self._session.commit()
                return PairingRedemption(
                    status=PairingRedemptionStatus.ALREADY_PENDING,
                    request=self._request_from_row(pending_row),
                )

            invitation_result = await self._session.execute(
                text("""
                    SELECT id, status, max_uses, use_count, expires_at,
                        auto_approve, created_by, reason
                    FROM ancora.telegram_pairing_invitations
                    WHERE code_hash = :code_hash
                    FOR UPDATE
                """),
                {"code_hash": code_hash},
            )
            invitation = invitation_result.fetchone()
            if invitation is None:
                await self._session.commit()
                return PairingRedemption(status=PairingRedemptionStatus.INVALID)

            existing = await self._session.execute(
                text("""
                    SELECT id, invitation_id, telegram_user_id, status, requested_at,
                        decided_by, decision_reason, decided_at
                    FROM ancora.telegram_pairing_requests
                    WHERE invitation_id = :invitation_id AND telegram_user_id = :telegram_user_id
                    FOR UPDATE
                """),
                {"invitation_id": invitation.id, "telegram_user_id": telegram_user_id},
            )
            existing_row = existing.fetchone()
            if existing_row is not None:
                await self._session.commit()
                return PairingRedemption(
                    status=(
                        PairingRedemptionStatus.ALREADY_PENDING
                        if existing_row.status == "pending"
                        else PairingRedemptionStatus.ALREADY_DECIDED
                    ),
                    request=self._request_from_row(existing_row),
                )

            if invitation.expires_at <= now:
                if invitation.status == "active":
                    await self._session.execute(
                        text("""
                            UPDATE ancora.telegram_pairing_invitations
                            SET status = 'expired'
                            WHERE id = :id AND status = 'active'
                        """),
                        {"id": invitation.id},
                    )
                await self._session.commit()
                return PairingRedemption(status=PairingRedemptionStatus.EXPIRED)
            if invitation.status == "revoked":
                await self._session.commit()
                return PairingRedemption(status=PairingRedemptionStatus.REVOKED)
            if invitation.status == "exhausted" or invitation.use_count >= invitation.max_uses:
                if invitation.status == "active":
                    await self._session.execute(
                        text("""
                            UPDATE ancora.telegram_pairing_invitations
                            SET status = 'exhausted'
                            WHERE id = :id AND status = 'active'
                        """),
                        {"id": invitation.id},
                    )
                await self._session.commit()
                return PairingRedemption(status=PairingRedemptionStatus.EXHAUSTED)
            if invitation.status != "active":  # defensive for unexpected persisted statuses
                await self._session.commit()
                return PairingRedemption(status=PairingRedemptionStatus.INVALID)

            if invitation.auto_approve:
                created = await self._session.execute(
                    text("""
                        INSERT INTO ancora.telegram_pairing_requests (
                            invitation_id, telegram_user_id, status, requested_at,
                            decided_by, decision_reason, decided_at
                        ) VALUES (
                            :invitation_id, :telegram_user_id, 'approved', :now,
                            :decided_by, :decision_reason, :now
                        )
                        RETURNING id, invitation_id, telegram_user_id, status, requested_at,
                            decided_by, decision_reason, decided_at
                    """),
                    {
                        "invitation_id": invitation.id,
                        "telegram_user_id": telegram_user_id,
                        "now": now,
                        "decided_by": invitation.created_by,
                        "decision_reason": invitation.reason,
                    },
                )
            else:
                created = await self._session.execute(
                    text("""
                        INSERT INTO ancora.telegram_pairing_requests (
                            invitation_id, telegram_user_id, status, requested_at
                        ) VALUES (:invitation_id, :telegram_user_id, 'pending', :now)
                        RETURNING id, invitation_id, telegram_user_id, status, requested_at,
                            decided_by, decision_reason, decided_at
                    """),
                    {
                        "invitation_id": invitation.id,
                        "telegram_user_id": telegram_user_id,
                        "now": now,
                    },
                )
            row = created.fetchone()
            if row is None:  # pragma: no cover - INSERT RETURNING always yields a row
                raise RuntimeError("Pairing redemption insert did not return a row")
            if invitation.auto_approve:
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
                        "telegram_user_id": telegram_user_id,
                        "request_id": row.id,
                        "actor": invitation.created_by,
                        "reason": invitation.reason,
                        "now": now,
                    },
                )
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_pairing_invitations
                    SET use_count = use_count + 1,
                        status = CASE
                            WHEN use_count + 1 >= max_uses THEN 'exhausted'
                            ELSE status
                        END
                    WHERE id = :id AND status = 'active'
                """),
                {"id": invitation.id},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return PairingRedemption(
            status=(
                PairingRedemptionStatus.AUTO_APPROVED
                if invitation.auto_approve
                else PairingRedemptionStatus.PENDING
            ),
            request=self._request_from_row(row),
        )

    async def list_pending_requests(self, limit: int = 100) -> list[PairingRequest]:
        """Return the bounded operator work queue without invitation codes or content."""
        result = await self._session.execute(
            text("""
                SELECT id, invitation_id, telegram_user_id, status, requested_at,
                    decided_by, decision_reason, decided_at
                FROM ancora.telegram_pairing_requests
                WHERE status = 'pending'
                ORDER BY requested_at ASC, id ASC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        return [self._request_from_row(row) for row in result.fetchall()]

    async def list_invitations(self, limit: int = 100) -> list[PairingInvitation]:
        """Return the most recent invitations, newest first; never the raw code."""
        result = await self._session.execute(
            text("""
                SELECT id, status, max_uses, use_count, expires_at, created_by,
                    reason, created_at, revoked_by, revoked_reason, revoked_at, auto_approve
                FROM ancora.telegram_pairing_invitations
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        return [
            PairingInvitation.model_validate(row, from_attributes=True)
            for row in result.fetchall()
        ]

    async def reject_request(
        self,
        request_id: UUID,
        *,
        actor: str,
        reason: str,
    ) -> PairingRequest | None:
        """Reject exactly one pending request; no authorization is ever created."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_pairing_requests
                    SET status = 'rejected', decided_by = :actor, decision_reason = :reason,
                        decided_at = :now
                    WHERE id = :id AND status = 'pending'
                    RETURNING id, invitation_id, telegram_user_id, status, requested_at,
                        decided_by, decision_reason, decided_at
                """),
                {"id": request_id, "actor": actor, "reason": reason, "now": now},
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._request_from_row(row) if row else None

    async def create_invitation(
        self,
        *,
        code_hash: str,
        max_uses: int,
        expires_at: datetime,
        created_by: str,
        reason: str,
        auto_approve: bool = False,
    ) -> PairingInvitation:
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    INSERT INTO ancora.telegram_pairing_invitations (
                        code_hash, status, max_uses, use_count, expires_at, created_by,
                        reason, created_at, auto_approve
                    ) VALUES (
                        :code_hash, 'active', :max_uses, 0, :expires_at, :created_by, :reason, :now,
                        :auto_approve
                    )
                    RETURNING id, status, max_uses, use_count, expires_at, created_by,
                        reason, created_at,
                        revoked_by, revoked_reason, revoked_at, auto_approve
                """),
                {
                    "code_hash": code_hash,
                    "max_uses": max_uses,
                    "expires_at": expires_at,
                    "created_by": created_by,
                    "reason": reason,
                    "now": now,
                    "auto_approve": auto_approve,
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
                        revoked_by, revoked_reason, revoked_at, auto_approve
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

    @staticmethod
    def _request_from_row(row: object) -> PairingRequest:
        return PairingRequest.model_validate(row, from_attributes=True)
