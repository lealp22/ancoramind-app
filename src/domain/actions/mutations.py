"""Canonical proposal dispatch on a caller-owned database transaction."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.actions.models import ClaimedProposal
from src.domain.calendar.provider import NoopCalendarProvider
from src.domain.calendar.service import CalendarService
from src.domain.dream.preferences import DreamPreferenceService
from src.domain.notes.service import NotesService
from src.domain.reminders.service import ReminderService
from src.domain.shared.recurrence import recurrence_rule_from_flat
from src.domain.todos.service import TodosService
from src.domain.vehicles.models import VehicleCreate
from src.domain.vehicles.service import VehicleService
from src.repositories.calendar import CalendarRepository
from src.repositories.dream_candidates import DreamCandidatesRepository
from src.repositories.maintenance import MaintenanceRepository
from src.repositories.notes import NotesRepository
from src.repositories.reminders import RemindersRepository
from src.repositories.todos import TodosRepository
from src.repositories.vehicles import VehiclesRepository
from src.security.user_context import UserContext

SUPPORTED_MUTATIONS = frozenset(
    {
        "remember_note",
        "register_vehicle",
        "register_vehicle_maintenance",
        "create_reminder",
        "snooze_reminder",
        "create_calendar_event",
        "create_todo_list",
        "rename_todo_list",
        "delete_todo_list",
        "create_todo_item",
        "update_todo_item",
        "set_todo_item_status",
        "move_todo_item",
        "delete_todo_item",
        "forget_dream_preference",
    }
)


async def apply_mutation(session: AsyncSession, proposal: ClaimedProposal, user_id: str) -> str:
    """Revalidate through domain services; no internal commits or external providers."""
    user = UserContext(user_id=user_id)
    p = proposal.payload
    tool = proposal.tool_name
    result: object
    if tool == "remember_note":
        result = await NotesService(NotesRepository(session)).remember(
            user, p["content"], commit=False
        )
    elif tool in {"register_vehicle", "register_vehicle_maintenance"}:
        vehicles = VehiclesRepository(session, auto_commit=False)
        service = VehicleService(vehicles, MaintenanceRepository(session))
        if tool == "register_vehicle":
            result = await service.register_vehicle(user, VehicleCreate.model_validate(p))
        else:
            vehicle_id = UUID(p["vehicle_id"])
            if await vehicles.get_by_id(user_id, vehicle_id) is None:
                raise ValueError("vehicle_not_owned")
            result = await service.register_maintenance(
                user,
                vehicle_id,
                date.fromisoformat(p["date"]),
                p["description"],
                mileage_km=p.get("mileage_km"),
                workshop=p.get("workshop"),
                cost_amount=Decimal(p["cost_amount"]) if p.get("cost_amount") is not None else None,
                cost_currency=p.get("cost_currency"),
                work_performed=p.get("work_performed"),
                notes=p.get("notes"),
                source_document_id=proposal.source_document_id,
                source_action_id=proposal.id,
                commit=False,
            )
    elif tool in {"create_reminder", "snooze_reminder", "create_calendar_event"}:
        reminders = ReminderService(RemindersRepository(session, auto_commit=False))
        rule = recurrence_rule_from_flat(
            p.get("recurrence_frequency"), p.get("recurrence_interval"), p.get("recurrence_until")
        )
        if tool == "snooze_reminder":
            result = await reminders.snooze_reminder(
                user, UUID(p["reminder_id"]), p["minutes"], proposal.id
            )
        elif tool == "create_reminder":
            result = await reminders.create_reminder(
                user,
                p["title"],
                datetime.fromisoformat(p["trigger_at"]),
                description=p.get("description"),
                source_document_id=proposal.source_document_id,
                source_action_id=proposal.id,
                recurrence_rule=rule,
            )
        else:
            # This executor deliberately covers canonical-only calendar. A real
            # external provider needs a durable external-action protocol first.
            event = await CalendarService(
                CalendarRepository(session, auto_commit=False), NoopCalendarProvider()
            ).create_event(
                user,
                p["title"],
                datetime.fromisoformat(p["start_at"]),
                end_at=datetime.fromisoformat(p["end_at"]) if p.get("end_at") else None,
                description=p.get("description"),
                location=p.get("location"),
                source_document_id=proposal.source_document_id,
                recurrence_rule=rule,
            )
            if p.get("with_reminder"):
                lead = p.get("reminder_lead_minutes", 0)
                if not isinstance(lead, int) or isinstance(lead, bool) or not 0 <= lead <= 10080:
                    raise ValueError("invalid_reminder_lead")
                await reminders.create_reminder(
                    user,
                    f"Recordatorio: {event.title}",
                    event.start_at - timedelta(minutes=lead),
                    source_document_id=proposal.source_document_id,
                    source_action_id=proposal.id,
                    recurrence_rule=rule,
                )
            result = event
    elif tool == "forget_dream_preference":
        preferences = DreamPreferenceService(DreamCandidatesRepository(session, auto_commit=False))
        candidate_id = p.get("candidate_id")
        result = await preferences.forget(user, UUID(candidate_id) if candidate_id else None)
    else:
        todos = TodosService(TodosRepository(session, auto_commit=False))
        if tool == "create_todo_list":
            result = await todos.create_list(user, p["name"])
        elif tool == "rename_todo_list":
            result = await todos.rename_list(user, UUID(p["list_id"]), p["name"])
        elif tool == "delete_todo_list":
            result = await todos.delete_list(user, UUID(p["list_id"]))
        elif tool in {"create_todo_item", "update_todo_item"}:
            kwargs: dict[str, Any] = {
                "description": p.get("description"),
                "priority": p.get("priority"),
                "due_date": datetime.fromisoformat(p["due_date"]) if p.get("due_date") else None,
            }
            if tool == "create_todo_item":
                result = await todos.add_item(user, UUID(p["list_id"]), p["title"], **kwargs)
            else:
                result = await todos.update_item(
                    user, UUID(p["item_id"]), title=p.get("title"), **kwargs
                )
        elif tool == "set_todo_item_status":
            result = await todos.set_item_status(user, UUID(p["item_id"]), p["status"])
        elif tool == "move_todo_item":
            result = await todos.move_item(user, UUID(p["item_id"]), UUID(p["target_list_id"]))
        elif tool == "delete_todo_item":
            result = await todos.delete_item(user, UUID(p["item_id"]))
        else:
            raise ValueError("unsupported_proposal")
    if result is None or result is False:
        raise ValueError("target_missing_or_not_owned")
    return "\u2705 Operaci\u00f3n ejecutada y registrada."
