"""Unit tests for TrivialExecutor (specs/035, BL-46): the WRITE_TRIVIAL tier.

Mutation + audit row are mocked at the module boundary (``apply_mutation``,
``ActionProposalsRepository``) because the atomicity/transaction guarantee
itself needs real PostgreSQL to mean anything — that is covered by
integration tests once Docker is available. These tests pin the pure
dispatch/error-handling logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.trivial_executor import TRIVIAL_MUTATIONS, TrivialExecutor


def _executor(session: AsyncMock) -> TrivialExecutor:
    return TrivialExecutor(sessions=AsyncMock(return_value=session))


def test_trivial_mutations_scope_matches_specs_035_must_have() -> None:
    """Pins the exact scope decided in specs/035 — a change here is governance."""
    assert {"create_todo_item", "set_todo_item_status", "remember_note"} == TRIVIAL_MUTATIONS


@pytest.mark.asyncio
async def test_rejects_tool_names_outside_the_trivial_scope() -> None:
    session = AsyncMock(spec=AsyncSession)
    executor = _executor(session)

    reply = await executor.execute("register_vehicle", {}, "user-1")

    assert "no tiene ejecutor determinista" in reply
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_commits_mutation_and_audit_row_once() -> None:
    session = AsyncMock(spec=AsyncSession)
    executor = _executor(session)
    payload = {"list_id": "11111111-1111-1111-1111-111111111111", "title": "leche"}

    with (
        patch(
            "src.domain.actions.trivial_executor.apply_mutation",
            new=AsyncMock(return_value="✅ Añadido."),
        ) as mocked_apply,
        patch(
            "src.domain.actions.trivial_executor.ActionProposalsRepository"
        ) as mocked_repo_cls,
    ):
        mocked_repo = mocked_repo_cls.return_value
        mocked_repo.create_self_authorized = AsyncMock()

        reply = await executor.execute("create_todo_item", payload, "user-1")

    assert reply == "✅ Añadido."
    mocked_apply.assert_awaited_once()
    claimed = mocked_apply.await_args.args[1]
    assert claimed.tool_name == "create_todo_item"
    assert claimed.payload == payload
    assert claimed.source_document_id is None
    mocked_repo.create_self_authorized.assert_awaited_once_with(
        "user-1", "create_todo_item", payload
    )
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_not_owned_rolls_back_and_audits_nothing() -> None:
    session = AsyncMock(spec=AsyncSession)
    executor = _executor(session)

    with (
        patch(
            "src.domain.actions.trivial_executor.apply_mutation",
            new=AsyncMock(side_effect=ValueError("target_missing_or_not_owned")),
        ),
        patch(
            "src.domain.actions.trivial_executor.ActionProposalsRepository"
        ) as mocked_repo_cls,
    ):
        reply = await executor.execute("set_todo_item_status", {"item_id": "x"}, "user-1")

    assert "No encontré" in reply
    mocked_repo_cls.return_value.create_self_authorized.assert_not_called()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_failure_rolls_back_with_a_generic_message_and_no_retry() -> None:
    session = AsyncMock(spec=AsyncSession)
    executor = _executor(session)

    with patch(
        "src.domain.actions.trivial_executor.apply_mutation",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        reply = await executor.execute("remember_note", {"content": "x"}, "user-1")

    assert "No pude completar" in reply
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_row_failure_also_rolls_back_the_mutation() -> None:
    """The mutation must never survive without its audit row (atomicity)."""
    session = AsyncMock(spec=AsyncSession)
    executor = _executor(session)

    with (
        patch(
            "src.domain.actions.trivial_executor.apply_mutation",
            new=AsyncMock(return_value="✅ Añadido."),
        ),
        patch(
            "src.domain.actions.trivial_executor.ActionProposalsRepository"
        ) as mocked_repo_cls,
    ):
        mocked_repo_cls.return_value.create_self_authorized = AsyncMock(
            side_effect=RuntimeError("db exploded")
        )

        reply = await executor.execute("remember_note", {"content": "x"}, "user-1")

    assert "No pude completar" in reply
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
