# Tasks — Spec 023: Remediación de auditoría

> Orden de ejecución: Fase 1 → 2 → 3 → 4 → 5 → 6. Fases 1-3 y 5-6 no tienen
> dependencias entre sí y podrían paralelizarse si hay más de un agente
> trabajando; se listan en el orden de riesgo acordado con el propietario.

---

## Incremento de cierre legacy — 2026-10-11

- [x] Diagnóstico remoto acotado solo lectura: health/readiness, auth sin
      credenciales, deployed SHA, runtime-config Supabase y superficies privadas.
- [x] Retirar `execute_*` del registro y ambas factories; cerrar confirmación/
      reutilización/auditoría legacy sin I/O, incluso con flag OFF.
- [x] Regresión de las diez ejecutoras con repositorio real y prueba de claim
      humano → ejecución Core única; concurrencia/rollback existentes preservados.
- [x] Alinear prompts, docs y harness de evals; casos de confirmación legacy
      rechazados antes de inferencia y pendientes de migración a harness Core.
- [x] Gates finales: 1263 unit, 144 integration passed (1 live STT skipped),
      Ruff/mypy limpios y catálogo estático válido.
- [ ] Rollout manual del SHA validado, consentimiento gobernado y E2E Telegram.
- [x] Completar `answerCallbackQuery` localmente: ID cifrado, acuse best-effort
      antes del Core y callbacks inválidos/OFF sin Agent. 1300 unit + 155
      integration passing (live STT omitido). Evidencia: `callback-acknowledgement.md`.
- [ ] Verificar configuración efectiva Gateway; E2E de botones en Telegram real.

Evidencia: `operational-review-2026-10-11.md`; no se marca cerrada toda la spec.
Las tareas anteriores/inferiores conservan su historia fechada.

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

- [x] T3.1 · **Implementado (2026-10-02).** Nuevo
      `src/agent/tools/sessions.py`: `track_session()` registra cada sesión
      abierta por los `_get_*` y `@closes_sessions` las cierra al terminar la
      tool, también si lanza excepción. Se eligió esta opción frente a
      `async with` en cada tool porque los `_get_*` construyen servicios
      reutilizados y los tests existentes los sustituyen. `functools.wraps`
      conserva nombre, docstring y firma: se comprobó con
      `Function.from_callable` que el schema de Agno sigue igual y que
      `run_context` sigue sin aparecer en él. Los `commit()` de los
      repositorios no cambian.
- [x] T3.2 · Aplicado a las 32 tools de `notes`, `documents`, `vehicles`,
      `maintenance`, `reminders`, `calendar` y `todos` (una comprobación con
      AST confirma que no queda ninguna tool pública sin el decorador).
      `LlmUsageRecorder` ya cerraba sus propias sesiones y no se toca. De
      paso, `get_document`, `get_vehicle_summary` y
      `get_vehicle_maintenance_history` validan el UUID **antes** de abrir
      sesión.
- [x] T3.3 · `tests/unit/test_tool_sessions_and_errors.py`: cierre con
      éxito, con excepción y sin fugas entre llamadas; schema de Agno
      intacto; tools reales (`search_notes`, `execute_calendar_event` con
      dos sesiones y fallo del servicio) cierran todas sus sesiones.
- [x] T3.4 · Nuevo `src/agent/tools/validation.py`: `parse_uuid` y
      `parse_optional_uuid` no repiten el valor rechazado (lo ha generado el
      LLM y no tiene límite de tamaño). Aplicados a `source_document_id` en
      `calendar`, `reminders`, `maintenance` y `vehicles`;
      `todos._parse_uuid` delega en el helper común.
- [x] T3.5 · Los `except Exception` de los ejecutores (`calendar`,
      `reminders`, `maintenance`, `vehicles`, `todos` ×2) y los errores de
      payload devuelven mensajes fijos (`INTERNAL_ERROR`,
      `INVALID_PROPOSAL_DATA`) y en el log solo queda la *clase* de la
      excepción. **Excepción deliberada:** el `ValueError` de dominio de
      `execute_vehicle` (matrícula duplicada) mantiene su mensaje, porque lo
      construye el servicio con datos del propio usuario y le sirve para
      entender qué pasó.
- [x] T3.6 · 15 tests nuevos: mensajes fijos sin texto de la excepción,
      registro de log solo con la clase del error, UUID inválido rechazado
      sin tocar la BD (parametrizado en 4 tools) y mensaje compartido con
      `todos`.
- [x] T3.7 · `ruff check` y `mypy src/` limpios; `pytest tests/unit/` → 585
      passed; `pytest tests/integration/` → 71 passed. Las firmas de los
      repositorios no cambian.

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

- [x] T4.1 · **Implementado (2026-10-02)** con el modelo de estados de
      `consent-design.md` (decisión del propietario, más estricto que el
      borrador inicial de esta tarea): `pending_confirmation → confirmed →
      executing → executed | failed_definitive | failed_ambiguous`, más
      `expired`/`discarded` sin ejecución. "Presentada" no es un estado sino
      evidencia (`presented_at` + `presented_response_id`), así que una
      propuesta sigue `pending_confirmation` hasta que se reclama.
      Migración `0006_proposal_consent`: 10 columnas (`payload_hash`,
      `chat_id`, `bot_id`, `presented_at`, `presented_response_id` → FK a
      `logical_responses`, `expires_at`, `confirming_interaction_id` → FK a
      `telegram_interactions`, `executing_at`, `completed_at`,
      `failure_reason`), CHECK con los 8 estados válidos, índice único
      parcial sobre `confirming_interaction_id` (un «Sí» autoriza como mucho
      una propuesta, garantizado por la BD) e índice de pendientes por
      principal. `init.sql` actualizado y equivalente a head. El downgrade
      reconvierte los estados nuevos a los que entiende el modelo anterior.
      Las propuestas existentes sin `payload_hash`/`source_interaction_id`
      se conservan para auditoría pero **no son ejecutables**.
- [x] T4.2 · **Implementado.** `src/domain/actions/models.py` (puro, sin
      Agno ni SQL): `ProposalStatus`, `ConsentRejection` (8 motivos tipados
      y sin contenido), `ConsentPrincipal`, `ClaimedProposal`,
      `payload_hash()` (SHA-256 canónico de herramienta + payload) y TTL de
      15 minutos. `ActionProposalsRepository`:
      - `create()` acepta `source_interaction_id`/`bot_id`/`chat_id` y
        guarda siempre el hash del payload normalizado.
      - `mark_presented()` abre la ventana de consentimiento solo una vez:
        volver a presentar no amplía el plazo.
      - `list_confirmable()` usa el reloj de PostgreSQL.
      - `claim_confirmation()` hace `SELECT … FOR UPDATE`, valida en orden
        (existencia y usuario → legacy → bot/chat → estado → presentada →
        caducada → hash del payload) y pasa a `confirmed` registrando la
        interacción confirmante.
      - `begin_execution()`/`complete_execution()`: los estados terminales
        no vuelven a cambiar.
      - `discard_pending_for_chat()` para `/new`.
      La API nueva **nunca hace commit**: lo hace quien la llama, para que
      claim, mutación y estado final vayan en la misma transacción (T4.5).
      **Bug corregido:** `mark_executed` exige ahora `status='confirmed'` y
      devuelve si hubo transición; antes sobrescribía cualquier estado del
      usuario.
      Tests: 17 de integración en `tests/integration/test_proposal_consent.py`
      (ciclo completo; un solo uso; una interacción no autoriza dos
      propuestas; índice único verificado directamente en la BD; 6 rechazos
      parametrizados; **carrera real entre dos sesiones con un solo
      ganador**; ventana que no se amplía; `/new`; fallo ambiguo terminal;
      CHECK de estados; regresión de `mark_executed`) + 2 de migración
      (columnas en head y downgrade con estados nuevos) + 5 unitarios en
      `tests/unit/test_proposal_consent_model.py`.
      **Pendiente para T4.3–T4.5:** los `execute_*` siguen usando la ruta
      legacy (`confirm`/`mark_executed`). Hasta reescribirlos, las
      propuestas nuevas se crean sin procedencia y, por tanto, no son
      reclamables por la API nueva.
- [x] T4.3 · **Implementado (2026-10-02)**, detrás de `GOVERNED_CONSENT_ENABLED`
      (`Settings.governed_consent_enabled`, apagado por defecto). El
      procesador resuelve en `_handle_consent_input` (antes de comandos y
      Agent): botones `c:<uuid>`/`d:<uuid>` vía `parse_consent_callback`, y
      «Sí»/«Sí <UUID>» vía `parse_consent_intent` ya existente. 0 propuestas
      vigentes → mensaje fijo; ≥2 → lista con IDs; «No» → `discard_proposal`.
      Cada rama usa `ActionProposalsRepository.claim_confirmation`, que
      revalida principal/bot/chat/plazo/hash — el `callback_data` nunca es
      prueba por sí mismo. Reutiliza la misma ruta de admisión/outbox que
      `/new` (`_persist_command_reply` → `_deliver_response`): el modelo
      nunca ve el callback ni el «Sí». **Nota de alcance:** no se ha
      implementado `answerCallbackQuery` (quitar el reloj de carga del
      botón en el cliente de Telegram) — queda para cuando se conecte el
      sender real a `callback_query_id`; no bloquea el resto del flujo.
      La ejecución real queda en `_execute_claimed`, un marcador de posición
      que confirma la propuesta y responde con mensaje fijo: implementarlo
      de verdad es T4.5 (`ProposalExecutor`).
- [x] T4.4 · **Implementado.** `ExecutionContext.provenance`
      (`InteractionProvenance`) viaja por `ContextVar`, no por
      `RunContext.metadata` como se había esbozado — más simple y ya
      existente para otros usos gobernados; `ActionProposalsRepository.
      create()` lo lee con `current_provenance()` sin que ninguna tool
      `propose_*` cambie. `_append_proposal_blocks` añade el bloque de
      `render_proposal_block` (nuevo `src/domain/actions/presentation.py`)
      al contenido antes de cifrar/persistir; `_pending_proposal_buttons`
      adjunta los botones solo al último chunk entregado. Tras confirmar la
      entrega de ese chunk, `_mark_proposals_presented` vuelve a consultar
      por `interaction_id` (no se fía del cálculo anterior) y llama a
      `mark_presented` en una transacción propia — **no la misma
      transacción que `mark_chunk_delivered`**, a diferencia de lo
      planificado; un fallo entre ambas deja el chunk entregado sin abrir
      el plazo, lo que es seguro (falla cerrado) pero no es ejecución
      atómica estricta. Documentado como limitación conocida.
      Tests: 4 integración de extremo a extremo en
      `tests/integration/test_interaction_processor.py` (propone → entrega
      con botones correctos → `presented_at` fijado → callback confirma →
      `status='confirmed'`) + 10 unitarios en
      `tests/unit/test_interaction_processor.py` (texto no es consentimiento,
      0/1/varias pendientes, `Sí <UUID>`, 4 motivos de rechazo con mensaje
      distinto, confirmar/descartar por botón, callback malformado) + 1
      integración de procedencia (T4.2) + 5 unitarios de
      `render_proposal_block`/botones. 605 unit + 91 integration passing;
      `ruff`/`mypy src/` limpios.

- [x] T4.5 · **Implementado (2026-10-02) — con reserva, no "sin reserva" como
      se había esbozado.** Quitar `confirm()` del todo habría roto el bot
      mientras `GOVERNED_CONSENT_ENABLED` esté apagado (nadie movería nunca
      una propuesta a `confirmed`). Decisión del propietario: nuevo
      `ActionProposalsRepository.confirm_or_use_confirmed()` — intenta el
      `confirm()` legacy primero (comportamiento sin cambios con el flag
      apagado); si la fila ya no está `pending_confirmation`, comprueba si
      ya quedó `confirmed` por el claim pre-Agent de T4.3 y, si es así,
      reutiliza esa confirmación sin que el LLM autorice nada. Aplicado a
      las 6 tools (`execute_vehicle`, `execute_vehicle_maintenance`,
      `execute_reminder`, `execute_calendar_event`, `execute_todo_list`,
      `execute_todo_item`), que ya no llaman a `confirm()` directamente.
      Tests: 2 de integración nuevos en `tests/integration/
      test_actions_repo.py` (camino legacy sin cambios; una propuesta
      confirmada por T4.3 se reutiliza sin segunda llamada a `confirm()`);
      7 mocks de tools actualizados (`.confirm.return_value` →
      `.confirm_or_use_confirmed.return_value`). 605 unit + 93 integration
      passing; `ruff`/`mypy src/` limpios.
- [x] T4.6 · **Implementado (2026-10-02).** `remember_note` sustituido por
      `propose_note`/`execute_note` con el mismo patrón `ActionProposal` que
      el resto de WRITE (`tool_name="remember_note"` en el payload, para no
      romper el histórico de propuestas). `propose_note` valida contenido no
      vacío y no escribe; `execute_note` usa `confirm_or_use_confirmed`
      (igual que T4.5) y solo entonces llama a `NotesService.remember`.
      `main.py` registra las 2 tools nuevas en vez de 1 (32→33 tools
      totales); `README.md`/`docs/architecture.md` actualizados. No hacía
      falta tocar `prompts/skills/*.md` ni `docs/adding-tools.md`: ninguno
      menciona `remember_note` por nombre.
      Tests: 6 unitarios nuevos en `tests/unit/test_note_tools.py`
      (propone sin escribir, rechaza contenido vacío sin proponer, ejecuta
      solo tras confirmación, no escribe sin propuesta pendiente) + 1
      ajustado en `test_tool_sessions_and_errors.py` (schema de Agno sobre
      `propose_note`). 609 unit + 93 integration passing; `ruff`/`mypy src/`
      limpios.
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
      **Implementado (2026-10-02):** `propose_document_delete` valida el
      UUID y la propiedad del documento (vía `get_document`) antes de crear
      la propuesta; `execute_document_delete` usa `confirm_or_use_confirmed`
      (igual que T4.5/T4.6) y solo entonces llama a
      `DocumentService.delete_document`. Registradas en `_init_domain_tools()`
      (33→35 tools totales); `prompts/skills/documents.md`, `README.md`,
      `docs/architecture.md` y `docs/governance.md` actualizados.
- [x] T4.8 · **Implementado (2026-10-02).** Unit + integration tests
      parametrizados por cada `execute_*` (incluido `execute_document_delete`)
      y rama TODO: `TestExecuteWithoutAConfirmedProposal` en
      `tests/unit/test_tool_sessions_and_errors.py` (8 casos — reminder,
      calendar, maintenance, vehicle, todo list, todo item, note, document
      delete — todos verifican que `confirm_or_use_confirmed` devolviendo
      `None` deja el servicio sin invocar). Las ramas de carrera real
      (confirmaciones concurrentes, un solo ganador, propuesta no
      presentada/expirada, usuario/chat/bot cruzado) ya estaban cubiertas en
      `tests/integration/test_proposal_consent.py` (T4.1/T4.2, PostgreSQL
      real) y no se duplican aquí.
      **Hueco real encontrado y cerrado:** `/new` nunca invocaba
      `discard_pending_for_chat` — el método existía en el repositorio
      (T4.1) pero `_handle_command` no lo llamaba, así que una propuesta
      pendiente seguía siendo confirmable con «Sí» tras resetear la
      conversación, contradiciendo `consent-design.md` ("`/new` invalida
      pendientes"). Añadido `_discard_pending_proposals_for_chat` en
      `processor.py`, invocado desde `_handle_command` cuando
      `handling.resets_session` y `governed_consent` están activos
      (best-effort: un fallo no bloquea la respuesta de `/new`, la ventana
      de 15 minutos sigue siendo la red de seguridad). Nuevo test de
      integración end-to-end
      `test_new_command_discards_pending_proposals_of_the_chat` en
      `tests/integration/test_interaction_processor.py` (propone, `/new`,
      verifica `status='discarded'` en PostgreSQL real).
      Resultados: 622 unit + 94 integration passing; `ruff`/`mypy src/`
      limpios.
- [x] T4.9 · **Ejecutado y verificado (2026-10-02).** `ruff check`, `mypy src/`,
      `pytest tests/unit/`, `pytest tests/integration/`, `python
      scripts/run_evals.py` y `git diff --check` en verde: 622 unit + 94
      integration passing; `ruff`/`mypy src/` limpios (112 módulos); evals
      27 casos / 6 categorías (corregida la referencia obsoleta a
      `remember_note` en `evals/security/cases.json` → `propose_note`/
      `execute_note`). Actualizados `specs/022-llm-input-trust/tasks.md`
      (T6a/T6b/T7 marcadas `[x]`, con remisión a esta spec como
      implementación), `specs/022-llm-input-trust/verification.md` (nueva
      sección "P0 — implementado") y `specs/022-llm-input-trust/spec.md`
      (cabecera del P0). También corregidas referencias residuales a
      `remember_note` como hallazgo abierto en `docs/llm-security-hardening.md`
      y en `BACKLOG.md` (BL-39/BL-40).

**Criterio de cierre:** ningún `execute_*` ni `remember_note` ejecuta sin un
claim atómico del Core basado en un «Sí» aislado posterior a una entrega
verificada; `mark_executed` exige `status='confirmed'`; existe
`propose_document_delete`/`execute_document_delete` gobernado; tests de
carrera y replay en verde con PostgreSQL real.

**Cumplido en código y tests (2026-10-02).** Con el flag
`GOVERNED_CONSENT_ENABLED` encendido, ningún `execute_*` (ni `remember_note`,
sustituido por `propose_note`/`execute_note`) ejecuta sin el claim atómico;
`mark_executed` exige `status='confirmed'` desde T4.2; `propose_document_delete`
/`execute_document_delete` existen desde T4.7; carrera y replay cubiertos con
PostgreSQL real (T4.1/T4.2/T4.8). **Matiz pendiente de decisión del
propietario:** el flag sigue apagado por defecto en producción —
`confirm_or_use_confirmed` cae al `confirm()` legacy mientras tanto, así que
el criterio de cierre se cumple como capability implementada y probada, no
como comportamiento ya vigente en producción. Activar el flag en producción
no forma parte de esta fase.

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
- [x] T5.2 · **Hecho (2026-10-03).** Ubicación decidida:
      `src/domain/preferences/timezone.py` (módulo propio, no
      `security/user_context.py` — la zona horaria es una preferencia, no
      identidad; mantiene `security/` sin depender de la capa de
      repositorios el día que la zona sea por usuario). Expone:
      - `resolve_user_timezone(user_context) -> ZoneInfo`: hoy ignora
        `user_context` y lee `Settings().user_timezone` (único punto de
        lectura de ese setting, como fija T5.1).
      - `to_utc(value, tz) -> datetime`: normaliza a UTC. Un valor *aware*
        se convierte tal cual; uno *naive* se interpreta en `tz`. Usa
        `zoneinfo.ZoneInfo` (stdlib) — se añadió `tzdata>=2024.1` como
        dependencia explícita en `pyproject.toml` porque Windows no trae
        una base IANA de sistema y `zoneinfo` depende del paquete `tzdata`
        para resolverla (ya estaba presente de forma transitiva vía
        `alembic`/`psycopg`/`pydantic`, pero no declarada).
      - `AmbiguousOrNonExistentTimeError(ValueError)`: se lanza en vez de
        fallar en silencio cuando la hora *naive* cae en un hueco
        (inexistente, cambio de primavera) o un solape (ambiguo, cambio de
        otoño) de DST — detectado comparando `fold=0`/`fold=1` y
        verificando el *roundtrip* UTC→local.

      **Desviación respecto al texto original de T5.2 (normalizar en
      `models.py`):** los validadores de Pydantic no reciben
      `user_context`, así que no pueden resolver una zona horaria. La
      normalización real vive en la capa de servicio
      (`ReminderService.create_reminder`, `CalendarService.create_event`),
      que ya recibe `user_context` y es el único punto que construye los
      modelos de persistencia. `ReminderCreate.trigger_at` y
      `CalendarEventCreate.start_at`/`end_at` añaden un `field_validator`
      que exige *aware* como red de seguridad (defensa en profundidad: un
      futuro caller que construya el modelo sin pasar por el servicio no
      puede persistir un naive ambiguo). Como `AmbiguousOrNonExistentTimeError`
      hereda de `ValueError`, los `except (KeyError, TypeError, ValueError)`
      ya existentes en `execute_reminder`/`execute_calendar_event`
      (`src/agent/tools/reminders.py` / `calendar.py`) la capturan sin
      cambios adicionales y devuelven el mensaje al usuario vía
      `invalid_proposal_reply`. El paso `propose_*` sigue sin tocar: no
      llama al servicio, solo guarda el ISO string en el payload de la
      propuesta — la validación ocurre al confirmar (`execute_*`), antes de
      persistir, que es el requisito real de T5.2.

      Tests: `tests/unit/test_preferences_timezone.py` (resolución, aware
      pass-through, naive verano/invierno, ambiguo, inexistente) +
      actualizados `tests/unit/test_reminder_calendar_models.py` (naive
      rechazado por el validador).
- [x] T5.3 · **Hecho (2026-10-03).** Añadida
      `to_local_display(value, tz) -> datetime` a
      `domain/preferences/timezone.py` (convierte un valor persistido —
      aware, UTC en la práctica — a la zona resuelta; un naive se trata como
      UTC defensivamente). Aplicada en los 4 puntos que leen un valor ya
      persistido: `list_reminders`, `execute_reminder`, `check_calendar`
      (por evento) y `execute_calendar_event`. `propose_reminder` y
      `propose_calendar_event` **no** se tocaron: muestran el ISO que el
      usuario escribió tal cual, antes de cualquier conversión — ya coincide
      con lo que escribió por construcción, no hay bug ahí.
      **Alcance añadido (mismo origen del bug, no listado explícitamente en
      el texto original de T5.3):** `check_calendar` también pasaba
      `start`/`end` *naive* sin normalizar al filtro SQL de
      `CalendarService.check_calendar` → mismo problema de offset que en la
      escritura, pero en la lectura por rango. Ahora normaliza con
      `to_utc()` antes de consultar (capturando
      `AmbiguousOrNonExistentTimeError` con una respuesta fija) y conserva
      los valores originales *tal como los escribió el usuario* solo para
      el mensaje "no tienes eventos entre X y Y".
- [x] T5.4 · **Hecho (2026-10-03).** `get_current_datetime` ahora recibe
      `run_context: RunContext` como primer parámetro (deja de ser la única
      tool sin él — resuelve para esta tool, por anticipado, la pregunta que
      T6.9 iba a plantear) y devuelve dos líneas: `UTC: ...` y
      `Local (Europe/Madrid): ...`, vía `resolve_user_timezone()`. Docstring
      actualizado indicando que el LLM debe usar el valor "Local" para
      resolver expresiones relativas antes de llamar a
      `propose_reminder`/`propose_calendar_event`.
- [x] T5.5 · **Hecho (2026-10-03).** Cobertura en tres niveles:
      - `tests/unit/test_preferences_timezone.py` — `to_utc`/
        `resolve_user_timezone` aislados: naive verano/invierno, aware
        pass-through, ambiguo (otoño, solape), inexistente (primavera,
        hueco).
      - `tests/unit/test_reminder_calendar_service.py` — a nivel de
        servicio: `ReminderService.create_reminder` /
        `CalendarService.create_event` con `17:00`/`17:30` naive en verano
        e invierno → `data.trigger_at`/`data.start_at` persistido en UTC
        correcto (p.ej. `17:00` verano Europe/Madrid → `15:00Z`); rechazo de
        entrada ambigua/inexistente antes de llamar al repositorio
        (`repo.create.assert_not_awaited()`).
      - `tests/unit/test_reminder_calendar_timezone_display.py` — cadena
        completa tool→servicio→(repo mockeado)→tool: ISO naive en el
        payload de la propuesta → `execute_reminder`/`execute_calendar_event`
        persisten el instante UTC correcto y la respuesta formateada
        muestra la hora local original (`17:00`/`17:30`, nunca el UTC
        crudo); `list_reminders`/`check_calendar` convierten un valor
        almacenado en UTC de vuelta a local al mostrarlo; casos DST con
        fecha fija de octubre (ambiguo) y marzo (inexistente).
      No se añadió un test de integración específico para el worker: ya
      opera comparando contra `trigger_at` en UTC
      (`WHERE trigger_at <= :now`, con `now = datetime.now(tz=UTC)`) y no
      cambió en esta fase — su corrección depende únicamente de que
      `create_reminder` persista el UTC correcto, cubierto arriba.
- [x] T5.6 · **Hecho (2026-10-03).** `ruff check src/ tests/ scripts/
      migrations/` limpio. `mypy src/` limpio (114 ficheros). `pytest
      tests/unit/` → 641 passed (excluyendo
      `test_telegram_admission_wiring.py`, que falla al recolectar por
      falta de `TELEGRAM_TOKEN` en el entorno — preexistente, confirmado
      reproducible en `main` antes de esta fase, no relacionado). `pytest
      tests/integration/` (PostgreSQL vía Docker) → 94 passed.

**Nota (2026-10-06, fuera de esta fase):** el fallo de
`test_telegram_admission_wiring.py` señalado arriba (T5.6) por falta de
`TELEGRAM_TOKEN` ya no es reproducible — el entorno de verificación lo
exporta. En su lugar se encontró y corrigió un fallo distinto y real en el
mismo archivo: sus dos factorías `Settings(...)` no pasaban `_env_file=None`
(patrón ya establecido en `test_config.py`), así que un `.env`/entorno local
con `ADMIN_DASHBOARD_ENABLED=true` (BL-43/specs-027) filtraba rutas
`/admin/dashboard/*` reales a la aserción de lista exacta de rutas del test,
rompiéndolo. Corregido añadiendo `_env_file=None` +
`runtime_config_admin_enabled=False`/`telegram_pairing_admin_enabled=False`/
`admin_dashboard_enabled=False` explícitos en ambas factorías. `pytest
tests/unit/` → 770 passed; `ruff check src/ tests/ scripts/ migrations/` y
`mypy src/` (126 ficheros) limpios.

**Criterio de cierre:** un recordatorio o evento creado con una hora local
dicha por el usuario se dispara/consulta en esa misma hora local, con
pruebas que cubren al menos un cambio de horario de verano/invierno.

---

## Fase 6 — Sincronización documental (🟡 medio)

- [x] T6.1 · **Hecho (2026-10-03).** Recuento real tras Fase 5:
      643 unit (`pytest tests/unit/`) + 94 integration
      (`pytest tests/integration/ -q --collect-only`, PostgreSQL/Docker).
      Actualizado en `AGENTS.md` (cabecera + árbol §3) y `BACKLOG.md`
      (snapshot). `README.md` no tenía un recuento de tests que corregir
      (su cabecera de capabilities decía "35 tools", ya correcto — ver T6.3).
- [x] T6.2 · **Hecho (2026-10-03).** Verificado caso por caso contra
      `verification.md` de cada spec antes de tocar nada (nunca asumido):
      specs/001 ("draft" → implemented), specs/009 ("pendiente" →
      implemented 2026-09-09, 94 passed), specs/010 ("pendiente" →
      implemented 2026-09-09), specs/013 ("implementation pending" → 🔶
      T2–T14 implementados localmente, con los pendientes reales
      enumerados) y ADR-004/ADR-005 (mismo ajuste que specs/013, con
      pointer a `verification.md`).
- [x] T6.3 · **Hecho (2026-10-03).** Reescrita `docs/architecture.md` §10
      para que sea un espejo exacto de la tabla de `README.md` §Capabilities
      (35 tools, no 32 — el número de la tarea original estaba desactualizado;
      verificado contando los `tools.extend(...)` reales en
      `_init_domain_tools()`/`src/main.py`): nombres `propose_*`/`execute_*`
      correctos, vehicle creation separada de vehicle write, TODO lists y
      TODO items incluidos.
- [x] T6.4 · **Hecho (2026-10-03).** specs/011 Fase 4 (specs/023) ya está
      completa — añadida una nota fechada en `verification.md` que marca la
      decisión original de 2026-09-10 ("items directos sin propose/execute")
      como superada por specs/023 Fase 4, sin reescribir la entrada
      histórica (se preserva como registro de la decisión original, por la
      convención de BACKLOG.md de no editar specs completados).
- [x] T6.5 · **Hecho (2026-10-03) — hallazgo real, no solo documental:**
      `skills/calendar.md` sí existe en disco (al contrario de lo que
      asumía el enunciado de la tarea), pero **nunca estaba cableado en
      `assemble_instructions()`** — un olvido real desde que se escribió el
      fichero (confirmado con `git log --follow`), no una decisión
      documentada. Corregido añadiéndolo a
      `src/agent/instructions.py::assemble_instructions()` (con test de
      regresión). `document_extraction.md` confirmado como exclusión
      intencional: lo carga `src/agent/document_extraction.py` directamente
      para la llamada de extracción separada, no el agente principal — ya
      documentado en código, y ahora también en `docs/governance.md`.
- [x] T6.6 · **Hecho (2026-10-03).** Elegida la opción "describir el
      formato real" (implementar un contrato JSON across 35 tools quedaba
      fuera de alcance de una fase de sincronización documental). Sustituido
      el bloque `{"status": ...}` en `prompts/tool_contract.md` por una
      descripción fiel con ejemplos reales tomados de `validation.py` y de
      tools concretas (reminders/notes), terminando en una línea explícita:
      "no hay un campo `status`, no lo esperes ni lo inventes".
- [x] T6.7 · **Hecho (2026-10-03).** Confirmado por grep (sin matches fuera
      de `__pycache__`/`egg-info` autogenerado) y eliminado:
      - `src/agent/context.py` — `UserContext` legado (shape distinto al
        canónico de `src/security/user_context.py`), sin ningún import.
      - `src/services/__init__.py` (paquete `src/services/` completo,
        vacío salvo el docstring) — a diferencia de `src/governance/`, que
        sí está documentado como "reservado" en AGENTS.md §3 y README.md
        (se deja tal cual), `src/services/` no aparecía en ningún documento
        de estructura; se eliminó en vez de justificarlo.
      - `_NOTE_TOOLS` global en `src/main.py` — se escribía
        (`.extend(...)`) pero nunca se leía en ningún sitio.
      `ruff`/`mypy`/`pytest tests/unit/` en verde tras la eliminación (ver
      T6.10).
- [x] T6.8 · **Hecho (2026-10-03).** Añadida la columna "Entorno" a la
      matriz A–Y de `specs/013-llm-access-governance/verification.md`,
      separada del ✅ genérico. Clasificación resultante: 6/25 casos (A, B,
      C, N, O, V) con evidencia de Railway real; C y Q combinan Railway con
      local; los 18 restantes solo tienen cobertura unit/integration local,
      nunca ejecutados contra el despliegue real — ahora explícito fila a
      fila en vez de mezclado dentro del texto del ✅.
- [x] T6.9 · **Resuelto en Fase 5 (T5.4, 2026-10-03), no intencional.**
      `get_current_datetime` no recibía `run_context` simplemente porque
      nunca necesitó identidad hasta que T5.4 le pidió resolver la zona
      horaria del usuario — en ese momento se le añadió `run_context` como
      primer parámetro, igual que al resto de tools (`src/agent/tools/system.py`).
      No se cambió su comportamiento observable salvo la línea "Local"
      añadida por T5.4. No hace falta anotar una excepción en AGENTS.md §4:
      la regla "`run_context` como primer parámetro de toda tool" nunca tuvo
      ahí una excepción documentada, y ahora es cierta sin salvedades.
- [x] T6.10 · **Hecho (2026-10-03).** `ruff check src/ tests/ scripts/
      migrations/` limpio. `mypy src/` limpio (112 ficheros — 114 antes de
      T6.7, menos los 2 ficheros eliminados). `pytest tests/unit/` → 645
      passed (643 de Fase 5 + 2 tests nuevos de T6.5 — regresión de la
      skill de calendario y de la exclusión de `document_extraction.md`).

**Criterio de cierre:** ningún documento (AGENTS/README/BACKLOG/specs/prompts)
contradice el estado real del código verificado en las fases 1–5.


