"""Guard the AgentOS REST surface AncoraMind does not use (specs/023 T1).

Agno's AgentOS mounts REST routes (/agents/*/runs, /sessions, /memories,
/config, /eval-runs, /components, /schedules, /approvals, /service-accounts,
/registry, ...) that this product never calls — the Agent only runs through
AncoraMind's own Telegram admission/processor. Those routes accept a
client-supplied ``user_id`` and bypass admission, budget and governance
entirely if left reachable without a credential.

Agno's native ``OS_SECURITY_KEY`` cannot be reused for this: its middleware
protects every route on the combined ``base_app`` except a fixed exclusion
list that does not include AncoraMind's own endpoints
(``/telegram/webhook``, ``/admin/*``, ``/health/readiness``), which already
carry their own authentication. This middleware is scoped the other way
around: it only gates paths that belong to Agno's REST surface and leaves
every AncoraMind-owned path untouched.
"""

from __future__ import annotations

import hmac

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Prefixes AncoraMind owns and must never be gated by this middleware. Any
# path not starting with one of these is assumed to belong to Agno's REST
# surface and requires the bearer token.
_UNGATED_PREFIXES = (
    "/",  # AgentOS home route (GET / only — exact match, see below)
    "/health",
    "/telegram",
    "/admin",
)


def _is_ancoramind_owned(path: str) -> bool:
    """Return True for paths this product serves itself (never gated here)."""
    if path == "/":
        return True
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in _UNGATED_PREFIXES
        if prefix != "/"
    )


def install_agent_os_rest_guard(app: FastAPI, security_key: str) -> None:
    """Require a bearer token on every Agno REST route, scoped by path.

    AncoraMind-owned routes (Telegram webhook, admin APIs, health) keep
    their existing authentication unchanged and are never touched here.
    """

    @app.middleware("http")
    async def _agent_os_rest_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        if _is_ancoramind_owned(request.url.path):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip() if header else ""
        if not token or not hmac.compare_digest(token, security_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )
        return await call_next(request)
