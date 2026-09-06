"""Action proposals repository — governance layer for WRITE operations."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ActionProposalsRepository:
    """Repository for action proposals (governance layer)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        user_id: str,
        tool_name: str,
        payload: dict,
        source_document_id: UUID | None = None,
    ) -> dict:
        """Create a pending action proposal."""
        import json
        now = datetime.now(tz=timezone.utc)
        stmt = text("""
            INSERT INTO ancora.action_proposals (user_id, tool_name, status, payload, source_document_id, created_at)
            VALUES (:uid,:tool,'pending_confirmation',CAST(:payload AS jsonb),:src,:now)
            RETURNING id,user_id,tool_name,status,payload,source_document_id,created_at
        """)
        result = await self._session.execute(stmt, {
            "uid": user_id, "tool": tool_name, "payload": json.dumps(payload),
            "src": source_document_id, "now": now,
        })
        row = result.fetchone()
        await self._session.commit()
        return {
            "id": str(row.id), "user_id": row.user_id, "tool_name": row.tool_name,
            "status": row.status, "payload": row.payload, "source_document_id": str(row.source_document_id) if row.source_document_id else None,
            "created_at": row.created_at.isoformat(),
        }

    async def get_pending(self, user_id: str, proposal_id: str) -> dict | None:
        """Get a pending proposal by ID."""
        stmt = text("""
            SELECT id,user_id,tool_name,status,payload,source_document_id,created_at
            FROM ancora.action_proposals
            WHERE id=:id AND user_id=:uid AND status='pending_confirmation'
        """)
        result = await self._session.execute(stmt, {"id": UUID(proposal_id), "uid": user_id})
        row = result.fetchone()
        if not row:
            return None
        return {
            "id": str(row.id), "user_id": row.user_id, "tool_name": row.tool_name,
            "status": row.status, "payload": row.payload, "source_document_id": str(row.source_document_id) if row.source_document_id else None,
        }

    async def confirm(self, user_id: str, proposal_id: str) -> dict | None:
        """Confirm a pending proposal."""
        now = datetime.now(tz=timezone.utc)
        stmt = text("""
            UPDATE ancora.action_proposals SET status='confirmed', confirmed_at=:now
            WHERE id=:id AND user_id=:uid AND status='pending_confirmation'
            RETURNING id,user_id,tool_name,status,payload
        """)
        result = await self._session.execute(stmt, {"id": UUID(proposal_id), "uid": user_id, "now": now})
        row = result.fetchone()
        await self._session.commit()
        if not row:
            return None
        return {"id": str(row.id), "tool_name": row.tool_name, "status": row.status, "payload": row.payload}

    async def mark_executed(self, user_id: str, proposal_id: str) -> None:
        """Mark a confirmed proposal as executed."""
        now = datetime.now(tz=timezone.utc)
        stmt = text("UPDATE ancora.action_proposals SET status='executed', executed_at=:now WHERE id=:id AND user_id=:uid")
        await self._session.execute(stmt, {"id": UUID(proposal_id), "uid": user_id, "now": now})
        await self._session.commit()