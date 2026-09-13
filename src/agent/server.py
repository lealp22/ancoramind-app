"""HTTP server configuration for local development and managed deployment."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    """Resolved AgentOS server settings for the current runtime environment."""

    host: str
    port: int
    reload: bool


def resolve_server_config(
    app_env: str,
    environ: Mapping[str, str],
) -> ServerConfig:
    """Resolve host, port, and reload mode without coupling to a deployment host.

    Railway provides ``PORT`` dynamically. ``AGENT_OS_PORT`` remains supported
    for local AgentOS configuration, while ``PORT`` takes precedence.
    """
    is_development = app_env.lower() == "development"
    host = environ.get("AGENT_OS_HOST") or ("localhost" if is_development else "0.0.0.0")
    raw_port = environ.get("PORT") or environ.get("AGENT_OS_PORT") or "7777"

    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(f"Invalid HTTP port: {raw_port}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"HTTP port must be between 1 and 65535: {port}")

    return ServerConfig(host=host, port=port, reload=is_development)
