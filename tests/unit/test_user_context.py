"""Unit tests for user context resolution."""

from dataclasses import FrozenInstanceError

import pytest
from agno.run import RunContext

from src.security.user_context import UserContext


class TestUserContext:
    def test_creation_with_user_id(self):
        ctx = UserContext(user_id="telegram-12345")
        assert ctx.user_id == "telegram-12345"
        assert ctx.channel == "telegram"

    def test_from_run_context_with_user_id(self):
        rc = RunContext(
            run_id="run-1",
            session_id="tg:ancora:12345",
            user_id="user-abc",
        )
        ctx = UserContext.from_run_context(rc)
        assert ctx.user_id == "user-abc"

    def test_from_run_context_parses_session_id(self):
        rc = RunContext(
            run_id="run-2",
            session_id="tg:ancora:67890",
            user_id=None,
        )
        ctx = UserContext.from_run_context(rc)
        assert ctx.user_id == "67890"

    def test_from_run_context_parses_generation_session_id(self):
        """BL-28: `/new` appends a generation; the chat id keeps its position."""
        rc = RunContext(
            run_id="run-4",
            session_id="tg:ancoramind:67890:2",
            user_id=None,
        )
        ctx = UserContext.from_run_context(rc)
        assert ctx.user_id == "67890"

    def test_from_run_context_fallback(self):
        rc = RunContext(
            run_id="run-3",
            session_id="",
            user_id=None,
        )
        ctx = UserContext.from_run_context(rc)
        assert ctx.user_id == "unknown"

    def test_frozen_dataclass(self):
        ctx = UserContext(user_id="test")
        with pytest.raises(FrozenInstanceError):
            ctx.user_id = "modified"  # type: ignore[misc]
