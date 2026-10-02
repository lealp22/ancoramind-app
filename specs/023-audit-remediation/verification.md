# Verification: 023 — Audit Remediation

> **Status:** 🔶 en curso — Fases 1 y 2 implementadas localmente (2026-10-02);
> verificación Railway de Fase 1 bloqueada (servicio pausado).

## Fase 1 — Superficie REST de AgentOS

- [ ] T1.1 Evidencia pre-fix (Railway): **bloqueada 2026-10-02 — servicio
      pausado.** `curl -i https://ancoramind-app-production.up.railway.app/health`
      devolvió `404` con `x-railway-fallback: true` y
      `{"status":"error","code":404,"message":"Application not found"}`
      (404 de Railway edge, no de la app — no hay servicio activo detrás del
      dominio). No es posible verificar la superficie REST contra un
      entorno real hasta reanudar el servicio.
- [x] T1.2–T1.4 Implementación local (2026-10-02): investigación confirmó
      que `AgentOS` no permite omitir routers selectivamente (opción a
      descartada); `OS_SECURITY_KEY` nativo también se descartó porque
      rompería `/admin/*` y `/health/readiness` (su exclusión por defecto no
      cubre rutas propias). Se implementó `src/agent/agent_os_rest_guard.py`
      (middleware propio acotado por prefijo) + `Settings.
      agent_os_security_key` fail-closed + `AgnoAPISettings(docs_enabled=
      False)` fuera de development. Verificación manual con `TestClient`
      contra la app real (`APP_ENV=production`, clave de prueba):

      | Ruta | Sin credencial | Con credencial correcta |
      |---|---|---|
      | `/config` | 401 | 200 |
      | `/sessions` | 401 | — |
      | `/memories` | 401 | — |
      | `/docs` | 401 | — |
      | `/openapi.json` | 401 | — |
      | `/health` | 200 (siempre público) | — |

      En `APP_ENV=development` (sin `AGENT_OS_SECURITY_KEY`), las mismas
      rutas devuelven `200` sin cambios — retrocompatible con el
      comportamiento previo a esta spec. `Settings()` con
      `APP_ENV=production` y sin `AGENT_OS_SECURITY_KEY` lanza
      `ValidationError` al construirse (fail-closed confirmado).
      Tests automatizados: `tests/unit/test_agent_os_rest_guard.py` (4),
      `tests/unit/test_config.py` (+3), `tests/unit/
      test_telegram_admission_wiring.py` (+1). `ruff check` y `mypy src/`
      limpios; `pytest tests/unit/` → 560 passed.
- [ ] T1.5 Evidencia post-fix (Railway): pendiente (depende de T1.1 —
      bloqueado por servicio pausado).



## Fase 2 — UserContext / APP_ENV

- [x] Implementada y verificada localmente (2026-10-02):
      - `UserContext.from_run_context` fail-closed: sin identidad de
        confianza → `ValueError` (antes devolvía `"unknown"` o el
        `session_id` tal cual, compartiendo datos canónicos entre runs no
        relacionados). 6 casos nuevos en `tests/unit/test_user_context.py`.
      - `Settings.app_env` por defecto `production`; sin `APP_ENV`, la app
        exige los secretos de producción (`AGENT_OS_SECURITY_KEY`,
        `TELEGRAM_WEBHOOK_SECRET_TOKEN`) o no arranca.
        `validate_webhook_secret_settings()` en `create_app()`.
      - `tests/conftest.py` declara `APP_ENV=development` para las suites.
        Comprobado que el `.env` local sigue resolviendo `development`.
      - Resultados: `ruff` y `mypy src/` limpios; unit 570 passed;
        integration 71 passed (PostgreSQL Docker local).
      - **Atención al desplegar:** Railway ya define `APP_ENV=production`
        y `TELEGRAM_WEBHOOK_SECRET_TOKEN`; antes de reanudar el servicio
        hay que añadir `AGENT_OS_SECURITY_KEY` o el deploy fallará en el
        healthcheck (comportamiento buscado, pero hay que tenerlo en
        cuenta).

## Fase 3 — Sesiones DB / validación UUID

- [ ] Pendiente.

## Fase 4 — Consentimiento gobernado

- [ ] Pendiente. Ver también `specs/022-llm-input-trust/verification.md`.

## Fase 5 — Zona horaria

- [ ] Pendiente.

## Fase 6 — Sincronización documental

- [ ] Pendiente.
