"""AncoraMind — Application configuration via Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM (Agno auto-detects from standard env vars) ──
    llm_provider: str = "openai"
    """Provider: openai | openrouter | openai-like"""

    openai_api_key: str = ""
    openrouter_api_key: str = ""
    llm_model: str = "gpt-5.4-mini"
    llm_base_url: str | None = None
    agent_tool_call_limit: int = Field(default=12, ge=1, le=20)
    """Hard safety cap for tool calls in a single agent run (specs/013 T7 target)."""

    # ── Telegram ──────────────────────────────────────
    telegram_token: str = ""
    telegram_webhook_secret_token: str = ""
    telegram_payload_encryption_key: str = ""
    """Fernet key for recoverable Telegram payloads; Railway secret only."""
    telegram_payload_key_version: int = Field(default=1, ge=1)
    telegram_bot_id: int = Field(default=0, ge=0)
    """Numeric Telegram bot identity from getMe; required for durable admission."""
    telegram_admission_enabled: bool = False
    """Enable the AncoraMind-owned /telegram/webhook admission endpoint."""
    telegram_admission_user_burst: int = Field(default=5, ge=1)
    telegram_admission_burst_window_seconds: int = Field(default=10, ge=1)
    telegram_admission_user_requests_per_minute: int = Field(default=10, ge=1)
    telegram_admission_user_requests_per_hour: int = Field(default=120, ge=1)
    telegram_admission_pending_global: int = Field(default=20, ge=1)
    telegram_admission_queued_per_chat: int = Field(default=5, ge=1)
    telegram_processor_enabled: bool = False
    """Start the T5 processor; requires the same trusted admission prerequisites."""
    telegram_processor_poll_interval_seconds: float = Field(default=1.0, gt=0)
    telegram_processor_global_concurrency: int = Field(default=2, ge=1, le=20)

    # ── Governed runtime config control plane (T6 / specs-013) ──
    runtime_config_admin_enabled: bool = False
    """Expose protected runtime-config admin API; disabled by default."""
    runtime_config_admin_token: str = ""
    """Bearer token for the HTTPS admin API; Railway secret only."""
    runtime_config_bootstrap_default_route: str = "ancoramind-default"
    """Secret-free logical route used before the DB control plane is available."""
    app_env: str = "development"

    # ── ngrok ─────────────────────────────────────────
    ngrok_url: str = ""

    # ── PostgreSQL ────────────────────────────────────
    agno_database_url: str = ""
    # ── Document Storage ─────────────────────────────
    document_storage_path: str = "./data/documents"
    document_storage_backend: str = "local"
    """Backend: local | supabase"""
    ancora_database_url: str = ""

    # ── Supabase (storage + managed PostgreSQL host) ──
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "ancora-documents"

    # ── Security ─────────────────────────────────────
    allowed_telegram_user_ids: str = ""

    # ── Reminder worker (BL-5 / ADR-003) ─────────────
    reminder_worker_enabled: bool = True
    """Start the reminder background worker. Auto-gated: also requires
    ANCORA_DATABASE_URL and TELEGRAM_TOKEN."""
    reminder_poll_interval_seconds: int = 60
    """Seconds between reminder worker scan cycles."""

    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse comma-separated allowed user IDs."""
        raw = self.allowed_telegram_user_ids.strip()
        if not raw:
            return []
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]

    # ── Observability ────────────────────────────────
    log_level: str = "INFO"

    # ── Application ──────────────────────────────────
    app_debug: bool = False

    @property
    def db_url(self) -> str | None:
        """Return the database URL for Agno, or None for default SQLite."""
        return self.agno_database_url if self.agno_database_url else None
