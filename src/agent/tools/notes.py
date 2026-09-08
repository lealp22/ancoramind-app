"""Note tools — thin Agno tool adapters for NotesService.

These are plain Python functions. Agno auto-converts them to tools.
The `run_context` parameter is injected automatically by Agno.
"""

from agno.run import RunContext

from src.domain.notes.service import NotesService
from src.repositories.database import get_session
from src.repositories.notes import NotesRepository
from src.security.user_context import UserContext


async def _get_notes_service() -> NotesService:
    """Create a NotesService with a fresh database session."""
    session = await get_session()
    repository = NotesRepository(session)
    return NotesService(repository)


async def remember_note(
    run_context: RunContext,
    content: str,
) -> str:
    """Store a personal note in canonical memory.

    Use this tool when the user explicitly asks you to remember something:
    - "Recuerda que la plaza del garaje es la 42"
    - "Apúntame que el código de la puerta es 7743"
    - "Guarda que mi médico se llama Dr. Martínez"

    The note will be stored in AncoraMind's canonical memory (PostgreSQL)
    and can be retrieved later via search_notes.

    Args:
        run_context: Injected by Agno — contains session and user info.
        content: The information to remember.

    Returns:
        Confirmation message.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_notes_service()
    note = await service.remember(user_ctx, content)
    return (
        f"Nota guardada (id: {note.id}). "
        f"Puedes buscarla después con search_notes."
    )


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
        return (
            "No encontré notas"
            + (f' que coincidan con "{query}".' if query else ".")
        )

    lines = []
    for note in notes:
        created = note.created_at.strftime("%Y-%m-%d %H:%M")
        lines.append(f"- [{created}] {note.content}")

    header = (
        f"Encontré {len(notes)} nota(s)"
        + (f' sobre "{query}"' if query else "")
        + ":\n\n"
    )
    return header + "\n".join(lines)
