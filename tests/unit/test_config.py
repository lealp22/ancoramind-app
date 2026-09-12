"""Unit tests for application configuration."""

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestSettings:
    """Tests for Settings loaded from environment variables."""

    def test_default_values(self, monkeypatch):
        """Settings should load with sensible defaults when no env vars are set."""
        # Ensure no leaking env vars
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AGNO_DATABASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        monkeypatch.delenv("AGENT_TOOL_CALL_LIMIT", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("APP_DEBUG", raising=False)

        settings = Settings(_env_file=None)
        assert settings.llm_model == "gpt-5.4-mini"
        assert settings.agent_tool_call_limit == 8
        assert settings.app_env == "development"
        assert settings.telegram_token == ""
        assert settings.app_debug is False

    def test_env_override(self, monkeypatch):
        """Environment variables should override defaults."""
        monkeypatch.setenv("LLM_MODEL", "gpt-5.6-luna")
        monkeypatch.setenv("AGENT_TOOL_CALL_LIMIT", "5")
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        settings = Settings(_env_file=None)
        assert settings.llm_model == "gpt-5.6-luna"
        assert settings.agent_tool_call_limit == 5
        assert settings.app_env == "production"
        assert settings.log_level == "DEBUG"

    @pytest.mark.parametrize("value", ["0", "21"])
    def test_agent_tool_call_limit_rejects_unsafe_values(self, monkeypatch, value):
        monkeypatch.setenv("AGENT_TOOL_CALL_LIMIT", value)

        with pytest.raises(ValidationError, match="agent_tool_call_limit"):
            Settings(_env_file=None)

    def test_db_url_property_when_empty(self, monkeypatch):
        """db_url should return None when AGNO_DATABASE_URL is not set."""
        monkeypatch.delenv("AGNO_DATABASE_URL", raising=False)
        settings = Settings(_env_file=None)
        assert settings.db_url is None

    def test_db_url_property_when_set(self, monkeypatch):
        """db_url should return the URL when AGNO_DATABASE_URL is set."""
        db_url = "postgresql+psycopg://user:pass@localhost:5432/db"
        monkeypatch.setenv("AGNO_DATABASE_URL", db_url)
        settings = Settings(_env_file=None)
        assert settings.db_url == db_url
