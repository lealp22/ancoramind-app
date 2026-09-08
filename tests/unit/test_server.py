"""Unit tests for environment-aware AgentOS server configuration."""

import pytest

from src.agent.server import ServerConfig, resolve_server_config


def test_development_defaults_to_localhost_with_reload():
    result = resolve_server_config("development", {})

    assert result == ServerConfig(host="localhost", port=7777, reload=True)


def test_production_uses_railway_port_and_disables_reload():
    result = resolve_server_config("production", {"PORT": "8080"})

    assert result == ServerConfig(host="0.0.0.0", port=8080, reload=False)


def test_port_prefers_railway_port_over_agent_os_port():
    result = resolve_server_config(
        "production",
        {"PORT": "8080", "AGENT_OS_PORT": "7777", "AGENT_OS_HOST": "127.0.0.1"},
    )

    assert result == ServerConfig(host="127.0.0.1", port=8080, reload=False)


@pytest.mark.parametrize("raw_port", ["0", "65536", "not-a-port"])
def test_invalid_port_raises_clear_error(raw_port):
    with pytest.raises(ValueError, match="port"):
        resolve_server_config("production", {"PORT": raw_port})
