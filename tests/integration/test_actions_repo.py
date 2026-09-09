"""Integration tests for ActionProposalsRepository against real PostgreSQL (specs/009)."""

import pytest
from sqlalchemy import text

from src.domain.documents.models import DocumentCreate
from src.repositories.actions import ActionProposalsRepository
from src.repositories.documents import DocumentsRepository

pytestmark = pytest.mark.integration


async def test_governance_lifecycle(session, user_a):
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

    confirmed = await repo.confirm(user_a, proposal_id)
    assert confirmed is not None
    assert confirmed["status"] == "confirmed"

    # Once confirmed it is no longer pending; a second confirm is a no-op
    assert await repo.get_pending(user_a, proposal_id) is None
    assert await repo.confirm(user_a, proposal_id) is None

    await repo.mark_executed(user_a, proposal_id)

    row = (
        await session.execute(
            text("SELECT status, confirmed_at, executed_at FROM ancora.action_proposals"
                 " WHERE id = :id"),
            {"id": proposal_id},
        )
    ).fetchone()
    assert row.status == "executed"
    assert row.confirmed_at is not None
    assert row.executed_at is not None


async def test_governance_is_user_scoped(session, user_a, user_b):
    repo = ActionProposalsRepository(session)

    proposal = await repo.create(user_a, "create_reminder", {"title": "ITV"})
    proposal_id = proposal["id"]

    # User B cannot read, confirm nor execute user A's proposal
    assert await repo.get_pending(user_b, proposal_id) is None
    assert await repo.confirm(user_b, proposal_id) is None
    await repo.mark_executed(user_b, proposal_id)

    assert await repo.get_pending(user_a, proposal_id) is not None
    assert (await repo.get_pending(user_a, proposal_id))["status"] == (
        "pending_confirmation"
    )


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
