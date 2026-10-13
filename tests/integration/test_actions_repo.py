"""Integration tests for ActionProposalsRepository against real PostgreSQL (specs/009)."""

import pytest
from sqlalchemy import text

from src.domain.documents.models import DocumentCreate
from src.repositories.actions import ActionProposalsRepository
from src.repositories.documents import DocumentsRepository

pytestmark = pytest.mark.integration


async def test_pending_proposal_cannot_be_confirmed_or_executed_by_legacy_api(session, user_a):
    repo = ActionProposalsRepository(session)

    proposal = await repo.create(
        user_a,
        "register_vehicle_maintenance",
        {"make": "Ford", "model": "Mondeo", "date": "2026-09-09"},
    )
    assert proposal["status"] == "pending_confirmation"
    # JSONB round-trip: payload comes back as a native dict
    assert proposal["payload"] == {"make": "Ford", "model": "Mondeo", "date": "2026-09-09"}
    proposal_id = proposal["id"]

    pending = await repo.get_pending(user_a, proposal_id)
    assert pending is not None
    assert pending["tool_name"] == "register_vehicle_maintenance"

    assert await repo.confirm(user_a, proposal_id) is None
    assert await repo.confirm_or_use_confirmed(user_a, proposal_id) is None
    assert not await repo.mark_executed(user_a, proposal_id)

    row = (
        await session.execute(
            text(
                "SELECT status, confirmed_at, executed_at FROM ancora.action_proposals"
                " WHERE id = :id"
            ),
            {"id": proposal_id},
        )
    ).fetchone()
    assert row.status == "pending_confirmation"
    assert row.confirmed_at is None
    assert row.executed_at is None


async def test_governance_is_user_scoped(session, user_a, user_b):
    repo = ActionProposalsRepository(session)

    proposal = await repo.create(user_a, "create_reminder", {"title": "ITV"})
    proposal_id = proposal["id"]

    # User B cannot read, confirm nor execute user A's proposal
    assert await repo.get_pending(user_b, proposal_id) is None
    assert await repo.confirm(user_b, proposal_id) is None
    await repo.mark_executed(user_b, proposal_id)

    assert await repo.get_pending(user_a, proposal_id) is not None
    assert (await repo.get_pending(user_a, proposal_id))["status"] == ("pending_confirmation")


async def test_source_document_set_null_on_document_delete(session, user_a):
    documents = DocumentsRepository(session)
    actions = ActionProposalsRepository(session)

    doc = await documents.create(
        user_a,
        DocumentCreate(
            storage_key="2026/09/itv.pdf",
            original_filename="itv.pdf",
            mime_type="application/pdf",
            size_bytes=512,
            content_hash="d" * 64,
        ),
    )
    proposal = await actions.create(
        user_a,
        "register_vehicle_maintenance",
        {"description": "ITV pasada"},
        source_document_id=doc.id,
    )
    assert proposal["source_document_id"] == str(doc.id)

    # ON DELETE SET NULL: the proposal survives without the provenance link
    assert await documents.delete(user_a, doc.id) is True

    pending = await actions.get_pending(user_a, proposal["id"])
    assert pending is not None
    assert pending["source_document_id"] is None


async def test_confirm_or_use_confirmed_never_authorizes_pending_proposals(session, user_a):
    """No rollout flag can restore model-owned authorization."""
    repo = ActionProposalsRepository(session)
    proposal = await repo.create(user_a, "create_reminder", {"title": "ITV"})

    result = await repo.confirm_or_use_confirmed(user_a, proposal["id"])

    assert result is None
    row = (
        await session.execute(
            text("SELECT confirmed_at FROM ancora.action_proposals WHERE id = :id"),
            {"id": proposal["id"]},
        )
    ).one()
    assert row.confirmed_at is None


async def test_legacy_api_cannot_reuse_a_core_claim(session, user_a):
    """A valid Core claim is exclusively consumed by ProposalExecutor."""
    from datetime import UTC, datetime
    from uuid import UUID

    from src.domain.actions.models import ConsentPrincipal

    repo = ActionProposalsRepository(session)
    source = (
        await session.execute(
            text("""
                INSERT INTO ancora.telegram_interactions (
                    bot_id, telegram_update_id, telegram_message_id, chat_id,
                    telegram_user_id, update_type, status, accepted_at,
                    received_at, updated_at
                ) VALUES (9001, 70001, 1, 7001, 7002, 'message', 'accepted',
                    now(), now(), now())
                RETURNING id
            """)
        )
    ).scalar_one()
    proposal = await repo.create(
        user_a,
        "create_reminder",
        {"title": "ITV"},
        source_interaction_id=source,
        bot_id=9001,
        chat_id=7001,
    )
    proposal_id = UUID(proposal["id"])
    response_id = (
        await session.execute(
            text("""
                INSERT INTO ancora.logical_responses (interaction_id, response_kind, status)
                VALUES (:interaction_id, 'agent', 'delivered')
                RETURNING id
            """),
            {"interaction_id": source},
        )
    ).scalar_one()
    principal = ConsentPrincipal(user_id=user_a, bot_id=9001, chat_id=7001)
    marked = await repo.mark_presented(
        [proposal_id],
        principal=principal,
        response_id=response_id,
        presented_at=datetime.now(tz=UTC),
    )
    assert marked == 1
    confirming = (
        await session.execute(
            text("""
                INSERT INTO ancora.telegram_interactions (
                    bot_id, telegram_update_id, telegram_message_id, chat_id,
                    telegram_user_id, update_type, status, accepted_at,
                    received_at, updated_at
                ) VALUES (9001, 70002, 1, 7001, 7002, 'callback_query', 'accepted',
                    now(), now(), now())
                RETURNING id
            """)
        )
    ).scalar_one()
    claim = await repo.claim_confirmation(
        proposal_id, principal=principal, confirming_interaction_id=confirming
    )
    await session.commit()
    assert claim.ok

    result = await repo.confirm_or_use_confirmed(user_a, proposal["id"])

    assert result is None
    assert not await repo.mark_executed(user_a, proposal["id"])
    assert (
        await session.scalar(
            text("SELECT status FROM ancora.action_proposals WHERE id=:id"),
            {"id": proposal_id},
        )
        == "confirmed"
    )


async def test_create_self_authorized_inserts_executed_row_without_committing(session, user_a):
    """WRITE_TRIVIAL audit row (specs/035): terminal state, no pending window."""
    repo = ActionProposalsRepository(session)

    record = await repo.create_self_authorized(
        user_a, "remember_note", {"content": "leche y pan"}
    )

    assert record["status"] == "executed"
    assert record["consent_mode"] == "self_authorized"
    assert record["payload"] == {"content": "leche y pan"}

    row = (
        await session.execute(
            text(
                "SELECT status, consent_mode, confirming_interaction_id,"
                " completed_at, executed_at FROM ancora.action_proposals WHERE id = :id"
            ),
            {"id": record["id"]},
        )
    ).one()
    assert row.status == "executed"
    assert row.consent_mode == "self_authorized"
    assert row.confirming_interaction_id is None
    assert row.completed_at is not None
    assert row.executed_at is not None

    # Never pending_confirmation at any point: nothing to claim/confirm later.
    assert await repo.get_pending(user_a, record["id"]) is None

    await session.rollback()
    assert (
        await session.scalar(
            text("SELECT 1 FROM ancora.action_proposals WHERE id = :id"),
            {"id": record["id"]},
        )
        is None
    ), "create_self_authorized must not commit on its own"


async def test_create_self_authorized_never_collides_on_null_confirming_interaction(
    session, user_a
):
    """Several self_authorized rows share NULL confirming_interaction_id safely.

    ``uq_action_proposals_confirming_interaction`` is a partial unique index on
    ``NOT NULL`` values, so this must not raise even though a real "Sí" could
    never authorise two proposals the same way.
    """
    repo = ActionProposalsRepository(session)

    first = await repo.create_self_authorized(user_a, "remember_note", {"content": "leche"})
    second = await repo.create_self_authorized(user_a, "remember_note", {"content": "pan"})
    await session.commit()

    assert first["id"] != second["id"]
    rows = (
        await session.execute(
            text(
                "SELECT confirming_interaction_id FROM ancora.action_proposals"
                " WHERE id = ANY(:ids)"
            ),
            {"ids": [first["id"], second["id"]]},
        )
    ).fetchall()
    assert all(row.confirming_interaction_id is None for row in rows)
