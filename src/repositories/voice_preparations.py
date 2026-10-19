"""Exclusive preparation with parent-row serialization and no implicit replay."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.speech.models import SpeechToTextResult, ValidatedVoiceAudio
from src.domain.speech.policy import SpeechCostEstimate
from src.domain.speech.preparation import SpeechTranscriptCipher, VoicePreparation


class VoicePreparationsRepository:
    """All writes commit atomically; scoped by admitted Telegram user identity."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _lock_key(interaction_id: UUID) -> int:
        # Signed 64-bit advisory key; collisions only serialize unrelated work.
        value = interaction_id.int & ((1 << 64) - 1)
        return value - (1 << 64) if value >= (1 << 63) else value

    async def try_preparation_lock(self, interaction_id: UUID) -> bool:
        """Transaction-scoped lock on a DEDICATED session, never committed by writes.

        The caller holds this transaction throughout preparation. Another process
        can recover the owner only after PostgreSQL releases its dead connection.
        """
        result = await self._session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": self._lock_key(interaction_id)},
        )
        return bool(result.scalar_one())

    async def maintenance_scopes(self) -> list[tuple[UUID, int, UUID]]:
        """Metadata discovery only; all subsequent recovery/purge writes are scoped."""
        result = await self._session.execute(
            text("""
            SELECT interaction_id, user_id, owner_token FROM ancora.voice_preparations
            WHERE status IN ('preparing', 'downloaded', 'transcribing', 'transcribed')
               OR transcript_ciphertext IS NOT NULL
        """)
        )
        return [(row[0], row[1], row[2]) for row in result.fetchall()]

    async def _write(self, query: str, params: dict[str, object]) -> VoicePreparation | None:
        try:
            # All preparation writes use the same parent-first lock order as
            # Agent/terminal transitions. Avoid persisting after parent cleanup.
            parent = await self._session.execute(
                text("""
                SELECT id FROM ancora.telegram_interactions
                WHERE id = :id AND telegram_user_id = :user_id AND status = 'accepted'
                FOR UPDATE
            """),
                {"id": params["id"], "user_id": params["user_id"]},
            )
            if parent.first() is None:
                await self._session.commit()
                return None
            result = await self._session.execute(text(query), params)
            row = result.mappings().first()
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return VoicePreparation.model_validate(row) if row is not None else None

    async def claim(
        self, interaction_id: UUID, user_id: int, owner_token: UUID, config_revision: int
    ) -> VoicePreparation | None:
        """Claim once; lock the parent so an Agent cannot win simultaneously.

        Only T4's trusted voice dispatcher may invoke this method. A database
        claim is not a substitute for checking original voice provenance.
        """
        if config_revision < 0:
            raise ValueError("config revision must be non-negative")
        return await self._write(
            """
            WITH parent AS (
                SELECT id, telegram_user_id FROM ancora.telegram_interactions
                WHERE id = :id AND telegram_user_id = :user_id
                  AND status = 'accepted' AND payload_ciphertext IS NOT NULL
                FOR UPDATE
            )
            INSERT INTO ancora.voice_preparations
                (interaction_id, user_id, owner_token, config_revision, status)
            SELECT id, telegram_user_id, :owner, :revision, 'preparing' FROM parent
            ON CONFLICT (interaction_id) DO NOTHING RETURNING *
        """,
            {
                "id": interaction_id,
                "user_id": user_id,
                "owner": owner_token,
                "revision": config_revision,
            },
        )

    async def mark_downloaded(
        self, interaction_id: UUID, user_id: int, owner_token: UUID
    ) -> VoicePreparation | None:
        return await self._write(
            """
            UPDATE ancora.voice_preparations SET status = 'downloaded', updated_at = now()
            WHERE interaction_id = :id AND user_id = :user_id AND owner_token = :owner
              AND status = 'preparing' RETURNING *
        """,
            {"id": interaction_id, "user_id": user_id, "owner": owner_token},
        )

    async def start_transcription(
        self,
        interaction_id: UUID,
        user_id: int,
        owner_token: UUID,
        *,
        call_id: UUID,
        logical_route: str,
        effective_route: str,
        audio: ValidatedVoiceAudio,
        estimate: SpeechCostEstimate,
    ) -> VoicePreparation | None:
        """Persist reservation/call intent BEFORE sending; no second attempt."""
        if (
            not logical_route
            or not effective_route
            or len(logical_route) > 127
            or len(effective_route) > 127
        ):
            raise ValueError("invalid speech route")
        if not estimate.estimated_cost_usd.is_finite() or estimate.estimated_cost_usd < 0:
            raise ValueError("invalid speech cost estimate")
        return await self._write(
            """
            UPDATE ancora.voice_preparations
            SET status = 'transcribing', call_id = :call_id, logical_route = :route,
                effective_route = :effective, duration_seconds = :duration,
                size_bytes = :size, estimated_cost = :cost, updated_at = now()
            WHERE interaction_id = :id AND user_id = :user_id AND owner_token = :owner
              AND status = 'downloaded' RETURNING *
        """,
            {
                "id": interaction_id,
                "user_id": user_id,
                "owner": owner_token,
                "call_id": call_id,
                "route": logical_route,
                "effective": effective_route,
                "duration": audio.duration_seconds,
                "size": len(audio.content),
                "cost": estimate.estimated_cost_usd,
            },
        )

    async def persist_transcript(
        self,
        interaction_id: UUID,
        user_id: int,
        owner_token: UUID,
        *,
        result: SpeechToTextResult,
        cipher: SpeechTranscriptCipher,
        actual_cost: Decimal | None = None,
    ) -> VoicePreparation | None:
        if actual_cost is not None and (not actual_cost.is_finite() or actual_cost < 0):
            raise ValueError("invalid actual speech cost")
        ciphertext, key_version = cipher.encrypt(result)
        return await self._write(
            """
            UPDATE ancora.voice_preparations v
            SET status = 'transcribed', transcript_ciphertext = :ciphertext,
                transcript_key_version = :key_version,
                transcript_expires_at = now() + interval '24 hours',
                actual_cost = :actual, updated_at = now()
            WHERE interaction_id = :id AND user_id = :user_id AND owner_token = :owner
              AND status = 'transcribing' AND call_id = :call_id
              AND EXISTS (SELECT 1 FROM ancora.telegram_interactions i
                          WHERE i.id = v.interaction_id AND i.status = 'accepted')
            RETURNING v.*
        """,
            {
                "id": interaction_id,
                "user_id": user_id,
                "owner": owner_token,
                "call_id": result.call_id,
                "ciphertext": ciphertext,
                "key_version": key_version,
                "actual": actual_cost,
            },
        )

    async def close_failed(
        self, interaction_id: UUID, user_id: int, owner_token: UUID, *, ambiguous: bool
    ) -> VoicePreparation | None:
        """Close this owner's unfinished row when preparation fails in-process.

        Only the caller's own non-terminal row moves; nothing is requeued, no
        transcript is touched and no STT/Agent attempt is granted. Must run
        while the parent interaction is still ``accepted`` (parent-first lock).
        """
        return await self._write(
            """
            UPDATE ancora.voice_preparations
            SET status = CASE WHEN :ambiguous OR status = 'transcribing'
                              THEN 'failed_ambiguous' ELSE 'failed_controlled' END,
                updated_at = now()
            WHERE interaction_id = :id AND user_id = :user_id AND owner_token = :owner
              AND status IN ('preparing', 'downloaded', 'transcribing') RETURNING *
        """,
            {
                "id": interaction_id,
                "user_id": user_id,
                "owner": owner_token,
                "ambiguous": ambiguous,
            },
        )

    async def get(self, interaction_id: UUID, user_id: int) -> VoicePreparation | None:
        result = await self._session.execute(
            text("""
            SELECT * FROM ancora.voice_preparations
            WHERE interaction_id = :id AND user_id = :user_id
        """),
            {"id": interaction_id, "user_id": user_id},
        )
        row = result.mappings().first()
        return VoicePreparation.model_validate(row) if row is not None else None

    async def recover_abandoned(
        self, *, user_id: int, owner_token: UUID, updated_before: datetime
    ) -> int:
        """Close a known-dead owner's work, NOT every active worker on startup.

        Caller must establish owner death and choose cutoff before starting new
        work. Never resets states or grants another STT/Agent attempt.
        """
        try:
            await self._session.execute(
                text("""
                SELECT i.id FROM ancora.telegram_interactions i
                JOIN ancora.voice_preparations v ON v.interaction_id = i.id
                WHERE v.user_id = :user_id AND v.owner_token = :owner
                  AND v.updated_at <= :cutoff AND i.status = 'accepted'
                ORDER BY i.id FOR UPDATE OF i
            """),
                {"user_id": user_id, "owner": owner_token, "cutoff": updated_before},
            )
            result = await self._session.execute(
                text("""
                WITH closed AS (
                    UPDATE ancora.voice_preparations
                    SET status = CASE WHEN status IN ('preparing', 'downloaded')
                                      THEN 'failed_controlled' ELSE 'failed_ambiguous' END,
                        transcript_expires_at = CASE WHEN transcript_ciphertext IS NOT NULL
                            THEN LEAST(transcript_expires_at, now() + interval '7 days')
                            ELSE NULL END, updated_at = now()
                    WHERE user_id = :user_id AND owner_token = :owner
                      AND updated_at <= :cutoff
                      AND status IN ('preparing', 'downloaded', 'transcribing', 'transcribed')
                      AND EXISTS (SELECT 1 FROM ancora.telegram_interactions i
                          WHERE i.id = interaction_id AND i.status = 'accepted')
                    RETURNING interaction_id, status
                )
                UPDATE ancora.telegram_interactions i
                SET status = c.status, completed_at = now(), updated_at = now(),
                    error_class = 'VoicePreparationRecovery',
                    error_detail_code = 'voice_preparation_abandoned',
                    payload_ciphertext = CASE WHEN c.status = 'failed_controlled'
                                             THEN NULL ELSE payload_ciphertext END,
                    payload_key_version = CASE WHEN c.status = 'failed_controlled'
                                              THEN NULL ELSE payload_key_version END
                FROM closed c WHERE i.id = c.interaction_id AND i.status = 'accepted'
                RETURNING i.id
            """),
                {"user_id": user_id, "owner": owner_token, "cutoff": updated_before},
            )
            rows = result.fetchall()
            await self._session.commit()
            return len(rows)
        except Exception:
            await self._session.rollback()
            raise

    async def purge_expired_transcripts(self, *, user_id: int, now: datetime) -> int:
        try:
            result = await self._session.execute(
                text("""
                UPDATE ancora.voice_preparations
                SET transcript_ciphertext = NULL, transcript_key_version = NULL,
                    transcript_expires_at = NULL, updated_at = :now
                WHERE user_id = :user_id AND transcript_expires_at <= :now
                  AND transcript_ciphertext IS NOT NULL RETURNING interaction_id
            """),
                {"user_id": user_id, "now": now},
            )
            rows = result.fetchall()
            await self._session.commit()
            return len(rows)
        except Exception:
            await self._session.rollback()
            raise
