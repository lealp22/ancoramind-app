"""Unit tests for DreamCandidatesRepository (specs/029 T5) — mocked session,
no PostgreSQL. Same style as test_repository_returning_guards.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.dream.models import DreamCandidateSnapshot
from src.repositories.dream_candidates import DreamCandidatesRepository


def _session_with_rows(rows: list[dict[str, object]]) -> AsyncSession:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session.execute.return_value = result
    return session


def _session_with_rowcount(rowcount: int) -> AsyncSession:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.rowcount = rowcount
    session.execute.return_value = result
    return session


async def test_list_active_parses_rows_into_snapshots():
    candidate_id = uuid4()
    row = {
        "id": candidate_id,
        "category": "tone_length",
        "key": "response_length",
        "value": "corto",
        "status": "active",
        "evidence_count": 2,
        "confidence": 0.8,
    }
    session = _session_with_rows([row])

    result = await DreamCandidatesRepository(session).list_active("user-1")

    assert result == [DreamCandidateSnapshot.model_validate(row)]
    params = session.execute.call_args.args[1]
    assert params == {"uid": "user-1"}


async def test_list_active_scopes_by_user_id_only():
    session = _session_with_rows([])

    result = await DreamCandidatesRepository(session).list_active("user-42")

    assert result == []
    sql = str(session.execute.call_args.args[0])
    assert "user_id = :uid" in sql
    assert "status = 'active'" in sql


async def test_forget_one_returns_true_when_a_row_was_updated():
    session = _session_with_rowcount(1)

    forgotten = await DreamCandidatesRepository(session).forget_one("user-1", uuid4())

    assert forgotten is True
    session.commit.assert_awaited_once()


async def test_forget_one_returns_false_when_nothing_matched():
    session = _session_with_rowcount(0)

    forgotten = await DreamCandidatesRepository(session).forget_one("user-1", uuid4())

    assert forgotten is False


async def test_forget_one_respects_auto_commit_false():
    session = _session_with_rowcount(1)

    await DreamCandidatesRepository(session, auto_commit=False).forget_one("user-1", uuid4())

    session.commit.assert_not_awaited()


async def test_forget_all_returns_the_affected_row_count():
    session = _session_with_rowcount(3)

    count = await DreamCandidatesRepository(session).forget_all("user-1")

    assert count == 3
    session.commit.assert_awaited_once()


async def test_forget_all_returns_zero_when_nothing_to_forget():
    session = _session_with_rowcount(0)

    count = await DreamCandidatesRepository(session).forget_all("user-1")

    assert count == 0


async def test_forget_queries_never_touch_other_users_rows():
    session = _session_with_rowcount(1)

    await DreamCandidatesRepository(session).forget_all("user-1")

    params = session.execute.call_args.args[1]
    assert params["uid"] == "user-1"
    sql = str(session.execute.call_args.args[0])
    assert "user_id = :uid" in sql
