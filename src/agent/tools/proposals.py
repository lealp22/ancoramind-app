"""Read tool for the Agent to see real action-proposal state (BL-47).

The Agent must never narrate "what's pending" from its own conversational
memory — a proposal it mentioned earlier in the chat may already be
executed or have expired, and the model has no way to know that from its
own history. ``list_pending_proposals`` is the one READ tool over
``action_proposals`` the Agent can call to get the truth instead of
guessing, exactly like every other read tool wraps its result in
``untrusted_results`` and never claims, confirms or mutates anything.
"""

import json

from agno.run import RunContext

from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_RESULT_RECORDS,
    MAX_SUMMARY_CHARS,
    bounded_text,
    render_retrieved_records,
)
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.security.user_context import UserContext


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


def _pending_proposal_record(proposal: dict[str, object]) -> dict[str, object]:
    summary, truncated = bounded_text(
        json.dumps(proposal["payload"], ensure_ascii=True), MAX_SUMMARY_CHARS
    )
    return {
        "source": "pending_proposal",
        "id": proposal["id"],
        "tool_name": proposal["tool_name"],
        "payload_summary": summary,
        "payload_summary_truncated": truncated,
        "created_at": proposal["created_at"],
        "expires_at": proposal["expires_at"],
    }


@closes_sessions
async def list_pending_proposals(run_context: RunContext) -> str:
    """List action proposals genuinely awaiting the user's confirmation right now.

    Use this tool whenever the user asks what's pending ("¿qué tengo
    pendiente de confirmar?", "¿qué propuestas me quedan?") or right after a
    confirmation attempt failed (not found / already expired). NEVER answer
    that question from your own memory of this conversation — a proposal you
    mentioned earlier may already be executed or expired by now; this tool
    is the only way to know the real state.

    Args:
        run_context: Injected by Agno.

    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    pending = await actions_repo.list_pending(user_ctx.user_id)
    if not pending:
        return "No tienes ninguna propuesta pendiente de confirmar ahora mismo."

    records = [_pending_proposal_record(p) for p in pending[:MAX_RESULT_RECORDS]]
    return render_retrieved_records("list_pending_proposals", records, len(pending))
