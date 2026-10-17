"""Deterministic presentation and confirmation controls for governed proposals.

Pure domain code (specs/023 T4.3-T4.4): no Agno, Telegram SDK or SQL.

* ``render_proposal_block`` builds the fixed text appended by the Core to a
  response that created a proposal. It is generated from the **stored**
  payload and optional user-scoped canonical target title, never from the
  model's wording, so what the user confirms is what will be executed.
* ``consent_buttons`` / ``parse_consent_callback`` encode the inline Sí/No
  buttons. Button data is only an identifier: it is never proof of consent —
  the Core re-validates principal, bot, chat, window and payload hash in
  ``ActionProposalsRepository.claim_confirmation``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Any
from uuid import UUID

_UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
_CALLBACK = re.compile(rf"(?P<action>[cd]):(?P<proposal_id>{_UUID})")
MAX_CALLBACK_DATA_BYTES = 64
"""Telegram's hard limit for ``callback_data``."""

MAX_FIELD_CHARS = 120
"""Bound each rendered value so a proposal block can never flood a message."""


class ConsentAction(StrEnum):
    CONFIRM = "c"
    DISCARD = "d"


@dataclass(frozen=True)
class ConsentCallback:
    action: ConsentAction
    proposal_id: UUID


@dataclass(frozen=True)
class ConsentButton:
    label: str
    callback_data: str


def consent_buttons(proposal_id: UUID) -> tuple[ConsentButton, ConsentButton]:
    """Inline Sí/No buttons for one proposal."""
    confirm = f"{ConsentAction.CONFIRM.value}:{proposal_id}"
    discard = f"{ConsentAction.DISCARD.value}:{proposal_id}"
    for data in (confirm, discard):
        if len(data.encode("utf-8")) > MAX_CALLBACK_DATA_BYTES:  # pragma: no cover
            raise ValueError("callback_data exceeds Telegram's 64-byte limit")
    return ConsentButton("✅ Sí", confirm), ConsentButton("❌ No", discard)


def parse_consent_callback(data: str | None) -> ConsentCallback | None:
    """Recognise only our exact button payloads; anything else is not consent."""
    if not isinstance(data, str) or len(data) > MAX_CALLBACK_DATA_BYTES:
        return None
    match = _CALLBACK.fullmatch(data)
    if match is None:
        return None
    return ConsentCallback(
        action=ConsentAction(match.group("action")),
        proposal_id=UUID(match.group("proposal_id")),
    )


_TOOL_TITLES = {
    "create_reminder": "Crear recordatorio",
    "snooze_reminder": "Posponer recordatorio",
    "create_calendar_event": "Añadir evento al calendario",
    "register_vehicle": "Registrar vehículo",
    "register_vehicle_maintenance": "Registrar mantenimiento",
    "create_todo_list": "Crear lista de tareas",
    "rename_todo_list": "Renombrar lista de tareas",
    "delete_todo_list": "Eliminar lista de tareas (y sus tareas)",
    "create_todo_item": "Añadir tarea",
    "update_todo_item": "Modificar tarea",
    "set_todo_item_status": "Cambiar estado de tarea",
    "move_todo_item": "Mover tarea",
    "delete_todo_item": "Eliminar tarea",
}

_FIELD_LABELS = {
    "title": "Título",
    "name": "Nombre",
    "description": "Descripción",
    "trigger_at": "Cuándo",
    "start_at": "Inicio",
    "end_at": "Fin",
    "location": "Lugar",
    "date": "Fecha",
    "mileage_km": "Kilometraje",
    "workshop": "Taller",
    "cost": "Importe",
    "work_performed": "Trabajos",
    "make": "Marca",
    "model": "Modelo",
    "year": "Año",
    "registration": "Matrícula",
    "nickname": "Apodo",
    "status": "Estado",
    "priority": "Prioridad",
    "due_date": "Fecha límite",
}
"""Only these fields are shown; identifiers and internal keys stay hidden."""


_PRIORITIES = {"high": "alta", "normal": "normal", "low": "baja"}
_RECURRENCE_UNITS = {
    "daily": ("día", "días"),
    "weekly": ("semana", "semanas"),
    "monthly": ("mes", "meses"),
    "yearly": ("año", "años"),
}
_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _render_field(tool_name: str, key: str, value: Any) -> str:
    if key == "priority" and isinstance(value, str):
        return _PRIORITIES.get(value, value)
    if (
        key == "due_date"
        and tool_name in {"create_todo_item", "update_todo_item"}
        and isinstance(value, str)
    ):
        try:
            due = datetime.fromisoformat(value)
        except ValueError:
            return value
        date_text = f"{due.day} de {_MONTHS[due.month - 1]} de {due.year}"
        # TODO date-only input is currently persisted as naive midnight.
        # Keep every explicit time/offset, including aware midnight; do
        # not apply this convention to reminder/calendar timestamps.
        if due.tzinfo is None and due.time() == time.min:
            return date_text
        return f"{date_text}, {due.timetz().isoformat()}"
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


def _duration(minutes: Any) -> str:
    """Display stored minutes without rounding or interpreting invalid values."""
    if not isinstance(minutes, int) or isinstance(minutes, bool):
        return str(minutes)
    hours, remainder = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {remainder} min" if remainder else f"{hours} h"


def _calendar_fields(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    frequency = payload.get("recurrence_frequency")
    fields: list[tuple[str, Any]] = []
    if frequency is None:
        fields.append(("Repetición", "no se repite"))
    else:
        interval = payload.get("recurrence_interval")
        if interval is None:
            interval = 1  # Same default as recurrence_rule_from_flat.
        units = _RECURRENCE_UNITS.get(str(frequency))
        unit = units[0 if interval == 1 else 1] if units else str(frequency)
        fields.append(("Repetición", f"cada {interval} {unit}"))
        fields.append(
            ("Repetir hasta (inclusive)", payload.get("recurrence_until") or "sin fecha límite")
        )
    with_reminder = bool(payload.get("with_reminder"))
    fields.append(("Aviso", "sí" if with_reminder else "no"))
    if with_reminder:
        lead = payload.get("reminder_lead_minutes", 0)
        fields.append(
            ("Antelación", "al inicio" if lead == 0 else f"{_duration(lead)} antes del inicio")
        )
    return fields


def render_proposal_block(
    proposal_id: UUID,
    tool_name: str,
    payload: dict[str, Any],
    *,
    reminder_title: str | None = None,
) -> str:
    """Fixed, Core-generated summary of exactly what «Sí» will execute."""
    lines = [f"📋 **Propuesta**: {_TOOL_TITLES.get(tool_name, tool_name)}"]
    fields: list[tuple[str, Any]] = []
    if tool_name == "snooze_reminder":
        # Never trust a title supplied in the tool payload. The Core resolves
        # this display-only context by reminder_id + the interaction's user.
        fields.append(("Recordatorio", reminder_title or "No disponible"))
        fields.append(
            ("Aplazamiento", f"{_duration(payload.get('minutes'))} desde la confirmación")
        )
    else:
        for key, label in _FIELD_LABELS.items():
            value = payload.get(key)
            if value is None or value == "" or value == []:
                continue
            fields.append((label, _render_field(tool_name, key, value)))
        if tool_name == "create_calendar_event":
            fields.extend(_calendar_fields(payload))
    for label, value in fields:
        rendered = str(value)
        rendered = " ".join(rendered.split())
        if len(rendered) > MAX_FIELD_CHARS:
            rendered = rendered[: MAX_FIELD_CHARS - 1] + "…"
        lines.append(f"   {label}: {rendered}")
    lines.append("Pulsa ✅ Sí para confirmar o ❌ No para descartarla (válida 15 min).")
    return "\n".join(lines)
