"""Unit tests for strict ActionProposal governance in TODO tools."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from agno.run import RunContext

from src.agent.tools import todos as todo_tools
from src.domain.todos.models import TodoItem


def _run_context() -> RunContext:
    return RunContext(
        run_id="run-todos-test",
        session_id="tg:ancoramind:452022640:test",
        user_id="452022640",
    )


def _item(title: str = "Preparar presentación") -> TodoItem:
    now = datetime.now(tz=UTC)
    return TodoItem(
        id=uuid4(),
        list_id=uuid4(),
        user_id="452022640",
        title=title,
        description=None,
        status="pending",
        priority=None,
        due_date=None,
        position=0,
        created_at=now,
        updated_at=now,
    )


async def test_propose_todo_item_records_intent_without_mutating(monkeypatch):
    actions = AsyncMock()
    actions.create.return_value = {"id": "proposal-1"}
    service = AsyncMock()

    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    monkeypatch.setattr(todo_tools, "_get_todos_service", AsyncMock(return_value=service))
    list_id = uuid4()

    response = await todo_tools.propose_todo_item(
        _run_context(),
        str(list_id),
        "  Preparar presentación  ",
        priority="high",
        due_date="2026-09-15",
    )

    actions.create.assert_awaited_once_with(
        user_id="452022640",
        tool_name="create_todo_item",
        payload={
            "list_id": str(list_id),
            "title": "Preparar presentación",
            "description": None,
            "priority": "high",
            "due_date": "2026-09-15T00:00:00",
        },
    )
    service.add_item.assert_not_awaited()
    assert "proposal-1" in response
    assert "¿Confirmas" in response


async def test_propose_todo_item_rejects_invalid_input_without_proposal(monkeypatch):
    actions = AsyncMock()
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))

    response = await todo_tools.propose_todo_item(
        _run_context(), str(uuid4()), "Tarea", priority="urgent"
    )

    actions.create.assert_not_awaited()
    assert response.startswith("Datos no válidos:")


async def test_execute_todo_item_creates_after_confirmation_and_audits(monkeypatch):
    list_id = uuid4()
    created = _item()
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {
        "tool_name": "create_todo_item",
        "payload": {
            "list_id": str(list_id),
            "title": "Preparar presentación",
            "description": "Slides",
            "priority": "high",
            "due_date": "2026-09-15T00:00:00",
        },
    }
    service = AsyncMock()
    service.add_item.return_value = created
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    monkeypatch.setattr(todo_tools, "_get_todos_service", AsyncMock(return_value=service))

    response = await todo_tools.execute_todo_item(_run_context(), "proposal-1")

    service.add_item.assert_awaited_once_with(
        todo_tools.UserContext(user_id="452022640"),
        list_id,
        "Preparar presentación",
        description="Slides",
        priority="high",
        due_date=datetime(2026, 9, 15),
    )
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-1")
    assert "Tarea añadida" in response


async def test_execute_todo_item_updates_after_confirmation_and_audits(monkeypatch):
    item_id = uuid4()
    updated = _item("Nuevo título")
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {
        "tool_name": "update_todo_item",
        "payload": {
            "item_id": str(item_id),
            "title": "Nuevo título",
            "description": None,
            "priority": "normal",
            "due_date": None,
        },
    }
    service = AsyncMock()
    service.update_item.return_value = updated
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    monkeypatch.setattr(todo_tools, "_get_todos_service", AsyncMock(return_value=service))

    response = await todo_tools.execute_todo_item(_run_context(), "proposal-2")

    service.update_item.assert_awaited_once_with(
        todo_tools.UserContext(user_id="452022640"),
        item_id,
        title="Nuevo título",
        description=None,
        priority="normal",
        due_date=None,
    )
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-2")
    assert "Tarea actualizada" in response


async def test_execute_todo_item_sets_status_after_confirmation(monkeypatch):
    item_id = uuid4()
    completed = _item()
    completed.status = "done"
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {
        "tool_name": "set_todo_item_status",
        "payload": {"item_id": str(item_id), "status": "done"},
    }
    service = AsyncMock()
    service.set_item_status.return_value = completed
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    monkeypatch.setattr(todo_tools, "_get_todos_service", AsyncMock(return_value=service))

    response = await todo_tools.execute_todo_item(_run_context(), "proposal-3")

    service.set_item_status.assert_awaited_once_with(
        todo_tools.UserContext(user_id="452022640"), item_id, "done"
    )
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-3")
    assert "Completada" in response


async def test_execute_todo_item_moves_after_confirmation(monkeypatch):
    item_id = uuid4()
    target_list_id = uuid4()
    moved = _item()
    moved.list_id = target_list_id
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {
        "tool_name": "move_todo_item",
        "payload": {"item_id": str(item_id), "target_list_id": str(target_list_id)},
    }
    service = AsyncMock()
    service.move_item.return_value = moved
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    monkeypatch.setattr(todo_tools, "_get_todos_service", AsyncMock(return_value=service))

    response = await todo_tools.execute_todo_item(_run_context(), "proposal-4")

    service.move_item.assert_awaited_once_with(
        todo_tools.UserContext(user_id="452022640"), item_id, target_list_id
    )
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-4")
    assert "Tarea movida" in response


async def test_execute_todo_item_deletes_after_confirmation(monkeypatch):
    item_id = uuid4()
    actions = AsyncMock()
    actions.confirm_or_use_confirmed.return_value = {
        "tool_name": "delete_todo_item",
        "payload": {"item_id": str(item_id)},
    }
    service = AsyncMock()
    service.delete_item.return_value = True
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    monkeypatch.setattr(todo_tools, "_get_todos_service", AsyncMock(return_value=service))

    response = await todo_tools.execute_todo_item(_run_context(), "proposal-5")

    service.delete_item.assert_awaited_once_with(
        todo_tools.UserContext(user_id="452022640"), item_id
    )
    actions.mark_executed.assert_awaited_once_with("452022640", "proposal-5")
    assert "Tarea eliminada" in response


async def test_item_proposal_tools_only_record_action_proposals(monkeypatch):
    actions = AsyncMock()
    actions.create.side_effect = lambda **kwargs: {"id": kwargs["tool_name"]}
    monkeypatch.setattr(todo_tools, "_get_actions_repo", AsyncMock(return_value=actions))
    item_id = str(uuid4())
    target_list_id = str(uuid4())

    await todo_tools.propose_todo_item_complete(_run_context(), item_id)
    await todo_tools.propose_todo_item_reopen(_run_context(), item_id)
    await todo_tools.propose_todo_item_move(_run_context(), item_id, target_list_id)
    await todo_tools.propose_todo_item_delete(_run_context(), item_id)

    assert [call.kwargs["tool_name"] for call in actions.create.await_args_list] == [
        "set_todo_item_status",
        "set_todo_item_status",
        "move_todo_item",
        "delete_todo_item",
    ]
    assert actions.create.await_args_list[0].kwargs["payload"]["status"] == "done"
    assert actions.create.await_args_list[1].kwargs["payload"]["status"] == "pending"
