# Verification: 023 — Audit Remediation

> **Status:** 🔶 en curso — Fases 1–3 implementadas localmente (2026-10-02);
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

- [x] Implementada y verificada localmente (2026-10-02):
      - `@closes_sessions` + `track_session()` (`src/agent/tools/sessions.py`)
        cierran todas las sesiones abiertas durante cada tool, también si
        falla. 32 tools cubiertas; el schema de Agno no cambia (verificado
        con `Function.from_callable`).
      - `src/agent/tools/validation.py`: validación de UUID sin repetir el
        valor rechazado y mensajes de error fijos (`INTERNAL_ERROR`,
        `INVALID_PROPOSAL_DATA`); en el log solo queda la clase de la
        excepción.
      - 15 tests nuevos en `tests/unit/test_tool_sessions_and_errors.py`.
        Un primer intento comprobaba `caplog.text` y fallaba en la suite
        completa porque otro test instala `MetadataOnlyJsonFormatter`
        (que descarta el texto del mensaje a propósito); se corrigió
        comprobando los `LogRecord` directamente.
      - Resultados: `ruff` y `mypy src/` limpios; unit 585 passed;
        integration 71 passed.

## Fase 4 — Consentimiento gobernado

- [x] T4.1–T4.2 implementadas y verificadas localmente (2026-10-02):
      - Migración `0006_proposal_consent` + `init.sql` equivalente.
        Probado con PostgreSQL real: instalación desde cero, adopción de
        `init.sql`, downgrade a la revisión anterior y vuelta a head, y
        downgrade con filas en estados nuevos (se reconvierten a estados
        que el modelo anterior entiende).
      - Repositorio de consentimiento sin commits propios. Concurrencia
        probada con dos sesiones independientes: un solo ganador, y el
        perdedor recibe `NOT_PENDING`.
      - Un bug encontrado al probar con PostgreSQL real que los mocks no
        habrían detectado: asyncpg rechazaba `complete_execution` porque el
        mismo parámetro se usaba como `VARCHAR` y como `text`. Se corrigió
        con un parámetro booleano aparte.
      - Resultados: `ruff` y `mypy src/` limpios; unit 590 passed;
        integration 89 passed.
- [x] T4.3–T4.4 implementadas y verificadas localmente (2026-10-02), detrás
      de `GOVERNED_CONSENT_ENABLED` (apagado por defecto):
      - Flujo real probado de extremo a extremo con PostgreSQL: una tool
        simulada crea una propuesta durante el run → el Core añade el
        bloque fijo + botones Sí/No al entregar → tras confirmar la
        entrega se marca `presented_at` → un segundo update de tipo
        `callback_query` con el botón "Sí" confirma la propuesta
        (`status='confirmed'`), sin segunda ejecución del Agent.
      - 10 casos unitarios de rechazo/ambigüedad con repositorio mockeado:
        sin pendientes, varias pendientes, `Sí <UUID>`, 4 motivos de
        rechazo con mensaje distinto cada uno, confirmar/descartar por
        botón, texto/callback que no es consentimiento.
      - **Desviaciones del diseño original**, documentadas en
        `tasks.md`: la procedencia viaja por `ContextVar` en vez de
        `RunContext.metadata`; `mark_presented` no comparte transacción
        con la confirmación de entrega (dos commits, falla cerrado si el
        segundo no llega); `answerCallbackQuery` no está implementado
        todavía (el botón no pierde su reloj de carga en el cliente).
      - Resultados: `ruff` y `mypy src/` limpios; unit 605 passed;
        integration 91 passed.
- [x] T4.5 implementada y verificada localmente (2026-10-02):
      - `confirm_or_use_confirmed()` (camino "con reserva", decisión del
        propietario sobre el diseño original "sin reserva" de `tasks.md`):
        comportamiento sin cambios con el flag apagado; con el flag
        encendido, una propuesta ya confirmada por T4.3 se ejecuta sin que
        el LLM la autorice. Aplicado a las 6 tools `execute_*`.
      - 2 tests de integración nuevos (camino legacy; reutilización del
        claim pre-Agent) + 7 mocks de tools actualizados al nuevo método.
      - Resultados: `ruff` y `mypy src/` limpios; unit 605 passed;
        integration 93 passed.
- [x] T4.6 implementada y verificada localmente (2026-10-02):
      - `remember_note` → `propose_note`/`execute_note`, mismo patrón
        ActionProposal que el resto de WRITE. `main.py` registra 2 tools
        en vez de 1 (32→33 tools totales); `README.md`/`docs/
        architecture.md` actualizados.
      - 6 tests unitarios nuevos + 1 ajustado (schema de Agno).
      - Resultados: `ruff` y `mypy src/` limpios; unit 609 passed;
        integration 93 passed.
- [ ] T4.7–T4.9 pendientes. Ver también
      `specs/022-llm-input-trust/verification.md`.

## Fase 5 — Zona horaria

- [ ] Pendiente.

## Fase 6 — Sincronización documental

- [ ] Pendiente.
