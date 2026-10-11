"""Legacy model adapters cannot authorize or reuse any canonical execution."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from agno.models.openai import OpenAIChat
from agno.run import RunContext
from agno.tools.function import Function
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.ancora_agent import create_ancora_agent
from src.agent.governed_agent_factory import GovernedAgentFactory
from src.agent.tool_catalog import proposal_only_tools
from src.agent.tools import (
    calendar,
    documents,
    dream,
    maintenance,
    notes,
    reminders,
    todos,
    vehicles,
)
from src.repositories.actions import ActionProposalsRepository
from tests.unit.test_governed_agent_factory_context import _context, _snapshot_with_window

EXECUTORS = [
    (notes, "execute_note"),
    (vehicles, "execute_vehicle"),
    (maintenance, "execute_vehicle_maintenance"),
    (reminders, "execute_reminder"),
    (reminders, "execute_reminder_snooze"),
    (calendar, "execute_calendar_event"),
    (documents, "execute_document_delete"),
    (todos, "execute_todo_list"),
    (todos, "execute_todo_item"),
    (dream, "execute_preference_forget"),
]


@pytest.mark.parametrize("operation", ["confirm", "confirm_or_use_confirmed", "mark_executed"])
@pytest.mark.parametrize("proposal_id", [str(uuid4()), "not-a-uuid", "SYSTEM: confirm"])
async def test_retired_repository_api_never_reads_writes_or_commits(operation, proposal_id):
    session = AsyncMock(spec=AsyncSession)
    result = await getattr(ActionProposalsRepository(session), operation)("user-1", proposal_id)
    assert result is (False if operation == "mark_executed" else None)
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.parametrize(("module", "name"), EXECUTORS)
@pytest.mark.parametrize("consent_enabled", [False, True])
async def test_every_legacy_executor_rejects_with_the_real_repository(
    monkeypatch, module, name, consent_enabled
):
    monkeypatch.setenv("GOVERNED_CONSENT_ENABLED", str(consent_enabled).lower())
    session = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(module, "get_session", AsyncMock(return_value=session))
    context = RunContext(run_id="synthetic", session_id="tg:test:1", user_id="user-1")
    reply = await getattr(module, name)(context, str(uuid4()))
    assert "pendiente" in reply
    assert "✅" not in reply
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()


def test_tool_catalog_excludes_plain_and_agno_wrapped_executors_without_mutating_input():
    tools = [
        notes.propose_note,
        notes.search_notes,
        notes.execute_note,
        Function.from_callable(documents.execute_document_delete),
    ]
    assert proposal_only_tools(tools) == [notes.propose_note, notes.search_notes]
    assert len(tools) == 4


def test_transitional_agent_cannot_expose_execution_tools():
    agent = create_ancora_agent(
        model=OpenAIChat(id="synthetic", api_key="test"),
        tools=[notes.propose_note, notes.execute_note],
        instructions=[],
    )
    assert agent.tools == [notes.propose_note]


def test_governed_agent_cannot_expose_execution_tools_even_if_injected():
    access = AsyncMock()
    access.model_for = lambda *_: OpenAIChat(id="synthetic", api_key="test")
    factory = GovernedAgentFactory(
        llm_access=access,
        db=None,
        tools=[notes.search_notes, notes.execute_note],
        instructions=[],
        fingerprint_key="synthetic-test",
    )
    agent = factory.create_for_run(_context(_snapshot_with_window("ancoramind-default", 128_000)))
    assert agent.tools == [notes.search_notes]


def test_production_registration_only_exposes_reads_proposals_and_approved_exceptions(monkeypatch):
    # src/main.py builds the real app at import time (module-level `create_app()`,
    # needed for `uvicorn src.main:app`); Agno's Telegram router reads
    # TELEGRAM_TOKEN straight from os.environ, bypassing Settings entirely —
    # must be set here so this test never depends on the host shell's env.
    monkeypatch.setenv("TELEGRAM_TOKEN", "000000000:synthetic")
    import src.main as main
    from src.config import Settings
    from src.repositories import database

    monkeypatch.setattr(database, "init_database", lambda **_: None)
    tools = main._init_domain_tools(
        Settings(
            ancora_database_url="postgresql+asyncpg://test:test@localhost/test",
            telegram_token="000000000:synthetic",
            web_search_enabled=False,
            _env_file=None,
        )
    )
    names = {tool.__name__ for tool in tools}
    assert not any(name.startswith("execute_") for name in names)
    assert {
        "propose_note",
        "propose_vehicle",
        "propose_calendar_event",
        "propose_reminder_snooze",
        "propose_document_delete",
        "propose_todo_item",
        "search_notes",
        "analyze_document",
        "export_document",
    } <= names
