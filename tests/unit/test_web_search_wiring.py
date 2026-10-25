"""Application wiring tests for the opt-in public web-search tool."""

from __future__ import annotations

from src.config import Settings
from src.main import _init_domain_tools


def test_web_search_is_not_registered_when_disabled() -> None:
    # Explícito: Settings lee también variables del proceso, no sólo el .env.
    settings = Settings(
        _env_file=None,
        app_env="development",
        ancora_database_url="",
        telegram_token="",
        web_search_enabled=False,
    )

    tools = _init_domain_tools(settings)

    assert tools == []


def test_web_search_is_registered_without_domain_database_when_enabled() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        ancora_database_url="",
        telegram_token="",
        web_search_enabled=True,
        tavily_api_key="tvly-test",
    )

    tools = _init_domain_tools(settings)

    assert [tool.__name__ for tool in tools] == ["search_web"]
