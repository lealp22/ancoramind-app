"""Unit tests for the governed Telegram pairing operator CLI (BL-24 T4)."""

from __future__ import annotations

import argparse

import pytest

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
        )
    )

    assert operation == (
        "POST",
        "/admin/telegram-pairing/invitations",
        {
            "max_uses": 2,
            "expires_in_minutes": 90,
            "reason": "controlled evaluator cohort",
        },
        True,
    )


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
