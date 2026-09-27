"""In-process, metadata-only health signals for the AncoraMind runtime.

The registry is deliberately volatile and informative: it never gates requests,
does not contain user data, and does not replace the durable PostgreSQL audit.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.observability import get_telemetry

logger = logging.getLogger(__name__)

HealthStatus = Literal["healthy", "degraded", "disabled", "unknown"]
SessionFactory = Callable[[], Awaitable[AsyncSession]]

_HEALTH_STATUSES = frozenset({"healthy", "degraded", "disabled", "unknown"})
_CIRCUIT_STATES = frozenset({"closed", "open", "half_open", "unknown"})
_HEALTH_COMPONENTS = frozenset(
    {
        "database",
        "app",
        "gateway",
        "gateway_circuit",
        "interaction_processor",
        "reminder_worker",
        "runtime_config",
    }
)


class HealthRegistry:
    """Keep bounded local health signals and export them through safe telemetry."""

    def __init__(self) -> None:
        self._components: dict[str, dict[str, object]] = {}
        self._queue_pending_global = 0
        self._queue_max_per_chat = 0
        self._config_revision = 0
        self._reminders_overdue = 0
        self._last_interaction_processed_at: datetime | None = None

    def set_component(self, component: str, status: HealthStatus) -> None:
        """Record a bounded component state without personal or exception content."""
        if component not in _HEALTH_COMPONENTS:
            raise ValueError(f"Unsupported health component: {component}")
        if status not in _HEALTH_STATUSES:
            raise ValueError(f"Unsupported health status: {status}")
        observed_at = datetime.now(tz=UTC)
        self._components[component] = {"status": status, "observed_at": observed_at}
        get_telemetry().gauge(
            "ancora.health.component",
            1 if status == "healthy" else 0,
            attributes={"ancora.health.component": component},
        )

    def heartbeat(self, component: str) -> None:
        """Publish one successful worker/processor cycle."""
        self.set_component(component, "healthy")
        get_telemetry().counter(
            "ancora.health.heartbeat",
            attributes={"ancora.health.component": component},
        )

    def record_reminders_delivered(self, count: int) -> None:
        """Count confirmed reminder deliveries and refresh the worker heartbeat."""
        self.heartbeat("reminder_worker")
        if count:
            get_telemetry().counter("ancora.reminders.delivered", count)

    def set_reminders_overdue(self, count: int) -> None:
        """Expose the current aggregate of pending reminders already past due."""
        self._reminders_overdue = max(0, count)
        get_telemetry().gauge("ancora.reminders.overdue", self._reminders_overdue)

    def set_circuit_state(self, state: str) -> None:
        """Publish a bounded gateway-circuit state without fabricating availability."""
        if state not in _CIRCUIT_STATES:
            raise ValueError(f"Unsupported circuit state: {state}")
        self.set_component("gateway_circuit", "degraded" if state == "open" else "unknown")
        get_telemetry().gauge(
            "ancora.gateway.circuit.state",
            1 if state == "open" else 0,
            attributes={"ancora.circuit.state": state},
        )

    def set_queue_depth(self, *, pending_global: int, max_per_chat: int) -> None:
        """Store bounded aggregate queue depths; never publish chat identifiers."""
        self._queue_pending_global = max(0, pending_global)
        self._queue_max_per_chat = max(0, max_per_chat)
        telemetry = get_telemetry()
        telemetry.gauge(
            "ancora.admission.queue.depth",
            self._queue_pending_global,
            attributes={"ancora.queue.scope": "global"},
        )
        telemetry.gauge(
            "ancora.admission.queue.depth",
            self._queue_max_per_chat,
            attributes={"ancora.queue.scope": "max_per_chat"},
        )

    def set_runtime_config_revision(self, revision: int, *, database_available: bool) -> None:
        """Expose only the numeric revision and control-plane availability."""
        self._config_revision = max(0, revision)
        get_telemetry().gauge("ancora.runtime_config.revision", self._config_revision)
        self.set_component("runtime_config", "healthy" if database_available else "degraded")

    def record_interaction_processed(self) -> None:
        """Record a successfully finalized interaction without retaining its identity."""
        self._last_interaction_processed_at = datetime.now(tz=UTC)
        self.refresh_interaction_freshness()

    def refresh_interaction_freshness(self) -> None:
        """Export the aggregate age of the latest successful interaction, when known."""
        if self._last_interaction_processed_at is None:
            return
        get_telemetry().gauge(
            "ancora.interactions.last_processed.age_seconds",
            self._interaction_processed_age_seconds(),
        )

    async def refresh_gateway(self, base_url: str, *, timeout_seconds: float) -> None:
        """Probe private LiteLLM readiness without credentials, bodies, or app gating."""
        readiness_url = _gateway_readiness_url(base_url)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
                response = await client.get(readiness_url)
            self.set_component("gateway", "healthy" if response.status_code == 200 else "degraded")
        except Exception:
            # Do not retain or export a URL, request error, response body, or credentials.
            self.set_component("gateway", "degraded")

    async def refresh_database_and_queue(self, session_factory: SessionFactory) -> None:
        """Best-effort bounded DB and aggregate queue probe for the monitor task."""
        session: AsyncSession | None = None
        try:
            session = await session_factory()
            await session.execute(text("SELECT 1"))
            counts = (
                await session.execute(
                    text("""
                        WITH accepted AS (
                            SELECT chat_id
                            FROM ancora.telegram_interactions
                            WHERE status = 'accepted'
                        ), per_chat AS (
                            SELECT chat_id, count(*) AS pending
                            FROM accepted
                            GROUP BY chat_id
                        )
                        SELECT
                            (SELECT count(*) FROM accepted) AS pending_global,
                            COALESCE((SELECT max(pending) FROM per_chat), 0) AS max_per_chat,
                            (
                                SELECT count(*)
                                FROM ancora.reminders
                                WHERE status = 'pending' AND trigger_at < now()
                            ) AS reminders_overdue
                    """)
                )
            ).one()
            self.set_component("database", "healthy")
            self.set_queue_depth(
                pending_global=int(counts.pending_global or 0),
                max_per_chat=int(counts.max_per_chat or 0),
            )
            self.set_reminders_overdue(int(counts.reminders_overdue or 0))
        except Exception:
            # The class/content of the underlying database error is intentionally
            # not exposed by readiness or telemetry.
            self.set_component("database", "degraded")
        finally:
            if session is not None:
                with contextlib.suppress(Exception):
                    await session.close()

    def snapshot(self) -> dict[str, object]:
        """Return metadata-only state. This method never performs I/O."""
        components = {
            name: {
                "status": state["status"],
                "observed_at": _iso(state["observed_at"]),
            }
            for name, state in sorted(self._components.items())
        }
        return {
            "status": "ok",
            "observed_at": datetime.now(tz=UTC).isoformat(),
            "components": components,
            "admission_queue": {
                "pending_global": self._queue_pending_global,
                "max_pending_per_chat": self._queue_max_per_chat,
            },
            "runtime_config": {"active_revision": self._config_revision},
            "reminders": {"overdue": self._reminders_overdue},
            "interactions": {
                "last_processed_at": _iso(self._last_interaction_processed_at),
                "last_processed_age_seconds": (
                    self._interaction_processed_age_seconds()
                    if self._last_interaction_processed_at is not None
                    else None
                ),
            },
        }

    def _interaction_processed_age_seconds(self) -> float:
        """Return a non-negative local freshness value without performing I/O."""
        if self._last_interaction_processed_at is None:
            return 0.0
        elapsed = datetime.now(tz=UTC) - self._last_interaction_processed_at
        return max(0.0, elapsed.total_seconds())


def install_health_readiness_endpoint(app: FastAPI, registry: HealthRegistry) -> None:
    """Install informational readiness without changing AgentOS's ``/health`` route."""
    app.state.health_registry = registry

    @app.get("/health/readiness")
    async def health_readiness() -> dict[str, object]:
        return registry.snapshot()


def install_health_monitor_lifespan(
    app: FastAPI,
    settings: Settings,
    *,
    session_factory: SessionFactory,
    registry: HealthRegistry,
) -> None:
    """Periodically refresh local signals; monitoring failures never stop the app."""
    previous_lifespan = app.router.lifespan_context

    async def monitor() -> None:
        while True:
            try:
                if settings.ancora_database_url:
                    await registry.refresh_database_and_queue(session_factory)
                else:
                    registry.set_component("database", "disabled")
                _refresh_task_component(
                    registry,
                    "reminder_worker",
                    getattr(app.state, "reminder_worker_task", None),
                )
                _refresh_task_component(
                    registry,
                    "interaction_processor",
                    getattr(app.state, "telegram_interaction_processor_task", None),
                )
                registry.refresh_interaction_freshness()
                if settings.litellm_proxy_enabled:
                    await registry.refresh_gateway(
                        settings.litellm_proxy_base_url,
                        timeout_seconds=settings.health_gateway_probe_timeout_seconds,
                    )
                else:
                    registry.set_component("gateway", "disabled")
                registry.set_circuit_state("unknown")
                manager = getattr(app.state, "runtime_config_manager", None)
                if manager is not None:
                    registry.set_runtime_config_revision(
                        manager.snapshot().revision,
                        database_available=manager.database_available,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Health monitor cycle failed; continuing", exc_info=False)
            await asyncio.sleep(settings.health_probe_interval_seconds)

    @asynccontextmanager
    async def health_monitor_lifespan(application: FastAPI) -> AsyncIterator[Any]:
        async with previous_lifespan(application) as state:
            task = asyncio.create_task(monitor(), name="ancoramind-health-monitor")
            application.state.health_monitor_task = task
            try:
                yield state
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                del application.state.health_monitor_task

    app.router.lifespan_context = health_monitor_lifespan


def _refresh_task_component(
    registry: HealthRegistry,
    component: str,
    task: asyncio.Task[Any] | None,
) -> None:
    if task is None:
        registry.set_component(component, "disabled")
    elif task.done():
        registry.set_component(component, "degraded")
    elif component not in registry._components:  # noqa: SLF001 - same module state check
        # An active task has not completed its first cycle yet; it is not a
        # heartbeat and must not be presented as one.
        registry.set_component(component, "unknown")


def _iso(value: object) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


def _gateway_readiness_url(base_url: str) -> str:
    """Convert the private OpenAI-compatible base URL into LiteLLM readiness."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/health/readiness"
