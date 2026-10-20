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
    llm_model: str = "gpt-6-luna"
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
    document_embedding_model: str = "text-embedding-3-small"
    """Physical embedding model for direct/local development only."""
    document_embedding_base_url: str | None = None
    document_embedding_dimensions: int = Field(default=1536, ge=1536, le=1536)
    """Fixed pgvector dimension; changing it requires a deliberate reindex migration."""
    document_embedding_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

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
    telegram_access_notice_enabled: bool = False
    """BL-52: bounded deterministic notice for rejected private users, without Agent/LLM.
    Independent of pairing; off by default until an explicit rollout.
    """
    pilot_notice_url: str = ""
    """Optional https link to the pilot terms, appended to the fixed /pair and /help
    replies. Empty (default) leaves those replies unchanged."""
    telegram_processor_enabled: bool = False
    telegram_voice_enabled: bool = False
    """Voice rollout gate; requires FFmpeg, private Gateway and versioned speech config."""
    telegram_voice_timeout_seconds: float = Field(default=60.0, gt=0, le=120)
    """Start the T5 processor; requires the same trusted admission prerequisites."""
    telegram_processor_poll_interval_seconds: float = Field(default=1.0, gt=0)
    telegram_processor_global_concurrency: int = Field(default=2, ge=1, le=20)
    telegram_fast_ack_enabled: bool = False
    """BL-32: send an early acknowledgement for attachment-bearing interactions
    before inference. Best-effort — a failure never blocks the main run."""
    context_compaction_enabled: bool = False
    """BL-34: summarize the oldest slice of a session's own exchange ledger
    via a governed LLM call once its cumulative tokens cross the threshold
    below. Off by default; a failed compaction never aborts the run."""
    context_compaction_token_threshold: int = Field(default=60_000, gt=0)
    """Cumulative session tokens (from llm_usage_events) that trigger compaction."""
    context_compaction_ratio: float = Field(default=0.4, gt=0, lt=1)
    """Fraction of the oldest exchanges summarized away once triggered."""
    governed_consent_enabled: bool = False
    """Resolve human consent and execute through the Core, never the LLM.
    Off by default: proposals remain pending and cannot execute; no legacy
    confirmation fallback. Enable only after the controlled Telegram rollout.
    """
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
    telegram_pairing_admin_enabled: bool = False
    """Expose protected operator endpoints for governed Telegram evaluator pairing."""
    telegram_pairing_enabled: bool = False
    """Enable private-chat `/pair <code>` redemption and durable authorization admission."""
    telegram_pairing_code_pepper: str = ""
    """Secret HMAC pepper for invitation codes; never persist or log the raw code."""

    # ── Admin dashboard (BL-43 / specs-027) ──────────
    admin_dashboard_enabled: bool = False
    """Expose the operator web dashboard at /admin/dashboard; disabled by default."""
    admin_dashboard_token: str = ""
    """Bearer token for the dashboard's own API, separate from
    RUNTIME_CONFIG_ADMIN_TOKEN so a browser-exposed secret never carries the
    CLI's runtime-config credential. Railway secret only."""
    admin_link_grafana_url: str = ""
    admin_link_railway_url: str = ""
    admin_link_supabase_url: str = ""
    admin_link_openrouter_url: str = ""
    admin_link_litellm_url: str = ""
    """Plain operator-facing links shown on the dashboard; empty hides the row."""
    app_env: str = "production"
    """Deployment environment. Defaults to the safe value (specs/023 T2):
    local development must opt in explicitly with APP_ENV=development, which
    relaxes Agno's webhook-secret check and AgentOS REST guarding."""
    agent_os_security_key: str = ""
    """Bearer token Agno's AgentOS requires on every REST route except
    /, /health, /info, /docs, /redoc. Railway secret only; required
    whenever APP_ENV != "development" (specs/023 T1)."""

    # ── Governed public web search (BL-30 / specs-025) ─────────────
    web_search_enabled: bool = False
    """Enable the bounded Tavily-only Phase 1 public web-search tool."""
    tavily_api_key: str = ""
    """Tavily secret held only in environment configuration; never log it."""
    web_search_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    web_search_max_results: int = Field(default=5, ge=1, le=5)
    web_search_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600)

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
    allowed_mime_types: str = (
        "application/pdf,image/jpeg,image/png,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    """Comma-separated MIME allowlist for Telegram document ingestion.

    The DOCX/XLSX/PPTX entries are the only types with a deterministic
    extractor (specs/021 Fase 2 / BL-35, ``src/agent/document_office.py``);
    macro-enabled `.docm`/`.xlsm`/`.pptm` and legacy binary `.doc`/`.xls`/
    `.ppt` are deliberately excluded.
    """
    document_vision_max_pdf_pages: int = Field(default=3, ge=1, le=10)
    """Maximum PDF pages rendered to images for the vision extraction route.

    Deliberately conservative: each page sent as an image costs a governed
    LLM inference call (BL-6, ``ancoramind-vision``). Does not apply to the
    deterministic text route — see ``document_text_max_pdf_pages``.
    """
    document_text_max_pdf_pages: int = Field(default=20, ge=1, le=50)
    """Maximum PDF pages read by the deterministic text extraction route.

    Independent of ``document_vision_max_pdf_pages`` (specs/021/BL-6, pending
    item resolved): ``extract_pdf_text_markdown`` never calls an LLM, so it
    can afford a more generous page budget than the vision fallback — same
    reasoning as the generous ``document_office_max_blocks`` cap for other
    deterministic extractors.
    """
    document_office_max_zip_entries: int = Field(default=200, ge=1, le=2000)
    """Max ZIP entries read from a DOCX/XLSX/PPTX before refusing it as suspicious."""
    document_office_max_uncompressed_bytes: int = Field(
        default=50_000_000, ge=1_000_000, le=200_000_000
    )
    """Max total uncompressed size across all Office-doc ZIP entries (zip-bomb guard)."""
    document_office_max_blocks: int = Field(default=3000, ge=1, le=20000)
    """Max paragraphs/table-rows/sheet-rows/slide-shapes rendered before truncating."""
    document_office_max_sheets: int = Field(default=20, ge=1, le=200)
    """Maximum XLSX worksheets read before truncating output."""
    document_office_max_slides: int = Field(default=100, ge=1, le=1000)
    """Maximum PPTX slides read before truncating output."""
    document_office_max_cols_per_sheet: int = Field(default=50, ge=1, le=500)
    """Maximum columns read per XLSX worksheet row."""
    document_export_max_markdown_chars: int = Field(default=20_000, ge=1, le=200_000)
    """Max Markdown input length accepted by export_document (BL-38 Fase 3)."""
    document_export_max_pages: int = Field(default=20, ge=1, le=100)
    """Max PDF pages rendered by export_document before truncating output."""
    document_export_max_pdf_bytes: int = Field(default=5_000_000, ge=1_000, le=50_000_000)
    """Max rendered PDF size accepted for delivery by export_document."""

    user_timezone: str = "Europe/Madrid"
    """IANA timezone used to interpret/display naive datetimes app-wide
    (specs/023 T5.1 — single fixed value for now). Read only via
    ``src.domain.preferences.timezone.resolve_user_timezone``; no other
    module may read this field directly."""

    # ── Reminder worker (BL-5 / ADR-003) ─────────────
    reminder_worker_enabled: bool = True
    """Start the reminder background worker. Auto-gated: also requires
    ANCORA_DATABASE_URL and TELEGRAM_TOKEN."""
    reminder_poll_interval_seconds: int = 60
    """Seconds between reminder worker scan cycles."""

    # ── Calendar provider (BL-7) ──────────────────────
    calendar_provider: str = "noop"
    """``noop`` (default, PostgreSQL-only) or ``caldav`` (BL-7: a single
    shared CalDAV calendar collection, not per-user accounts)."""
    calendar_caldav_base_url: str = ""
    calendar_caldav_username: str = ""
    calendar_caldav_password: str = ""

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
    health_gateway_probe_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    """Short private LiteLLM readiness timeout; monitoring remains fail-open."""

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

    @model_validator(mode="after")
    def validate_pilot_notice_url(self) -> "Settings":
        """The link is sent verbatim to users: only a plain https URL is accepted."""
        url = self.pilot_notice_url.strip()
        if url and (not url.startswith("https://") or any(ch.isspace() for ch in url)):
            raise ValueError("PILOT_NOTICE_URL must be an https:// URL without whitespace")
        return self

    @model_validator(mode="after")
    def validate_web_search_settings(self) -> "Settings":
        """Never enable an external search capability without its secret."""
        if self.web_search_enabled and not self.tavily_api_key.strip():
            raise ValueError("WEB_SEARCH_ENABLED requires TAVILY_API_KEY")
        return self

    @model_validator(mode="after")
    def validate_calendar_provider_settings(self) -> "Settings":
        """Fail closed: a CalDAV provider may not silently fall back to noop."""
        if self.calendar_provider not in ("noop", "caldav"):
            raise ValueError("CALENDAR_PROVIDER must be 'noop' or 'caldav'")
        if self.calendar_provider != "caldav":
            return self
        missing = [
            name
            for name, value in (
                ("CALENDAR_CALDAV_BASE_URL", self.calendar_caldav_base_url),
                ("CALENDAR_CALDAV_USERNAME", self.calendar_caldav_username),
                ("CALENDAR_CALDAV_PASSWORD", self.calendar_caldav_password),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError("CALENDAR_PROVIDER=caldav requires: " + ", ".join(missing))
        return self

    @model_validator(mode="after")
    def validate_agent_os_security_key(self) -> "Settings":
        """Fail closed: never run AgentOS's REST surface unauthenticated outside dev.

        Agno's AgentOS mounts REST routes (/agents/*/runs, /sessions,
        /memories, /config, /eval-runs, ...) that AncoraMind does not use —
        the Agent only runs through the Telegram webhook. Those routes
        accept a client-supplied user_id, bypassing admission/governance
        entirely if left open (specs/023 T1).
        """
        if self.app_env.lower() == "development":
            return self
        if not self.agent_os_security_key.strip():
            raise ValueError(
                "AGENT_OS_SECURITY_KEY is required when APP_ENV != 'development' "
                "(AgentOS REST routes would otherwise be reachable without auth)"
            )
        return self

