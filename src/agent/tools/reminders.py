"""Reminder tools — thin Agno tool adapters with action proposal governance."""

from datetime import datetime
from uuid import UUID

from agno.run import RunContext

from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.untrusted_results import (
    MAX_RESULT_RECORDS,
    MAX_SUMMARY_CHARS,
    MAX_TITLE_CHARS,
    bounded_text,
    render_retrieved_records,
)
from src.agent.tools.validation import (
    internal_error_reply,
    invalid_proposal_reply,
    parse_optional_uuid,
    parse_uuid,
)
from src.domain.preferences.timezone import resolve_user_timezone, to_local_display
from src.domain.reminders.service import ReminderService
from src.domain.shared.recurrence import recurrence_rule_from_flat, recurrence_rule_to_flat
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.reminders import RemindersRepository
from src.security.user_context import UserContext


async def _get_reminder_service() -> ReminderService:
    session = track_session(await get_session())
    return ReminderService(RemindersRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


@closes_sessions
async def list_reminders(run_context: RunContext, status: str | None = None) -> str:
    """List your reminders.

    Use when the user asks about reminders:
    - "¿Qué recordatorios tengo?"
    - "¿Qué me tengo que acordar?"

    Args:
        run_context: Injected by Agno.
        status: Optional filter (pending, fired, dismissed). Defaults to all.

    """
    user_ctx = UserContext.from_run_context(run_context)
    tz = resolve_user_timezone(user_ctx)
    service = await _get_reminder_service()
    reminders = await service.list_reminders(user_ctx, status)

    if not reminders:
        return "No tienes recordatorios" + (f" con estado '{status}'." if status else ".")

    bounded = reminders[:MAX_RESULT_RECORDS]
    records: list[dict[str, object]] = []
    for r in bounded:
        title, title_truncated = bounded_text(r.title, MAX_TITLE_CHARS)
        record: dict[str, object] = {
            "source": "reminder",
            "id": str(r.id),
            "title": title,
            "title_truncated": title_truncated,
            "status": r.status,
            "trigger_at": to_local_display(r.trigger_at, tz).strftime("%Y-%m-%d %H:%M"),
            "recurring": bool(r.recurrence_rule),
        }
        if r.description:
            description, description_truncated = bounded_text(r.description, MAX_SUMMARY_CHARS)
            record["description"] = description
            record["description_truncated"] = description_truncated
        records.append(record)
    return render_retrieved_records("list_reminders", records, len(reminders))


@closes_sessions
async def propose_reminder(
    run_context: RunContext,
    title: str,
    trigger_at: str,
    description: str | None = None,
    source_document_id: str | None = None,
    recurrence_frequency: str | None = None,
    recurrence_interval: int | None = None,
    recurrence_until: str | None = None,
) -> str:
    """PROPOSE a reminder — requires user confirmation.

    Use when the user wants to be reminded of something:
    - "Recuérdame llamar al dentista el jueves a las 17:00"
    - "Avísame de la revisión del coche en 2 semanas"
    - "Recuérdame cada año el cumpleaños de mi madre el 10 de mayo"

    Args:
        run_context: Injected by Agno.
        title: Reminder title.
        trigger_at: ISO 8601 datetime (e.g. '2026-08-28T17:00:00').
        description: Optional details.
        source_document_id: Optional source document.
        recurrence_frequency: Optional — "daily", "weekly", "monthly" or
            "yearly" for a repeating reminder. Omit for a one-off.
        recurrence_interval: Optional — repeat every N units (default 1).
        recurrence_until: Optional ISO 8601 date — last date the
            recurrence applies to (open-ended if omitted).

    """
    user_ctx = UserContext.from_run_context(run_context)

    try:
        parsed = datetime.fromisoformat(trigger_at)
    except ValueError:
        return f"Fecha no válida: {trigger_at}. Usa formato ISO 8601 (YYYY-MM-DDTHH:MM)."

    src_doc = parse_optional_uuid(source_document_id, "documento")
    if isinstance(src_doc, str):
        return src_doc

    try:
        rule = recurrence_rule_from_flat(
            recurrence_frequency, recurrence_interval, recurrence_until
        )
    except (ValueError, TypeError):
        return (
            f"Regla de recurrencia no válida: frecuencia={recurrence_frequency!r}. "
            "Usa 'daily', 'weekly', 'monthly' o 'yearly'."
        )

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="create_reminder",
        payload={
            "title": title,
            "trigger_at": trigger_at,
            "description": description,
            "source_document_id": str(src_doc) if src_doc else None,
            **recurrence_rule_to_flat(rule),
        },
        source_document_id=src_doc,
    )

    lines = [
        f"⏰ **Propuesta de recordatorio** (`{proposal['id']}`)",
        f"   Título: {title}",
        f"   Cuándo: {parsed.strftime('%Y-%m-%d %H:%M')}",
    ]
    if description:
        lines.append(f"   Detalle: {description}")
    if rule:
        lines.append(f"   🔁 Se repite: {rule.frequency.value} (cada {rule.interval})")
    lines.append("\n¿Confirmas la creación de este recordatorio?")
    return "\n".join(lines)


@closes_sessions
async def execute_reminder(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed reminder proposal.

    Only call after user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_reminder.

    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_reminder_service()
    try:
        rule = recurrence_rule_from_flat(
            payload.get("recurrence_frequency"),
            payload.get("recurrence_interval"),
            payload.get("recurrence_until"),
        )
        reminder = await service.create_reminder(
            user_context=user_ctx,
            title=payload["title"],
            trigger_at=datetime.fromisoformat(payload["trigger_at"]),
            description=payload.get("description"),
            source_document_id=UUID(payload["source_document_id"])
            if payload.get("source_document_id")
            else None,
            recurrence_rule=rule,
        )
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        local_trigger = to_local_display(reminder.trigger_at, resolve_user_timezone(user_ctx))
        return (
            f"✅ **Recordatorio creado**: {reminder.title}\n"
            f"   Cuándo: {local_trigger.strftime('%Y-%m-%d %H:%M')}"
        )
    except (KeyError, TypeError, ValueError) as e:
        return invalid_proposal_reply("execute_reminder", e)
    except Exception as e:
        return internal_error_reply("execute_reminder", e)


def _format_snooze_duration(minutes: int) -> str:
    """Render a validated snooze duration compactly for a confirmation reply."""
    hours, remaining_minutes = divmod(minutes, 60)
    if hours == 0:
        return f"{minutes} min"
    if remaining_minutes == 0:
        return f"{hours} h"
    return f"{hours} h {remaining_minutes} min"


@closes_sessions
async def propose_reminder_snooze(run_context: RunContext, reminder_id: str, minutes: int) -> str:
    """PROPOSE snoozing a reminder — requires user confirmation.

    Use when the user wants to be reminded again later about something,
    typically right after seeing it in list_reminders (e.g. a reminder that
    just fired):
    - "Recuérdamelo dentro de 20 minutos"
    - "Avísame otra vez en 1 hora y media"
    - "Posponlo 1 hora"

    This is independent of any recurrence the reminder has (e.g. snoozing a
    yearly birthday reminder a few hours does not change when it fires next
    year).

    Args:
        run_context: Injected by Agno.
        reminder_id: ID of the reminder to snooze (from list_reminders).
        minutes: How many minutes from now to re-notify (5-10,080).

    """
    user_ctx = UserContext.from_run_context(run_context)
    rid = parse_uuid(reminder_id, "recordatorio")
    if isinstance(rid, str):
        return rid
    if not (5 <= minutes <= 10_080):
        return "El aplazamiento debe estar entre 5 minutos y 7 días."

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="snooze_reminder",
        payload={"reminder_id": str(rid), "minutes": minutes},
    )
    return (
        f"⏰ **Propuesta de aplazamiento** (`{proposal['id']}`)\n"
        f"   Recordatorio: `{rid}`\n"
        f"   Repetir en: {_format_snooze_duration(minutes)}\n\n"
        "¿Confirmas posponer este recordatorio?"
    )


@closes_sessions
async def execute_reminder_snooze(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed reminder-snooze proposal.

    Only call after user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_reminder_snooze.

    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_reminder_service()
    try:
        snoozed = await service.snooze_reminder(
            user_context=user_ctx,
            original_id=UUID(payload["reminder_id"]),
            minutes=int(payload["minutes"]),
            proposal_id=UUID(proposal_id),
        )
        if snoozed is None:
            return "No se encontró ese recordatorio o no te pertenece."
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        local_trigger = to_local_display(snoozed.trigger_at, resolve_user_timezone(user_ctx))
        return (
            f"✅ **Recordatorio aplazado**: {snoozed.title}\n"
            f"   Próximo aviso: {local_trigger.strftime('%Y-%m-%d %H:%M')}"
        )
    except (KeyError, TypeError, ValueError) as e:
        return invalid_proposal_reply("execute_reminder_snooze", e)
    except Exception as e:
        return internal_error_reply("execute_reminder_snooze", e)
