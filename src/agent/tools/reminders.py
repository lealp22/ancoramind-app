"""Reminder tools — thin Agno tool adapters with action proposal governance."""

from datetime import datetime
from uuid import UUID

from agno.run import RunContext

from src.domain.reminders.service import ReminderService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.reminders import RemindersRepository
from src.security.user_context import UserContext


async def _get_reminder_service() -> ReminderService:
    session = await get_session()
    return ReminderService(RemindersRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = await get_session()
    return ActionProposalsRepository(session)


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
    service = await _get_reminder_service()
    reminders = await service.list_reminders(user_ctx, status)

    if not reminders:
        return "No tienes recordatorios" + (f" con estado '{status}'." if status else ".")

    lines = [f"⏰ **Recordatorios** ({len(reminders)}):\n"]
    for r in reminders:
        trigger = r.trigger_at.strftime("%Y-%m-%d %H:%M")
        status_icon = {"pending": "⏳", "fired": "✅", "dismissed": "❌"}.get(r.status, "")
        lines.append(f"{status_icon} **{r.title}** — {trigger} [{r.status}]")
        if r.description:
            lines.append(f"   {r.description}")
    return "\n".join(lines)


async def propose_reminder(
    run_context: RunContext,
    title: str,
    trigger_at: str,
    description: str | None = None,
    source_document_id: str | None = None,
) -> str:
    """PROPOSE a reminder — requires user confirmation.

    Use when the user wants to be reminded of something:
    - "Recuérdame llamar al dentista el jueves a las 17:00"
    - "Avísame de la revisión del coche en 2 semanas"

    Args:
        run_context: Injected by Agno.
        title: Reminder title.
        trigger_at: ISO 8601 datetime (e.g. '2026-08-28T17:00:00').
        description: Optional details.
        source_document_id: Optional source document.
    """
    user_ctx = UserContext.from_run_context(run_context)

    try:
        parsed = datetime.fromisoformat(trigger_at)
    except ValueError:
        return f"Fecha no válida: {trigger_at}. Usa formato ISO 8601 (YYYY-MM-DDTHH:MM)."

    src_doc = UUID(source_document_id) if source_document_id else None

    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="create_reminder",
        payload={
            "title": title,
            "trigger_at": trigger_at,
            "description": description,
            "source_document_id": str(src_doc) if src_doc else None,
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
    lines.append("\n¿Confirmas la creación de este recordatorio?")
    return "\n".join(lines)


async def execute_reminder(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed reminder proposal.

    Only call after user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_reminder.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    service = await _get_reminder_service()
    try:
        reminder = await service.create_reminder(
            user_context=user_ctx,
            title=payload["title"],
            trigger_at=datetime.fromisoformat(payload["trigger_at"]),
            description=payload.get("description"),
            source_document_id=UUID(payload["source_document_id"])
            if payload.get("source_document_id")
            else None,
        )
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        return (
            f"✅ **Recordatorio creado**: {reminder.title}\n"
            f"   Cuándo: {reminder.trigger_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"   ID: `{reminder.id}`"
        )
    except (KeyError, TypeError, ValueError) as e:
        return f"❌ Datos de propuesta no válidos: {str(e)[:200]}"
    except Exception as e:
        return f"❌ Error al crear recordatorio: {str(e)[:200]}"
