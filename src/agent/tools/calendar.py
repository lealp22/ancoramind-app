"""Calendar tools — thin Agno tool adapters with action proposal governance."""

from datetime import datetime
from uuid import UUID

from agno.run import RunContext

from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.calendar import CalendarRepository
from src.repositories.database import get_session
from src.security.user_context import UserContext


async def _get_calendar_service():
    session = await get_session()
    return CalendarService(CalendarRepository(session), NoopCalendarProvider())


async def _get_actions_repo():
    session = await get_session()
    return ActionProposalsRepository(session)


async def check_calendar(
    run_context: RunContext,
    start: str,
    end: str | None = None,
) -> str:
    """Check your calendar for a date or date range.

    Use when the user asks about their schedule:
    - "¿Qué tengo esta semana?"
    - "¿Qué tengo el jueves?"

    Args:
        run_context: Injected by Agno.
        start: Start datetime ISO 8601 (e.g. '2026-08-24T00:00:00').
        end: Optional end datetime. Defaults to end of the same day.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_calendar_service()

    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return f"Fecha de inicio no válida: {start}. Usa ISO 8601."

    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            return f"Fecha de fin no válida: {end}. Usa ISO 8601."
    else:
        end_dt = start_dt.replace(hour=23, minute=59, second=59)

    events = await service.check_calendar(user_ctx, start_dt, end_dt)

    if not events:
        return f"No tienes eventos entre {start_dt:%Y-%m-%d} y {end_dt:%Y-%m-%d}."

    lines = [f"📅 **Eventos** ({len(events)}):\n"]
    for e in events:
        start_str = e.start_at.strftime("%Y-%m-%d %H:%M")
        end_str = f" → {e.end_at.strftime('%H:%M')}" if e.end_at else ""
        lines.append(f"- **{e.title}** — {start_str}{end_str}")
        if e.location:
            lines.append(f"   📍 {e.location}")
    return "\n".join(lines)


async def propose_calendar_event(
    run_context: RunContext,
    title: str,
    start_at: str,
    end_at: str | None = None,
    description: str | None = None,
    location: str | None = None,
    source_document_id: str | None = None,
) -> str:
    """PROPOSE a calendar event — requires user confirmation (EXTERNAL_ACTION).

    Use when the user wants to add something to their calendar:
    - "Tengo dentista el jueves a las 17:30"
    - "Añade reunión el lunes a las 10"

    Args:
        run_context: Injected by Agno.
        title: Event title.
        start_at: Start datetime ISO 8601.
        end_at: Optional end datetime ISO 8601.
        description: Optional details.
        location: Optional location.
        source_document_id: Optional source document.
    """
    user_ctx = UserContext.from_run_context(run_context)

    try:
        start_dt = datetime.fromisoformat(start_at)
    except ValueError:
        return f"Fecha de inicio no válida: {start_at}. Usa ISO 8601."

    end_dt = None
    if end_at:
        try:
            end_dt = datetime.fromisoformat(end_at)
        except ValueError:
            return f"Fecha de fin no válida: {end_at}. Usa ISO 8601."

    src_doc = UUID(source_document_id) if source_document_id else None

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="create_calendar_event",
        payload={
            "title": title, "start_at": start_at, "end_at": end_at,
            "description": description, "location": location,
            "source_document_id": str(src_doc) if src_doc else None,
        },
        source_document_id=src_doc,
    )

    lines = [
        f"📅 **Propuesta de evento** (`{proposal['id']}`)",
        f"   Título: {title}",
        f"   Inicio: {start_dt.strftime('%Y-%m-%d %H:%M')}",
    ]
    if end_dt:
        lines.append(f"   Fin: {end_dt.strftime('%H:%M')}")
    if location:
        lines.append(f"   📍 {location}")
    lines.append("\n¿Confirmas añadir este evento al calendario?")
    return "\n".join(lines)


async def execute_calendar_event(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed calendar event proposal.

    Only call after user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_calendar_event.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_calendar_service()
    try:
        event = await service.create_event(
            user_context=user_ctx,
            title=payload["title"],
            start_at=datetime.fromisoformat(payload["start_at"]),
            end_at=datetime.fromisoformat(payload["end_at"])
            if payload.get("end_at") else None,
            description=payload.get("description"),
            location=payload.get("location"),
            source_document_id=UUID(payload["source_document_id"])
            if payload.get("source_document_id") else None,
        )
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        return (
            f"✅ **Evento añadido al calendario**: {event.title}\n"
            f"   Inicio: {event.start_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"   ID: `{event.id}`"
        )
    except Exception as e:
        return f"❌ Error al crear evento: {str(e)[:200]}"