"""Todo tools — thin Agno tool adapters for TodosService.

List management is a WRITE operation: propose_*/execute_* governance applies
to list creation/rename/delete. Item operations (add/edit/move/delete,
mark done/pending) are scoped to a user-owned list and execute directly
after resolving identity from RunContext — same level of reversibility as
notes (canonical memory, no external side effects).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from agno.run import RunContext

from src.domain.todos.models import TodoItem
from src.domain.todos.service import TodosService
from src.repositories.actions import ActionProposalsRepository
from src.repositories.database import get_session
from src.repositories.todos import TodosRepository
from src.security.user_context import UserContext

_PRIORITY_ICONS = {"high": "🔴", "normal": "🟡", "low": "🟢"}


async def _get_todos_service() -> TodosService:
    session = await get_session()
    return TodosService(TodosRepository(session))


async def _get_actions_repo() -> ActionProposalsRepository:
    session = await get_session()
    return ActionProposalsRepository(session)


def _parse_uuid(value: str, label: str) -> UUID | str:
    try:
        return UUID(value)
    except ValueError:
        return f"ID no válido ({label}): {value}"


def _format_list_line(list_id: UUID, name: str) -> str:
    return f"📋 **{name}** — `{list_id}`"


def _format_item_line(item: TodoItem) -> str:
    icon = "✅" if item.status == "done" else "⏳"
    prio = _PRIORITY_ICONS.get(item.priority or "", "")
    due = f" — 📅 {item.due_date.strftime('%Y-%m-%d')}" if item.due_date else ""
    desc = f"\n   {item.description}" if item.description else ""
    prio_txt = f"{prio} " if prio else ""
    return f"{icon} {prio_txt}**{item.title}** `{item.id}` [{item.status}]{due}{desc}"


async def list_todo_lists(run_context: RunContext) -> str:
    """List your TODO lists.

    Use when the user asks about their lists:
    - "¿Qué listas tengo?"
    - "Muéstrame mis listas de tareas"

    Args:
        run_context: Injected by Agno.
    """
    user_ctx = UserContext.from_run_context(run_context)
    service = await _get_todos_service()
    lists = await service.list_lists(user_ctx)
    if not lists:
        return (
            "No tienes listas TODO todavía. "
            "Pídeme crear una con propose_todo_list "
            '(ej. "Crea una lista Trabajo").'
        )
    lines = [f"📋 **Tus listas TODO** ({len(lists)}):\n"]
    for lst in lists:
        items = await service.list_items(user_ctx, lst.id)
        pending = sum(1 for i in (items or []) if i.status == "pending")
        total = len(items or [])
        lines.append(f"{_format_list_line(lst.id, lst.name)} — {pending}/{total} pendientes")
    return "\n".join(lines)


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
    user_ctx = UserContext.from_run_context(run_context)
    if not name or not name.strip():
        return "Dime el nombre de la lista (ej. Trabajo, Personal, Compra)."
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="create_todo_list",
        payload={"name": name.strip()},
    )
    return (
        f"📋 **Propuesta de lista TODO** (`{proposal['id']}`)\n"
        f"   Nombre: {name.strip()}\n"
        "\n¿Confirmas la creación de esta lista?"
    )


async def execute_todo_list(run_context: RunContext, proposal_id: str) -> str:
    """Execute a confirmed TODO-list proposal.

    Only call after the user explicitly confirmed ('Sí').

    Args:
        run_context: Injected by Agno.
        proposal_id: Proposal ID from propose_todo_list / propose_todo_list_rename
            / propose_todo_list_delete.
    """
    user_ctx = UserContext.from_run_context(run_context)
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.confirm(user_ctx.user_id, proposal_id)
    if not proposal:
        return f"No se encontró la propuesta `{proposal_id}` o ya no está pendiente."
    payload = proposal["payload"]
    tool_name = proposal["tool_name"]
    service = await _get_todos_service()
    try:
        if tool_name == "create_todo_list":
            created = await service.create_list(user_ctx, payload["name"])
            result = f"✅ **Lista creada**: {created.name}\n   ID: `{created.id}`"
        elif tool_name == "rename_todo_list":
            renamed = await service.rename_list(
                user_ctx, UUID(payload["list_id"]), payload["name"]
            )
            if not renamed:
                return f"No se encontró la lista `{payload['list_id']}`."
            result = f"✅ **Lista renombrada**: {renamed.name}\n   ID: `{renamed.id}`"
        elif tool_name == "delete_todo_list":
            ok = await service.delete_list(user_ctx, UUID(payload["list_id"]))
            if not ok:
                return f"No se encontró la lista `{payload['list_id']}`."
            result = (
                f"✅ **Lista eliminada** (`{payload['list_id']}`) "
                "junto con sus tareas."
            )
        else:
            return f"Propuesta de tipo desconocido: {tool_name}"
        await actions_repo.mark_executed(user_ctx.user_id, proposal_id)
        return result
    except Exception as e:
        return f"❌ Error: {str(e)[:200]}"


async def propose_todo_list_rename(
    run_context: RunContext, list_id: str, name: str
) -> str:
    """PROPOSE renaming a TODO list — requires user confirmation.

    Use when the user wants to rename a list:
    - "Renombra la lista Compra a Supermercado"

    Args:
        run_context: Injected by Agno.
        list_id: UUID of the list (from list_todo_lists).
        name: New name for the list.
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(list_id, "lista")
    if isinstance(parsed, str):
        return parsed
    if not name or not name.strip():
        return "Dime el nuevo nombre de la lista."
    service = await _get_todos_service()
    target = await service.list_lists(user_ctx)
    current = next((lst for lst in target if lst.id == parsed), None)
    if current is None:
        return f"No se encontró la lista `{list_id}`."
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="rename_todo_list",
        payload={"list_id": str(parsed), "name": name.strip()},
    )
    return (
        f"📋 **Propuesta de renombrado** (`{proposal['id']}`)\n"
        f"   {current.name} → {name.strip()}\n"
        "\n¿Confirmas el cambio de nombre?"
    )


async def propose_todo_list_delete(run_context: RunContext, list_id: str) -> str:
    """PROPOSE deleting a TODO list (and its items) — requires confirmation.

    Use when the user wants to remove a list:
    - "Elimina la lista Compra"
    - "Borra la lista de Proyecto X"

    Args:
        run_context: Injected by Agno.
        list_id: UUID of the list (from list_todo_lists).
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(list_id, "lista")
    if isinstance(parsed, str):
        return parsed
    service = await _get_todos_service()
    target = await service.list_lists(user_ctx)
    current = next((lst for lst in target if lst.id == parsed), None)
    if current is None:
        return f"No se encontró la lista `{list_id}`."
    items = await service.list_items(user_ctx, parsed)
    n_items = len(items or [])
    actions_repo = await _get_actions_repo()
    proposal = await actions_repo.create(
        user_id=user_ctx.user_id,
        tool_name="delete_todo_list",
        payload={"list_id": str(parsed)},
    )
    return (
        f"📋 **Propuesta de borrado** (`{proposal['id']}`)\n"
        f"   Lista: {current.name} ({n_items} tarea(s) se eliminarán)\n"
        "\n¿Confirmas la eliminación?"
    )


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
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(list_id, "lista")
    if isinstance(parsed, str):
        return parsed
    service = await _get_todos_service()
    try:
        items = await service.list_items(
            user_ctx, parsed, status=status, priority=priority
        )
    except ValueError as e:
        return f"Filtro no válido: {e}"
    if items is None:
        return f"No se encontró la lista `{list_id}`."
    if not items:
        return "La lista no tiene tareas con esos filtros. 📭"
    lines = [f"📋 **Tareas** ({len(items)}):\n"]
    for item in items:
        lines.append(_format_item_line(item))
    return "\n".join(lines)


async def add_todo_item(
    run_context: RunContext,
    list_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> str:
    """Add a task to a TODO list.

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
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(list_id, "lista")
    if isinstance(parsed, str):
        return parsed
    if not title or not title.strip():
        return "Dime el título de la tarea."
    due = None
    if due_date:
        try:
            due = datetime.fromisoformat(due_date)
        except ValueError:
            return f"Fecha no válida: {due_date}. Usa formato ISO 8601 (YYYY-MM-DD)."
    service = await _get_todos_service()
    try:
        item = await service.add_item(
            user_ctx, parsed, title,
            description=description, priority=priority, due_date=due,
        )
    except ValueError as e:
        return f"Datos no válidos: {e}"
    if item is None:
        return f"No se encontró la lista `{list_id}`."
    return f"✅ **Tarea añadida**: {item.title}\n   ID: `{item.id}`"


async def update_todo_item(
    run_context: RunContext,
    item_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> str:
    """Edit a TODO task (title, description, priority, due date).

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
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(item_id, "tarea")
    if isinstance(parsed, str):
        return parsed
    due = None
    if due_date:
        try:
            due = datetime.fromisoformat(due_date)
        except ValueError:
            return f"Fecha no válida: {due_date}. Usa formato ISO 8601 (YYYY-MM-DD)."
    service = await _get_todos_service()
    try:
        item = await service.update_item(
            user_ctx, parsed, title=title,
            description=description, priority=priority, due_date=due,
        )
    except ValueError as e:
        return f"Datos no válidos: {e}"
    if item is None:
        return f"No se encontró la tarea `{item_id}`."
    return f"✅ **Tarea actualizada**: {item.title}\n   ID: `{item.id}`"


async def complete_todo_item(run_context: RunContext, item_id: str) -> str:
    """Mark a TODO task as done.

    Use when the user finished something:
    - "Hecho lo de preparar la presentación"
    - "Marca como completada la tarea de comprar leche"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(item_id, "tarea")
    if isinstance(parsed, str):
        return parsed
    service = await _get_todos_service()
    item = await service.set_item_status(user_ctx, parsed, "done")
    if item is None:
        return f"No se encontró la tarea `{item_id}`."
    return f"✅ **Completada**: {item.title}"


async def reopen_todo_item(run_context: RunContext, item_id: str) -> str:
    """Mark a TODO task back as pending.

    Use when the user wants to reopen a done task:
    - "Reabre la tarea de preparar la presentación"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(item_id, "tarea")
    if isinstance(parsed, str):
        return parsed
    service = await _get_todos_service()
    item = await service.set_item_status(user_ctx, parsed, "pending")
    if item is None:
        return f"No se encontró la tarea `{item_id}`."
    return f"⏳ **Reabierta**: {item.title}"


async def move_todo_item(
    run_context: RunContext, item_id: str, target_list_id: str
) -> str:
    """Move a TODO task to another list.

    Use when the user wants to reorganize:
    - "Mueve esa tarea a la lista Personal"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
        target_list_id: UUID of the destination list (from list_todo_lists).
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed_item = _parse_uuid(item_id, "tarea")
    if isinstance(parsed_item, str):
        return parsed_item
    parsed_list = _parse_uuid(target_list_id, "lista destino")
    if isinstance(parsed_list, str):
        return parsed_list
    service = await _get_todos_service()
    item = await service.move_item(user_ctx, parsed_item, parsed_list)
    if item is None:
        return "No se encontró la tarea o la lista destino."
    return f"✅ **Tarea movida**: {item.title}\n   Lista destino: `{item.list_id}`"


async def delete_todo_item(run_context: RunContext, item_id: str) -> str:
    """Delete a TODO task.

    Use when the user wants to remove a task:
    - "Elimina esa tarea"
    - "Borra lo de comprar leche"

    Args:
        run_context: Injected by Agno.
        item_id: UUID of the item (from list_todo_items).
    """
    user_ctx = UserContext.from_run_context(run_context)
    parsed = _parse_uuid(item_id, "tarea")
    if isinstance(parsed, str):
        return parsed
    service = await _get_todos_service()
    ok = await service.delete_item(user_ctx, parsed)
    if not ok:
        return f"No se encontró la tarea `{item_id}`."
    return f"✅ **Tarea eliminada** (`{item_id}`)."
