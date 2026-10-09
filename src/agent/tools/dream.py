"""Dream preference tools — thin Agno adapters for DreamPreferenceService.

(specs/029 §6, T5) ``list_my_preferences`` is READ. Forgetting a preference is DESTRUCTIVE and
follows the same propose/execute pattern as every other governed mutation
(AGENTS.md §2.4) — ``propose_preference_forget``/``execute_preference_forget``
never write directly from the model's call.
"""

from uuid import UUID

from agno.run import RunContext

from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_RESULT_RECORDS,
    MAX_SUMMARY_CHARS,
    bounded_text,
    render_retrieved_records,
)
from src.agent.tools.validation import internal_error_reply, invalid_proposal_reply, parse_uuid
from src.domain.dream.preferences import DreamPreferenceService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.dream_candidates import DreamCandidatesRepository
from src.security.user_context import UserContext


async def _get_preference_service() -> DreamPreferenceService:
    session = track_session(await get_session())
    return DreamPreferenceService(DreamCandidatesRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


@closes_sessions
async def list_my_preferences(run_context: RunContext) -> str:
    """List the user's confirmed preferences learned from past conversations.

    Use when the user asks what you know or remember about their habits or
    preferences:
    - "¿Qué sabes de mí?"
    - "¿Qué preferencias tienes guardadas?"
    - "¿Recuerdas cómo prefiero las respuestas?"

    Only confirmed (active) preferences are returned — tentative ones still
    being corroborated across conversations are never shown as settled fact.

    Args:
        run_context: Injected by Agno — contains session and user info.

    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_preference_service()
    preferences = await service.list_preferences(user_ctx)

    if not preferences:
        return "No tengo ninguna preferencia confirmada guardada todavía."

    records: list[dict[str, object]] = []
    for candidate in preferences[:MAX_RESULT_RECORDS]:
        value, truncated = bounded_text(candidate.value, MAX_SUMMARY_CHARS)
        records.append(
            {
                "source": "dream_preference",
                "id": str(candidate.id),
                "category": candidate.category.value,
                "key": candidate.key,
                "value": value,
                "value_truncated": truncated,
                "confidence": candidate.confidence,
            }
        )
    return render_retrieved_records("list_my_preferences", records, len(preferences))


@closes_sessions
async def propose_preference_forget(
    run_context: RunContext, candidate_id: str | None = None
) -> str:
    """PROPOSE forgetting one learned preference, or all of them — requires confirmation.

    Use when the user wants you to stop remembering a preference:
    - "Olvida que prefiero respuestas cortas"
    - "Olvida todo lo que sabes de mí"

    Args:
        run_context: Injected by Agno.
        candidate_id: The preference UUID to forget (from list_my_preferences),
            or omit/None to forget every confirmed preference.

    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed_id: str | None = None
    if candidate_id is not None and candidate_id.strip():
        parsed = parse_uuid(candidate_id, "preferencia")
        if isinstance(parsed, str):
            return parsed
        parsed_id = str(parsed)

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="forget_dream_preference",
        payload={"candidate_id": parsed_id},
    )
    scope = f"la preferencia `{parsed_id}`" if parsed_id else "**todas** tus preferencias guardadas"
    return (
        f"🗑️ **Propuesta de olvido** (`{proposal['id']}`)\n"
        f"   Vas a olvidar {scope}.\n"
        "\n¿Confirmas? Esta acción no se puede deshacer."
    )


@closes_sessions
async def execute_preference_forget(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed preference-forget proposal.

    Only call after the user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_preference_forget.

    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_preference_service()
    try:
        candidate_id = payload.get("candidate_id")
        if candidate_id is not None:
            forgotten = await service.forget(user_ctx, UUID(candidate_id))
            if not forgotten:
                return f"No encontré la preferencia `{candidate_id}`."
            await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
            return "✅ Preferencia olvidada."
        count = await service.forget(user_ctx, None)
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        return f"✅ Olvidadas {count} preferencia(s)."
    except (KeyError, TypeError, ValueError) as e:
        return invalid_proposal_reply("execute_preference_forget", e)
    except Exception as e:
        return internal_error_reply("execute_preference_forget", e)
