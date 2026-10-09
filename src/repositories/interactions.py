"""Async PostgreSQL repository for the specs/013 Telegram interaction ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interactions.models import (
    InteractionStatus,
    LogicalResponse,
    TelegramAdmissionLimits,
    TelegramAdmissionResult,
    TelegramDeliveryCreate,
    TelegramInteraction,
    TelegramInteractionCreate,
    TelegramResponseDelivery,
)


class TelegramInteractionsRepository:
    """Persist durable interactions/deliveries with transactional idempotency."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def admit(
        self,
        interaction: TelegramInteractionCreate,
        delivery: TelegramDeliveryCreate,
    ) -> TelegramAdmissionResult:
        """Insert once by bot/update, record every delivery, and commit atomically."""
        now = datetime.now(tz=UTC)
        insert_interaction = text("""
            INSERT INTO ancora.telegram_interactions (
                bot_id, telegram_update_id, telegram_message_id, chat_id,
                telegram_user_id, update_type, status, payload_ciphertext,
                payload_key_version, payload_fingerprint, accepted_at, received_at, updated_at
            ) VALUES (
                :bot_id, :telegram_update_id, :telegram_message_id, :chat_id,
                :telegram_user_id, :update_type, :status, :payload_ciphertext,
                :payload_key_version, :payload_fingerprint,
                :accepted_at, :now, :now
            )
            ON CONFLICT (bot_id, telegram_update_id) DO NOTHING
            RETURNING id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                telegram_user_id, update_type, status, payload_ciphertext,
                payload_key_version, payload_fingerprint, received_at, accepted_at,
                agent_started_at, completed_at, updated_at
        """)
        params = {
            "bot_id": interaction.bot_id,
            "telegram_update_id": interaction.telegram_update_id,
            "telegram_message_id": interaction.telegram_message_id,
            "chat_id": interaction.chat_id,
            "telegram_user_id": interaction.telegram_user_id,
            "update_type": interaction.update_type,
            "status": interaction.status.value,
            "payload_ciphertext": interaction.payload_ciphertext,
            "payload_key_version": interaction.payload_key_version,
            "payload_fingerprint": interaction.payload_fingerprint,
            "accepted_at": now if interaction.status is InteractionStatus.ACCEPTED else None,
            "now": now,
        }
        try:
            result = await self._session.execute(insert_interaction, params)
            row = result.fetchone()
            duplicate = row is None
            if row is None:
                existing = await self._session.execute(
                    text("""
                        SELECT id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                            telegram_user_id, update_type, status, payload_ciphertext,
                            payload_key_version, payload_fingerprint, received_at, accepted_at,
                            agent_started_at, completed_at, updated_at
                        FROM ancora.telegram_interactions
                        WHERE bot_id = :bot_id AND telegram_update_id = :telegram_update_id
                    """),
                    {
                        "bot_id": interaction.bot_id,
                        "telegram_update_id": interaction.telegram_update_id,
                    },
                )
                row = existing.fetchone()
                if row is None:  # pragma: no cover - PostgreSQL conflict guarantees visibility
                    raise RuntimeError("Interaction disappeared after idempotency conflict")

            parsed = self._interaction_from_row(row)
            await self._session.execute(
                text("""
                    INSERT INTO ancora.telegram_deliveries (
                        interaction_id, railway_request_id, duplicate, http_status,
                        delivery_status, received_at
                    ) VALUES (
                        :interaction_id, :railway_request_id, :duplicate, :http_status,
                        :delivery_status, :received_at
                    )
                """),
                {
                    "interaction_id": parsed.id,
                    "railway_request_id": delivery.railway_request_id,
                    "duplicate": duplicate,
                    "http_status": delivery.http_status,
                    "delivery_status": delivery.delivery_status,
                    "received_at": now,
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return TelegramAdmissionResult(interaction=parsed, duplicate=duplicate)

    async def admit_with_limits(
        self,
        interaction: TelegramInteractionCreate,
        delivery: TelegramDeliveryCreate,
        limits: TelegramAdmissionLimits,
        *,
        deterministic_reply_ciphertext: bytes | None = None,
        deterministic_reply_key_version: int | None = None,
        deterministic_reply_length: int | None = None,
        deterministic_reply_chunk_count: int | None = None,
    ) -> TelegramAdmissionResult:
        """Atomically deduplicate, apply durable admission limits, and audit delivery.

        A transaction-scoped advisory lock deliberately serializes admission in the
        initial single-replica rollout. It keeps duplicate detection, rate checks,
        queue checks, interaction creation and delivery audit in one commit.
        """
        now = datetime.now(tz=UTC)
        try:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": 813_013_004},
            )
            existing_result = await self._session.execute(
                text("""
                    SELECT id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                        telegram_user_id, update_type, status, payload_ciphertext,
                        payload_key_version, payload_fingerprint, error_class,
                        error_detail_code, received_at, accepted_at, agent_started_at,
                        completed_at, updated_at
                    FROM ancora.telegram_interactions
                    WHERE bot_id = :bot_id AND telegram_update_id = :telegram_update_id
                """),
                {
                    "bot_id": interaction.bot_id,
                    "telegram_update_id": interaction.telegram_update_id,
                },
            )
            existing = existing_result.fetchone()
            if existing is not None:
                parsed = self._interaction_from_row(existing)
                await self._record_delivery(
                    interaction_id=parsed.id,
                    delivery=delivery,
                    duplicate=True,
                    delivery_status="duplicate",
                    received_at=now,
                )
                await self._session.commit()
                return TelegramAdmissionResult(interaction=parsed, duplicate=True)

            effective = interaction
            if interaction.status is InteractionStatus.ACCEPTED:
                rejection = await self._limit_rejection(interaction, limits, now)
                if rejection is not None:
                    effective = interaction.model_copy(
                        update={
                            "status": InteractionStatus.REJECTED,
                            "payload_ciphertext": None,
                            "payload_key_version": None,
                            "error_class": "admission_rejected",
                            "error_detail_code": rejection,
                        }
                    )

            has_deterministic_reply = all(
                value is not None
                for value in (
                    deterministic_reply_ciphertext,
                    deterministic_reply_key_version,
                    deterministic_reply_length,
                    deterministic_reply_chunk_count,
                )
            )
            if has_deterministic_reply and effective.status is InteractionStatus.ACCEPTED:
                effective = effective.model_copy(
                    update={"status": InteractionStatus.RESPONSE_READY}
                )
            parsed = await self._insert_interaction(effective, now)
            await self._record_delivery(
                interaction_id=parsed.id,
                delivery=delivery,
                duplicate=False,
                delivery_status=parsed.status.value,
                received_at=now,
            )
            if has_deterministic_reply and parsed.status is InteractionStatus.RESPONSE_READY:
                assert deterministic_reply_ciphertext is not None
                assert deterministic_reply_key_version is not None
                assert deterministic_reply_length is not None
                assert deterministic_reply_chunk_count is not None
                await self._create_pending_response(
                    interaction_id=parsed.id,
                    content_ciphertext=deterministic_reply_ciphertext,
                    content_key_version=deterministic_reply_key_version,
                    content_length=deterministic_reply_length,
                    chunk_count=deterministic_reply_chunk_count,
                    now=now,
                )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return TelegramAdmissionResult(interaction=parsed, duplicate=False)

    async def _limit_rejection(
        self,
        interaction: TelegramInteractionCreate,
        limits: TelegramAdmissionLimits,
        now: datetime,
    ) -> str | None:
        """Evaluate rate and queue limits for a new, already-authorized update."""
        if interaction.telegram_user_id is None or interaction.chat_id is None:
            return "missing_admission_identity"
        counts = (
            await self._session.execute(
                text("""
                    SELECT
                        count(*) FILTER (
                            WHERE telegram_user_id = :telegram_user_id
                              AND accepted_at >= :burst_since
                              AND status NOT IN ('rejected', 'ignored')
                        ) AS user_burst,
                        count(*) FILTER (
                            WHERE telegram_user_id = :telegram_user_id
                              AND accepted_at >= :minute_since
                              AND status NOT IN ('rejected', 'ignored')
                        ) AS user_minute,
                        count(*) FILTER (
                            WHERE telegram_user_id = :telegram_user_id
                              AND accepted_at >= :hour_since
                              AND status NOT IN ('rejected', 'ignored')
                        ) AS user_hour,
                        count(*) FILTER (WHERE status = 'accepted') AS pending_global,
                        count(*) FILTER (
                            WHERE chat_id = :chat_id AND status = 'accepted'
                        ) AS queued_per_chat
                    FROM ancora.telegram_interactions
                """),
                {
                    "telegram_user_id": interaction.telegram_user_id,
                    "chat_id": interaction.chat_id,
                    "burst_since": now - timedelta(seconds=limits.burst_window_seconds),
                    "minute_since": now - timedelta(minutes=1),
                    "hour_since": now - timedelta(hours=1),
                },
            )
        ).one()
        if counts.user_burst >= limits.user_burst:
            return "user_burst_exceeded"
        if counts.user_minute >= limits.user_requests_per_minute:
            return "user_minute_limit_exceeded"
        if counts.user_hour >= limits.user_requests_per_hour:
            return "user_hour_limit_exceeded"
        if counts.pending_global >= limits.pending_global:
            return "pending_global_capacity_exceeded"
        if counts.queued_per_chat >= limits.queued_per_chat:
            return "queued_per_chat_capacity_exceeded"
        return None

    async def _insert_interaction(
        self,
        interaction: TelegramInteractionCreate,
        now: datetime,
    ) -> TelegramInteraction:
        """Insert a unique interaction while the admission advisory lock is held."""
        result = await self._session.execute(
            text("""
                INSERT INTO ancora.telegram_interactions (
                    bot_id, telegram_update_id, telegram_message_id, chat_id,
                    telegram_user_id, update_type, status, payload_ciphertext,
                    payload_key_version, payload_fingerprint, error_class,
                    error_detail_code, accepted_at, received_at, updated_at
                ) VALUES (
                    :bot_id, :telegram_update_id, :telegram_message_id, :chat_id,
                    :telegram_user_id, :update_type, :status, :payload_ciphertext,
                    :payload_key_version, :payload_fingerprint, :error_class,
                    :error_detail_code, :accepted_at, :now, :now
                )
                RETURNING id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                    telegram_user_id, update_type, status, payload_ciphertext,
                    payload_key_version, payload_fingerprint, error_class,
                    error_detail_code, received_at, accepted_at, agent_started_at,
                    completed_at, updated_at
            """),
            {
                "bot_id": interaction.bot_id,
                "telegram_update_id": interaction.telegram_update_id,
                "telegram_message_id": interaction.telegram_message_id,
                "chat_id": interaction.chat_id,
                "telegram_user_id": interaction.telegram_user_id,
                "update_type": interaction.update_type,
                "status": interaction.status.value,
                "payload_ciphertext": interaction.payload_ciphertext,
                "payload_key_version": interaction.payload_key_version,
                "payload_fingerprint": interaction.payload_fingerprint,
                "error_class": interaction.error_class,
                "error_detail_code": interaction.error_detail_code,
                "accepted_at": (
                    now
                    if interaction.status
                    in {InteractionStatus.ACCEPTED, InteractionStatus.RESPONSE_READY}
                    else None
                ),
                "now": now,
            },
        )
        row = result.fetchone()
        if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
            raise RuntimeError("Interaction insert did not return a row")
        return self._interaction_from_row(row)

    async def _create_pending_response(
        self,
        *,
        interaction_id: UUID,
        content_ciphertext: bytes,
        content_key_version: int,
        content_length: int,
        chunk_count: int,
        now: datetime,
    ) -> LogicalResponse:
        """Create deterministic outbox data inside the caller's open transaction."""
        created = await self._session.execute(
            text("""
                INSERT INTO ancora.logical_responses (
                    interaction_id, response_kind, content_ciphertext,
                    content_key_version, content_length, chunk_count, status, created_at
                ) VALUES (
                    :interaction_id, 'agent_final', :content_ciphertext,
                    :content_key_version, :content_length, :chunk_count,
                    'pending_delivery', :now
                )
                RETURNING id, interaction_id, response_kind, content_ciphertext,
                    content_key_version, content_length, chunk_count, status, created_at
            """),
            {
                "interaction_id": interaction_id,
                "content_ciphertext": content_ciphertext,
                "content_key_version": content_key_version,
                "content_length": content_length,
                "chunk_count": chunk_count,
                "now": now,
            },
        )
        row = created.fetchone()
        if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
            raise RuntimeError("Logical response insert did not return a row")
        response = self._response_from_row(row)
        await self._session.execute(
            text("""
                INSERT INTO ancora.telegram_response_deliveries (
                    logical_response_id, chunk_index, status
                )
                SELECT :logical_response_id, generate_series(0, :chunk_count - 1), 'pending'
            """),
            {"logical_response_id": response.id, "chunk_count": chunk_count},
        )
        return response

    async def _record_delivery(
        self,
        *,
        interaction_id: UUID,
        delivery: TelegramDeliveryCreate,
        duplicate: bool,
        delivery_status: str,
        received_at: datetime,
    ) -> None:
        """Persist one delivery as part of the caller's current transaction."""
        await self._session.execute(
            text("""
                INSERT INTO ancora.telegram_deliveries (
                    interaction_id, railway_request_id, duplicate, http_status,
                    delivery_status, received_at
                ) VALUES (
                    :interaction_id, :railway_request_id, :duplicate, :http_status,
                    :delivery_status, :received_at
                )
            """),
            {
                "interaction_id": interaction_id,
                "railway_request_id": delivery.railway_request_id,
                "duplicate": duplicate,
                "http_status": delivery.http_status,
                "delivery_status": delivery_status,
                "received_at": received_at,
            },
        )

    async def claim_agent_start(self, interaction_id: UUID) -> TelegramInteraction | None:
        """Atomically transition a recoverable accepted interaction to agent_started."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'agent_started',
                        agno_run_id = COALESCE(:agno_run_id, agno_run_id),
                        agent_started_at = :now,
                        updated_at = :now
                    WHERE id = :id AND status = 'accepted'
                    RETURNING id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                        telegram_user_id, update_type, status, payload_ciphertext,
                        payload_key_version, payload_fingerprint, agno_session_id,
                        agno_run_id, error_class, error_detail_code, received_at,
                        accepted_at, agent_started_at, response_ready_at,
                        delivery_started_at, completed_at, updated_at
                """),
                {"id": interaction_id, "agno_run_id": None, "now": now},
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._interaction_from_row(row) if row is not None else None

    async def claim_agent_start_with_run_id(
        self,
        interaction_id: UUID,
        agno_run_id: str,
        agno_session_id: str,
    ) -> TelegramInteraction | None:
        """Claim accepted work exactly once and bind the future Agent run identity."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'agent_started', agno_run_id = :agno_run_id,
                        agno_session_id = :agno_session_id,
                        agent_started_at = :now, updated_at = :now
                    WHERE id = :id AND status = 'accepted'
                    RETURNING id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                        telegram_user_id, update_type, status, payload_ciphertext,
                        payload_key_version, payload_fingerprint, agno_session_id,
                        agno_run_id, error_class, error_detail_code, received_at,
                        accepted_at, agent_started_at, response_ready_at,
                        delivery_started_at, completed_at, updated_at
                """),
                {
                    "id": interaction_id,
                    "agno_run_id": agno_run_id,
                    "agno_session_id": agno_session_id,
                    "now": now,
                },
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._interaction_from_row(row) if row is not None else None

    async def current_session_id(self, chat_id: int) -> str | None:
        """Return the conversation session the chat is currently using, if any.

        The ledger is the source of truth for conversation generations: every
        Agent run stores the session it used and ``/new`` stores the generation
        it opened, so a restart can never resurrect an abandoned history (BL-28).
        """
        result = await self._session.execute(
            text("""
                SELECT agno_session_id
                FROM ancora.telegram_interactions
                WHERE chat_id = :chat_id AND agno_session_id IS NOT NULL
                ORDER BY received_at DESC, telegram_update_id DESC
                LIMIT 1
            """),
            {"chat_id": chat_id},
        )
        row = result.fetchone()
        return row.agno_session_id if row is not None else None

    async def list_recoverable_work(self, limit: int = 20) -> list[TelegramInteraction]:
        """List accepted/response-ready work in deterministic chat/update order."""
        result = await self._session.execute(
            text("""
                SELECT id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                    telegram_user_id, update_type, status, payload_ciphertext,
                    payload_key_version, payload_fingerprint, agno_session_id,
                    agno_run_id, error_class, error_detail_code, received_at,
                    accepted_at, agent_started_at, response_ready_at,
                    delivery_started_at, completed_at, updated_at
                FROM ancora.telegram_interactions
                WHERE status IN ('accepted', 'response_ready')
                ORDER BY chat_id NULLS LAST, received_at, telegram_update_id
                LIMIT :limit
            """),
            {"limit": limit},
        )
        return [self._interaction_from_row(row) for row in result.fetchall()]

    async def mark_inflight_as_ambiguous(self) -> int:
        """Close unrecoverable post-side-effect states after a processor restart."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'failed_ambiguous',
                        error_class = 'ProcessorRecovery',
                        error_detail_code = CASE
                            WHEN status = 'agent_started' THEN 'restart_after_agent_started'
                            ELSE 'restart_during_delivery'
                        END,
                        completed_at = :now,
                        updated_at = :now
                    WHERE status IN ('agent_started', 'delivery_started')
                    RETURNING id
                """),
                {"now": now},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return len(result.fetchall())

    async def persist_response_ready(
        self,
        interaction_id: UUID,
        *,
        content_ciphertext: bytes,
        content_key_version: int,
        content_length: int,
        chunk_count: int,
    ) -> LogicalResponse | None:
        """Persist final output and delivery chunks before any Telegram side effect."""
        now = datetime.now(tz=UTC)
        try:
            transitioned = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'response_ready', response_ready_at = :now, updated_at = :now
                    WHERE id = :id AND status = 'agent_started'
                    RETURNING id
                """),
                {"id": interaction_id, "now": now},
            )
            if transitioned.fetchone() is None:
                await self._session.rollback()
                return None

            created = await self._session.execute(
                text("""
                    INSERT INTO ancora.logical_responses (
                        interaction_id, response_kind, content_ciphertext,
                        content_key_version, content_length, chunk_count, status, created_at
                    ) VALUES (
                        :interaction_id, 'agent_final', :content_ciphertext,
                        :content_key_version, :content_length, :chunk_count,
                        'pending_delivery', :now
                    )
                    RETURNING id, interaction_id, response_kind, content_ciphertext,
                        content_key_version, content_length, chunk_count, status, created_at
                """),
                {
                    "interaction_id": interaction_id,
                    "content_ciphertext": content_ciphertext,
                    "content_key_version": content_key_version,
                    "content_length": content_length,
                    "chunk_count": chunk_count,
                    "now": now,
                },
            )
            row = created.fetchone()
            if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
                raise RuntimeError("Logical response insert did not return a row")
            response = self._response_from_row(row)
            await self._session.execute(
                text("""
                    INSERT INTO ancora.telegram_response_deliveries (
                        logical_response_id, chunk_index, status
                    )
                    SELECT :logical_response_id, generate_series(0, :chunk_count - 1), 'pending'
                """),
                {"logical_response_id": response.id, "chunk_count": chunk_count},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return response

    async def create_ack_response(
        self,
        interaction_id: UUID,
        *,
        content_ciphertext: bytes,
        content_key_version: int,
        content_length: int,
    ) -> UUID | None:
        """Persist a best-effort early acknowledgement (BL-32), outside the
        main response's state machine.

        Deliberately never reads or writes ``telegram_interactions.status`` —
        it must coexist with ``agent_started`` while the real run is still in
        flight. ``ON CONFLICT (interaction_id, response_kind) DO NOTHING``
        makes a reprocessed update a no-op: this returns ``None`` (never
        resend) rather than a second ack ever being created. Returns the new
        delivery row's id on success.
        """
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    WITH inserted AS (
                        INSERT INTO ancora.logical_responses (
                            interaction_id, response_kind, content_ciphertext,
                            content_key_version, content_length, chunk_count,
                            status, created_at
                        ) VALUES (
                            :interaction_id, 'ack', :content_ciphertext,
                            :content_key_version, :content_length, 1,
                            'pending_delivery', :now
                        )
                        ON CONFLICT (interaction_id, response_kind) DO NOTHING
                        RETURNING id
                    )
                    INSERT INTO ancora.telegram_response_deliveries (
                        logical_response_id, chunk_index, status
                    )
                    SELECT id, 0, 'pending' FROM inserted
                    RETURNING id
                """),
                {
                    "interaction_id": interaction_id,
                    "content_ciphertext": content_ciphertext,
                    "content_key_version": content_key_version,
                    "content_length": content_length,
                    "now": now,
                },
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return row[0] if row is not None else None

    async def mark_ack_delivery_outcome(
        self,
        delivery_id: UUID,
        *,
        status: str,
        telegram_message_id: int | None = None,
        error_class: str | None = None,
    ) -> None:
        """Record the ack send outcome. Never touches ``telegram_interactions``."""
        now = datetime.now(tz=UTC)
        try:
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_response_deliveries
                    SET status = :status, telegram_message_id = :telegram_message_id,
                        error_class = :error_class,
                        started_at = COALESCE(started_at, :now), completed_at = :now
                    WHERE id = :id
                """),
                {
                    "id": delivery_id,
                    "status": status,
                    "telegram_message_id": telegram_message_id,
                    "error_class": error_class,
                    "now": now,
                },
            )
            await self._session.execute(
                text("""
                    UPDATE ancora.logical_responses lr
                    SET status = :status
                    FROM ancora.telegram_response_deliveries trd
                    WHERE trd.id = :id AND lr.id = trd.logical_response_id
                """),
                {"id": delivery_id, "status": status},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def claim_command_reply(
        self,
        interaction_id: UUID,
        *,
        agno_session_id: str | None,
        content_ciphertext: bytes,
        content_key_version: int,
        content_length: int,
        chunk_count: int,
        voice_failure_notice: bool = False,
    ) -> LogicalResponse | None:
        """Persist a deterministic command reply before any Telegram side effect.

        The transition is gated on ``accepted`` (or an explicitly requested
        pre-Agent ambiguous voice failure notice), so a replayed update can never
        be answered twice. Nothing external happens before the commit: unlike an
        Agent run, a crash here leaves plain accepted work that the next cycle
        re-derives deterministically, never an ambiguous effect.
        """
        now = datetime.now(tz=UTC)
        try:
            transitioned = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'response_ready',
                        agno_session_id = COALESCE(:agno_session_id, agno_session_id),
                        response_ready_at = :now,
                        updated_at = :now
                    WHERE id = :id AND NOT EXISTS (
                        SELECT 1 FROM ancora.logical_responses WHERE interaction_id = :id
                    ) AND (
                        status = 'accepted' OR (
                            :voice_failure_notice AND status = 'failed_ambiguous'
                            AND error_class IN ('VoicePreparationError', 'VoicePreparationRecovery')
                            AND agent_started_at IS NULL
                        )
                    )
                    RETURNING id
                """),
                {
                    "id": interaction_id,
                    "agno_session_id": agno_session_id,
                    "voice_failure_notice": voice_failure_notice,
                    "now": now,
                },
            )
            if transitioned.fetchone() is None:
                await self._session.rollback()
                return None

            created = await self._session.execute(
                text("""
                    INSERT INTO ancora.logical_responses (
                        interaction_id, response_kind, content_ciphertext,
                        content_key_version, content_length, chunk_count, status, created_at
                    ) VALUES (
                        :interaction_id, 'agent_final', :content_ciphertext,
                        :content_key_version, :content_length, :chunk_count,
                        'pending_delivery', :now
                    )
                    RETURNING id, interaction_id, response_kind, content_ciphertext,
                        content_key_version, content_length, chunk_count, status, created_at
                """),
                {
                    "interaction_id": interaction_id,
                    "content_ciphertext": content_ciphertext,
                    "content_key_version": content_key_version,
                    "content_length": content_length,
                    "chunk_count": chunk_count,
                    "now": now,
                },
            )
            row = created.fetchone()
            if row is None:  # pragma: no cover - INSERT RETURNING always returns one row
                raise RuntimeError("Logical response insert did not return a row")
            response = self._response_from_row(row)
            await self._session.execute(
                text("""
                    INSERT INTO ancora.telegram_response_deliveries (
                        logical_response_id, chunk_index, status
                    )
                    SELECT :logical_response_id, generate_series(0, :chunk_count - 1), 'pending'
                """),
                {"logical_response_id": response.id, "chunk_count": chunk_count},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return response

    async def list_voice_failure_notices(self, limit: int = 20) -> list[TelegramInteraction]:
        """Only notification recovery, never resurrect STT or an Agent run."""
        rows = (
            await self._session.execute(
                text("""
            SELECT i.* FROM ancora.telegram_interactions i
            WHERE i.status = 'failed_ambiguous' AND i.agent_started_at IS NULL
              AND i.error_class IN ('VoicePreparationError', 'VoicePreparationRecovery')
              AND NOT EXISTS (SELECT 1 FROM ancora.logical_responses r
                              WHERE r.interaction_id = i.id)
            ORDER BY i.received_at LIMIT :limit
        """),
                {"limit": limit},
            )
        ).fetchall()
        return [self._interaction_from_row(row) for row in rows]

    async def claim_delivery_start(self, interaction_id: UUID) -> LogicalResponse | None:
        """Claim a response-ready outbox once before external Telegram delivery."""
        now = datetime.now(tz=UTC)
        try:
            transitioned = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'delivery_started', delivery_started_at = :now, updated_at = :now
                    WHERE id = :id AND status = 'response_ready'
                    RETURNING id
                """),
                {"id": interaction_id, "now": now},
            )
            if transitioned.fetchone() is None:
                await self._session.rollback()
                return None
            response_result = await self._session.execute(
                text("""
                    SELECT id, interaction_id, response_kind, content_ciphertext,
                        content_key_version, content_length, chunk_count, status, created_at
                    FROM ancora.logical_responses
                    WHERE interaction_id = :interaction_id AND response_kind = 'agent_final'
                """),
                {"interaction_id": interaction_id},
            )
            row = response_result.fetchone()
            if row is None:
                raise RuntimeError("response_ready interaction has no logical response")
            await self._session.execute(
                text("""
                    UPDATE ancora.logical_responses
                    SET status = 'delivery_started'
                    WHERE id = :id AND status = 'pending_delivery'
                """),
                {"id": row.id},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._response_from_row(row)

    async def list_response_deliveries(
        self,
        logical_response_id: UUID,
    ) -> list[TelegramResponseDelivery]:
        """Return persisted chunk delivery state ordered by chunk index."""
        result = await self._session.execute(
            text("""
                SELECT id, logical_response_id, chunk_index, status, telegram_message_id,
                    started_at, completed_at, error_class
                FROM ancora.telegram_response_deliveries
                WHERE logical_response_id = :logical_response_id
                ORDER BY chunk_index
            """),
            {"logical_response_id": logical_response_id},
        )
        return [self._delivery_from_row(row) for row in result.fetchall()]

    async def claim_response_chunk(
        self,
        logical_response_id: UUID,
        chunk_index: int,
    ) -> TelegramResponseDelivery | None:
        """Persist ``sending`` before issuing the non-idempotent sendMessage call."""
        now = datetime.now(tz=UTC)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_response_deliveries
                    SET status = 'sending', started_at = :now
                    WHERE logical_response_id = :logical_response_id
                      AND chunk_index = :chunk_index
                      AND status = 'pending'
                    RETURNING id, logical_response_id, chunk_index, status,
                        telegram_message_id, started_at, completed_at, error_class
                """),
                {
                    "logical_response_id": logical_response_id,
                    "chunk_index": chunk_index,
                    "now": now,
                },
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._delivery_from_row(row) if row is not None else None

    async def mark_response_chunk_delivered(
        self,
        delivery_id: UUID,
        telegram_message_id: int,
    ) -> None:
        """Record the confirmed Telegram response chunk delivery."""
        now = datetime.now(tz=UTC)
        try:
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_response_deliveries
                    SET status = 'completed', telegram_message_id = :telegram_message_id,
                        completed_at = :now
                    WHERE id = :id AND status = 'sending'
                """),
                {"id": delivery_id, "telegram_message_id": telegram_message_id, "now": now},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def finalize_response_delivery(
        self,
        interaction_id: UUID,
        logical_response_id: UUID,
    ) -> bool:
        """Complete the interaction only after every deterministic chunk is confirmed."""
        now = datetime.now(tz=UTC)
        try:
            pending = await self._session.execute(
                text("""
                    SELECT count(*)
                    FROM ancora.telegram_response_deliveries
                    WHERE logical_response_id = :logical_response_id
                      AND status <> 'completed'
                """),
                {"logical_response_id": logical_response_id},
            )
            if int(pending.scalar_one()) != 0:
                await self._session.rollback()
                return False
            await self._session.execute(
                text("""
                    UPDATE ancora.logical_responses
                    SET status = 'completed'
                    WHERE id = :id AND status = 'delivery_started'
                """),
                {"id": logical_response_id},
            )
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = 'completed', completed_at = :now,
                        payload_ciphertext = NULL, payload_key_version = NULL, updated_at = :now
                    WHERE id = :id AND status = 'delivery_started'
                """),
                {"id": interaction_id, "now": now},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return True

    async def fail_response_delivery(
        self,
        interaction_id: UUID,
        logical_response_id: UUID,
        delivery_id: UUID,
        *,
        status: InteractionStatus,
        error_class: str,
    ) -> None:
        """Record a definitive/ambiguous outbound failure without automatic resend."""
        if status not in {
            InteractionStatus.FAILED_DEFINITIVE,
            InteractionStatus.FAILED_AMBIGUOUS,
        }:
            raise ValueError("Response delivery failure must be definitive or ambiguous")
        now = datetime.now(tz=UTC)
        try:
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_response_deliveries
                    SET status = 'failed', error_class = :error_class, completed_at = :now
                    WHERE id = :id AND status = 'sending'
                """),
                {"id": delivery_id, "error_class": error_class, "now": now},
            )
            await self._session.execute(
                text("""
                    UPDATE ancora.logical_responses
                    SET status = 'failed'
                    WHERE id = :id
                """),
                {"id": logical_response_id},
            )
            await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = :status, error_class = :error_class,
                        error_detail_code = 'telegram_delivery_failure',
                        completed_at = :now,
                        payload_ciphertext = CASE WHEN :clear_payload THEN NULL
                            ELSE payload_ciphertext END,
                        payload_key_version = CASE WHEN :clear_payload THEN NULL
                            ELSE payload_key_version END,
                        updated_at = :now
                    WHERE id = :id AND status = 'delivery_started'
                """),
                {
                    "id": interaction_id,
                    "status": status.value,
                    "error_class": error_class,
                    "clear_payload": status is InteractionStatus.FAILED_DEFINITIVE,
                    "now": now,
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def update_status(
        self,
        interaction_id: UUID,
        status: InteractionStatus,
        *,
        error_class: str | None = None,
        error_detail_code: str | None = None,
    ) -> TelegramInteraction | None:
        """Transition an interaction status and clear payload at terminal states when requested."""
        now = datetime.now(tz=UTC)
        clear_payload = status in {
            InteractionStatus.IGNORED,
            InteractionStatus.REJECTED,
            InteractionStatus.COMPLETED,
            InteractionStatus.FAILED_CONTROLLED,
            InteractionStatus.FAILED_DEFINITIVE,
        }
        terminal = status in {
            InteractionStatus.IGNORED,
            InteractionStatus.REJECTED,
            InteractionStatus.COMPLETED,
            InteractionStatus.FAILED_CONTROLLED,
            InteractionStatus.FAILED_DEFINITIVE,
            InteractionStatus.FAILED_AMBIGUOUS,
        }
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET status = :status,
                        error_class = :error_class,
                        error_detail_code = :error_detail_code,
                        completed_at = CASE WHEN :terminal THEN :now ELSE completed_at END,
                        payload_ciphertext = CASE WHEN :clear_payload THEN NULL
                            ELSE payload_ciphertext END,
                        payload_key_version = CASE WHEN :clear_payload THEN NULL
                            ELSE payload_key_version END,
                        updated_at = :now
                    WHERE id = :id
                    RETURNING id, bot_id, telegram_update_id, telegram_message_id, chat_id,
                        telegram_user_id, update_type, status, payload_ciphertext,
                        payload_key_version, payload_fingerprint, received_at, accepted_at,
                        agent_started_at, completed_at, updated_at
                """),
                {
                    "id": interaction_id,
                    "status": status.value,
                    "error_class": error_class,
                    "error_detail_code": error_detail_code,
                    "terminal": terminal,
                    "clear_payload": clear_payload,
                    "now": now,
                },
            )
            row = result.fetchone()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return self._interaction_from_row(row) if row is not None else None

    async def purge_expired_payloads(self, now: datetime | None = None) -> int:
        """Delete recoverable payloads retained for failed_ambiguous investigation.

        Other terminal states clear their payload synchronously in ``update_status``.
        This query is intentionally safe to run repeatedly from a future lifecycle
        worker; it does not delete interaction metadata needed for auditability.
        """
        current = now or datetime.now(tz=UTC)
        expiry = current - timedelta(days=7)
        try:
            result = await self._session.execute(
                text("""
                    UPDATE ancora.telegram_interactions
                    SET payload_ciphertext = NULL,
                        payload_key_version = NULL,
                        updated_at = :now
                    WHERE status = 'failed_ambiguous'
                      AND completed_at <= :expiry
                      AND payload_ciphertext IS NOT NULL
                    RETURNING id
                """),
                {"now": current, "expiry": expiry},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return len(result.fetchall())

    @staticmethod
    def _interaction_from_row(row: object) -> TelegramInteraction:
        return TelegramInteraction.model_validate(row, from_attributes=True)

    @staticmethod
    def _response_from_row(row: object) -> LogicalResponse:
        return LogicalResponse.model_validate(row, from_attributes=True)

    @staticmethod
    def _delivery_from_row(row: object) -> TelegramResponseDelivery:
        return TelegramResponseDelivery.model_validate(row, from_attributes=True)
