"""AncoraMind — Application configuration via Pydantic Settings."""

from pydantic import Field, model_validator
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
    llm_model: str = "gpt-5.6-luna"
    llm_base_url: str | None = None
    agent_tool_call_limit: int = Field(default=12, ge=1, le=20)
    """Hard safety cap for tool calls in a single agent run (specs/013 T7 target)."""
    litellm_proxy_enabled: bool = False
    """Route all application inference through the private LiteLLM Proxy (T11)."""
    litellm_proxy_base_url: str = ""
    """Private OpenAI-compatible LiteLLM /v1 URL; never expose the proxy publicly."""
    litellm_proxy_virtual_key: str = ""
    """AncoraMind-only LiteLLM virtual key; Railway secret and never a runtime revision."""
    litellm_proxy_default_route: str = "ancoramind-default-r1"
    """Versioned LiteLLM alias used by the transitional AgentOS singleton."""

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
    execution_budget_fingerprint_key: str = ""
    """Explicit HMAC key for tool-call fingerprints; when empty, a dedicated
    subkey is derived from TELEGRAM_PAYLOAD_ENCRYPTION_KEY (Railway secrets only)."""

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
    max_file_size_mb: int = Field(default=20, ge=1, le=20)
    """Maximum Telegram attachment size accepted for document ingestion."""
    allowed_mime_types: str = "application/pdf,image/jpeg,image/png"
    """Comma-separated MIME allowlist for Telegram document ingestion."""
    document_vision_max_pdf_pages: int = Field(default=3, ge=1, le=10)
    """Maximum PDF pages rendered to images for the vision extraction route."""

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

    @property
    def allowed_document_mime_types(self) -> frozenset[str]:
        """Return normalized MIME types accepted from Telegram attachments."""
        return frozenset(
            mime.strip().lower() for mime in self.allowed_mime_types.split(",") if mime.strip()
        )

    @property
    def budget_fingerprint_key(self) -> str | None:
        """HMAC key for tool-call fingerprints (T8).

        Prefers an explicit ``EXECUTION_BUDGET_FINGERPRINT_KEY`` and otherwise
        derives a dedicated subkey from the payload encryption secret, so the
        governed processor path (which already requires that secret) always has
        a fingerprint key available.
        """
        if self.execution_budget_fingerprint_key:
            return self.execution_budget_fingerprint_key
        from src.domain.llm_access.fingerprints import derive_fingerprint_key

        return derive_fingerprint_key(self.telegram_payload_encryption_key)

    # ── Observability ────────────────────────────────
    log_level: str = "INFO"
    observability_json_logs: bool = True
    """Emit structured metadata-only logs; enabled by default for every environment."""
    otel_exporter_otlp_endpoint: str = ""
    """Private Collector gRPC endpoint. Empty keeps OTLP exporting disabled/fail-open."""
    otel_exporter_otlp_insecure: bool = True
    otel_exporter_otlp_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    otel_export_interval_millis: int = Field(default=30000, ge=1000, le=300000)
    health_probe_interval_seconds: float = Field(default=30.0, ge=5, le=300)
    """Cadence of the internal metadata-only health monitor; it never gates traffic."""

    # ── Application ──────────────────────────────────
    app_debug: bool = False

    @property
    def db_url(self) -> str | None:
        """Return the database URL for Agno, or None for default SQLite."""
        return self.agno_database_url if self.agno_database_url else None

    @model_validator(mode="after")
    def validate_litellm_proxy_settings(self) -> "Settings":
        """Fail closed: an enabled Gateway may not silently fall back to a provider."""
        if not self.litellm_proxy_enabled:
            return self
        missing = [
            name
            for name, value in (
                ("LITELLM_PROXY_BASE_URL", self.litellm_proxy_base_url),
                ("LITELLM_PROXY_VIRTUAL_KEY", self.litellm_proxy_virtual_key),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError("LITELLM_PROXY_ENABLED requires: " + ", ".join(missing))
        if not self.litellm_proxy_default_route.strip():
            raise ValueError("LITELLM_PROXY_DEFAULT_ROUTE must not be blank")
        return self
