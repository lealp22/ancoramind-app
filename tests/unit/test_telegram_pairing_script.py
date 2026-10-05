"""Unit tests for the governed Telegram pairing operator CLI (BL-24 T4)."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

from scripts import telegram_pairing
from scripts.telegram_pairing import build_operation


def test_list_pending_is_read_only_and_bounded() -> None:
    operation = build_operation(argparse.Namespace(command="list-pending", limit=25))

    assert operation == ("GET", "/admin/telegram-pairing/requests?limit=25", None, False)


def test_issue_builds_auditable_payload_without_a_raw_code_argument() -> None:
    operation = build_operation(
        argparse.Namespace(
            command="issue",
            max_uses=2,
            expires_in_minutes=90,
            reason="controlled evaluator cohort",
            auto_approve=False,
        )
    )

    assert operation == (
        "POST",
        "/admin/telegram-pairing/invitations",
        {
            "max_uses": 2,
            "expires_in_minutes": 90,
            "reason": "controlled evaluator cohort",
            "auto_approve": False,
        },
        True,
    )


def test_issue_can_opt_into_auto_approve() -> None:
    operation = build_operation(
        argparse.Namespace(
            command="issue",
            max_uses=1,
            expires_in_minutes=60,
            reason="trusted colleague",
            auto_approve=True,
        )
    )

    assert operation[2]["auto_approve"] is True


@pytest.mark.parametrize(
    ("command", "expected_path"),
    [
        ("approve", "/admin/telegram-pairing/requests/request-id/approve"),
        ("reject", "/admin/telegram-pairing/requests/request-id/reject"),
    ],
)
def test_decisions_use_the_protected_request_routes(command: str, expected_path: str) -> None:
    operation = build_operation(
        argparse.Namespace(command=command, request_id="request-id", reason="reviewed")
    )

    assert operation == ("POST", expected_path, {"reason": "reviewed"}, True)


def test_revocations_target_the_correct_durable_state() -> None:
    invitation = build_operation(
        argparse.Namespace(
            command="revoke-invitation",
            invitation_id="invitation-id",
            reason="distribution stopped",
        )
    )
    authorization = build_operation(
        argparse.Namespace(
            command="revoke-authorization",
            telegram_user_id=42,
            reason="evaluation ended",
        )
    )

    assert invitation == (
        "POST",
        "/admin/telegram-pairing/invitations/invitation-id/revoke",
        {"reason": "distribution stopped"},
        True,
    )
    assert authorization == (
        "POST",
        "/admin/telegram-pairing/authorizations/42/revoke",
        {"reason": "evaluation ended"},
        True,
    )


def test_unknown_command_is_rejected_without_network_access() -> None:
    with pytest.raises(ValueError, match="Unsupported pairing command"):
        build_operation(argparse.Namespace(command="unknown"))


def test_main_list_pending_does_not_require_actor_or_print_bearer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        telegram_pairing,
        "_parse_args",
        lambda: argparse.Namespace(command="list-pending", limit=10, base_url="https://example.test"),
    )
    monkeypatch.setattr(
        telegram_pairing,
        "_settings",
        lambda: SimpleNamespace(runtime_config_admin_token="bearer-that-must-not-print"),
    )

    def request(**kwargs: object) -> tuple[int, str]:
        captured.update(kwargs)
        return 200, '{"requests": []}'

    monkeypatch.setattr(telegram_pairing, "_request", request)

    assert telegram_pairing.main() == 0

    output = capsys.readouterr()
    assert captured["actor"] is None
    assert "bearer-that-must-not-print" not in output.out
    assert "bearer-that-must-not-print" not in output.err
    assert '"requests": []' in output.out


def test_main_issue_requires_actor_before_making_a_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("RUNTIME_CONFIG_ADMIN_ACTOR", raising=False)
    monkeypatch.setattr(
        telegram_pairing,
        "_parse_args",
        lambda: argparse.Namespace(
            command="issue",
            max_uses=1,
            expires_in_minutes=60,
            reason="controlled evaluator",
            auto_approve=False,
            base_url="https://example.test",
        ),
    )
    monkeypatch.setattr(
        telegram_pairing,
        "_settings",
        lambda: SimpleNamespace(runtime_config_admin_token="bearer-that-must-not-print"),
    )
    monkeypatch.setattr(
        telegram_pairing,
        "_request",
        lambda **_: pytest.fail("A mutation without an actor must not make a request"),
    )

    assert telegram_pairing.main() == 1

    output = capsys.readouterr()
    assert "RUNTIME_CONFIG_ADMIN_ACTOR is required" in output.err
    assert "bearer-that-must-not-print" not in output.err


def test_main_preserves_one_time_issue_response_and_returns_failure_for_http_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RUNTIME_CONFIG_ADMIN_ACTOR", "operator@example.com")
    monkeypatch.setattr(
        telegram_pairing,
        "_parse_args",
        lambda: argparse.Namespace(
            command="issue",
            max_uses=1,
            expires_in_minutes=60,
            reason="controlled evaluator",
            auto_approve=False,
            base_url="https://example.test",
        ),
    )
    monkeypatch.setattr(
        telegram_pairing,
        "_settings",
        lambda: SimpleNamespace(runtime_config_admin_token="bearer-that-must-not-print"),
    )
    monkeypatch.setattr(
        telegram_pairing,
        "_request",
        lambda **_: (201, '{"code":"one-time-code","invitation":{"id":"safe-id"}}'),
    )

    assert telegram_pairing.main() == 0
    output = capsys.readouterr()
    assert "one-time-code" in output.out
    assert "bearer-that-must-not-print" not in output.out

    monkeypatch.setattr(telegram_pairing, "_request", lambda **_: (409, '{"detail":"conflict"}'))

    assert telegram_pairing.main() == 1
    assert "HTTP 409" in capsys.readouterr().out
