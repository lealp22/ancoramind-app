"""Unit test for LlmUsageRepository.sum_session_tokens (BL-34, 2026-10-12).

The method's remaining behaviour (record/finish_speech_call/summarize_spend)
is only covered by tests/integration/test_llm_usage_repo.py against real
PostgreSQL — this one new aggregate query gets the same AsyncMock-based unit
coverage every other new repository method got this session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.repositories.llm_usage import LlmUsageRepository


async def test_sum_session_tokens_returns_the_aggregate() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = MagicMock(total=12_345)
    session.execute.return_value = result

    total = await LlmUsageRepository(session).sum_session_tokens("tg:ancoramind:4")

    assert total == 12_345
    query, params = session.execute.await_args.args
    assert "SUM(e.total_tokens)" in str(query)
    assert "WHERE i.agno_session_id = :session_id" in str(query)
    assert params == {"session_id": "tg:ancoramind:4"}


async def test_sum_session_tokens_defaults_to_zero_for_an_empty_session() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.one.return_value = MagicMock(total=0)
    session.execute.return_value = result

    total = await LlmUsageRepository(session).sum_session_tokens("tg:ancoramind:empty")

    assert total == 0
