"""Host-side guardrails; actual library accounting proof runs offline in Docker."""

import json

import pytest

from scripts import check_litellm_accounting_offline as probe


@pytest.mark.parametrize("name", ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "LITELLM_MASTER_KEY",
                                 "LITELLM_PROXY_VIRTUAL_KEY", "DATABASE_URL", "REDIS_URL"])
def test_probe_refuses_credentialed_environment_before_importing_library(monkeypatch, capsys, name):
    monkeypatch.setattr(probe.importlib.metadata, "version", lambda _: probe.VERSION)
    monkeypatch.setenv(name, "synthetic-private-must-not-be-printed")
    assert probe.main() == 1
    output = capsys.readouterr()
    assert "synthetic-private" not in output.out + output.err
    assert json.loads(output.out) == {
        "status": "offline_accounting_blocked", "inference_started": False,
        "network_attempts": 0,
    }


def test_probe_refuses_wrong_version_without_starting_library(monkeypatch, capsys):
    monkeypatch.setattr(probe.importlib.metadata, "version", lambda _: "not-approved")
    assert probe.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "offline_accounting_blocked"
