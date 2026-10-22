"""Calendar tools — thin Agno tool adapters with action proposal governance."""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from agno.run import RunContext

from src.agent.calendar_caldav import create_calendar_provider
from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_RESULT_RECORDS,
    MAX_TITLE_CHARS,
    bounded_text,
    render_retrieved_records,
)
from src.agent.tools.validation import (
    INVALID_RECURRENCE,
    internal_error_reply,
    invalid_proposal_reply,
    parse_optional_uuid,
)
from src.domain.calendar.models import CalendarEvent
from src.domain.calendar.service import CalendarService
from src.domain.preferences.display import format_temporal
from src.domain.preferences.timezone import (
    AmbiguousOrNonExistentTimeError,
    resolve_user_timezone,
    to_utc,
)
from src.domain.reminders.service import ReminderService
from src.domain.shared.recurrence import recurrence_rule_from_flat, recurrence_rule_to_flat
from src.repositories.actions import ActionProposalsRepository
from src.repositories.calendar import CalendarRepository
from src.repositories.database import get_session
from src.repositories.reminders import RemindersRepository
from src.security.user_context import UserContext

logger = logging.getLogger(__name__)


async def _get_calendar_service() -> CalendarService:
    from src.config import Settings

    session = track_session(await get_session())
    return CalendarService(CalendarRepository(session), create_calendar_provider(Settings()))


async def _get_reminder_service() -> ReminderService:
    session = track_session(await get_session())
    return ReminderService(RemindersRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


@closes_sessions
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
    tz = resolve_user_timezone(user_ctx)
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

    # start_dt/end_dt may be naive (local wall-clock, specs/023 T5.2/T5.3) —
    # normalize to UTC for the query, but keep the originals for the "sin
    # eventos" message so it echoes exactly what the user asked for.
    try:
        start_query = to_utc(start_dt, tz)
        end_query = to_utc(end_dt, tz)
    except AmbiguousOrNonExistentTimeError:
        return (
            "La fecha indicada no existe o es ambigua por el cambio de horario "
            "de verano/invierno. Especifica un offset UTC explícito u otra hora."
        )

    events = await service.check_calendar(user_ctx, start_query, end_query)

    if not events:
        return f"No tienes eventos entre {start_dt:%Y-%m-%d} y {end_dt:%Y-%m-%d}."

    bounded_events = events[:MAX_RESULT_RECORDS]
    records: list[dict[str, object]] = []
    for event in bounded_events:
        title, title_truncated = bounded_text(event.title, MAX_TITLE_CHARS)
        local_start = format_temporal(event.start_at, tz)
        record: dict[str, object] = {
            "source": "calendar_event",
            "id": str(event.id),
            "title": title,
            "title_truncated": title_truncated,
            "start_at": local_start,
            "end_at": (
                format_temporal(event.end_at, tz)
                if event.end_at
                else None
            ),
            "recurring": bool(event.recurrence_rule),
        }
        if event.location:
            location, location_truncated = bounded_text(event.location, MAX_TITLE_CHARS)
            record["location"] = location
            record["location_truncated"] = location_truncated
        records.append(record)
    return render_retrieved_records("check_calendar", records, len(events))


@closes_sessions
async def propose_calendar_event(
    run_context: RunContext,
    title: str,
    start_at: str,
    end_at: str | None = None,
    description: str | None = None,
    location: str | None = None,
    source_document_id: str | None = None,
    recurrence_frequency: str | None = None,
    recurrence_interval: int | None = None,
    recurrence_until: str | None = None,
    with_reminder: bool = False,
    reminder_lead_minutes: int = 0,
) -> str:
    """PROPOSE a calendar event — requires user confirmation (EXTERNAL_ACTION).

    Use when the user wants to add something to their calendar:
    - "Tengo dentista el jueves a las 17:30"
    - "Añade reunión el lunes a las 10"
    - "Cada año el 15 de marzo es mi cumpleaños, recuérdamelo"
    - "Clase de yoga todos los lunes" / "Revisión del coche cada 6 meses"

    Args:
        run_context: Injected by Agno.
        title: Event title.
        start_at: Start datetime ISO 8601.
        end_at: Optional end datetime ISO 8601.
        description: Optional details.
        location: Optional location.
        source_document_id: Optional source document.
        recurrence_frequency: Optional — "daily", "weekly", "monthly" or
            "yearly" for a repeating event (e.g. "cada año el 15 de marzo
            es mi cumpleaños" -> "yearly"; "cada 6 meses" -> "monthly" +
            interval=6; "clase todos los lunes" -> "weekly"). Omit for a
            one-off event.
        recurrence_interval: Optional integer 1-365 — repeat every N units (default 1).
        recurrence_until: Optional inclusive upper bound as a timezone-aware ISO 8601 datetime
            with an explicit offset or Z, e.g. '2026-11-15T10:00:00+01:00';
            not a date-only or naive value. Preserve the supplied time and offset.
            Omit for open-ended recurrence. Ask for clarification if time or zone is unclear.
        with_reminder: If True, also create a Telegram reminder linked to
            this event (same recurrence), so the user is notified each
            time it occurs — use when the user implies they want to be
            notified, not just have it listed in the calendar (e.g.
            "recuérdame cada año el cumpleaños de mi madre" -> True).
        reminder_lead_minutes: Optional — notify this many minutes before
            start_at instead of exactly at start_at (default 0).

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

    src_doc = parse_optional_uuid(source_document_id, "documento")
    if isinstance(src_doc, str):
        return src_doc

    try:
        rule = recurrence_rule_from_flat(
            recurrence_frequency, recurrence_interval, recurrence_until
        )
    except (ValueError, TypeError):
        return INVALID_RECURRENCE

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="create_calendar_event",
        payload={
            "title": title,
            "start_at": start_at,
            "end_at": end_at,
            "description": description,
            "location": location,
            "source_document_id": str(src_doc) if src_doc else None,
            "with_reminder": with_reminder,
            "reminder_lead_minutes": reminder_lead_minutes,
            **recurrence_rule_to_flat(rule),
        },
        source_document_id=src_doc,
    )

    display_start = format_temporal(start_dt, resolve_user_timezone(user_ctx), allow_date=False)
    lines = [
        f"📅 **Propuesta de evento** (`{proposal['id']}`)",
        f"   Título: {title}",
        f"   Inicio: {display_start}",
    ]
    if end_dt:
        lines.append(f"   Fin: {format_temporal(end_dt, resolve_user_timezone(user_ctx))}")
    if location:
        lines.append(f"   📍 {location}")
    if rule:
        lines.append(f"   🔁 Se repite: {rule.frequency.value} (cada {rule.interval})")
    if with_reminder:
        lines.append("   ⏰ Se creará también un recordatorio vinculado")
    lines.append("\n¿Confirmas añadir este evento al calendario?")
    return "\n".join(lines)


@closes_sessions
async def execute_calendar_event(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed calendar event proposal.

    Only call after user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_calendar_event.

    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_calendar_service()
    try:
        rule = recurrence_rule_from_flat(
            payload.get("recurrence_frequency"),
            payload.get("recurrence_interval"),
            payload.get("recurrence_until"),
        )
        event = await service.create_event(
            user_context=user_ctx,
            title=payload["title"],
            start_at=datetime.fromisoformat(payload["start_at"]),
            end_at=datetime.fromisoformat(payload["end_at"]) if payload.get("end_at") else None,
            description=payload.get("description"),
            location=payload.get("location"),
            source_document_id=UUID(payload["source_document_id"])
            if payload.get("source_document_id")
            else None,
            recurrence_rule=rule,
        )
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        local_start = format_temporal(event.start_at, resolve_user_timezone(user_ctx))
        lines = [
            f"✅ **Evento añadido al calendario**: {event.title}",
            f"   Inicio: {local_start}",
            f"   ID: `{event.id}`",
        ]
        if payload.get("with_reminder"):
            lines.append(await _create_linked_reminder(user_ctx, event, payload))
        return "\n".join(lines)
    except (KeyError, TypeError, ValueError) as e:
        return invalid_proposal_reply("execute_calendar_event", e)
    except Exception as e:
        return internal_error_reply("execute_calendar_event", e)


async def _create_linked_reminder(
    user_ctx: UserContext, event: CalendarEvent, payload: dict[str, Any]
) -> str:
    """Create a reminder linked to a just-created event (if `with_reminder`).

    Separate commit from the event's — this codebase has no cross-repository
    transactions (every repo method commits on its own), so a crash between
    the two leaves the event without its reminder. Accepted limitation
    (specs/024): on failure here, the event itself is still reported as
    created, with this line explaining what did not happen, instead of a
    generic error masking the partial success.
    """
    try:
        lead_minutes = int(payload.get("reminder_lead_minutes") or 0)
        rule = recurrence_rule_from_flat(
            payload.get("recurrence_frequency"),
            payload.get("recurrence_interval"),
            payload.get("recurrence_until"),
        )
        reminder_service = await _get_reminder_service()
        reminder = await reminder_service.create_reminder(
            user_context=user_ctx,
            title=f"Recordatorio: {event.title}",
            trigger_at=event.start_at - timedelta(minutes=lead_minutes),
            source_document_id=event.source_document_id,
            recurrence_rule=rule,
        )
        return f"   ⏰ Recordatorio vinculado creado: `{reminder.id}`"
    except Exception:
        logger.exception("No se pudo crear el recordatorio vinculado al evento")
        return "   ⚠️ El evento se creó, pero no se pudo crear el recordatorio vinculado."
