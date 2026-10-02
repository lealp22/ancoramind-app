# Tasks — Spec 023: Remediación de auditoría

> Orden de ejecución: Fase 1 → 2 → 3 → 4 → 5 → 6. Fases 1-3 y 5-6 no tienen
> dependencias entre sí y podrían paralelizarse si hay más de un agente
> trabajando; se listan en el orden de riesgo acordado con el propietario.

---

## Fase 1 — Cerrar la superficie REST de AgentOS (🔴 crítico)

**Objetivo:** que ningún endpoint no gobernado (`/agents/*/runs`, `/sessions`,
`/memories`, `/config`, `/docs`, `/openapi.json`) sea alcanzable sin
autenticación, y verificarlo contra el entorno real antes de cerrar.

- [ ] T1.1 · **Verificación en caliente (no destructiva) — BLOQUEADA
      (2026-10-02): el servicio Railway está pausado.** Intento registrado:
      `curl -i https://ancoramind-app-production.up.railway.app/health` →
      `404` con `x-railway-fallback: true` y
      `{"status":"error","code":404,"message":"Application not found"}` —
      es el 404 propio del edge de Railway cuando no hay servicio activo
      detrás del dominio, no una respuesta de la app. No se puede distinguir
      "ruta cerrada" de "servicio apagado" en este estado. **Retomar esta
      tarea cuando el servicio esté reanudado**, repitiendo contra
      `/config`, `/openapi.json`, `/docs`, `/sessions`, `/memories`,
      `/eval-runs` y registrando el resultado en `verification.md` antes de
      tocar código si alguna devuelve `200`.
- [x] T1.2 · **Decisión aprobada (2026-10-02):** intentar (a) y caer a (b)
      automáticamente si (a) no es técnicamente viable; documentar en
      `verification.md` cuál de las dos se aplicó y por qué.

      **Resultado de la investigación (2026-10-02):** opción (a) **no es
      viable**. `AgentOS.get_app()`/`_add_built_in_routes()` añaden
      incondicionalmente los routers de agentes, sesiones, memoria,
      aprendizajes, métricas, trazas, eval-runs, etc. (no hay parámetro
      para omitirlos selectivamente sin forkear Agno). **Se aplica (b):**
      - `AgentOS(..., settings=AgnoAPISettings(os_security_key=...))`
        activa `_add_auth_middleware`, que exige `Authorization: Bearer
        <key>` en todas las rutas **excepto** `/`, `/health`, `/info`,
        `/docs`, `/redoc` (excluidas por defecto — bien, porque Railway
        healthcheck necesita `/health` público).
      - `AgnoAPISettings(docs_enabled=False)` desactiva por completo
        `/docs`, `/redoc` y `/openapi.json` (devuelven 404 en vez de 200),
        cerrando el único hueco que la exclusión de auth deja abierto.
      - Combinando ambas, la única ruta pública queda `/`, `/health` e
        `/info` (metadata mínima, sin datos de usuario) — aceptable.

- [x] T1.3 · **Implementado (2026-10-02).** `OS_SECURITY_KEY` nativo de Agno
      no es reusable sin más: protege *todas* las rutas del `base_app`
      combinado excepto una lista fija (`/`, `/health`, `/info`, `/docs`,
      `/redoc` + prefijos de interfaces Agno "self-authenticating"), que no
      incluye nuestras rutas propias (`/admin/runtime-config`,
      `/admin/telegram-pairing`, `/health/readiness`) — las habría roto.
      Se implementó en su lugar `src/agent/agent_os_rest_guard.py`: un
      middleware propio y acotado por prefijo que exige
      `Authorization: Bearer <AGENT_OS_SECURITY_KEY>` únicamente en rutas
      que **no** empiecen por `/`, `/health`, `/telegram`, `/admin` (deja
      intacto el esquema de auth de cada endpoint propio). `src/config.py`
      añade `agent_os_security_key: str = ""` con validación fail-closed
      (`validate_agent_os_security_key`, análoga a
      `validate_litellm_proxy_settings`): si `APP_ENV != "development"` y la
      clave está vacía, `Settings()` lanza `ValueError` al construirse — la
      app no arranca. `src/main.py` pasa además
      `AgentOS(..., settings=AgnoAPISettings(docs_enabled=app_env==
      "development"))`, cerrando `/docs`/`/redoc`/`/openapi.json` del todo
      fuera de desarrollo, e instala el guard tras `get_app()` solo si
      `agent_os_security_key` está configurada.
- [x] T1.4 · **Implementado.** `tests/unit/test_agent_os_rest_guard.py` (4
      tests: ruta Agno sin credencial → 401; con credencial incorrecta →
      401; con credencial correcta → 200; rutas propias — `/health`,
      `/telegram/webhook`, `/admin/runtime-config`, `/` — nunca gateadas) +
      `tests/unit/test_config.py` (3 tests: `APP_ENV=production` sin clave →
      `ValidationError`; `APP_ENV=development` sin clave → OK; clave
      aceptada en producción) + ampliación de
      `tests/unit/test_telegram_admission_wiring.py` (verifica que
      `create_app()` instala el guard con la clave correcta y que
      `AgnoAPISettings.docs_enabled` es `False` en producción). Verificado
      también manualmente con `TestClient` contra la app real: `/config`,
      `/sessions`, `/memories`, `/docs`, `/openapi.json` → `401` sin
      credencial y `200` con el bearer correcto; `/health` siempre `200`;
      comportamiento en `APP_ENV=development` sin cambios (retrocompatible).
- [ ] T1.5 · Re-ejecutar T1.1 contra Railway tras el despliegue para confirmar
      el cierre real, no solo local. **Bloqueada igual que T1.1** — el
      servicio está pausado (ver `verification.md`). Registrar en
      `verification.md` en cuanto se reanude.
- [x] T1.6 · `ruff check src/ tests/ scripts/ migrations/` y `mypy src/`
      limpios; `pytest tests/unit/` → 560 passed (552 previas + 8 nuevas).


**Criterio de cierre:** `/config`, `/memories`, `/agents/*/runs`, `/sessions`,
`/docs`, `/openapi.json` devuelven 401/403/404 sin credencial válida, tanto
en local (test automatizado) como en Railway (verificación manual
documentada).

---

## Fase 2 — `UserContext` fail-closed + `APP_ENV` seguro por defecto (🟠 alto)

- [x] T2.1 · **Implementado (2026-10-02).** `UserContext.from_run_context`
      ya no cae a `session_id` completo ni a `"unknown"`: acepta
      `run_context.user_id` (no vacío) o, solo en la ruta legacy, el chat id
      de `tg:{entity}:{chat_id}[:generation]`; en cualquier otro caso lanza
      `ValueError("UserContext: no trusted identity in RunContext")`.
      Comprobado que ninguna tool captura esa excepción para persistir
      datos: se lanza antes de abrir sesión o repositorio, así que se
      propaga como error de tool sin escribir nada. Los dos caminos reales
      (runner gobernado con `user_id=str(telegram_user_id)` y AgentOS
      legacy con `user_id=from.id`) siempre aportan identidad.
- [x] T2.2 · `tests/unit/test_user_context.py`: el antiguo
      `test_from_run_context_fallback` (que esperaba `"unknown"`) pasa a
      fail-closed, con casos parametrizados para `session_id` arbitrario,
      segmentos insuficientes, chat id vacío, esquema no Telegram y
      `user_id` en blanco. Los casos válidos existentes siguen pasando.
- [x] T2.3 · `Settings.app_env` pasa de `"development"` a `"production"`
      por defecto. `.env.example` lo documenta; `docker-compose.yml` ya fija
      `APP_ENV=development` (sin cambios); `docs/development.md` añade
      `APP_ENV` y `AGENT_OS_SECURITY_KEY` a la tabla de variables. Nuevo
      `tests/conftest.py` declara `APP_ENV=development` para las suites
      (el mismo opt-in que hace un desarrollador local), con `setdefault`
      para respetar un valor explícito; los tests de producción lo
      sobrescriben con `monkeypatch`.
- [x] T2.4 · **Mejora sobre lo planificado:** en vez de solo un
      `logger.warning`, `validate_webhook_secret_settings()` (en
      `src/agent/telegram_admission.py`, invocada en `create_app()`) hace
      fallar el arranque si `APP_ENV != "development"` y falta
      `TELEGRAM_WEBHOOK_SECRET_TOKEN`. Motivo: Agno ya rechaza esos updates
      en tiempo de petición, así que un warning dejaría el bot caído en
      silencio; fallar al arrancar lo hace visible en el healthcheck de
      Railway. 3 tests en `tests/unit/test_telegram_admission.py`.
- [x] T2.5 · `test_app_env_defaults_to_production` y
      `test_missing_app_env_fails_closed_without_production_secrets` en
      `tests/unit/test_config.py`.
- [x] T2.6 · `ruff check` y `mypy src/` limpios; `pytest tests/unit/` →
      570 passed; `pytest tests/integration/` → 71 passed (PostgreSQL
      Docker local), confirmando que el nuevo `tests/conftest.py` no rompe
      la suite de integración.

**Criterio de cierre:** sin `APP_ENV` explícito, la app arranca en modo
"producción" (secret de webhook exigido); `UserContext` nunca degrada a un
usuario `"unknown"`. ✅ Cumplido localmente.

---

## Fase 3 — Cierre de sesiones DB + validación de UUID en tools (🟠 alto)

> Restaurada el 2026-10-02: una edición previa demasiado grande la perdió
> al escribir la Fase 4; el contenido es el mismo que se había planificado.

**Objetivo:** evitar agotamiento del pool de conexiones bajo carga y errores
no controlados por UUID malformado en tools.

- [ ] T3.1 · Auditar `src/agent/tools/*.py`: cada `_get_*_service()`/
      `_get_actions_repo()` llama `await get_session()` sin cerrar. Usar
      `async with` sobre `AsyncSession` (SQLAlchemy 2.0 lo soporta),
      manteniendo los `commit()` explícitos actuales (sin cambiar la
      semántica transaccional — eso es Fase 4/T6b).
- [ ] T3.2 · Aplicar el patrón en `notes.py`, `documents.py`, `vehicles.py`,
      `maintenance.py`, `reminders.py`, `calendar.py`, `todos.py`. Cuando una
      tool use dos sesiones (servicio + `ActionProposalsRepository`), cerrar
      cada una; no compartir sesión entre repos sin motivo.
- [ ] T3.3 · Unit tests: una sesión falsa registra `close()`; afirmar que se
      cierra tras cada tool, también por el camino de error.
- [ ] T3.4 · Validación de UUID: generalizar `todos.py::_parse_uuid` en un
      helper común (`src/agent/tools/_validation.py`) y usarlo en
      `calendar.py`, `reminders.py`, `maintenance.py`, `vehicles.py` en vez
      de `UUID(source_document_id)` sin capturar; devolver mensaje legible en
      español.
- [ ] T3.5 · Sustituir `except Exception as e: ... str(e)[:200]` por un
      mensaje fijo en español y llevar el detalle solo a `logger.exception`
      (nunca a la respuesta que ve el LLM/usuario). Aplicar en
      `calendar.py`, `reminders.py`, `maintenance.py`, `vehicles.py`,
      `todos.py`.
- [ ] T3.6 · Unit tests por archivo: UUID inválido → mensaje controlado;
      excepción genérica → mensaje fijo y detalle registrado solo en logs.
- [ ] T3.7 · `ruff check`, `mypy src/`, `pytest tests/unit/` en verde;
      `pytest tests/integration/` si cambian firmas de repositorios.

**Criterio de cierre:** ninguna tool deja una sesión DB abierta tras su
retorno; ningún UUID malformado produce un traceback sin capturar; ningún
mensaje de error expone detalle interno.

---

## Fase 4 — Consentimiento gobernado por el Core, no por el LLM (🔴 crítico)

> Depende de que fase 3 esté cerrada (los repos ya cierran sesión
> correctamente antes de tocar límites transaccionales). Sigue el contrato ya
> **diseñado** (no re-diseñado aquí) en
> `specs/022-llm-input-trust/consent-design.md` — esta fase es la
> implementación de su T6b/T7/T8 pendientes, registrada aquí para
> integrarse en el plan de remediación con secuencia explícita.

- [ ] T4.1 · Migración Alembic aditiva: añadir a `action_proposals` (o tabla
      nueva de consentimiento si el diseño de specs/022 lo requiere) los
      campos para: presentación verificada (`presented_at`,
      `presented_via_delivery_id` o similar), expiración (`expires_at`,
      default `created_at + 15 min` fijado en el momento de presentación, no
      de creación), y estado ampliado (`pending_confirmation` →
      `presented` → `confirmed` → `executed` / `expired` / `superseded`).
      Mantener `migrations/init.sql` equivalente a head.
- [ ] T4.2 · `ActionProposalsRepository`: añadir
      `mark_presented(proposal_id, delivery_id, presented_at)`,
      `claim_confirmation(user_id, proposal_id, chat_id, bot_id, now) ->
      ProposalRecord | ConsentClaimError` con **una sola** transacción que
      valida: existe, pertenece al mismo `user_id`/`chat_id`/`bot_id`, está
      `presented` (no solo `pending_confirmation`), no ha expirado, y hace el
      `UPDATE ... WHERE status='presented' RETURNING ...` atómico (ya no es
      el actual `confirm()` sin matices). `mark_executed` debe exigir
      `status='confirmed'` en el `WHERE` (hoy no lo hace — bug a corregir
      aquí).
- [ ] T4.3 · Mover la detección de «Sí» / «Sí <UUID>» desde las tools al
      procesador de interacciones (`domain/interactions/processor.py`),
      reusando `parse_consent_intent` ya existente, **antes** de invocar al
      Agent (mismo patrón que `commands.py` resuelve `/new`, AGENTS.md §4).
      0 propuestas vigentes presentadas → no ejecutar, informar; ≥2 → listar
      IDs y pedir `Sí <UUID>`, sin invocar al Agent.
- [ ] T4.4 · Marcar `presented_at`/`presented_via_delivery_id` cuando la
      outbox confirma la entrega del mensaje que contiene la propuesta
      (hook junto a `telegram_response_deliveries` en
      `src/repositories/interactions.py`). Enlazar outbox↔proposal con FK.
- [ ] T4.5 · Reescribir `execute_vehicle`, `execute_vehicle_maintenance`,
      `execute_reminder`, `execute_calendar_event`, `execute_todo_list`,
      `execute_todo_item`: dejan de llamar `actions_repo.confirm()` bajo
      criterio del LLM; solo ejecutan una propuesta cuyo estado ya es
      `confirmed` por el claim del Core (T4.3). Si el Core aún no gestiona
      la confirmación para una ruta dada, rechazar con mensaje claro.
- [ ] T4.6 · `remember_note`: convertir a `propose_note`/`execute_note` con
      el mismo patrón `ActionProposal` (AGENTS.md §2.4). Actualizar
      `prompts/skills/*.md` y `docs/adding-tools.md` si cambia el ejemplo.
- [x] T4.7 · **Decisión aprobada (2026-10-02):** `analyze_document`/
      `DocumentService.ingest` **se mantienen automáticos** — enviar un
      documento ya es una señal de intención suficiente ("quiero que esto
      se guarde"); pedir confirmación añadiría fricción innecesaria para el
      caso común. Se documenta como **excepción aprobada** a la regla WRITE
      de AGENTS.md §2.4 en el propio AGENTS.md y en `docs/governance.md`
      (tabla de riesgo), con esta justificación de UX.
      En su lugar, se cierra el hueco real: **no existe hoy ninguna tool
      para borrar un documento** aunque `DocumentService.delete_document`
      ya existe en el dominio. Añadir `propose_document_delete` /
      `execute_document_delete` (DESTRUCTIVE, propose/confirm como el resto
      de borrados — p.ej. `propose_todo_list_delete`), registrar en
      `_init_domain_tools()`, actualizar `prompts/skills/documents.md` y
      `README.md` (tabla de capabilities). Esto cubre el caso "no quiero
      esto guardado" sin penalizar el caso común.
- [ ] T4.8 · Unit + integration tests parametrizados por cada `execute_*`
      (incluido `execute_document_delete`) y rama TODO: replay del mismo
      update, confirmaciones concurrentes, propuesta no presentada/expirada,
      `Sí` sin vigentes, `Sí` con 2+, usuario/chat/bot cruzado, `/new`
      invalidando propuestas del chat.
- [ ] T4.9 · `ruff check`, `mypy src/`, `pytest tests/unit/` y
      `tests/integration/` en verde. Actualizar
      `specs/022-llm-input-trust/tasks.md`/`verification.md`.

**Criterio de cierre:** ningún `execute_*` ni `remember_note` ejecuta sin un
claim atómico del Core basado en un «Sí» aislado posterior a una entrega
verificada; `mark_executed` exige `status='confirmed'`; existe
`propose_document_delete`/`execute_document_delete` gobernado; tests de
carrera y replay en verde con PostgreSQL real.

---

## Fase 5 — Zona horaria correcta en recordatorios/calendario (🟠 alto)

- [x] T5.1 · **Decisión aprobada (2026-10-02) — opción B "resolver
      preparado":** una sola zona horaria fija para toda la app por ahora
      (`Settings.user_timezone: str = "Europe/Madrid"`), pero el acceso a
      esa zona se hace siempre a través de una única función
      `resolve_user_timezone(user_context) -> ZoneInfo` en
      `src/domain/*` (ubicación concreta a decidir en T5.2 — candidato:
      `src/security/user_context.py` o un módulo propio
      `src/domain/preferences/timezone.py`). Ningún otro módulo lee
      `Settings.user_timezone` directamente. Hoy esa función ignora
      `user_context` y devuelve siempre la zona fija; el día que exista
      configuración por usuario, solo se cambia esa función (p.ej. para
      leer una tabla `ancora.user_preferences`) sin tocar tools ni
      servicios. **Se descarta** guardar un offset numérico por usuario
      (se rompe con el cambio de hora estacional) y depender de que el
      usuario especifique la zona en cada mensaje (frágil).
- [ ] T5.2 · Implementar `resolve_user_timezone()` como se describe en
      T5.1. `src/domain/reminders/models.py` / `calendar/models.py`:
      normalizar cualquier `datetime` *naive* recibido asumiendo la zona
      resuelta y convirtiendo a UTC antes de persistir (usar
      `zoneinfo.ZoneInfo`, stdlib, sin dependencia nueva). Rechazar con
      mensaje claro si el valor es ambiguo (hora inexistente/duplicada por
      cambio de horario) en vez de fallar silenciosamente.
- [ ] T5.3 · Tools (`reminders.py`, `calendar.py`): al formatear fechas de
      vuelta al usuario (`trigger_at.strftime(...)`), convertir de UTC a la
      zona resuelta por `resolve_user_timezone()` antes de mostrar, para que
      lo que el usuario escribió y lo que ve coincidan.
- [ ] T5.4 · `get_current_datetime`: devolver también la hora local (vía
      `resolve_user_timezone()`) además de UTC, documentándolo en el
      docstring (el LLM usa esta tool para resolver "hoy", "esta semana",
      etc.). Nota: esta tool no recibe `run_context` hoy (ver T6.9) — si se
      necesita `user_context` para resolver la zona, añadirlo aquí mismo en
      vez de duplicar la excepción documentada en T6.9.
- [ ] T5.5 · Unit tests: entrada `17:00` naive con zona resuelta
      `Europe/Madrid` en verano (UTC+2) → persistido como `15:00Z`; worker de
      recordatorios dispara en el instante UTC correcto; respuesta formateada
      muestra `17:00` de nuevo. Caso de cambio de horario (DST) cubierto con
      un dato de prueba fijo en octubre/marzo.

- [ ] T5.6 · `ruff check`, `mypy src/`, `pytest tests/unit/` y
      `tests/integration/` en verde.

**Criterio de cierre:** un recordatorio o evento creado con una hora local
dicha por el usuario se dispara/consulta en esa misma hora local, con
pruebas que cubren al menos un cambio de horario de verano/invierno.

---

## Fase 6 — Sincronización documental (🟡 medio)

- [ ] T6.1 · Actualizar recuento de tests en `AGENTS.md`, `README.md`,
      `BACKLOG.md` al valor real tras cada fase anterior (ejecutar
      `pytest tests/unit/ -q` y `pytest tests/integration/ -q --collect-only`
      para los números exactos en el momento del commit final de esta spec).
- [ ] T6.2 · Actualizar `> **Status:**` en `specs/001`, `specs/009`,
      `specs/010`, `specs/013` y los ADR-004/005 que digan "pendiente"/
      "implementation pending" cuando el código ya está implementado
      (confirmar caso por caso contra el código actual, no asumir).
- [ ] T6.3 · Reescribir `docs/architecture.md` §10 (tabla de capabilities)
      para que coincida con la tabla real de `README.md` (32 tools, nombres
      `propose_*`/`execute_*` correctos, incluir TODO lists).
- [ ] T6.4 · Corregir `specs/011-todo-lists/verification.md` §"items
      directos sin propose/execute" para reflejar que, tras fase 4, todo
      item también pasa por propose/execute (si fase 4 ya se completó) o
      anotar explícitamente la discrepancia pendiente (si no).
- [ ] T6.5 · `docs/governance.md`: quitar la referencia a
      `skills/calendar.md` (no existe) o crear el fichero si la skill de
      calendario merece su propio prompt separado de `tool_contract.md`
      (decidir y documentar la elección). Revisar si `assemble_instructions`
      debería cargar `document_extraction.md` y no lo hace — si es
      intencional, documentarlo; si es un olvido, añadirlo.
- [ ] T6.6 · `prompts/tool_contract.md`: el bloque "Tool Result Patterns"
      (JSON `{"status": ...}`) no corresponde a ninguna tool real (todas
      devuelven texto en español). Sustituir por una descripción fiel al
      formato real de retorno (texto con emojis/negritas, ver AGENTS.md §4)
      o implementar el contrato JSON si se decide que es preferible — elegir
      y documentar, no dejar la discrepancia.
- [ ] T6.7 · Eliminar o justificar código muerto: `src/agent/context.py`
      (`UserContext` legado, no usado — confirmar con
      `search_codebase`/`grep` antes de borrar), `src/services/__init__.py`
      y `src/governance/__init__.py` vacíos (decidir si se quitan o se deja
      nota de "reservado para uso futuro"), `_NOTE_TOOLS` global en
      `src/main.py` (confirmar si algo lo consume; si no, eliminar).
- [ ] T6.8 · `specs/013-llm-access-governance/verification.md`: añadir una
      columna explícita "entorno" (local/Railway) a la matriz A–Y en vez de
      un solo ✅ ambiguo, para que BACKLOG.md y el spec no se contradigan
      sobre qué está realmente validado en producción.
- [ ] T6.9 · Revisar/documentar por qué `get_current_datetime` no recibe
      `run_context` (única tool sin ese parámetro) — si es intencional
      (no necesita identidad), anotarlo en AGENTS.md §4 como excepción
      explícita; si no, evaluar si debería tenerlo por consistencia (sin
      cambiar su comportamiento).
- [ ] T6.10 · `ruff check`, `mypy src/`, `pytest tests/unit/` en verde tras
      cualquier eliminación de código.

**Criterio de cierre:** ningún documento (AGENTS/README/BACKLOG/specs/prompts)
contradice el estado real del código verificado en las fases 1–5.


