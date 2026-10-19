"""Unit tests for the LiteLLM Gateway alias operator script (ADR-005 amendment).

These tests exercise the pure payload/allowlist logic only: no network, no
credentials and no real Gateway.
"""

from __future__ import annotations

import argparse
import json

import pytest

from scripts.litellm_gateway_alias import (
    DEFAULT_RPM,
    DEFAULT_TPM,
    AliasError,
    build_model_payload,
    command_publish,
    command_retire,
    is_base_alias,
    merge_alias_allowlist,
    remove_from_allowlist,
    validate_alias,
)


def _publish_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "alias": "ancoramind-default-r2",
        "model": "openrouter/gpt-5.6-luna",
        "rpm": DEFAULT_RPM,
        "tpm": DEFAULT_TPM,
        "force": False,
        "allow_base": False,
        "api_base": None,
        "num_retries": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_publish_payload_mirrors_the_base_alias_shape() -> None:
    payload = build_model_payload(alias="ancoramind-default-r2", model="openrouter/gpt-5.6-luna")

    assert payload["model_name"] == "ancoramind-default-r2"
    assert payload["litellm_params"] == {
        "model": "openrouter/gpt-5.6-luna",
        "api_key": "os.environ/OPENROUTER_API_KEY",
    }
    assert payload["model_info"] == {"rpm": DEFAULT_RPM, "tpm": DEFAULT_TPM}


def test_stt_payload_adds_api_base_and_single_attempt() -> None:
    payload = build_model_payload(
        alias="ancoramind-stt-r1",
        model="openai/openai/whisper-large-v3-turbo",
        api_base="https://openrouter.ai/api/v1",
        num_retries=0,
    )

    assert payload["litellm_params"] == {
        "model": "openai/openai/whisper-large-v3-turbo",
        "api_key": "os.environ/OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1",
        "num_retries": 0,
    }


def test_payload_rejects_insecure_api_base() -> None:
    with pytest.raises(AliasError, match="https"):
        build_model_payload(
            alias="ancoramind-stt-r1", model="openai/x", api_base="http://openrouter.ai"
        )


def test_payload_rejects_negative_retries() -> None:
    with pytest.raises(AliasError, match="num_retries"):
        build_model_payload(alias="ancoramind-stt-r1", model="openai/x", num_retries=-1)


def test_publish_payload_never_contains_a_secret() -> None:
    raw = json.dumps(build_model_payload(alias="ancoramind-default-r2", model="openrouter/x"))

    assert "sk-" not in raw
    assert "os.environ/OPENROUTER_API_KEY" in raw


def test_alias_must_be_versioned() -> None:
    invalid_aliases = (
        "ancoramind-default",
        "Ancoramind-Default-r2",
        "ancoramind-default-r0",
        "ab-r1",
    )
    for invalid in invalid_aliases:
        with pytest.raises(AliasError, match="versioned Gateway alias"):
            validate_alias(invalid)

    assert validate_alias("ancoramind-default-r12") == "ancoramind-default-r12"


def test_payload_rejects_blank_model_and_non_positive_limits() -> None:
    with pytest.raises(AliasError, match="model must not be blank"):
        build_model_payload(alias="ancoramind-default-r2", model="   ")

    with pytest.raises(AliasError, match="positive integers"):
        build_model_payload(alias="ancoramind-default-r2", model="openrouter/x", rpm=0)


def test_grant_is_additive_and_deduplicated() -> None:
    merged = merge_alias_allowlist(
        ["ancoramind-default-r1", "ancoramind-fast-r1"],
        ["ancoramind-default-r2", "ancoramind-fast-r1"],
    )

    # Base order preserved so a rollback to r1 keeps working without a re-grant.
    assert merged == [
        "ancoramind-default-r1",
        "ancoramind-fast-r1",
        "ancoramind-default-r2",
    ]


def test_grant_validates_every_requested_alias() -> None:
    with pytest.raises(AliasError, match="versioned Gateway alias"):
        merge_alias_allowlist(["ancoramind-default-r1"], ["not-versioned"])


def test_retire_removes_only_the_requested_alias() -> None:
    remaining = remove_from_allowlist(
        ["ancoramind-default-r1", "ancoramind-default-r2", "ancoramind-fast-r1"],
        ["ancoramind-default-r2"],
    )

    assert remaining == ["ancoramind-default-r1", "ancoramind-fast-r1"]


def test_base_aliases_are_recognised() -> None:
    assert is_base_alias("ancoramind-default-r1") is True
    assert is_base_alias("ancoramind-default-r2") is False


def test_publish_refuses_to_mutate_a_base_alias(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(AliasError, match="base alias declared in"):
        command_publish(_publish_args(alias="ancoramind-default-r1"), {}, dry_run=True)


def test_publish_dry_run_needs_no_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    assert command_publish(_publish_args(), {}, dry_run=True) == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed["model_name"] == "ancoramind-default-r2"
    assert printed["litellm_params"]["model"] == "openrouter/gpt-5.6-luna"


def test_retire_refuses_base_aliases_without_the_override() -> None:
    args = argparse.Namespace(alias=["ancoramind-default-r1"], allow_base=False)

    with pytest.raises(AliasError, match="Refusing to retire base aliases"):
        command_retire(args, {}, dry_run=True)


def test_retire_reports_the_guard_message_for_every_base_alias() -> None:
    args = argparse.Namespace(
        alias=["ancoramind-default-r1", "ancoramind-fast-r1"],
        allow_base=False,
    )

    with pytest.raises(AliasError) as excinfo:
        command_retire(args, {}, dry_run=True)

    assert "ancoramind-default-r1" in str(excinfo.value)
    assert "ancoramind-fast-r1" in str(excinfo.value)
