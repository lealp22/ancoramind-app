"""Unit tests for FastAPI lifespan wiring of the reminder worker (BL-22)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from fastapi import FastAPI

import src.agent.lifecycle as lifecycle_module
from src.agent.lifecycle import (
    install_interaction_processor_lifespan,
    install_reminder_worker_lifespan,
)
from src.config import Settings
from src.domain.runtime_config.service import RuntimeConfigManager


def _settings(
    *,
    reminder_worker_enabled: bool = True,
    ancora_database_url: str = "postgresql+asyncpg://user:pass@localhost/db",
    telegram_token: str = "123456:token",
    reminder_poll_interval_seconds: int = 1,
    telegram_admission_enabled: bool = False,
    telegram_processor_enabled: bool = False,
) -> Settings:
    return Settings(
        reminder_worker_enabled=reminder_worker_enabled,
        ancora_database_url=ancora_database_url,
        telegram_token=telegram_token,
        reminder_poll_interval_seconds=reminder_poll_interval_seconds,
        telegram_admission_enabled=telegram_admission_enabled,
        telegram_processor_enabled=telegram_processor_enabled,
        telegram_bot_id=456 if telegram_admission_enabled else 0,
        telegram_webhook_secret_token="secret" if telegram_admission_enabled else "",
        telegram_payload_encryption_key=(
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" if telegram_admission_enabled else ""
        ),
        allowed_telegram_user_ids="999" if telegram_admission_enabled else "",
    )


async def test_auto_gates_keep_existing_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    original = app.router.lifespan_context

    assert not install_reminder_worker_lifespan(app, _settings(reminder_worker_enabled=False))
    assert app.router.lifespan_context is original

    assert not install_reminder_worker_lifespan(app, _settings(ancora_database_url=""))
    assert app.router.lifespan_context is original

    assert not install_reminder_worker_lifespan(app, _settings(telegram_token=""))
    assert app.router.lifespan_context is original


async def test_lifespan_starts_cancels_and_cleans_worker_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class FakeWorker:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def run_forever(self, interval_seconds: int) -> None:
            assert interval_seconds == 1
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    monkeypatch.setattr(lifecycle_module, "RemindersWorker", FakeWorker)

    assert install_reminder_worker_lifespan(app, _settings())

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=0.2)
        task = app.state.reminder_worker_task
        assert task.get_name() == "reminder-worker"
        assert not task.done()

    assert cancelled.is_set()
    assert not hasattr(app.state, "reminder_worker_task")


async def test_lifespan_preserves_existing_lifecycle_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    events: list[str] = []
    started = asyncio.Event()

    @asynccontextmanager
    async def original_lifespan(_: FastAPI) -> AsyncIterator[None]:
        events.append("original-enter")
        try:
            yield
        finally:
            events.append("original-exit")

    class FakeWorker:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run_forever(self, interval_seconds: int) -> None:
            events.append("worker-start")
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                events.append("worker-cancelled")
                raise

    app.router.lifespan_context = original_lifespan
    monkeypatch.setattr(lifecycle_module, "RemindersWorker", FakeWorker)
    assert install_reminder_worker_lifespan(app, _settings())

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=0.2)
        assert events == ["original-enter", "worker-start"]

    assert events == [
        "original-enter",
        "worker-start",
        "worker-cancelled",
        "original-exit",
    ]


async def test_interaction_processor_auto_gates_and_cancels_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    original = app.router.lifespan_context
    manager = cast(RuntimeConfigManager, object())

    assert not install_interaction_processor_lifespan(
        app,
        _settings(telegram_processor_enabled=False),
        db=None,
        tools=[],
        instructions=[],
        runtime_config_manager=manager,
    )
    assert app.router.lifespan_context is original

    assert not install_interaction_processor_lifespan(
        app,
        _settings(telegram_processor_enabled=True, telegram_admission_enabled=False),
        db=None,
        tools=[],
        instructions=[],
        runtime_config_manager=manager,
    )
    assert app.router.lifespan_context is original

    recovered = asyncio.Event()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class FakeProcessor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def recover_once(self) -> int:
            recovered.set()
            return 1

        async def run_forever(self, interval_seconds: float) -> None:
            assert interval_seconds == 1
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    monkeypatch.setattr(lifecycle_module, "InteractionProcessor", FakeProcessor)
    assert install_interaction_processor_lifespan(
        app,
        _settings(telegram_processor_enabled=True, telegram_admission_enabled=True),
        db=None,
        tools=[],
        instructions=[],
        runtime_config_manager=manager,
    )

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(recovered.wait(), timeout=0.2)
        await asyncio.wait_for(started.wait(), timeout=0.2)
        task = app.state.telegram_interaction_processor_task
        assert task.get_name() == "telegram-interaction-processor"
        assert not task.done()

    assert cancelled.is_set()
    assert not hasattr(app.state, "telegram_interaction_processor_task")
