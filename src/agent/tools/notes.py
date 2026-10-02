"""Note tools — thin Agno tool adapters for NotesService.

These are plain Python functions. Agno auto-converts them to tools.
The `run_context` parameter is injected automatically by Agno.

Writing a note is governed (specs/023 T4.6, AGENTS.md §2.4): the previous
``remember_note`` wrote directly from the model's call, with no ActionProposal
and no human confirmation. ``propose_note``/``execute_note`` follow the same
propose/confirm pattern as every other WRITE tool.
"""

from agno.run import RunContext

from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_NOTE_CHARS,
    MAX_RESULT_RECORDS,
    bounded_text,
    render_retrieved_records,
)
from src.agent.tools.validation import internal_error_reply, invalid_proposal_reply
from src.domain.notes.service import NotesService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.notes import NotesRepository
from src.security.user_context import UserContext


async def _get_notes_service() -> NotesService:
    """Create a NotesService with a fresh, call-scoped database session."""
    session = track_session(await get_session())
    repository = NotesRepository(session)
    return NotesService(repository)


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


@closes_sessions
async def propose_note(run_context: RunContext, content: str) -> str:
    """PROPOSE storing a personal note — requires user confirmation.

    Use when the user explicitly asks you to remember something:
    - "Recuerda que la plaza del garaje es la 42"
    - "Apúntame que el código de la puerta es 7743"
    - "Guarda que mi médico se llama Dr. Martínez"

    Args:
        run_context: Injected by Agno — contains session and user info.
        content: The information to remember.
    """
    user_ctx = UserContext.from_run_context(run_context)
    if not content or not content.strip():
        return "Dime qué quieres que recuerde."

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="remember_note",
        payload={"content": content.strip()},
    )
    return (
        f"📝 **Propuesta de nota** (`{proposal['id']}`)\n"
        f"   {content.strip()}\n"
        "\n¿Confirmas que la guarde?"
    )


@closes_sessions
async def execute_note(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed note proposal.

    Only call after user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_note.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_notes_service()
    try:
        note = await service.remember(user_ctx, payload["content"])
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        return f"✅ Nota guardada (id: `{note.id}`). Puedes buscarla después con search_notes."
    except (KeyError, TypeError, ValueError) as e:
        return invalid_proposal_reply("execute_note", e)
    except Exception as e:
        return internal_error_reply("execute_note", e)


@closes_sessions
async def search_notes(
    run_context: RunContext,
    query: str | None = None,
) -> str:
    """Search personal notes previously stored by the user.

    Use this tool when the user asks about something they previously
    told you to remember:
    - "¿Qué plaza de garaje tengo?"
    - "¿Cuál era el código de la puerta?"
    - "¿Cómo se llamaba mi médico?"

    Args:
        run_context: Injected by Agno — contains session and user info.
        query: Optional search term. If omitted, returns recent notes.

    Returns:
        Formatted list of matching notes, or a message if none found.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_notes_service()
    notes = await service.search(user_ctx, query)

    if not notes:
        return "No encontré notas que coincidan con la búsqueda." if query else "No encontré notas."

    records: list[dict[str, object]] = []
    for note in notes[:MAX_RESULT_RECORDS]:
        content, truncated = bounded_text(note.content, MAX_NOTE_CHARS)
        records.append(
            {
                "source": "canonical_note",
                "id": str(note.id),
                "created_at": note.created_at.isoformat(),
                "content": content,
                "content_truncated": truncated,
            }
        )
    return render_retrieved_records("search_notes", records, len(notes))

