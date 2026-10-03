"""Todo tools — thin Agno adapters with strict ActionProposal governance.

Every TODO mutation is a WRITE operation. A propose_* tool records the intent
as a pending ActionProposal; execute_* confirms it, revalidates ownership via
the domain service, performs the mutation, and records execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from agno.run import RunContext
from pydantic import ValidationError

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
    parse_uuid,
)
from src.domain.todos.models import TodoItem, TodoItemCreate, TodoItemUpdate
from src.domain.todos.service import TodosService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.todos import TodosRepository
from src.security.user_context import UserContext


async def _get_todos_service() -> TodosService:
    session = track_session(await get_session())
    return TodosService(TodosRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = track_session(await get_session())
    return ActionProposalsRepository(session)


def _parse_uuid(value: str, label: str) -> UUID | str:
    return parse_uuid(value, label)


def _parse_due_date(value: str | None) -> datetime | str | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return f"Fecha no válida: {value}. Usa formato ISO 8601 (YYYY-MM-DD)."


def _todo_item_record(item: TodoItem) -> dict[str, object]:
    title, title_truncated = bounded_text(item.title, MAX_TITLE_CHARS)
    record: dict[str, object] = {
        "source": "todo_item",
        "id": str(item.id),
        "title": title,
        "title_truncated": title_truncated,
        "status": item.status,
        "priority": item.priority,
        "due_date": item.due_date.strftime("%Y-%m-%d") if item.due_date else None,
    }
    if item.description:
        description, description_truncated = bounded_text(item.description, MAX_SUMMARY_CHARS)
        record["description"] = description
        record["description_truncated"] = description_truncated
    return record


async def _create_proposal(
    user_context: UserContext,
    tool_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    actions_repo = await _get_actions_repo()
    return await actions_repo.create(
        user_id=user_context.user_id,
        tool_name=tool_name,
        payload=payload,
    )


@closes_sessions
async def list_todo_lists(run_context: RunContext) -> str:
    """List your TODO lists.

    Use when the user asks about their lists:
    - "¿Qué listas tengo?"
    - "Muéstrame mis listas de tareas"

    Args:
        run_context: Injected by Agno.
    """
    user_context = UserContext.from_run_context(run_context)
    service = await _get_todos_service()
    lists = await service.list_lists(user_context)
    if not lists:
        return (
            "No tienes listas TODO todavía. "
            "Pídeme crear una con propose_todo_list "
            '(ej. "Crea una lista Trabajo").'
        )

    bounded_lists = lists[:MAX_RESULT_RECORDS]
    records: list[dict[str, object]] = []
    for todo_list in bounded_lists:
        items = await service.list_items(user_context, todo_list.id)
        pending = sum(1 for item in (items or []) if item.status == "pending")
        total = len(items or [])
        name, name_truncated = bounded_text(todo_list.name, MAX_TITLE_CHARS)
        records.append(
            {
                "source": "todo_list",
                "id": str(todo_list.id),
                "name": name,
                "name_truncated": name_truncated,
                "pending_count": pending,
                "total_count": total,
            }
        )
    return render_retrieved_records("list_todo_lists", records, len(lists))


@closes_sessions
async def propose_todo_list(run_context: RunContext, name: str) -> str:
    """PROPOSE a new TODO list — requires user confirmation.

    Use when the user wants a new task list:
    - "Crea una lista Trabajo"
    - "Quiero una lista para temas personales"
    - "Nueva lista de la compra"

    Args:
        run_context: Injected by Agno.
        name: List name (ej. "Trabajo", "Personal", "Compra").
    """
    user_context = UserContext.from_run_context(run_context)
    if not name or not name.strip():
        return "Dime el nombre de la lista (ej. Trabajo, Personal, Compra)."
    proposal = await _create_proposal(
        user_context,
        "create_todo_list",
        {"name": name.strip()},
    )
    return (
        f"📋 **Propuesta de lista TODO** (`{proposal['id']}`)\n"
        f"   Nombre: {name.strip()}\n"
        "\n¿Confirmas la creación de esta lista?"
    )


@closes_sessions
async def execute_todo_list(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed TODO-list proposal.

    Only call after the user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from a propose_todo_list* tool.
    """
    user_context = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_context.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    tool_name = proposal["tool_name"]
    service = await _get_todos_service()
    try:
        if tool_name == "create_todo_list":
            created = await service.create_list(user_context, payload["name"])
            result = f"✅ **Lista creada**: {created.name}\n   ID: `{created.id}`"
        elif tool_name == "rename_todo_list":
            renamed = await service.rename_list(
                user_context, UUID(payload["list_id"]), payload["name"]
            )
            if not renamed:
                return f"No se encontró la lista `{payload['list_id']}`."
            result = f"✅ **Lista renombrada**: {renamed.name}\n   ID: `{renamed.id}`"
        elif tool_name == "delete_todo_list":
            deleted = await service.delete_list(user_context, UUID(payload["list_id"]))
            if not deleted:
                return f"No se encontró la lista `{payload['list_id']}`."
            result = f"✅ **Lista eliminada** (`{payload['list_id']}`) junto con sus tareas."
        else:
            return f"Propuesta de lista desconocida: {tool_name}"
        await actions_repo.mark_executed(user_context.user_id, proposal_id)
        return result
    except (KeyError, TypeError, ValueError) as error:
        return invalid_proposal_reply("execute_todo_list", error)
    except Exception as error:
        return internal_error_reply("execute_todo_list", error)


@closes_sessions
async def propose_todo_list_rename(run_context: RunContext, list_id: str, name: str) -> str:
    """PROPOSE renaming a TODO list — requires user confirmation.

    Use when the user wants to rename a list:
    - "Renombra la lista Compra a Supermercado"

    Args:
        run_context: Injected by Agno.
        list_id: UUID of the list (from list_todo_lists).
        name: New list name.
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_list_id = _parse_uuid(list_id, "lista")
    if isinstance(parsed_list_id, str):
        return parsed_list_id
    if not name or not name.strip():
        return "Dime el nuevo nombre de la lista."

    service = await _get_todos_service()
    current = await service.list_lists(user_context)
    target = next((todo_list for todo_list in current if todo_list.id == parsed_list_id), None)
    if target is None:
        return f"No se encontró la lista `{list_id}`."

    proposal = await _create_proposal(
        user_context,
        "rename_todo_list",
        {"list_id": str(parsed_list_id), "name": name.strip()},
    )
    return (
        f"📋 **Propuesta de renombrado** (`{proposal['id']}`)\n"
        f"   {target.name} → {name.strip()}\n"
        "\n¿Confirmas el cambio de nombre?"
    )


@closes_sessions
async def propose_todo_list_delete(run_context: RunContext, list_id: str) -> str:
    """PROPOSE deleting a TODO list and its tasks — requires confirmation.

    Use when the user wants to remove a list:
    - "Elimina la lista Compra"
    - "Borra la lista de Proyecto X"

    Args:
        run_context: Injected by Agno.
        list_id: UUID of the list (from list_todo_lists).
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_list_id = _parse_uuid(list_id, "lista")
    if isinstance(parsed_list_id, str):
        return parsed_list_id

    service = await _get_todos_service()
    current = await service.list_lists(user_context)
    target = next((todo_list for todo_list in current if todo_list.id == parsed_list_id), None)
    if target is None:
        return f"No se encontró la lista `{list_id}`."
    items = await service.list_items(user_context, parsed_list_id)

    proposal = await _create_proposal(
        user_context,
        "delete_todo_list",
        {"list_id": str(parsed_list_id)},
    )
    return (
        f"📋 **Propuesta de borrado** (`{proposal['id']}`)\n"
        f"   Lista: {target.name} ({len(items or [])} tarea(s) se eliminarán)\n"
        "\n¿Confirmas la eliminación?"
    )


@closes_sessions
async def list_todo_items(
    run_context: RunContext,
    list_id: str,
    status: str | None = None,
    priority: str | None = None,
) -> str:
    """List tasks inside a TODO list, with optional filters.

    Use when the user asks what's in a list:
    - "¿Qué tengo en la lista Trabajo?"
    - "Muéstrame las pendientes de Personal"

    Args:
        run_context: Injected by Agno.
        list_id: UUID of the list (from list_todo_lists).
        status: Optional filter: pending | done.
        priority: Optional filter: low | normal | high.
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_list_id = _parse_uuid(list_id, "lista")
    if isinstance(parsed_list_id, str):
        return parsed_list_id
    service = await _get_todos_service()
    try:
        items = await service.list_items(
            user_context, parsed_list_id, status=status, priority=priority
        )
    except ValueError as error:
        return f"Filtro no válido: {error}"
    if items is None:
        return f"No se encontró la lista `{list_id}`."
    if not items:
        return "La lista no tiene tareas con esos filtros. 📭"
    records = [_todo_item_record(item) for item in items[:MAX_RESULT_RECORDS]]
    return render_retrieved_records("list_todo_items", records, len(items))


@closes_sessions
async def propose_todo_item(
    run_context: RunContext,
    list_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> str:
    """PROPOSE adding a task to a TODO list — requires user confirmation.

    Use when the user wants to add something to a list:
    - "Añade a Trabajo: preparar la presentación"
    - "Apunta en Personal comprar regalo, prioridad alta"

    Args:
        run_context: Injected by Agno.
        list_id: UUID of the list (from list_todo_lists).
        title: Task title.
        description: Optional details.
        priority: Optional: low | normal | high.
        due_date: Optional ISO 8601 datetime (ej. '2026-09-15').
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_list_id = _parse_uuid(list_id, "lista")
    if isinstance(parsed_list_id, str):
        return parsed_list_id
    if not title or not title.strip():
        return "Dime el título de la tarea."
    parsed_due_date = _parse_due_date(due_date)
    if isinstance(parsed_due_date, str):
        return parsed_due_date
    try:
        data = TodoItemCreate(
            title=title.strip(),
            description=description.strip() if description else None,
            priority=priority,
            due_date=parsed_due_date,
        )
    except ValidationError as error:
        return f"Datos no válidos: {error.errors()[0]['msg']}"

    proposal = await _create_proposal(
        user_context,
        "create_todo_item",
        {
            "list_id": str(parsed_list_id),
            "title": data.title,
            "description": data.description,
            "priority": data.priority,
            "due_date": data.due_date.isoformat() if data.due_date else None,
        },
    )
    details = [
        f"📋 **Propuesta de nueva tarea** (`{proposal['id']}`)",
        f"   Título: {data.title}",
        f"   Lista: `{parsed_list_id}`",
    ]
    if data.priority:
        details.append(f"   Prioridad: {data.priority}")
    if data.due_date:
        details.append(f"   Fecha límite: {data.due_date:%Y-%m-%d}")
    details.append("\n¿Confirmas añadir esta tarea?")
    return "\n".join(details)


@closes_sessions
async def propose_todo_item_update(
    run_context: RunContext,
    item_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> str:
    """PROPOSE editing a TODO task — requires user confirmation.

    Use when the user wants to change a task:
    - "Cambia el título de esa tarea a ..."
    - "Ponle prioridad alta"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
        title: New title (optional).
        description: New description (optional).
        priority: New priority low | normal | high (optional).
        due_date: New due date ISO 8601 (optional).
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_item_id = _parse_uuid(item_id, "tarea")
    if isinstance(parsed_item_id, str):
        return parsed_item_id
    if all(value is None for value in (title, description, priority, due_date)):
        return "Indica al menos un dato de la tarea que quieras cambiar."
    parsed_due_date = _parse_due_date(due_date)
    if isinstance(parsed_due_date, str):
        return parsed_due_date
    try:
        data = TodoItemUpdate(
            title=title.strip() if title else None,
            description=description.strip() if description else description,
            priority=priority,
            due_date=parsed_due_date,
        )
    except ValidationError as error:
        return f"Datos no válidos: {error.errors()[0]['msg']}"

    proposal = await _create_proposal(
        user_context,
        "update_todo_item",
        {
            "item_id": str(parsed_item_id),
            "title": data.title,
            "description": data.description,
            "priority": data.priority,
            "due_date": data.due_date.isoformat() if data.due_date else None,
        },
    )
    return (
        f"📋 **Propuesta de actualización** (`{proposal['id']}`)\n"
        f"   Tarea: `{parsed_item_id}`\n"
        "\n¿Confirmas los cambios de esta tarea?"
    )


@closes_sessions
async def propose_todo_item_complete(run_context: RunContext, item_id: str) -> str:
    """PROPOSE marking a TODO task as done — requires user confirmation.

    Use when the user finished something:
    - "Hecho lo de preparar la presentación"
    - "Marca como completada la tarea de comprar leche"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
    """
    return await _propose_todo_item_status(run_context, item_id, "done", "completar")


@closes_sessions
async def propose_todo_item_reopen(run_context: RunContext, item_id: str) -> str:
    """PROPOSE reopening a TODO task — requires user confirmation.

    Use when the user wants to reopen a done task:
    - "Reabre la tarea de preparar la presentación"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
    """
    return await _propose_todo_item_status(run_context, item_id, "pending", "reabrir")


async def _propose_todo_item_status(
    run_context: RunContext,
    item_id: str,
    status: str,
    action_label: str,
) -> str:
    user_context = UserContext.from_run_context(run_context)
    parsed_item_id = _parse_uuid(item_id, "tarea")
    if isinstance(parsed_item_id, str):
        return parsed_item_id
    proposal = await _create_proposal(
        user_context,
        "set_todo_item_status",
        {"item_id": str(parsed_item_id), "status": status},
    )
    return (
        f"📋 **Propuesta para {action_label} tarea** (`{proposal['id']}`)\n"
        f"   Tarea: `{parsed_item_id}`\n"
        "\n¿Confirmas esta acción?"
    )


@closes_sessions
async def propose_todo_item_move(run_context: RunContext, item_id: str, target_list_id: str) -> str:
    """PROPOSE moving a TODO task to another list — requires confirmation.

    Use when the user wants to reorganize:
    - "Mueve esa tarea a la lista Personal"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
        target_list_id: UUID of the destination list (from list_todo_lists).
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_item_id = _parse_uuid(item_id, "tarea")
    if isinstance(parsed_item_id, str):
        return parsed_item_id
    parsed_target_list_id = _parse_uuid(target_list_id, "lista destino")
    if isinstance(parsed_target_list_id, str):
        return parsed_target_list_id
    proposal = await _create_proposal(
        user_context,
        "move_todo_item",
        {"item_id": str(parsed_item_id), "target_list_id": str(parsed_target_list_id)},
    )
    return (
        f"📋 **Propuesta de mover tarea** (`{proposal['id']}`)\n"
        f"   Tarea: `{parsed_item_id}`\n"
        f"   Lista destino: `{parsed_target_list_id}`\n"
        "\n¿Confirmas el movimiento?"
    )


@closes_sessions
async def propose_todo_item_delete(run_context: RunContext, item_id: str) -> str:
    """PROPOSE deleting a TODO task — requires user confirmation.

    Use when the user wants to remove a task:
    - "Elimina esa tarea"
    - "Borra lo de comprar leche"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
    """
    user_context = UserContext.from_run_context(run_context)
    parsed_item_id = _parse_uuid(item_id, "tarea")
    if isinstance(parsed_item_id, str):
        return parsed_item_id
    proposal = await _create_proposal(
        user_context,
        "delete_todo_item",
        {"item_id": str(parsed_item_id)},
    )
    return (
        f"📋 **Propuesta de borrado de tarea** (`{proposal['id']}`)\n"
        f"   Tarea: `{parsed_item_id}`\n"
        "\n¿Confirmas la eliminación?"
    )


@closes_sessions
async def execute_todo_item(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed TODO-item proposal.

    Only call after the user explicitly confirmed ('Sí'). The Core revalidates
    list/item ownership before every mutation.

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from a propose_todo_item* tool.
    """
    user_context = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm_or_use_confirmed(user_context.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."

    payload = proposal["payload"]
    tool_name = proposal["tool_name"]
    service = await _get_todos_service()
    try:
        if tool_name == "create_todo_item":
            item = await service.add_item(
                user_context,
                UUID(payload["list_id"]),
                payload["title"],
                description=payload.get("description"),
                priority=payload.get("priority"),
                due_date=datetime.fromisoformat(payload["due_date"])
                if payload.get("due_date")
                else None,
            )
            if item is None:
                return f"No se encontró la lista `{payload['list_id']}`."
            result = f"✅ **Tarea añadida**: {item.title}\n   ID: `{item.id}`"
        elif tool_name == "update_todo_item":
            item = await service.update_item(
                user_context,
                UUID(payload["item_id"]),
                title=payload.get("title"),
                description=payload.get("description"),
                priority=payload.get("priority"),
                due_date=datetime.fromisoformat(payload["due_date"])
                if payload.get("due_date")
                else None,
            )
            if item is None:
                return f"No se encontró la tarea `{payload['item_id']}`."
            result = f"✅ **Tarea actualizada**: {item.title}\n   ID: `{item.id}`"
        elif tool_name == "set_todo_item_status":
            item = await service.set_item_status(
                user_context,
                UUID(payload["item_id"]),
                payload["status"],
            )
            if item is None:
                return f"No se encontró la tarea `{payload['item_id']}`."
            result = (
                f"✅ **Completada**: {item.title}"
                if item.status == "done"
                else f"⏳ **Reabierta**: {item.title}"
            )
        elif tool_name == "move_todo_item":
            item = await service.move_item(
                user_context,
                UUID(payload["item_id"]),
                UUID(payload["target_list_id"]),
            )
            if item is None:
                return "No se encontró la tarea o la lista destino."
            result = f"✅ **Tarea movida**: {item.title}\n   Lista destino: `{item.list_id}`"
        elif tool_name == "delete_todo_item":
            deleted = await service.delete_item(user_context, UUID(payload["item_id"]))
            if not deleted:
                return f"No se encontró la tarea `{payload['item_id']}`."
            result = f"✅ **Tarea eliminada** (`{payload['item_id']}`)."
        else:
            return f"Propuesta de tarea desconocida: {tool_name}"
        await actions_repo.mark_executed(user_context.user_id, proposal_id)
        return result
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        return invalid_proposal_reply("execute_todo_item", error)
    except Exception as error:
        return internal_error_reply("execute_todo_item", error)
