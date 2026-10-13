"""Deterministic executor for the WRITE_TRIVIAL tier (specs/035, BL-46).

Independent of the Agent runtime and of ``ProposalExecutor``'s confirmation
pipeline: there is no proposal to claim here, because the tool layer already
decided the mutation is trivial (same precedent as ``analyze_document``,
specs/023 T4.7 — the user's own request is the signal). Reuses
``apply_mutation()`` so every supported WRITE_TRIVIAL tool is backed by the
exact same domain-service call as its WRITE_REVIEWABLE counterpart; nothing
new is added to ``mutations.py``.
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import ClaimedProposal
from src.domain.actions.mutations import apply_mutation
from src.repositories.actions import ActionProposalsRepository

TRIVIAL_MUTATIONS = frozenset({"create_todo_item", "set_todo_item_status", "remember_note"})
"""The only tool_names TrivialExecutor will run (specs/035 Must Have scope).

Deliberately a strict subset of ``mutations.SUPPORTED_MUTATIONS``: adding a
tool here is a governance decision (WRITE_REVIEWABLE -> WRITE_TRIVIAL), never
an implementation convenience, so it is not inferred from the larger set.
"""


class TrivialExecutor:
    """Mutation + self-authorized audit row commit atomically, no confirmation step.

    Deliberately does not extend ``ProposalExecutor`` nor share its
    ``SUPPORTED`` set: there is no claimed confirmation to revalidate here
    (no ``FOR UPDATE`` on a pre-existing row, no payload-hash tamper check
    against stored evidence), and mixing both state machines in one class
    would complicate the audited reviewable path for no benefit.
    """

    def __init__(self, sessions: Callable[[], Awaitable[AsyncSession]]):
        self._sessions = sessions

    async def execute(self, tool_name: str, payload: dict[str, object], user_id: str) -> str:
        """Run the mutation and its audit row on one transaction.

        A failure before the commit (not owned, unexpected error) rolls back
        and reports nothing executed — there was never a prior proposal row
        to mark failed, so nothing needs to be audited: it never happened.
        """
        if tool_name not in TRIVIAL_MUTATIONS:
            return "Esta operación todavía no tiene ejecutor determinista. No se ha ejecutado."
        session = await self._sessions()
        try:
            # Synthetic claim: apply_mutation() dispatches purely on
            # tool_name/payload and never reads confirming_interaction_id, so
            # this placeholder is never persisted or compared against
            # anything — the mutation's authorization already happened in
            # the tool's own branch decision (trivial vs reviewable), not via
            # a confirmed ActionProposal.
            claimed = ClaimedProposal(
                id=uuid4(),
                tool_name=tool_name,
                payload=payload,
                source_document_id=None,
                confirming_interaction_id=uuid4(),
            )
            reply = await apply_mutation(session, claimed, user_id)
            await ActionProposalsRepository(session).create_self_authorized(
                user_id, tool_name, payload
            )
            await session.commit()
            return reply
        except ValueError:
            await session.rollback()
            return "No encontré ese elemento, o no es tuyo. No se ha ejecutado nada."
        except Exception:
            await session.rollback()
            return "No pude completar la operación. No se reintentará automáticamente."
        finally:
            await session.close()
