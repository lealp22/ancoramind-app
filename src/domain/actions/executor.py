"""Deterministic transactional note executor, independent of the Agent runtime."""

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import ClaimedProposal, ProposalStatus, payload_hash
from src.domain.notes.service import NotesService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.notes import NotesRepository
from src.security.user_context import UserContext


class ProposalExecutor:
    """Supported operations commit mutation and terminal audit in one transaction.

    Unsupported operations fail closed BEFORE the confirmation is consumed.
    Extend only with transactional domain services, never legacy execute tools.
    """

    SUPPORTED = frozenset({"remember_note"})

    def __init__(self, sessions: Callable[[], Awaitable[AsyncSession]]):
        self._sessions = sessions

    async def execute(self, proposal: ClaimedProposal, *, user_id: str) -> str:
        if proposal.tool_name not in self.SUPPORTED:
            return "Esta operación todavía no tiene ejecutor determinista. No se ha ejecutado."
        session = await self._sessions()
        repo = ActionProposalsRepository(session)
        try:
            stored = (
                (
                    await session.execute(
                        text("""
                SELECT tool_name, payload, payload_hash, confirming_interaction_id
                FROM ancora.action_proposals
                WHERE id=:id AND user_id=:user_id AND status='confirmed'
                FOR UPDATE
            """),
                        {"id": proposal.id, "user_id": user_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                stored is None
                or stored["tool_name"] != proposal.tool_name
                or stored["confirming_interaction_id"] != proposal.confirming_interaction_id
                or stored["payload"] != proposal.payload
                or stored["payload_hash"] != payload_hash(proposal.tool_name, proposal.payload)
            ):
                await session.rollback()
                return "No pude verificar la propuesta. No se ha ejecutado ninguna operación."
            if not await repo.begin_execution(proposal.id, user_id=user_id):
                return "Esa propuesta ya no está disponible para ejecutar."
            note = await NotesService(NotesRepository(session)).remember(
                UserContext(user_id=user_id),
                proposal.payload["content"],
                commit=False,
            )
            if not await repo.complete_execution(
                proposal.id, user_id=user_id, status=ProposalStatus.EXECUTED
            ):
                raise RuntimeError("proposal_execution_transition_failed")
            await session.commit()
            return f"✅ Nota guardada (id: `{note.id}`)."
        except Exception:
            await session.rollback()
            if await repo.begin_execution(proposal.id, user_id=user_id):
                await repo.complete_execution(
                    proposal.id,
                    user_id=user_id,
                    status=ProposalStatus.FAILED_AMBIGUOUS,
                    failure_reason="note_execution_failed",
                )
                await session.commit()
            return "No pude verificar la ejecución. No se reintentará automáticamente."
        finally:
            await session.close()
