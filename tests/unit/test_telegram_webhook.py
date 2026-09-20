"""Unit tests for Telegram webhook deployment helpers."""

import json
from io import BytesIO
from urllib.error import URLError

import pytest

from src.agent.telegram_webhook import (
    build_command_menu_payload,
    build_webhook_url,
    summarize_webhook_info,
    telegram_api_request,
)
from src.domain.interactions.commands import (
    BOT_COMMAND_MENU,
    handle_telegram_command,
    parse_telegram_command,
)


class FakeResponse:
    """Minimal context-manager response for urllib request tests."""

    def __init__(self, body: dict):
        self._body = BytesIO(json.dumps(body).encode("utf-8"))

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.mark.parametrize(
    "base_url,expected",
    [
        (
            "https://ancoramind-production.up.railway.app",
            "https://ancoramind-production.up.railway.app/telegram/webhook",
        ),
        (
            "https://ancoramind-production.up.railway.app/",
            "https://ancoramind-production.up.railway.app/telegram/webhook",
        ),
    ],
)
def test_build_webhook_url(base_url, expected):
    assert build_webhook_url(base_url) == expected


@pytest.mark.parametrize(
    "base_url",
    ["http://example.test", "not-a-url", "https://example.test?x=1"],
)
def test_build_webhook_url_requires_clean_https_url(base_url):
    with pytest.raises(ValueError, match="Webhook base URL"):
        build_webhook_url(base_url)


def test_telegram_api_request_posts_payload_without_exposing_token():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return FakeResponse({"ok": True, "result": {"url": "https://example.test"}})

    result = telegram_api_request(
        "sensitive-token",
        "setWebhook",
        {"url": "https://example.test/telegram/webhook", "secret_token": "secret"},
        opener=opener,
    )

    request, timeout = requests[0]
    assert result == {"url": "https://example.test"}
    assert timeout == 15
    assert request.full_url.endswith("/setsWebhook") is False
    assert request.full_url.endswith("/setWebhook")
    assert b"secret_token=secret" in request.data


def test_telegram_api_request_returns_sanitized_error_message():
    def opener(request, timeout):
        return FakeResponse({"ok": False, "description": "Bad Request: invalid webhook URL"})

    with pytest.raises(RuntimeError, match="invalid webhook URL") as exc_info:
        telegram_api_request("sensitive-token", "setWebhook", opener=opener)

    assert "sensitive-token" not in str(exc_info.value)


def test_telegram_api_request_handles_network_error_without_token():
    def opener(request, timeout):
        raise URLError("network unavailable")

    with pytest.raises(RuntimeError, match="network unavailable") as exc_info:
        telegram_api_request("sensitive-token", "getWebhookInfo", opener=opener)

    assert "sensitive-token" not in str(exc_info.value)


def test_summarize_webhook_info_excludes_secret_like_fields():
    summary = summarize_webhook_info(
        {
            "url": "https://example.test/telegram/webhook",
            "pending_update_count": 2,
            "secret_token": "must-not-appear",
            "allowed_updates": ["message"],
        }
    )

    assert summary == {
        "url": "https://example.test/telegram/webhook",
        "pending_update_count": 2,
    }


class TestCommandMenuPayload:
    def test_serializes_the_domain_command_menu(self) -> None:
        payload = build_command_menu_payload(BOT_COMMAND_MENU)

        assert json.loads(payload) == [
            {"command": "new", "description": "Empezar una conversación nueva"},
            {"command": "help", "description": "Ver los comandos disponibles"},
        ]

    def test_every_advertised_command_is_actually_handled(self) -> None:
        for name, _ in BOT_COMMAND_MENU:
            command = parse_telegram_command(f"/{name}")
            assert command is not None
            assert handle_telegram_command(command).reply_text

    @pytest.mark.parametrize(
        "commands",
        [
            (),
            (("con-guion", "descripción"),),
            (("ñ", "descripción"),),
            (("valido", "   "),),
            (("valido", "d" * 257),),
        ],
    )
    def test_rejects_entries_the_bot_api_would_refuse(self, commands) -> None:
        with pytest.raises(ValueError, match="command"):
            build_command_menu_payload(commands)
