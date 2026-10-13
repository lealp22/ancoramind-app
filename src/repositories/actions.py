"""Action proposals repository — governance layer for WRITE operations.

The legacy execution API is retired (BL-39/40): ``confirm``,
``confirm_or_use_confirmed`` and ``mark_executed`` fail closed without I/O.
Only Core-owned consent and ``ProposalExecutor`` can authorize and execute.
``create`` still commits a pending proposal; it never writes canonical data.

* Consent API (``mark_presented``, ``list_confirmable``, ``claim_confirmation``,
  ``begin_execution``, ``complete_execution``, ``discard_pending_for_chat``,
  ``create_self_authorized``) — the Core-owned state machine of
  ``specs/022-llm-input-trust/consent-design.md`` (extended by ``specs/035``
  for the WRITE_TRIVIAL tier). These methods **never commit**: the caller owns
  the transaction so that the claim, the canonical mutation and the terminal
  state can be committed (or rolled back) together.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import (
    CONSENT_TTL,
    ClaimedProposal,
    ConsentClaimResult,
    ConsentMode,
    ConsentPrincipal,
    ConsentRejection,
    ProposalStatus,
    payload_hash,
)
from src.domain.llm_access.context import current_provenance

ProposalPayload = dict[str, Any]
ProposalRecord = dict[str, Any]

_TERMINAL_EXECUTION_STATUSES = frozenset(
    {
        ProposalStatus.EXECUTED,
        ProposalStatus.FAILED_DEFINITIVE,
        ProposalStatus.FAILED_AMBIGUOUS,
    }
)


class ActionProposalsRepository:
    """Repository for action proposals (governance layer)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        user_id: str,
        tool_name: str,
        payload: ProposalPayload,
        source_document_id: UUID | None = None,
        *,
        source_interaction_id: UUID | None = None,
        bot_id: int | None = None,
        chat_id: int | None = None,
    ) -> ProposalRecord:
        """Create a pending action proposal.

        The payload is normalised through a JSON round-trip and hashed, so the
        hash recomputed from the stored JSONB at claim time matches exactly.
        Without ``source_interaction_id``/``bot_id``/``chat_id`` the proposal
        has no consent provenance and ``claim_confirmation`` rejects it.
        """
        now = datetime.now(tz=UTC)
        normalized = json.loads(json.dumps(payload))
        if source_interaction_id is None and bot_id is None and chat_id is None:
            # specs/023 T4.4: the trusted origin comes from the governed run the
            # Core bound, never from tool arguments the model controls.
            provenance = current_provenance()
            if provenance is not None:
                source_interaction_id = provenance.interaction_id
                bot_id = provenance.bot_id
                chat_id = provenance.chat_id
        stmt = text("""
            INSERT INTO ancora.action_proposals
                (user_id, tool_name, status, payload, source_document_id, created_at,
                 payload_hash, source_interaction_id, bot_id, chat_id)
            VALUES (:uid,:tool,'pending_confirmation',CAST(:payload AS jsonb),:src,:now,
                    :hash,:source_interaction,:bot_id,:chat_id)
            RETURNING id,user_id,tool_name,status,payload,source_document_id,created_at
        """)
        result = await self._session.execute(
            stmt,
            {
                "uid": user_id,
                "tool": tool_name,
                "payload": json.dumps(normalized),
                "src": source_document_id,
                "now": now,
                "hash": payload_hash(tool_name, normalized),
                "source_interaction": source_interaction_id,
                "bot_id": bot_id,
                "chat_id": chat_id,
            },
        )
        row = result.fetchone()
        if row is None:
            raise RuntimeError("Action proposal insert did not return a row")
        await self._session.commit()
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "tool_name": row.tool_name,
            "status": row.status,
            "payload": row.payload,
            "source_document_id": (str(row.source_document_id) if row.source_document_id else None),
            "created_at": row.created_at.isoformat(),
        }

    async def create_self_authorized(
        self,
        user_id: str,
        tool_name: str,
        payload: ProposalPayload,
        *,
        source_interaction_id: UUID | None = None,
        bot_id: int | None = None,
        chat_id: int | None = None,
    ) -> ProposalRecord:
        """Audit a WRITE_TRIVIAL mutation already decided by the caller (specs/035).

        Unlike ``create()``, this inserts directly in a terminal ``executed``
        state with ``consent_mode='self_authorized'`` — there is no
        ``pending_confirmation`` window because the user's own request was
        the signal (same precedent as ``analyze_document``, specs/023 T4.7),
        not a proposal awaiting a «Sí». ``confirming_interaction_id`` stays
        ``NULL``: this is not a confirmation, and that column's unique index
        is partial on ``NOT NULL``, so leaving it unset never collides with a
        real confirmation on another row.

        Belongs to the Consent API discipline: **never commits**. The caller
        (``TrivialExecutor``) must run the canonical mutation and this insert
        on the same transaction and commit them together, so a mutation is
        never audited without having happened and vice versa.
        """
        now = datetime.now(tz=UTC)
        normalized = json.loads(json.dumps(payload))
        if source_interaction_id is None and bot_id is None and chat_id is None:
            provenance = current_provenance()
            if provenance is not None:
                source_interaction_id = provenance.interaction_id
                bot_id = provenance.bot_id
                chat_id = provenance.chat_id
        stmt = text("""
            INSERT INTO ancora.action_proposals
                (user_id, tool_name, status, consent_mode, payload, created_at,
                 payload_hash, source_interaction_id, bot_id, chat_id,
                 completed_at, executed_at)
            VALUES (:uid,:tool,'executed','self_authorized',CAST(:payload AS jsonb),:now,
                    :hash,:source_interaction,:bot_id,:chat_id,:now,:now)
            RETURNING id,user_id,tool_name,status,payload,source_document_id,created_at
        """)
        result = await self._session.execute(
            stmt,
            {
                "uid": user_id,
                "tool": tool_name,
                "payload": json.dumps(normalized),
                "now": now,
                "hash": payload_hash(tool_name, normalized),
                "source_interaction": source_interaction_id,
                "bot_id": bot_id,
                "chat_id": chat_id,
            },
        )
        row = result.fetchone()
        if row is None:
            raise RuntimeError("Self-authorized action proposal insert did not return a row")
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "tool_name": row.tool_name,
            "status": row.status,
            "consent_mode": ConsentMode.SELF_AUTHORIZED.value,
            "payload": row.payload,
            "source_document_id": None,
            "created_at": row.created_at.isoformat(),
        }

    async def get_pending(self, user_id: str, proposal_id: str) -> ProposalRecord | None:
        """Get a pending proposal by ID."""
        stmt = text("""
            SELECT id,user_id,tool_name,status,payload,source_document_id,created_at
            FROM ancora.action_proposals
            WHERE id=:id AND user_id=:uid AND status='pending_confirmation'
        """)
        result = await self._session.execute(stmt, {"id": UUID(proposal_id), "uid": user_id})
        row = result.fetchone()
        if not row:
            return None
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "tool_name": row.tool_name,
            "status": row.status,
            "payload": row.payload,
            "source_document_id": (str(row.source_document_id) if row.source_document_id else None),
        }

    async def confirm(self, user_id: str, proposal_id: str) -> ProposalRecord | None:
        """Retired: an LLM-supplied ID is never evidence of human consent.

        Keep a rejecting shim for old adapters, independently of rollout flags.
        Confirmation must use ``claim_confirmation`` from the trusted processor.
        """
        return None

    async def confirm_or_use_confirmed(
        self, user_id: str, proposal_id: str
    ) -> ProposalRecord | None:
        """Retired: even confirmed proposals must use the atomic Core executor.

        Returning a confirmed row here would let legacy tools mutate outside
        the single-use execution claim and its transaction. Never reuse it.
        """
        return None

    async def mark_executed(self, user_id: str, proposal_id: str) -> bool:
        """Retired: terminal audit belongs to the Core execution transaction."""
        return False

    # ── Consent API (specs/022 consent-design.md) — never commits ──────────

    async def mark_presented(
        self,
        proposal_ids: list[UUID],
        *,
        principal: ConsentPrincipal,
        response_id: UUID,
        presented_at: datetime,
    ) -> int:
        """Record verified delivery of proposals; starts their consent window.

        Only pending, provenance-bearing proposals of the same principal that
        were not presented before are touched: re-presenting never extends an
        existing deadline. Returns how many proposals became confirmable.
        """
        if not proposal_ids:
            return 0
        result = await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET presented_at = :presented_at,
                    presented_response_id = :response_id,
                    expires_at = :expires_at
                WHERE id = ANY(:ids)
                  AND user_id = :uid AND bot_id = :bot_id AND chat_id = :chat_id
                  AND status = 'pending_confirmation'
                  AND presented_at IS NULL
                  AND payload_hash IS NOT NULL
                  AND source_interaction_id IS NOT NULL
                RETURNING id
            """),
            {
                "ids": list(proposal_ids),
                "uid": principal.user_id,
                "bot_id": principal.bot_id,
                "chat_id": principal.chat_id,
                "response_id": response_id,
                "presented_at": presented_at,
                "expires_at": presented_at + CONSENT_TTL,
            },
        )
        return len(result.fetchall())

    async def list_confirmable(self, principal: ConsentPrincipal) -> list[UUID]:
        """Pending, presented, unexpired proposals of this principal (DB clock).

        The pre-Agent consent check uses this to resolve a bare «Sí»: exactly
        one result is required; zero or several never execute anything.
        """
        result = await self._session.execute(
            text("""
                SELECT id FROM ancora.action_proposals
                WHERE user_id = :uid AND bot_id = :bot_id AND chat_id = :chat_id
                  AND status = 'pending_confirmation'
                  AND presented_at IS NOT NULL
                  AND expires_at > now()
                ORDER BY presented_at, id
            """),
            {
                "uid": principal.user_id,
                "bot_id": principal.bot_id,
                "chat_id": principal.chat_id,
            },
        )
        return [row.id for row in result.fetchall()]

    async def list_created_in_interaction(
        self, interaction_id: UUID, *, user_id: str
    ) -> list[ProposalRecord]:
        """Pending proposals a governed run created; presented after its answer."""
        result = await self._session.execute(
            text("""
                SELECT id, tool_name, payload
                FROM ancora.action_proposals
                WHERE source_interaction_id = :interaction_id AND user_id = :uid
                  AND status = 'pending_confirmation' AND presented_at IS NULL
                ORDER BY created_at, id
            """),
            {"interaction_id": interaction_id, "uid": user_id},
        )
        return [
            {"id": row.id, "tool_name": row.tool_name, "payload": row.payload}
            for row in result.fetchall()
        ]

    async def resolve_voice_consent(
        self,
        *,
        principal: ConsentPrincipal,
        interaction_id: UUID,
        session_id: str,
        discard: bool,
        supported_tools: frozenset[str],
    ) -> tuple[ConsentClaimResult | None, str | None]:
        """Single-use vocal consent with original admission/presentation evidence.

        Lock the admitted interaction then eligible proposals. Compare presentation
        against admission time, not STT completion; constrain source generation.
        Re-read the durable payload/transcript rather than trusting a text argument.
        """
        current = (
            (
                await self._session.execute(
                    text("""
            SELECT i.status, i.bot_id, i.chat_id, i.telegram_user_id, i.update_type,
                   i.accepted_at, i.payload_ciphertext, i.payload_key_version,
                   v.status AS voice_status, v.transcript_ciphertext,
                   v.transcript_key_version, v.transcript_expires_at > now() AS transcript_current
            FROM ancora.telegram_interactions i
            JOIN ancora.voice_preparations v ON v.interaction_id = i.id
                AND v.user_id = i.telegram_user_id
            WHERE i.id = :interaction AND i.telegram_user_id = :user_id
            FOR UPDATE OF i
        """),
                    {"interaction": interaction_id, "user_id": int(principal.user_id)},
                )
            )
            .mappings()
            .first()
        )
        if (
            current is None
            or current["status"] != "accepted"
            or current["voice_status"] != "transcribed"
            or not current["transcript_current"]
            or current["update_type"] != "message"
            or current["bot_id"] != principal.bot_id
            or current["chat_id"] != principal.chat_id
        ):
            return None, "voice_evidence_invalid"
        if await self._interaction_already_used(interaction_id):
            return None, "voice_already_used"
        rows = (
            (
                await self._session.execute(
                    text("""
            SELECT p.id, p.tool_name FROM ancora.action_proposals p
            JOIN ancora.telegram_interactions source ON source.id = p.source_interaction_id
            WHERE p.user_id = :uid AND p.bot_id = :bot AND p.chat_id = :chat
              AND p.status = 'pending_confirmation' AND p.presented_at IS NOT NULL
              AND p.presented_at <= :accepted AND p.expires_at > now()
              AND source.agno_session_id = :generation
            ORDER BY p.id FOR UPDATE OF p
        """),
                    {
                        "uid": principal.user_id,
                        "bot": principal.bot_id,
                        "chat": principal.chat_id,
                        "accepted": current["accepted_at"],
                        "generation": session_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            return None, "voice_no_unique_proposal"
        if not discard and rows[0]["tool_name"] not in supported_tools:
            return None, "voice_executor_unavailable"
        result = await self.claim_confirmation(
            rows[0]["id"], principal=principal, confirming_interaction_id=interaction_id
        )
        if result.ok and discard:
            await self._session.execute(
                text("""
                UPDATE ancora.action_proposals SET status = 'discarded', completed_at = now(),
                    failure_reason = 'user_declined_voice'
                WHERE id = :id AND user_id = :uid AND status = 'confirmed'
                  AND confirming_interaction_id = :interaction
            """),
                {"id": rows[0]["id"], "uid": principal.user_id, "interaction": interaction_id},
            )
        return result, None

    async def claim_confirmation(
        self,
        proposal_id: UUID,
        *,
        principal: ConsentPrincipal,
        confirming_interaction_id: UUID,
    ) -> ConsentClaimResult:
        """Atomically consume consent for one proposal (single use).

        ``SELECT ... FOR UPDATE`` serialises concurrent claims on the same row;
        the losing claim re-reads ``confirmed`` and is rejected as
        ``NOT_PENDING``. The partial unique index on
        ``confirming_interaction_id`` stops one «Sí» authorising two proposals
        even across processes. Expiry is evaluated with the database clock.
        Nothing is committed here; a rejection leaves the row untouched
        (except an elapsed window, which is recorded as ``expired``).
        """
        if await self._interaction_already_used(confirming_interaction_id):
            return ConsentClaimResult(rejection=ConsentRejection.INTERACTION_ALREADY_USED)

        row = (
            await self._session.execute(
                text("""
                    SELECT id, user_id, tool_name, status, payload, payload_hash,
                           source_document_id, source_interaction_id, bot_id, chat_id,
                           presented_at, expires_at, expires_at <= now() AS is_expired
                    FROM ancora.action_proposals
                    WHERE id = :id AND user_id = :uid
                    FOR UPDATE
                """),
                {"id": proposal_id, "uid": principal.user_id},
            )
        ).fetchone()
        rejection = self._claim_rejection(row, principal)
        if rejection is not None:
            if rejection is ConsentRejection.EXPIRED and row is not None:
                await self._expire(row.id)
            return ConsentClaimResult(rejection=rejection)
        assert row is not None  # narrowed by _claim_rejection

        await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET status = 'confirmed', confirmed_at = now(),
                    confirming_interaction_id = :interaction_id
                WHERE id = :id AND status = 'pending_confirmation'
            """),
            {"id": row.id, "interaction_id": confirming_interaction_id},
        )
        return ConsentClaimResult(
            claimed=ClaimedProposal(
                id=row.id,
                tool_name=row.tool_name,
                payload=row.payload,
                source_document_id=row.source_document_id,
                confirming_interaction_id=confirming_interaction_id,
            )
        )

    @staticmethod
    def _claim_rejection(row: Any, principal: ConsentPrincipal) -> ConsentRejection | None:
        """Ordered checks; the first failing one is the reported reason."""
        if row is None:
            return ConsentRejection.NOT_FOUND
        if row.payload_hash is None or row.source_interaction_id is None:
            return ConsentRejection.LEGACY_PROPOSAL
        if row.bot_id != principal.bot_id or row.chat_id != principal.chat_id:
            return ConsentRejection.PRINCIPAL_MISMATCH
        if row.status != ProposalStatus.PENDING_CONFIRMATION:
            return ConsentRejection.NOT_PENDING
        if row.presented_at is None:
            return ConsentRejection.NOT_PRESENTED
        if row.is_expired:
            return ConsentRejection.EXPIRED
        if payload_hash(row.tool_name, row.payload) != row.payload_hash:
            return ConsentRejection.PAYLOAD_TAMPERED
        return None

    async def begin_execution(self, proposal_id: UUID, *, user_id: str) -> bool:
        """``confirmed -> executing``: durable marker before any side effect."""
        result = await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET status = 'executing', executing_at = now()
                WHERE id = :id AND user_id = :uid AND status = 'confirmed'
                RETURNING id
            """),
            {"id": proposal_id, "uid": user_id},
        )
        return result.fetchone() is not None

    async def complete_execution(
        self,
        proposal_id: UUID,
        *,
        user_id: str,
        status: ProposalStatus,
        failure_reason: str | None = None,
    ) -> bool:
        """``executing -> executed | failed_definitive | failed_ambiguous``.

        A terminal row never moves again: an uncertain outcome is never turned
        back into a pending or confirmed (re-executable) proposal.
        """
        if status not in _TERMINAL_EXECUTION_STATUSES:
            raise ValueError(f"Not a terminal execution status: {status}")
        if status is ProposalStatus.EXECUTED and failure_reason is not None:
            raise ValueError("An executed proposal carries no failure reason")
        result = await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET status = :status, completed_at = now(),
                    executed_at = CASE WHEN :succeeded THEN now() ELSE executed_at END,
                    failure_reason = :failure_reason
                WHERE id = :id AND user_id = :uid AND status = 'executing'
                RETURNING id
            """),
            {
                "id": proposal_id,
                "uid": user_id,
                "status": status.value,
                "succeeded": status is ProposalStatus.EXECUTED,
                "failure_reason": failure_reason,
            },
        )
        return result.fetchone() is not None

    async def discard_proposal(
        self, proposal_id: UUID, *, principal: ConsentPrincipal, reason: str = "user_declined"
    ) -> bool:
        """Discard one pending proposal (the «No» button — specs/023 T4.3)."""
        result = await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET status = 'discarded', completed_at = now(), failure_reason = :reason
                WHERE id = :id AND user_id = :uid AND bot_id = :bot_id AND chat_id = :chat_id
                  AND status = 'pending_confirmation'
                RETURNING id
            """),
            {
                "id": proposal_id,
                "uid": principal.user_id,
                "bot_id": principal.bot_id,
                "chat_id": principal.chat_id,
                "reason": reason,
            },
        )
        return result.fetchone() is not None

    async def discard_pending_for_chat(self, principal: ConsentPrincipal) -> int:
        """Invalidate every pending proposal of a chat (``/new`` — consent-design)."""
        result = await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET status = 'discarded', completed_at = now(),
                    failure_reason = 'conversation_reset'
                WHERE user_id = :uid AND bot_id = :bot_id AND chat_id = :chat_id
                  AND status = 'pending_confirmation'
                RETURNING id
            """),
            {
                "uid": principal.user_id,
                "bot_id": principal.bot_id,
                "chat_id": principal.chat_id,
            },
        )
        return len(result.fetchall())

    async def _interaction_already_used(self, interaction_id: UUID) -> bool:
        row = (
            await self._session.execute(
                text("""
                    SELECT 1 FROM ancora.action_proposals
                    WHERE confirming_interaction_id = :interaction_id
                """),
                {"interaction_id": interaction_id},
            )
        ).fetchone()
        return row is not None

    async def _expire(self, proposal_id: UUID) -> None:
        await self._session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET status = 'expired', completed_at = now(),
                    failure_reason = 'consent_window_elapsed'
                WHERE id = :id AND status = 'pending_confirmation'
            """),
            {"id": proposal_id},
        )
