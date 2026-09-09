"""AncoraMind — Application configuration via Pydantic Settings."""

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

    # ── Telegram ──────────────────────────────────────
    telegram_token: str = ""
    telegram_webhook_secret_token: str = ""
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
