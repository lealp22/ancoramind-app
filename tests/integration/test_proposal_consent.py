"""Integration tests for the Core-owned consent state machine (specs/023 T4.1-T4.2).

Every test runs against real PostgreSQL so that row locks, the database clock,
the status CHECK constraint and the single-use unique index are exercised —
none of that is observable with mocked repositories.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import (
    ConsentPrincipal,
    ConsentRejection,
    ProposalStatus,
)
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session

pytestmark = pytest.mark.integration

BOT_ID = 8001
CHAT_ID = 2001
_update_ids = count(50_000)


def _principal(user_id: str, *, chat_id: int = CHAT_ID) -> ConsentPrincipal:
    return ConsentPrincipal(user_id=user_id, bot_id=BOT_ID, chat_id=chat_id)


async def _interaction(session: AsyncSession, *, chat_id: int = CHAT_ID) -> UUID:
    """Insert a minimal admitted Telegram interaction and return its id."""
    row = (
        await session.execute(
            text("""
                INSERT INTO ancora.telegram_interactions (
                    bot_id, telegram_update_id, telegram_message_id, chat_id,
                    telegram_user_id, update_type, status, accepted_at,
                    received_at, updated_at
                ) VALUES (
                    :bot_id, :update_id, 1, :chat_id, 3001, 'message', 'accepted',
                    now(), now(), now()
                ) RETURNING id
            """),
            {"bot_id": BOT_ID, "update_id": next(_update_ids), "chat_id": chat_id},
        )
    ).fetchone()
    assert row is not None
    await session.commit()
    return row.id


async def _response(session: AsyncSession, interaction_id: UUID) -> UUID:
    row = (
        await session.execute(
            text("""
                INSERT INTO ancora.logical_responses
                    (interaction_id, response_kind, status)
                VALUES (:interaction_id, 'agent', 'delivered')
                RETURNING id
            """),
            {"interaction_id": interaction_id},
        )
    ).fetchone()
    assert row is not None
    await session.commit()
    return row.id


async def _presented_proposal(
    session: AsyncSession,
    user_id: str,
    *,
    payload: dict[str, object] | None = None,
) -> UUID:
    """Create a provenance-bearing proposal and record its verified delivery."""
    repo = ActionProposalsRepository(session)
    source = await _interaction(session)
    proposal = await repo.create(
        user_id,
        "create_reminder",
        payload or {"title": "ITV", "trigger_at": "2026-10-20T09:00:00"},
        source_interaction_id=source,
        bot_id=BOT_ID,
        chat_id=CHAT_ID,
    )
    proposal_id = UUID(proposal["id"])
    response_id = await _response(session, source)
    marked = await repo.mark_presented(
        [proposal_id],
        principal=_principal(user_id),
        response_id=response_id,
        presented_at=datetime.now(tz=UTC),
    )
    assert marked == 1
    await session.commit()
    return proposal_id


async def _status(session: AsyncSession, proposal_id: UUID) -> str:
    row = (
        await session.execute(
            text("SELECT status FROM ancora.action_proposals WHERE id = :id"),
            {"id": proposal_id},
        )
    ).fetchone()
    assert row is not None
    return str(row.status)


async def test_full_consent_lifecycle(session: AsyncSession, user_a: str) -> None:
    repo = ActionProposalsRepository(session)
    proposal_id = await _presented_proposal(session, user_a)
    confirming = await _interaction(session)

    assert await repo.list_confirmable(_principal(user_a)) == [proposal_id]

    result = await repo.claim_confirmation(
        proposal_id, principal=_principal(user_a), confirming_interaction_id=confirming
    )
    assert result.ok and result.claimed is not None
    assert result.claimed.tool_name == "create_reminder"
    assert result.claimed.confirming_interaction_id == confirming
    assert await repo.begin_execution(proposal_id, user_id=user_a)
    assert await repo.complete_execution(
        proposal_id, user_id=user_a, status=ProposalStatus.EXECUTED
    )
    await session.commit()

    assert await _status(session, proposal_id) == "executed"
    assert await repo.list_confirmable(_principal(user_a)) == []
    # A terminal proposal never moves again.
    assert not await repo.begin_execution(proposal_id, user_id=user_a)


async def test_claim_is_single_use(session: AsyncSession, user_a: str) -> None:
    repo = ActionProposalsRepository(session)
    proposal_id = await _presented_proposal(session, user_a)
    first = await repo.claim_confirmation(
        proposal_id,
        principal=_principal(user_a),
        confirming_interaction_id=await _interaction(session),
    )
    await session.commit()
    second = await repo.claim_confirmation(
        proposal_id,
        principal=_principal(user_a),
        confirming_interaction_id=await _interaction(session),
    )

    assert first.ok
    assert second.rejection is ConsentRejection.NOT_PENDING


async def test_one_interaction_authorises_at_most_one_proposal(
    session: AsyncSession, user_a: str
) -> None:
    repo = ActionProposalsRepository(session)
    first_id = await _presented_proposal(session, user_a)
    second_id = await _presented_proposal(session, user_a, payload={"title": "Otra"})
    confirming = await _interaction(session)

    assert (
        await repo.claim_confirmation(
            first_id, principal=_principal(user_a), confirming_interaction_id=confirming
        )
    ).ok
    await session.commit()
    second = await repo.claim_confirmation(
        second_id, principal=_principal(user_a), confirming_interaction_id=confirming
    )

    assert second.rejection is ConsentRejection.INTERACTION_ALREADY_USED
    assert await _status(session, second_id) == "pending_confirmation"


async def test_unique_index_backs_single_use_even_without_the_pre_check(
    session: AsyncSession, user_a: str
) -> None:
    """The DB, not only Python, guarantees one confirming interaction per proposal."""
    first_id = await _presented_proposal(session, user_a)
    second_id = await _presented_proposal(session, user_a, payload={"title": "Otra"})
    confirming = await _interaction(session)
    statement = text("""
        UPDATE ancora.action_proposals
        SET status = 'confirmed', confirming_interaction_id = :interaction
        WHERE id = :id
    """)
    await session.execute(statement, {"id": first_id, "interaction": confirming})
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(statement, {"id": second_id, "interaction": confirming})
    await session.rollback()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("legacy", ConsentRejection.LEGACY_PROPOSAL),
        ("not_presented", ConsentRejection.NOT_PRESENTED),
        ("other_chat", ConsentRejection.PRINCIPAL_MISMATCH),
        ("other_user", ConsentRejection.NOT_FOUND),
        ("tampered", ConsentRejection.PAYLOAD_TAMPERED),
        ("expired", ConsentRejection.EXPIRED),
    ],
)
async def test_claim_rejections(
    session: AsyncSession, user_a: str, user_b: str, case: str, expected: ConsentRejection
) -> None:
    repo = ActionProposalsRepository(session)
    principal = _principal(user_a)
    if case == "legacy":
        proposal_id = UUID((await repo.create(user_a, "create_reminder", {"title": "x"}))["id"])
    elif case == "not_presented":
        proposal_id = UUID(
            (
                await repo.create(
                    user_a,
                    "create_reminder",
                    {"title": "x"},
                    source_interaction_id=await _interaction(session),
                    bot_id=BOT_ID,
                    chat_id=CHAT_ID,
                )
            )["id"]
        )
    else:
        proposal_id = await _presented_proposal(session, user_a)
    if case == "other_chat":
        principal = _principal(user_a, chat_id=CHAT_ID + 1)
    elif case == "other_user":
        principal = _principal(user_b)
    elif case == "tampered":
        await session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET payload = '{"title": "cambiado"}'::jsonb WHERE id = :id
            """),
            {"id": proposal_id},
        )
    elif case == "expired":
        await session.execute(
            text("""
                UPDATE ancora.action_proposals
                SET expires_at = now() - interval '1 second' WHERE id = :id
            """),
            {"id": proposal_id},
        )
    await session.commit()

    result = await repo.claim_confirmation(
        proposal_id, principal=principal, confirming_interaction_id=await _interaction(session)
    )
    await session.commit()

    assert result.rejection is expected
    assert result.claimed is None
    expected_status = "expired" if case == "expired" else "pending_confirmation"
    assert await _status(session, proposal_id) == expected_status


async def test_concurrent_claims_from_separate_sessions_yield_one_winner(
    session: AsyncSession, user_a: str
) -> None:
    """Two processes racing on the same proposal: the row lock serialises them."""
    proposal_id = await _presented_proposal(session, user_a)
    interactions = [await _interaction(session), await _interaction(session)]

    async def claim(interaction_id: UUID) -> ConsentRejection | None:
        own = await get_session()
        try:
            result = await ActionProposalsRepository(own).claim_confirmation(
                proposal_id,
                principal=_principal(user_a),
                confirming_interaction_id=interaction_id,
            )
            await own.commit()
            return result.rejection
        finally:
            await own.close()

    outcomes = await asyncio.gather(*(claim(i) for i in interactions))

    assert sorted(outcomes, key=str) == sorted([None, ConsentRejection.NOT_PENDING], key=str)
    assert await _status(session, proposal_id) == "confirmed"


async def test_mark_presented_never_extends_an_existing_window(
    session: AsyncSession, user_a: str
) -> None:
    repo = ActionProposalsRepository(session)
    proposal_id = await _presented_proposal(session, user_a)
    later = datetime.now(tz=UTC) + timedelta(hours=1)

    remarked = await repo.mark_presented(
        [proposal_id],
        principal=_principal(user_a),
        response_id=await _response(session, await _interaction(session)),
        presented_at=later,
    )

    assert remarked == 0


async def test_mark_presented_skips_legacy_and_foreign_proposals(
    session: AsyncSession, user_a: str, user_b: str
) -> None:
    repo = ActionProposalsRepository(session)
    legacy_id = UUID((await repo.create(user_a, "create_reminder", {"title": "x"}))["id"])
    response_id = await _response(session, await _interaction(session))

    marked = await repo.mark_presented(
        [legacy_id],
        principal=_principal(user_a),
        response_id=response_id,
        presented_at=datetime.now(tz=UTC),
    )
    foreign = await repo.mark_presented(
        [legacy_id],
        principal=_principal(user_b),
        response_id=response_id,
        presented_at=datetime.now(tz=UTC),
    )

    assert marked == 0 and foreign == 0


async def test_discard_pending_for_chat_invalidates_only_that_chat(
    session: AsyncSession, user_a: str
) -> None:
    repo = ActionProposalsRepository(session)
    proposal_id = await _presented_proposal(session, user_a)

    other = await repo.discard_pending_for_chat(_principal(user_a, chat_id=CHAT_ID + 1))
    discarded = await repo.discard_pending_for_chat(_principal(user_a))
    await session.commit()

    assert other == 0 and discarded == 1
    assert await _status(session, proposal_id) == "discarded"
    result = await repo.claim_confirmation(
        proposal_id,
        principal=_principal(user_a),
        confirming_interaction_id=await _interaction(session),
    )
    assert result.rejection is ConsentRejection.NOT_PENDING


async def test_ambiguous_failure_is_terminal(session: AsyncSession, user_a: str) -> None:
    repo = ActionProposalsRepository(session)
    proposal_id = await _presented_proposal(session, user_a)
    assert (
        await repo.claim_confirmation(
            proposal_id,
            principal=_principal(user_a),
            confirming_interaction_id=await _interaction(session),
        )
    ).ok
    assert await repo.begin_execution(proposal_id, user_id=user_a)
    assert await repo.complete_execution(
        proposal_id,
        user_id=user_a,
        status=ProposalStatus.FAILED_AMBIGUOUS,
        failure_reason="provider_timeout",
    )
    await session.commit()

    assert await _status(session, proposal_id) == "failed_ambiguous"
    assert not await repo.complete_execution(
        proposal_id, user_id=user_a, status=ProposalStatus.EXECUTED
    )
    with pytest.raises(ValueError):
        await repo.complete_execution(proposal_id, user_id=user_a, status=ProposalStatus.CONFIRMED)


async def test_status_check_constraint_rejects_unknown_states(
    session: AsyncSession, user_a: str
) -> None:
    repo = ActionProposalsRepository(session)
    proposal_id = UUID((await repo.create(user_a, "create_reminder", {"title": "x"}))["id"])

    with pytest.raises(DBAPIError):
        await session.execute(
            text("UPDATE ancora.action_proposals SET status = 'approved' WHERE id = :id"),
            {"id": proposal_id},
        )
    await session.rollback()


async def test_legacy_mark_executed_cannot_consume_even_confirmed_proposals(
    session: AsyncSession, user_a: str
) -> None:
    """Regression (specs/023 T4.2): it used to overwrite any status of the user."""
    repo = ActionProposalsRepository(session)
    proposal_id = (await repo.create(user_a, "create_reminder", {"title": "x"}))["id"]

    assert await repo.mark_executed(user_a, proposal_id) is False
    assert await _status(session, UUID(proposal_id)) == "pending_confirmation"

    presented = await _presented_proposal(session, user_a)
    claim = await repo.claim_confirmation(
        presented,
        principal=_principal(user_a),
        confirming_interaction_id=await _interaction(session),
    )
    await session.commit()
    assert claim.ok
    assert await repo.mark_executed(user_a, str(presented)) is False
    assert await _status(session, presented) == "confirmed"


async def test_create_takes_provenance_from_the_governed_run(
    session: AsyncSession, user_a: str
) -> None:
    """specs/023 T4.4: provenance is bound by the Core, not passed by the model."""
    from src.domain.llm_access.context import execution_context_scope
    from src.domain.llm_access.models import InteractionProvenance

    repo = ActionProposalsRepository(session)
    source = await _interaction(session)
    context = _context_with(InteractionProvenance(source, BOT_ID, CHAT_ID))

    with execution_context_scope(context):
        proposal_id = UUID((await repo.create(user_a, "create_reminder", {"title": "x"}))["id"])
    outside = UUID((await repo.create(user_a, "create_reminder", {"title": "y"}))["id"])

    rows = {
        row.id: row
        for row in (
            await session.execute(
                text("""
                    SELECT id, source_interaction_id, bot_id, chat_id
                    FROM ancora.action_proposals WHERE id = ANY(:ids)
                """),
                {"ids": [proposal_id, outside]},
            )
        ).fetchall()
    }
    assert (rows[proposal_id].source_interaction_id, rows[proposal_id].bot_id) == (source, BOT_ID)
    assert rows[proposal_id].chat_id == CHAT_ID
    assert rows[outside].source_interaction_id is None
    assert rows[outside].bot_id is None


def _context_with(provenance: object) -> object:
    from uuid import uuid4

    from src.domain.llm_access.models import ExecutionBudget, ExecutionContext
    from src.domain.runtime_config.models import (
        RuntimeConfigSnapshot,
        bootstrap_runtime_configuration,
        config_checksum,
    )

    config = bootstrap_runtime_configuration()
    snapshot = RuntimeConfigSnapshot(
        revision=0, checksum=config_checksum(config), config=config, source="bootstrap"
    )
    return ExecutionContext(
        correlation_id=uuid4(),
        telegram_update_id=1,
        agno_run_id="run-1",
        agno_session_id="tg:ancora:2001",
        config=snapshot,
        budget=ExecutionBudget.from_config(config.execution_budget, started_at_monotonic=0.0),
        provenance=provenance,  # type: ignore[arg-type]
    )
