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
        monkeypatch.delenv("LITELLM_PROXY_ENABLED", raising=False)
        monkeypatch.delenv("LITELLM_PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_PROXY_VIRTUAL_KEY", raising=False)
        monkeypatch.delenv("TELEGRAM_ADMISSION_ENABLED", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_ID", raising=False)
        monkeypatch.delenv("TELEGRAM_ADMISSION_USER_BURST", raising=False)
        monkeypatch.delenv("TELEGRAM_PROCESSOR_ENABLED", raising=False)
        monkeypatch.delenv("TELEGRAM_PROCESSOR_POLL_INTERVAL_SECONDS", raising=False)
        monkeypatch.delenv("TELEGRAM_PROCESSOR_GLOBAL_CONCURRENCY", raising=False)
        monkeypatch.delenv("RUNTIME_CONFIG_ADMIN_ENABLED", raising=False)
        monkeypatch.delenv("RUNTIME_CONFIG_ADMIN_TOKEN", raising=False)
        monkeypatch.delenv("RUNTIME_CONFIG_BOOTSTRAP_DEFAULT_ROUTE", raising=False)
        # The other defaults are asserted in an explicit development
        # environment; the safe APP_ENV default itself is covered by
        # test_app_env_defaults_to_production (specs/023 T2).
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("OBSERVABILITY_JSON_LOGS", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("APP_DEBUG", raising=False)

        settings = Settings(_env_file=None)
        assert settings.llm_model == "gpt-6-luna"
        assert settings.agent_tool_call_limit == 12
        assert settings.litellm_proxy_enabled is False
        assert settings.app_env == "development"
        assert settings.telegram_token == ""
        assert settings.telegram_admission_enabled is False
        assert settings.telegram_bot_id == 0
        assert settings.telegram_admission_user_burst == 5
        assert settings.telegram_processor_enabled is False
        assert settings.telegram_processor_poll_interval_seconds == 1.0
        assert settings.telegram_processor_global_concurrency == 2
        assert settings.runtime_config_admin_enabled is False
        assert settings.runtime_config_admin_token == ""
        assert settings.runtime_config_bootstrap_default_route == "ancoramind-default"
        assert settings.app_debug is False
        assert settings.observability_json_logs is True
        assert settings.otel_exporter_otlp_endpoint == ""

    def test_env_override(self, monkeypatch):
        """Environment variables should override defaults."""
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        monkeypatch.setenv("AGENT_TOOL_CALL_LIMIT", "5")
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AGENT_OS_SECURITY_KEY", "test-only-secret")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")


        settings = Settings(_env_file=None)
        assert settings.llm_model == "custom-model"
        assert settings.agent_tool_call_limit == 5
        assert settings.app_env == "production"
        assert settings.log_level == "DEBUG"

    def test_observability_env_overrides(self, monkeypatch):
        monkeypatch.setenv("OBSERVABILITY_JSON_LOGS", "false")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.internal:4317")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_INSECURE", "false")

        settings = Settings(_env_file=None)

        assert settings.observability_json_logs is False
        assert settings.otel_exporter_otlp_endpoint == "http://collector.internal:4317"
        assert settings.otel_exporter_otlp_insecure is False

    def test_litellm_proxy_requires_private_url_and_virtual_key(self, monkeypatch) -> None:
        # A local Gateway validation can export these; clear them so the
        # fail-closed invariant is asserted instead of the ambient environment.
        monkeypatch.delenv("LITELLM_PROXY_ENABLED", raising=False)
        monkeypatch.delenv("LITELLM_PROXY_BASE_URL", raising=False)
        monkeypatch.delenv("LITELLM_PROXY_VIRTUAL_KEY", raising=False)

        with pytest.raises(ValidationError, match="LITELLM_PROXY_BASE_URL"):
            Settings(litellm_proxy_enabled=True, _env_file=None)

        with pytest.raises(ValidationError, match="LITELLM_PROXY_VIRTUAL_KEY"):
            Settings(
                litellm_proxy_enabled=True,
                litellm_proxy_base_url="http://litellm.railway.internal:4000",
                _env_file=None,
            )

    def test_litellm_proxy_settings_are_loaded_when_complete(self, monkeypatch) -> None:
        monkeypatch.delenv("LITELLM_PROXY_DEFAULT_ROUTE", raising=False)

        settings = Settings(
            litellm_proxy_enabled=True,
            litellm_proxy_base_url="http://litellm.railway.internal:4000",
            litellm_proxy_virtual_key="sk-ancoramind-only",
            _env_file=None,
        )

        assert settings.litellm_proxy_enabled is True
        assert settings.litellm_proxy_default_route == "ancoramind-default-r1"

    def test_telegram_admission_env_overrides(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ADMISSION_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_ID", "987654")
        monkeypatch.setenv("TELEGRAM_ADMISSION_USER_BURST", "3")

        settings = Settings(_env_file=None)

        assert settings.telegram_admission_enabled is True
        assert settings.telegram_bot_id == 987654
        assert settings.telegram_admission_user_burst == 3

    def test_telegram_processor_env_overrides(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_PROCESSOR_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_PROCESSOR_POLL_INTERVAL_SECONDS", "2.5")
        monkeypatch.setenv("TELEGRAM_PROCESSOR_GLOBAL_CONCURRENCY", "4")

        settings = Settings(_env_file=None)

        assert settings.telegram_processor_enabled is True
        assert settings.telegram_processor_poll_interval_seconds == 2.5
        assert settings.telegram_processor_global_concurrency == 4

    def test_runtime_config_admin_env_overrides(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_CONFIG_ADMIN_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONFIG_ADMIN_TOKEN", "admin-secret")
        monkeypatch.setenv("RUNTIME_CONFIG_BOOTSTRAP_DEFAULT_ROUTE", "ancoramind-fast")

        settings = Settings(_env_file=None)

        assert settings.runtime_config_admin_enabled is True
        assert settings.runtime_config_admin_token == "admin-secret"
        assert settings.runtime_config_bootstrap_default_route == "ancoramind-fast"

    def test_app_env_defaults_to_production(self, monkeypatch):
        """specs/023 T2: with APP_ENV absent, the app runs in its safe mode
        (production), so production secrets are demanded rather than
        silently skipped."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("AGENT_OS_SECURITY_KEY", "test-only-secret")

        settings = Settings(_env_file=None)

        assert settings.app_env == "production"

    def test_missing_app_env_fails_closed_without_production_secrets(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("AGENT_OS_SECURITY_KEY", raising=False)

        with pytest.raises(ValidationError, match="AGENT_OS_SECURITY_KEY"):
            Settings(_env_file=None)

    def test_agent_os_security_key_required_outside_development(self, monkeypatch):
        """specs/023 T1: a non-development app must not expose AgentOS's REST
        surface without a bearer credential."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("AGENT_OS_SECURITY_KEY", raising=False)

        with pytest.raises(ValidationError, match="AGENT_OS_SECURITY_KEY"):
            Settings(_env_file=None)

    def test_agent_os_security_key_not_required_in_development(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("AGENT_OS_SECURITY_KEY", raising=False)

        settings = Settings(_env_file=None)

        assert settings.agent_os_security_key == ""

    def test_agent_os_security_key_accepted_in_production(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AGENT_OS_SECURITY_KEY", "a-real-secret")

        settings = Settings(_env_file=None)

        assert settings.agent_os_security_key == "a-real-secret"

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
