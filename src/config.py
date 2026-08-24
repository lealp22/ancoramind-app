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
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
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
    ancora_database_url: str = ""

    # ── Security ─────────────────────────────────────
    allowed_telegram_user_ids: str = ""

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