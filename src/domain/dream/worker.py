"""DreamWorker — background consolidation loop (specs/029 §7).

Mirrors ``src/domain/reminders/worker.py``: a per-cycle exception is logged
and the loop continues (never kills the process), ``asyncio.CancelledError``
propagates for clean shutdown, and all durability lives behind
``DreamRepositoryPort`` — this module has no FastAPI, no Agno and no SQL.
"""

from __future__ import annotations

import asyncio
import logging

from src.domain.dream.ports import DreamConsolidationPort, DreamRepositoryPort
from src.domain.dream.service import DreamPromotionService

logger = logging.getLogger(__name__)


class DreamWorker:
    def __init__(
        self,
        *,
        repository: DreamRepositoryPort,
        consolidation: DreamConsolidationPort,
        promotion: DreamPromotionService | None = None,
        batch_limit: int = 20,
    ) -> None:
        self._repository = repository
        self._consolidation = consolidation
        self._promotion = promotion or DreamPromotionService()
        self._batch_limit = batch_limit

    async def run_once(self) -> int:
        """Consolidate every currently eligible user batch once; return the count applied."""
        applied = 0
        batches = await self._repository.claim_eligible_batches(limit=self._batch_limit)
        for batch in batches:
            outcome = await self._consolidation.consolidate(batch)
            if outcome.status != "completed" or outcome.batch is None:
                await self._repository.record_run_failure(batch.user_id, outcome)
                continue
            mutations = self._promotion.decide(
                existing=list(batch.existing),
                proposals=list(outcome.batch.proposals),
            )
            await self._repository.apply_batch_result(
                batch.user_id,
                mutations=mutations,
                cursor_interaction_id=batch.cursor_interaction_id,
                outcome=outcome,
            )
            applied += 1
        await self._repository.purge_expired()
        return applied

    async def run_forever(self, interval_seconds: float) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Dream worker cycle failed")
            await asyncio.sleep(interval_seconds)


__all__ = ["DreamWorker"]
