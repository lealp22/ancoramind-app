"""Unit tests for tool DB-session lifecycle and safe error replies (specs/023 T3)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from agno.run import RunContext
from agno.tools.function import Function

from src.agent.tools import calendar, maintenance, notes, reminders, todos, vehicles
from src.agent.tools.sessions import closes_sessions, track_session
from src.agent.tools.validation import (
    INTERNAL_ERROR,
    INVALID_PROPOSAL_DATA,
    parse_optional_uuid,
    parse_uuid,
)

PROPOSAL_ID = "11111111-1111-1111-1111-111111111111"


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _run_context() -> RunContext:
    return RunContext(run_id="run-1", session_id="tg:ancora:42", user_id="42")


class TestClosesSessions:
    async def test_closes_every_tracked_session_on_success(self) -> None:
        opened: list[_FakeSession] = []

        @closes_sessions
        async def tool() -> str:
            for _ in range(2):
                opened.append(track_session(_FakeSession()))  # type: ignore[arg-type]
            return "ok"

        assert await tool() == "ok"
        assert len(opened) == 2
        assert all(session.closed for session in opened)

    async def test_closes_tracked_sessions_when_tool_raises(self) -> None:
        opened: list[_FakeSession] = []

        @closes_sessions
        async def tool() -> str:
            opened.append(track_session(_FakeSession()))  # type: ignore[arg-type]
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await tool()
        assert opened[0].closed

    async def test_scopes_do_not_leak_between_calls(self) -> None:
        first: list[_FakeSession] = []

        @closes_sessions
        async def tool() -> None:
            first.append(track_session(_FakeSession()))  # type: ignore[arg-type]

        await tool()
        await tool()
        assert len(first) == 2 and all(session.closed for session in first)

    def test_preserves_agno_schema(self) -> None:
        function = Function.from_callable(notes.propose_note)
        assert function.name == "propose_note"
        assert "requires user confirmation" in (function.description or "")
        assert list(function.parameters["properties"]) == ["content"]


class TestToolsCloseRealSessions:
    async def test_search_notes_closes_its_session(self, monkeypatch) -> None:
        session = _FakeSession()
        service = AsyncMock()
        service.search.return_value = []
        monkeypatch.setattr(notes, "get_session", AsyncMock(return_value=session))
        monkeypatch.setattr(notes, "NotesRepository", lambda _session: object())
        monkeypatch.setattr(notes, "NotesService", lambda _repo: service)

        reply = await notes.search_notes(_run_context())

        assert reply == "No encontré notas."
        assert session.closed

    async def test_execute_closes_both_sessions_when_service_fails(self, monkeypatch) -> None:
        sessions: list[_FakeSession] = []

        async def fake_get_session() -> _FakeSession:
            sessions.append(_FakeSession())
            return sessions[-1]

        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = {
            "payload": {"title": "Dentista", "start_at": "2026-10-02T17:00:00"}
        }
        service = AsyncMock()
        service.create_event.side_effect = RuntimeError("connection reset")
        monkeypatch.setattr(calendar, "get_session", fake_get_session)
        monkeypatch.setattr(calendar, "ActionProposalsRepository", lambda _s: actions)
        monkeypatch.setattr(calendar, "CalendarRepository", lambda _s: object())
        monkeypatch.setattr(calendar, "CalendarService", lambda *_args: service)

        reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        assert reply == INTERNAL_ERROR
        assert len(sessions) == 2
        assert all(session.closed for session in sessions)


class TestSafeErrorReplies:
    def _patch_calendar(self, monkeypatch, proposal: dict[str, Any], service: Any) -> None:
        actions = AsyncMock()
        actions.confirm_or_use_confirmed.return_value = proposal
        monkeypatch.setattr(calendar, "get_session", AsyncMock(return_value=_FakeSession()))
        monkeypatch.setattr(calendar, "ActionProposalsRepository", lambda _s: actions)
        monkeypatch.setattr(calendar, "CalendarRepository", lambda _s: object())
        monkeypatch.setattr(calendar, "CalendarService", lambda *_args: service)

    async def test_internal_error_never_echoes_exception_text(self, monkeypatch, caplog) -> None:
        secret = "password=hunter2 host=db.internal"
        service = AsyncMock()
        service.create_event.side_effect = RuntimeError(secret)
        self._patch_calendar(
            monkeypatch,
            {"payload": {"title": "t", "start_at": "2026-10-02T17:00:00"}},
            service,
        )

        with caplog.at_level(logging.ERROR):
            reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        assert reply == INTERNAL_ERROR
        assert secret not in reply
        # Assert on the raw records, not caplog.text: the production
        # MetadataOnlyJsonFormatter may be installed by another test and drops
        # message text by design.
        records = [r for r in caplog.records if r.name == "src.agent.tools.validation"]
        assert records, "the failure must be logged"
        for record in records:
            assert secret not in record.getMessage()
            assert record.args == ("execute_calendar_event", "RuntimeError")

    async def test_malformed_proposal_gets_fixed_reply(self, monkeypatch) -> None:
        self._patch_calendar(monkeypatch, {"payload": {}}, AsyncMock())

        reply = await calendar.execute_calendar_event(_run_context(), PROPOSAL_ID)

        assert reply == INVALID_PROPOSAL_DATA
        assert "title" not in reply


class TestUuidValidation:
    def test_parse_uuid_rejects_without_echoing_input(self) -> None:
        reply = parse_uuid("'; DROP TABLE x; --", "documento")
        assert isinstance(reply, str)
        assert reply.startswith("ID no válido (documento)")
        assert "DROP" not in reply

    def test_parse_optional_uuid(self) -> None:
        assert parse_optional_uuid(None, "documento") is None
        assert parse_optional_uuid("  ", "documento") is None
        assert str(parse_optional_uuid(PROPOSAL_ID, "documento")) == PROPOSAL_ID

    @pytest.mark.parametrize(
        ("module", "tool", "kwargs"),
        [
            (
                reminders,
                "propose_reminder",
                {"title": "t", "trigger_at": "2026-10-02T17:00:00"},
            ),
            (
                calendar,
                "propose_calendar_event",
                {"title": "t", "start_at": "2026-10-02T17:00:00"},
            ),
            (
                maintenance,
                "propose_vehicle_maintenance",
                {"vehicle_id": PROPOSAL_ID, "date_str": "2026-10-02", "description": "d"},
            ),
            (vehicles, "propose_vehicle", {"make": "Ford", "model": "Focus"}),
        ],
    )
    async def test_invalid_source_document_id_is_rejected_before_any_db_access(
        self, monkeypatch, module: Any, tool: str, kwargs: dict[str, Any]
    ) -> None:
        get_session = AsyncMock(side_effect=AssertionError("DB must not be touched"))
        monkeypatch.setattr(module, "get_session", get_session)

        reply = await getattr(module, tool)(
            _run_context(), source_document_id="not-a-uuid", **kwargs
        )

        assert reply.startswith("ID no válido (documento)")
        get_session.assert_not_awaited()

    def test_todos_parse_uuid_uses_shared_message(self) -> None:
        reply = todos._parse_uuid("nope", "lista")
        assert reply == parse_uuid("nope", "lista")

