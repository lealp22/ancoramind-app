"""Unit tests for wiring the AncoraMind-owned admission route before AgentOS."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pytest import MonkeyPatch

import src.main as main_module
from src.config import Settings


def _settings() -> Settings:
    return Settings(
        telegram_token="123456:token",
        ancora_database_url="postgresql+asyncpg://user:pass@localhost/db",
        telegram_admission_enabled=True,
        telegram_bot_id=456,
        telegram_webhook_secret_token="webhook-secret",
        telegram_payload_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        allowed_telegram_user_ids="999",
    )


def test_create_app_preserves_ancoramind_webhook_route_when_admission_enabled(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeAgentOS:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def get_app(self) -> FastAPI:
            base_app = captured["base_app"]
            assert isinstance(base_app, FastAPI)
            return base_app

    monkeypatch.setattr(main_module, "Settings", _settings)
    monkeypatch.setattr(main_module, "create_db", lambda **_: object())
    monkeypatch.setattr(main_module, "create_model_from_settings", lambda _: object())
    monkeypatch.setattr(main_module, "assemble_instructions", lambda: ["test"])
    monkeypatch.setattr(main_module, "_init_domain_tools", lambda _: [])
    monkeypatch.setattr(main_module, "create_ancora_agent", lambda **_: object())
    monkeypatch.setattr(main_module, "Telegram", lambda **_: object())
    monkeypatch.setattr(main_module, "AgentOS", FakeAgentOS)
    monkeypatch.setattr(main_module, "_register_reminder_worker", lambda *_: None)

    app, _ = main_module.create_app()

    routes = [route for route in app.routes if isinstance(route, APIRoute)]
    assert [(route.path, route.methods) for route in routes] == [
        ("/telegram/webhook", {"POST"}),
    ]
    assert captured["on_route_conflict"] == "preserve_base_app"
    assert captured["telemetry"] is False
    assert captured["tracing"] is False
