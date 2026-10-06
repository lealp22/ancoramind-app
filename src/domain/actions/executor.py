"""Deterministic canonical executor, independent of the Agent runtime."""

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import ClaimedProposal, ProposalStatus, payload_hash
from src.domain.actions.mutations import SUPPORTED_MUTATIONS, apply_mutation
from src.repositories.actions import ActionProposalsRepository
from src.repositories.documents import DocumentsRepository
from src.storage.base import DocumentStorage


class ProposalExecutor:
    """Supported operations commit mutation and terminal audit in one transaction.

    Unsupported operations fail closed BEFORE the confirmation is consumed.
    Extend only with transactional domain services, never legacy execute tools.
    """

    SUPPORTED = SUPPORTED_MUTATIONS | {"delete_document"}

    def __init__(
        self,
        sessions: Callable[[], Awaitable[AsyncSession]],
        *,
        storage: DocumentStorage | None = None,
    ):
        self._sessions = sessions
        self._storage = storage

    async def execute(self, proposal: ClaimedProposal, *, user_id: str) -> str:
        if proposal.tool_name not in self.SUPPORTED:
            return "Esta operación todavía no tiene ejecutor determinista. No se ha ejecutado."
        session = await self._sessions()
        repo = ActionProposalsRepository(session)
        external_started = False
        commit_started = False
        try:
            stored = (
                (
                    await session.execute(
                        text("""
                SELECT tool_name, payload, payload_hash, confirming_interaction_id,
                       source_document_id
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
                or stored["source_document_id"] != proposal.source_document_id
                or stored["payload_hash"] != payload_hash(proposal.tool_name, proposal.payload)
            ):
                await session.rollback()
                return "No pude verificar la propuesta. No se ha ejecutado ninguna operación."
            if not await repo.begin_execution(proposal.id, user_id=user_id):
                return "Esa propuesta ya no está disponible para ejecutar."
            if proposal.source_document_id is not None:
                source = await session.scalar(
                    text("SELECT id FROM ancora.documents WHERE id=:id AND user_id=:uid"),
                    {"id": proposal.source_document_id, "uid": user_id},
                )
                if source is None:
                    raise ValueError("source_document_not_owned")
            if proposal.tool_name == "delete_document":
                from uuid import UUID

                if self._storage is None:
                    raise ValueError("document_storage_unavailable")
                documents = DocumentsRepository(session, auto_commit=False)
                document_id = UUID(proposal.payload["document_id"])
                # Hold the target until the execution intent is durable.
                await session.execute(
                    text(
                        "SELECT id FROM ancora.documents WHERE id=:id AND user_id=:uid FOR UPDATE"
                    ),
                    {"id": document_id, "uid": user_id},
                )
                document = await documents.get_by_id(user_id, document_id)
                if document is None:
                    raise ValueError("document_not_owned")
                await session.commit()
                external_started = True
                # No replay once this durable intent has committed. A crash may
                # leave executing; operators reconcile rather than retry deletion.
                await self._storage.delete(document.storage_key)
                if not await documents.delete(user_id, document_id):
                    raise RuntimeError("document_delete_transition_failed")
                reply = "✅ Documento eliminado."
            else:
                reply = await apply_mutation(session, proposal, user_id)
            if not await repo.complete_execution(
                proposal.id, user_id=user_id, status=ProposalStatus.EXECUTED
            ):
                raise RuntimeError("proposal_execution_transition_failed")
            commit_started = True
            await session.commit()
            return reply
        except Exception:
            await session.rollback()
            if external_started or await repo.begin_execution(proposal.id, user_id=user_id):
                await repo.complete_execution(
                    proposal.id,
                    user_id=user_id,
                    status=(
                        ProposalStatus.FAILED_AMBIGUOUS
                        if external_started or commit_started
                        else ProposalStatus.FAILED_DEFINITIVE
                    ),
                    failure_reason="proposal_execution_failed",
                )
                await session.commit()
            return "No pude verificar la ejecución. No se reintentará automáticamente."
        finally:
            await session.close()
