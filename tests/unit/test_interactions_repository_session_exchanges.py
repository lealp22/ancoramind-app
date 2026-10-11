"""Unit test for TelegramInteractionsRepository.list_session_exchanges (BL-34).

The rest of this repository is covered only by
tests/integration/test_telegram_interactions_repository.py against real
PostgreSQL — this one new read gets the same AsyncMock-based unit coverage
every other new repository method got this session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.repositories.interactions import TelegramInteractionsRepository


async def test_list_session_exchanges_maps_rows_oldest_first() -> None:
    session = AsyncMock()
    first_id, second_id = uuid4(), uuid4()
    rows = [
        MagicMock(interaction_id=first_id, payload_ciphertext=b"a", response_ciphertext=b"b"),
        MagicMock(interaction_id=second_id, payload_ciphertext=b"c", response_ciphertext=None),
    ]
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute.return_value = result

    exchanges = await TelegramInteractionsRepository(session).list_session_exchanges(
        "tg:ancoramind:4"
    )

    assert [exchange.interaction_id for exchange in exchanges] == [first_id, second_id]
    assert exchanges[0].payload_ciphertext == b"a"
    assert exchanges[0].response_ciphertext == b"b"
    assert exchanges[1].response_ciphertext is None
    query, params = session.execute.await_args.args
    assert "response_kind = 'agent_final'" in str(query)
    assert "ORDER BY i.received_at ASC" in str(query)
    assert params == {"session_id": "tg:ancoramind:4"}


async def test_list_session_exchanges_returns_empty_for_no_match() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = []
    session.execute.return_value = result

    exchanges = await TelegramInteractionsRepository(session).list_session_exchanges("none")

    assert exchanges == []
