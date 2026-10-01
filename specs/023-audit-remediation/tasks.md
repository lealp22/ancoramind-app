# Tasks — Spec 023: Remediación de auditoría

> Orden de ejecución: Fase 1 → 2 → 3 → 4 → 5 → 6. Fases 1-3 y 5-6 no tienen
> dependencias entre sí y podrían paralelizarse si hay más de un agente
> trabajando; se listan en el orden de riesgo acordado con el propietario.

---

## Fase 1 — Cerrar la superficie REST de AgentOS (🔴 crítico)

**Objetivo:** que ningún endpoint no gobernado (`/agents/*/runs`, `/sessions`,
`/memories`, `/config`, `/docs`, `/openapi.json`) sea alcanzable sin
autenticación, y verificarlo contra el entorno real antes de cerrar.

- [ ] T1.1 · **Verificación en caliente (no destructiva).** Contra el dominio
      Railway actual: `curl -i https://<dominio>/config`,
      `curl -i https://<dominio>/openapi.json`. Si devuelven `200`, documentar
      el hallazgo con timestamp en `verification.md` antes de tocar código
      (evidencia de explotabilidad real, no solo local).
- [x] T1.2 · **Decisión aprobada (2026-10-02):** intentar (a) y caer a (b)
      automáticamente si (a) no es técnicamente viable; documentar en
      `verification.md` cuál de las dos se aplicó y por qué.
      - **(a) Preferida — quitar las rutas.** No usamos la API REST de Agno
        (solo hablamos con el bot por Telegram vía nuestro webhook, ya
        protegido). Investigar si `AgentOS(...)` permite omitir
        `/agents/*/runs`, `/sessions`, `/memories`, `/config`, `/eval-runs`,
        `/docs`/`/openapi.json` (parámetros del constructor — p.ej. no pasar
        ciertos routers, o un flag de superficie reducida en
        `agno.os.app.AgentOS`). Si existe esa opción, usarla: menos
        superficie, sin secreto nuevo que gestionar/rotar.
      - **(b) Fallback — poner candado.** Si (a) no es viable sin romper algo
        que sí necesitamos (p.ej. `/health`), configurar `OS_SECURITY_KEY`
        (mecanismo nativo de Agno) con un secreto Railway-only de alta
        entropía, verificando que activa `_add_auth_middleware` sobre
        *todas* las rutas del `base_app` combinado (incluida
        `/telegram/webhook` legado si sigue montado). Rotación del secreto
        documentada igual que el resto de secretos Railway-only del repo.
      - En ambos casos: `app_debug=False` ⇒ sin `/docs`/`/openapi.json` en
        producción (Starlette/FastAPI `docs_url=None` si `AgentOS` lo
        permite pasar).
- [ ] T1.3 · Implementar la opción elegida en `src/main.py` /
      `src/agent/ancora_agent.py` (lo que corresponda). Si es (b), añadir
      `Settings.agent_os_security_key: str = ""` con validación fail-closed
      análoga a `validate_litellm_proxy_settings` (si `APP_ENV=production` y
      la clave está vacía, no arrancar — ver fase 2 para la lógica de
      `APP_ENV`).
- [ ] T1.4 · Test unitario: construir la app con `TELEGRAM_TOKEN` dummy y
      `APP_ENV=production`, listar `app.openapi()["paths"]` o inspeccionar
      middlewares, y afirmar que una petición sin credencial a `/config` o
      `/memories` devuelve `401`/`403` (usar `TestClient` de FastAPI/Starlette,
      ya transitivo vía `fastapi`). Este test debe fallar hoy (red test) y
      pasar tras T1.3.
- [ ] T1.5 · Re-ejecutar T1.1 contra Railway tras el despliegue para confirmar
      el cierre real, no solo local. Registrar en `verification.md`.
- [ ] T1.6 · `ruff check`, `mypy src/`, `pytest tests/unit/` en verde.

**Criterio de cierre:** `/config`, `/memories`, `/agents/*/runs`, `/sessions`,
`/docs`, `/openapi.json` devuelven 401/403/404 sin credencial válida, tanto
en local (test automatizado) como en Railway (verificación manual
documentada).

---

## Fase 2 — `UserContext` fail-closed + `APP_ENV` seguro por defecto (🟠 alto)

- [ ] T2.1 · `UserContext.from_run_context`: eliminar el fallback a
      `session_id` completo o `"unknown"`. Si no hay `run_context.user_id` y
      el `session_id` no tiene el formato `tg:{entity}:{chat_id}`, lanzar
      `ValueError("UserContext: no trusted identity in RunContext")` en vez
      de degradar silenciosamente. Las tools que llaman a esta función ya
      están en un `try/except` amplio en algunos sitios — revisar que la
      excepción se propague como error de tool, no como respuesta "unknown"
      persistida en BD.
- [ ] T2.2 · Unit tests: `run_context` sin `user_id` y con `session_id`
      vacío/malformado → `ValueError`; formato correcto → user_id esperado
      (casos ya cubiertos deben seguir pasando).
- [ ] T2.3 · `Settings.app_env`: cambiar el default de `"development"` a
      `"production"` en `src/config.py`. Actualizar `.env.example`,
      `docker-compose.yml` (mantener `APP_ENV=development` explícito ahí,
      ya que es un entorno local real) y `docs/development.md` para que el
      desarrollador local tenga que declarar `APP_ENV=development`
      explícitamente en su `.env`.
- [ ] T2.4 · Añadir un `model_validator` en `Settings` (igual patrón que
      `validate_litellm_proxy_settings`): si `app_env != "development"` y
      `telegram_webhook_secret_token` está vacío pero el admission legado de
      Agno pudiera recibir tráfico (es decir, siempre que
      `TELEGRAM_TOKEN` esté seteado), registrar un `logger.warning` fuerte;
      documentar que Agno exige el secret en modo no-development (ya lo hace
      `agno.os.interfaces.telegram.security.get_webhook_secret_token`), así
      que basta con el cambio de default — pero añadir un test que lo
      confirme explícitamente para esta base de código.
- [ ] T2.5 · Test de regresión: con `APP_ENV` no seteado (ausente del
      entorno), `Settings().app_env == "production"`.
- [ ] T2.6 · `ruff check`, `mypy src/`, `pytest tests/unit/` en verde.

**Criterio de cierre:** sin `APP_ENV` explícito, la app arranca en modo
"producción" (secret de webhook exigido); `UserContext` nunca degrada a un
usuario `"unknown"`.

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


