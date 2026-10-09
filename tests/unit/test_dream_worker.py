"""Unit tests for DreamWorker (specs/029 T3) — mocked ports, no database."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock
from uuid import uuid4

from src.domain.dream.models import DreamCandidateBatch, DreamConsolidationOutcome
from src.domain.dream.ports import DreamBatch
from src.domain.dream.worker import DreamWorker


def _batch(user_id: str = "42") -> DreamBatch:
    return DreamBatch(
        user_id=user_id,
        transcripts=("usuario: hola\nagent: hola",),
        existing=(),
        cursor_interaction_id=uuid4(),
    )


def _completed_outcome(proposals: list = []) -> DreamConsolidationOutcome:  # noqa: B006
    return DreamConsolidationOutcome(
        batch=DreamCandidateBatch(proposals=proposals),
        provider="OpenRouter",
        model="test/model",
        status="completed",
    )


async def test_run_once_applies_mutations_for_each_eligible_batch():
    repository = AsyncMock()
    repository.claim_eligible_batches.return_value = [_batch("1"), _batch("2")]
    consolidation = AsyncMock()
    consolidation.consolidate.return_value = _completed_outcome()
    worker = DreamWorker(repository=repository, consolidation=consolidation)

    applied = await worker.run_once()

    assert applied == 2
    assert consolidation.consolidate.await_count == 2
    assert repository.apply_batch_result.await_count == 2
    repository.record_run_failure.assert_not_awaited()
    repository.purge_expired.assert_awaited_once()


async def test_run_once_records_failure_without_applying_mutations():
    repository = AsyncMock()
    repository.claim_eligible_batches.return_value = [_batch()]
    consolidation = AsyncMock()
    consolidation.consolidate.return_value = DreamConsolidationOutcome(
        batch=None, provider="", model="", status="failed", error_class="DreamRouteUnavailable"
    )
    worker = DreamWorker(repository=repository, consolidation=consolidation)

    applied = await worker.run_once()

    assert applied == 0
    repository.apply_batch_result.assert_not_awaited()
    repository.record_run_failure.assert_awaited_once()
    repository.purge_expired.assert_awaited_once()


async def test_run_once_purges_even_when_no_batches_are_eligible():
    repository = AsyncMock()
    repository.claim_eligible_batches.return_value = []
    consolidation = AsyncMock()
    worker = DreamWorker(repository=repository, consolidation=consolidation)

    applied = await worker.run_once()

    assert applied == 0
    consolidation.consolidate.assert_not_awaited()
    repository.purge_expired.assert_awaited_once()


async def test_run_forever_logs_and_continues_after_a_cycle_exception():
    repository = AsyncMock()
    repository.claim_eligible_batches.side_effect = [RuntimeError("boom"), asyncio.CancelledError()]
    consolidation = AsyncMock()
    worker = DreamWorker(repository=repository, consolidation=consolidation)

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(worker.run_forever(interval_seconds=0), timeout=2)

    assert repository.claim_eligible_batches.call_count == 2


async def test_run_forever_propagates_cancellation_without_sleeping_forever():
    repository = AsyncMock()
    repository.claim_eligible_batches.side_effect = asyncio.CancelledError()
    consolidation = AsyncMock()
    worker = DreamWorker(repository=repository, consolidation=consolidation)

    try:
        await asyncio.wait_for(worker.run_forever(interval_seconds=0), timeout=2)
        raise AssertionError("expected CancelledError to propagate")
    except asyncio.CancelledError:
        pass
