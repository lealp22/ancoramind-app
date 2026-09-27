"""Unit tests for deterministic Telegram commands and session generations (BL-28)."""

from __future__ import annotations

import pytest

from src.domain.interactions.commands import (
    HELP_REPLY,
    NEW_SESSION_REPLY,
    UNSUPPORTED_COMMAND_REPLY,
    default_session_id,
    handle_telegram_command,
    next_session_id,
    parse_telegram_command,
    parse_telegram_pairing_command,
    telemetry_label,
)


class TestParseTelegramCommand:
    def test_parses_a_plain_command(self) -> None:
        command = parse_telegram_command("/new")

        assert command is not None
        assert command.name == "new"
        assert command.raw == "/new"

    def test_normalizes_case_and_ignores_arguments(self) -> None:
        command = parse_telegram_command("  /New ahora mismo  ")

        assert command is not None
        assert command.name == "new"

    def test_parses_a_command_addressed_to_this_bot(self) -> None:
        command = parse_telegram_command("/help@AncoraMindBot", bot_username="@ancoramindbot")

        assert command is not None
        assert command.name == "help"

    def test_a_command_addressed_to_another_bot_is_conversation(self) -> None:
        assert parse_telegram_command("/new@otherbot", bot_username="ancoramindbot") is None

    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "   ",
            "hola",
            "/",
            "//new",
            "/new/mas",
            "/new-algo",
            "/home/user/notas.txt",
            "/" + "a" * 33,
        ],
    )
    def test_non_commands_stay_conversation(self, text: str | None) -> None:
        assert parse_telegram_command(text) is None

    def test_pairing_requires_one_bounded_credential_argument(self) -> None:
        code = "a" * 24

        pairing = parse_telegram_pairing_command(f"/pair {code}")

        assert pairing is not None
        assert pairing.code == code
        assert parse_telegram_pairing_command("/pair") is None
        assert parse_telegram_pairing_command(f"/pair {code} trailing") is None
        assert parse_telegram_pairing_command("/pair too-short") is None


class TestHandleTelegramCommand:
    def test_new_resets_the_conversation(self) -> None:
        command = parse_telegram_command("/new")
        assert command is not None

        handling = handle_telegram_command(command)

        assert handling.resets_session is True
        assert handling.reply_text == NEW_SESSION_REPLY

    @pytest.mark.parametrize("text", ["/help", "/start"])
    def test_help_keeps_the_conversation(self, text: str) -> None:
        command = parse_telegram_command(text)
        assert command is not None

        handling = handle_telegram_command(command)

        assert handling.resets_session is False
        assert handling.reply_text == HELP_REPLY

    def test_unknown_command_never_echoes_user_text(self) -> None:
        command = parse_telegram_command("/borralotodo")
        assert command is not None

        handling = handle_telegram_command(command)

        assert handling.reply_text == UNSUPPORTED_COMMAND_REPLY
        assert handling.resets_session is False
        assert "borralotodo" not in handling.reply_text

    def test_replies_carry_no_markdown_markers(self) -> None:
        for reply in (HELP_REPLY, NEW_SESSION_REPLY, UNSUPPORTED_COMMAND_REPLY):
            assert "**" not in reply
            assert "`" not in reply


class TestSessionGenerations:
    def test_default_session_is_used_before_any_new(self) -> None:
        assert default_session_id(77) == "tg:ancoramind:77"

    def test_next_session_appends_and_increments_the_generation(self) -> None:
        assert next_session_id(77, None) == "tg:ancoramind:77:1"
        assert next_session_id(77, "tg:ancoramind:77") == "tg:ancoramind:77:1"
        assert next_session_id(77, "tg:ancoramind:77:1") == "tg:ancoramind:77:2"
        assert next_session_id(77, "tg:ancoramind:77:41") == "tg:ancoramind:77:42"

    @pytest.mark.parametrize(
        "stored",
        ["tg:ancoramind:88:9", "tg:ancoramind:77:abc", "otro:formato", "  "],
    )
    def test_unexpected_session_shapes_restart_the_counter(self, stored: str) -> None:
        assert next_session_id(77, stored) == "tg:ancoramind:77:1"


class TestTelemetryLabel:
    def test_supported_commands_use_their_own_bounded_name(self) -> None:
        command = parse_telegram_command("/new")
        assert command is not None
        assert telemetry_label(command) == "new"

    def test_unsupported_commands_never_leak_user_text(self) -> None:
        command = parse_telegram_command("/borralotodo")
        assert command is not None
        assert telemetry_label(command) == "unsupported"
