"""WRITE_TRIVIAL mutations and audit must survive or roll back together."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import payload_hash
from src.domain.actions.trivial_executor import TrivialExecutor
from src.domain.todos.models import TodoListCreate
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.todos import TodosRepository

pytestmark = pytest.mark.integration


async def _audit_rows(session: AsyncSession):
    return (
        await session.execute(
            text("""
                SELECT tool_name, payload, payload_hash, status, consent_mode,
                       confirming_interaction_id, presented_at, completed_at
                FROM ancora.action_proposals WHERE user_id = :uid ORDER BY created_at, id
            """),
            {"uid": "it-trivial-owner"},
        )
    ).all()


async def test_todo_lifecycle_and_note_commit_with_terminal_audit(session: AsyncSession) -> None:
    user = "it-trivial-owner"
    todo_list = await TodosRepository(session).create_list(user, TodoListCreate(name="Sintética"))
    executor = TrivialExecutor(get_session)

    assert "✅" in await executor.execute(
        "create_todo_item", {"list_id": str(todo_list.id), "title": "Sintética"}, user
    )
    item_id = await session.scalar(
        text("SELECT id FROM ancora.todo_items WHERE user_id = :uid"), {"uid": user}
    )
    assert isinstance(item_id, UUID)
    for status in ("done", "pending"):
        assert "✅" in await executor.execute(
            "set_todo_item_status", {"item_id": str(item_id), "status": status}, user
        )
        assert (
            await session.scalar(
                text("SELECT status FROM ancora.todo_items WHERE id = :id AND user_id = :uid"),
                {"id": item_id, "uid": user},
            )
            == status
        )
    assert "✅" in await executor.execute("remember_note", {"content": "Nota sintética"}, user)
    assert (
        await session.scalar(
            text("SELECT content FROM ancora.notes WHERE user_id = :uid"), {"uid": user}
        )
        == "Nota sintética"
    )

    rows = await _audit_rows(session)
    assert [row.tool_name for row in rows] == [
        "create_todo_item",
        "set_todo_item_status",
        "set_todo_item_status",
        "remember_note",
    ]
    for row in rows:
        assert row.status == "executed" and row.consent_mode == "self_authorized"
        assert row.confirming_interaction_id is None and row.presented_at is None
        assert row.completed_at is not None
        assert row.payload_hash == payload_hash(row.tool_name, row.payload)


async def test_real_ownership_rejection_writes_neither_mutation_nor_audit(
    session: AsyncSession,
) -> None:
    todo_list = await TodosRepository(session).create_list(
        "it-other-owner", TodoListCreate(name="Ajena")
    )
    reply = await TrivialExecutor(get_session).execute(
        "create_todo_item",
        {"list_id": str(todo_list.id), "title": "No debe existir"},
        "it-trivial-owner",
    )
    assert "No encontré" in reply
    assert await session.scalar(text("SELECT count(*) FROM ancora.todo_items")) == 0
    assert await _audit_rows(session) == []


async def test_audit_failure_rolls_back_real_note_and_audit_insert(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ActionProposalsRepository.create_self_authorized
    audit_calls = 0

    async def fail_after_insert(self, user_id, tool_name, payload, **kwargs):
        nonlocal audit_calls
        audit_calls += 1
        await original(self, user_id, tool_name, payload, **kwargs)
        raise RuntimeError("scripted failure after real audit INSERT")

    monkeypatch.setattr(ActionProposalsRepository, "create_self_authorized", fail_after_insert)
    reply = await TrivialExecutor(get_session).execute(
        "remember_note", {"content": "No debe persistir"}, "it-trivial-owner"
    )
    assert "No pude completar" in reply
    assert audit_calls == 1
    assert await session.scalar(text("SELECT count(*) FROM ancora.notes")) == 0
    assert await _audit_rows(session) == []


async def test_commit_failure_rolls_back_real_mutation_and_audit(
    session: AsyncSession,
) -> None:
    commits = 0

    class FailingCommitSession(AsyncSession):
        async def commit(self) -> None:
            nonlocal commits
            commits += 1
            raise RuntimeError("scripted pre-commit failure")

    async def failing_session() -> AsyncSession:
        return FailingCommitSession(bind=session.bind, expire_on_commit=False)

    factory: Callable[[], Awaitable[AsyncSession]] = failing_session
    reply = await TrivialExecutor(factory).execute(
        "remember_note", {"content": "No debe persistir"}, "it-trivial-owner"
    )
    assert "No pude completar" in reply and commits == 1
    assert await session.scalar(text("SELECT count(*) FROM ancora.notes")) == 0
    assert await _audit_rows(session) == []
