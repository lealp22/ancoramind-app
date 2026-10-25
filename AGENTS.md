# AGENTS.md — Contexto para Agentes de Programación

> Guía para asistentes de IA que trabajan en este repositorio.
> Última actualización: 2026-10-14

---

## 1. Qué es este proyecto

**AncoraMind** — asistente personal agentic (POC/MVP) que convierte información
cotidiana desordenada en memoria operativa: notas, documentos, datos de vehículos,
recordatorios y eventos, con trazabilidad completa.

- **Runtime agentic:** Agno + AgentOS (infraestructura reemplazable)
- **Canal:** Telegram (solo private chats)
- **Base de datos canónica:** PostgreSQL (schema `ancora`, separado de `agno_runtime`)
- **Lenguaje:** Python 3.12+
- **Estado actual:** Milestones M1–M5 completos (ver §8) + listas TODO +
  recurrencia/snooze (BL-41/specs/024) + extracción determinista de PDF con
  capa de texto (BL-38 Fase 1/specs/021) + adaptador físico de evals y harness
  Core de consentimiento sin inferencia real (BL-8/specs/018 T6/T6b) + frontera `untrusted_results`
  extendida a vehículos/recordatorios/calendario/TODOs (BL-39/specs/022 T8) +
  subclasificación WRITE_TRIVIAL/WRITE_REVIEWABLE para TODO items y notas
  (BL-46/specs/035, ver §2.4) + tool de lectura `list_pending_proposals`
  para que el Agent nunca narre propuestas pendientes desde memoria
  conversacional (BL-47) + presentación particionada `AgentReply` para un
  único bloque Core de propuestas en Telegram (BL-48/specs/036, desplegada y
  parcialmente validada E2E; matriz restante pendiente). Desde 2026-10-16:
  el Agent principal termina mediante `present_reply` (`tool_choice=required`,
  sin JSON mode/output_schema); el Core nunca entrega `proposal_text` sin
  propuestas persistidas; una salida terminal inválida queda `failed_ambiguous`
  y genera un aviso fijo sin retry. La tool terminal consume presupuesto, no
  escribe datos canónicos ni concede consentimiento. BL-47 se validó E2E con
  lectura real + `present_reply` (`tool_call_count=2`).
  BL-46 completado con variantes reviewable descripción-sola/fecha-sola; BL-48
  espera ejecución real del harness aislado (lanzador one-shot y revisión humana
  local preparados, sin aprobación de gasto ni acceso nuevo).
  1626 unit tests y 207 integration PostgreSQL superados; una prueba STT live
  se omite por diseño. Ruff y `mypy src/` limpios; ambos son gates globales en CI.
  BL-52/specs/037 desplegado y validado E2E acotado: primer aviso, cooldown,
  renovación y `/help` autorizado; rejected intacto/sin IA. Flag
  `TELEGRAM_ACCESS_NOTICE_ENABLED` ON en producción (default en código OFF).
  Head Alembic local/Supabase `0017_access_notice_index`. Panel y pairing
  permanecen ON por decisión del propietario, sin apagado automático post-E2E.
  BL-49/specs/038 desplegado: bloque Core de calendario con
  recurrencia/límite/aviso/antelación y snooze con título canónico scoped al
  usuario y duración. Sin cambios de payload/hash, consentimiento ni ejecución;
  presentación/descarte Telegram superados en SHA `65295ac`. Primera petición
  natural de recurrencia rechazada sin propuesta. BL-54/specs/039: corregida
  contradicción de contrato `recurrence_until` (datetime con zona,
  no fecha sola), rango de intervalo y error fijo sin eco en ambas tools;
  parser intacto. SHA `778c5a3` desplegado por el propietario y CI verde:
  petición natural con zona/límite explícitos y descarte E2E superados;
  cero eventos/avisos nuevos. Cierre acotado, causa histórica exacta no
  confirmada ni garantía semántica general. Cambio evaluable documentado.
  Runtime config activa:
  revisión 8, default `ancoramind-default-r4` y embeddings `ancoramind-embeddings-r1`.

  **Evaluador specs/040 (código desplegado idle; uso real pendiente):** consola reutilizable
  `scripts/eval_console.py`, worker desacoplado y revisión recuperable sin nueva
  inferencia, evidencia/revisiones **sólo sintéticas** cifradas en volumen separado,
  autosave por criterio y promoción humana/versionada de golden Agent/juez. Es una
  decisión explícita del propietario de persistir contenido sintético privado:
  no captura de contenido personal ni logs/OTel con prompts/resultados. Retención
  bruta7d/purga manual, markers anti-replay conservados; exports sanitizados
  explícitos. Candidato histórico db0c59b sigue sin esa recuperación; no inventar
  revisión ni relanzar campaña interrumpida. Nuevo código publicado en7ea0cf06
  vía specs/041. Setup reutilizable realizado por propietario y campaña real única
  autorizada5casos/nominal0,10USD/humano/cifrado7d: run52759a15ad454050aef8b5c1a9b3f122
  stopped con5calls. Caso1 passed técnico+2labels pass/3calls; caso2
  InvalidPresentationOutputError sin observación,3restantes no iniciados. No tecla p
  ni setup demostrado como causa. No reconstruir salida faltante ni repetir run.
  Incremento local diagnóstico allowlist/counters/estado terminal/checkpoint/status,
  sin contenido extra, retries ni cambios prompts/provider/guard de aceptación.
  Reproducciones offline/caso mixto guionizado y158focales/1skip superados;
  1925unitarias/1skip,80,98 %,14integraciones focales PostgreSQL local,
  Ruff/mypy178/catálogos/diff limpios. Nueva
  huella requiere SHA/CI/publicación y aprobación independientes. Causa histórica
  exacta/validación E2E completa siguen abiertas; no inferir por publicar.
  **Cambio operativo autorizado specs/042 (local):** propietario aprueba sesión
  acotada0,10USD acumulados incluyendo histórico, no nuevas aprobaciones por SHA
  de diagnóstico/operación. Base3f2e8b89/CI39219285248 verde sólo diagnóstico;
  sesión nueva requiere otro commit/CI/publicación. Ledger cifrado/clave fija,
  scope de casos/modelo/prompts/runtime, import conservador de reportes previos,
  reserva por caso/reparto saldo/claim source/lease worker, checks Gateway pre/post
  POST vía LLMAccess, sin resets/retries/replay incierto ni secretos extra.
  `session-init --accept-session` sólo GET e import; luego run manual omite passed
  históricos sin certificarlos para SHA nuevo. Scope/presupuesto distintos o saldo
  insuficiente requieren hablar, no renovar autorización repetidamente por comando.
  Mismo source/caso no se relanza; incertidumbre preserva reserva. Nominal/estimado,
  no promesa de factura exacta/ledger distribuido. Sin inferencia/deploy por agente.
  Validación sesión1969unitarias/1skip,81,22 %,44pruebas nuevas de sesión,
  Ruff/mypy180/catálogos/diff limpios; paquete sellado/help offline válido.
  Integraciones intentadas bloqueadas14errores setup: Docker daemon/PG local
  ausentes, no fixtures remotos. No afirmar passed. Pendiente SHA/CI/publicación;
  import separa db0c59b/claves2h previas de7ea0cf06, sin borrar/mutar históricos.
  Sesión publicada32474d5b/CI39237715770/workflow39239239445,
  deploymente30e1e80-fc2d-4cfd-b4b7-6652f667f349 idle verificado. Propietario reporta
  session-init bloqueado session_prior_execution_not_terminal/sin inferencia.
  Bug de orden reproducido: check terminal antes de excluir db0c59b interrumpido;
  fix sólo local separa histórico primero, estado actual/desconocido no terminal
  sigue bloqueado.80focales/1991unitarias/1skip/81,22 %,Ruff/mypy180/diff limpios.
  Metadata posterior del propietario confirma current_or_other/stopped y
  pre_session_db0c59b/running: mecanismo confirmado, no worker vivo demostrado.
  Recheck21focales pasa; fix sin publicar, no afirmar E2E resuelto. No borrar
  archivos/editar estados/reiniciar presupuesto.
  Fix import publicado Git68ae6654/CI39246649825 verde; workflow39248955747 bloquea
  correctamente: pendingWork con botfce3f7ac y collector5de0748a NEEDS_APPROVAL de
  ese push, aunque patch`{}` y sin staged config. Dashboard ofrece Skip/Deploy.
  No cancelar/aprobar ni ignorar trabajos ajenos automáticamente; propietario puede
  Skip sólo esos pendientes si no deseados, conservar SUCCESS y verificar entorno
  vacío antes de nuevo workflow mismoSHA. No parche extra ni reiniciar claves.
 42regresiones guard pasan; evaluador sigue32474d5b/e30e1e80, sin inferencia.
  1753 unitarias/1 skip symlink Windows,207 integración/1 STT skip,80,85 % cobertura;
  Ruff/mypy src177 limpios. Detalle `specs/040-durable-eval-review/`.

  **Publicación evaluador specs/041 (primer rollout verificado):** workflow manual
  `Actualizar evaluador` (`.github/workflows/deploy-evals.yml`) con SHA completo,
  CI exacta y confirmación de ausencia de campaña. Sólo runner GitHub alojado;
  **no instalar/ejecutar Railway CLI en el ordenador gestionado del propietario**.
  Secret inicial `RAILWAY_EVALS_DEPLOY_TOKEN` en environment GitHub
  `ancoramind-evals-deploy` (token Railway de proyecto/entorno, NO sólo servicio).
  Helper empaqueta contexto eval allowlist y publica/verifica sólo evals sin
  inferencia ni tocar volumen/otros servicios. Secreto creado por propietario;
  SHA da351546/CI verde y run39157815349 bloqueado antes de mutaciones. Contador
  nullable corregido, pero schema staged es NON_NULL: exigir null era otro error.
  Enmienda autorizada: leer patch sólo en memoria, permitir únicamente STAGED/`{}`
  exacto y pendingWork del mismo id/entorno, sin hijos/otras operaciones; cualquier
  contenido/error/inconsistencia bloquea. No imprimir/persistir patch ni valores,
  ni aplicar/descartar borrador. b0b6beb9/run39160757789 supera staged pero rechaza
  réplica legacy=null: manifiesto regional tiene una réplica y hay RUNNING.
  Fix local usa evidencia explícita del manifiesto, nunca default null→1, reasons
  específicos y check_only opcional sin escrituras/subida. CLI5.70.0/docs/API
  contrastados, fixture API saneada/adaptador integral y arranque Docker offline
  del paquete b0b6 superados (dependencias cacheadas, no build fresh).
  SHA7ea0cf06002d76692f230d189c43e8f9f5e742b1/CI39163986626 verde; check_only
  run39164426466 y publicación39165134464 correctos: deployed_idle_verified,
  deploymentb4305cc0-3ddd-404e-8dbc-a3b002103b1f,1 RUNNING/0crashed, sin pendingWork,
  volumen conservado/otros servicios sin cambios según workflow. SHA/huella por
  sello/log del upload; pin GitHub histórico db0c59b permanece sin reconnect.
  1867 unitarias/1 skip,127 focales,80,85 %,Ruff/mypy177 limpios.
  Segundo run39171845184 bloqueado tras Alt+Deploy de variables: API sin borrador
  devuelve id literal `<empty>`, STAGED/entorno/patch`{}` y pendingWork`[]`; helper
  sólo aceptaba UUID+fila. Fix local acepta sólo ambas combinaciones exactas,
  manteniendo rechazo de contenido/errores/inconsistencias;158 focales pasan,
  1898 unitarias/1skip,80,85 %,Ruff/mypy177/diff limpios.
  Publicado helper1c700339 en workflow39173039736: deployed_idle_verified,
  candidato7ea0cf06/deployment085cb777-6e58-489b-93ef-c4596d68e0c7,1RUNNING/0crashed,
  sin pendingWork/volumen y otros servicios conservados según workflow/MCP.
  Propietario reporta clave eval r4 nominal0,10USD/7d creada sin inferencia; variables
  aplicadas mediante nueva publicación (valores no consultados), volumen conservado.
  Campaña posterior parcial real descrita arriba; sin inferencia ni CLI local por
  agente. Diagnóstico nuevo sólo local; no relanzar campaña histórica.
  Instrucciones navegador `specs/041-manual-eval-deploy/runbook.md`.

  **Dashboard propio (local, 2026-10-22):** `/admin/dashboard` tiene Resumen,
  Propuestas, Administración y Prompts. Pestañas/salud compacta y gráficos
  FinOps (columnas diarias, dos anillos, tres barras sin umbrales) documentados
  en `docs/runbooks-027-admin-dashboard.md` y specs/027/043. Catálogo specs/048:
  contenido de `prompts/`, usos literales detectados y versiones Git exportadas
  en `src/agent/prompt_history.json`; no edita/aprueba/activa ni prueba prompt/run.
  Tras commitear cambios de prompts, regenerar con
  `python scripts/export_prompt_history.py` y commitear el artefacto;
  `--check` es gate CI (checkout completo). No necesita `.git`/GitHub en runtime.
  2260 unitarias/2 skips, Ruff/mypy187 y navegador aislado superados en specs/048;
  no despliegue ni validación remota nueva. No confundir con Grafana/specs016.

  **Trazas de contenido enmascarado en Phoenix (BL-56/specs/046/ADR-007, local,
  2026-10-25):** implementado con el flag `PHOENIX_TRACING_ENABLED` **apagado** y sin
  ninguna variable `PHOENIX_*` en Railway (comprobado por nombre); no desplegado ni
  probado contra Phoenix real. Pipeline separado del de Grafana
  (`src/observability/phoenix_export.py`, `phoenix_capture.py`, `field_policy.py`),
  captura manual en `GovernedInteractionRunner.run`, fail-open y fail-closed por span.
  Voz, adjuntos, documentos y resultados de lectura nunca se capturan; una tool sin
  clasificar en `phoenix_capture.py` queda excluida. Un test de extremo a extremo
  (`tests/unit/test_phoenix_pipeline_privacy.py`) comprueba lo que recibe cada
  exportador. Su hallazgo: los spans de Grafana copiaban el mensaje y la traza de
  una excepción de tool; corregido en `telemetry.py`. Verificado por consulta:
  el runtime de Agno (`agno_runtime`) guarda sin enmascarar los resultados de las
  tools y no tiene retención (BL-34, decisión pendiente). La purga a 7 días de
  payloads ambiguos está implementada pero ningún código de producción la invoca.
  Inventario, límites del enmascarado y borrado por usuario:
  `docs/production-security-privacy.md`. Runbook en `docs/runbooks-phoenix-tracing.md`.
  Gates locales superados (2682 unitarias, 218 integración PostgreSQL local con 1 skip
  STT por diseño, Ruff, mypy190, prompts `--check`). Pendiente: SHA/CI en `main` (17
  commits locales sin subir), activación controlada (T12); activar exige antes publicar
  `docs/pilot-terms.md` y comprobar la retención y el puerto gRPC en Phoenix.

---

## 2. Principios arquitectónicos NO negociables

Estas reglas vienen del brief de ingeniería. **No violarlas aunque parezca más simple:**

1. **Agno es infraestructura reemplazable; AncoraMind Core es el producto.**
   La lógica de negocio (`src/domain/`) NUNCA hereda de clases de Agno. Debe poder
   invocarse desde REST API, CLI, MCP, u otro runtime sin duplicación.

2. **Añadir capacidad ≈ añadir Tool.** Un solo agente principal. Sin routers,
   sin subagentes, sin workflows nuevos salvo necesidad demostrable.

3. **Frontera probabilístico/determinista.** El LLM decide *qué capability
   solicitar*; el Core decide *qué permisos tiene*. La identidad del usuario
   (UserContext) NUNCA procede del LLM — se resuelve del `RunContext` de Agno.

4. **Toda operación WRITE/EXTERNAL_ACTION/DESTRUCTIVE requiere gobernanza.** Patrón ActionProposal:
   `propose_*` crea propuesta `pending_confirmation` → usuario confirma ("Sí")
   → `execute_*` valida, ejecuta y audita. Ejemplos:
   `propose_vehicle_maintenance` / `execute_vehicle_maintenance`.
   **Hardening local (2026-10-11, BL-39/40):** el Agent solo dispone de
   READ/`propose_*` y excepciones aprobadas; ningún `execute_*` se registra.
   Confirmación y ejecución viven en el Core (`ProposalExecutor`). Las APIs
   legacy `confirm`/`confirm_or_use_confirmed`/`mark_executed` rechazan sin I/O.
   Con `GOVERNED_CONSENT_ENABLED=false` las propuestas no se ejecutan; no hay
   fallback al criterio del LLM. Pendiente rollout manual y E2E Telegram.
   **Excepción aprobada (specs/023 T4.7, 2026-10-02):** `analyze_document`/
   `DocumentService.ingest` siguen siendo automáticos — enviar un adjunto ya
   es la señal de intención de guardarlo; pedir confirmación añadiría
   fricción innecesaria para el caso común. A cambio existe
   `propose_document_delete`/`execute_document_delete` (DESTRUCTIVE,
   gobernado) para el caso "no quiero esto guardado".
   **Subclasificación WRITE_TRIVIAL / WRITE_REVIEWABLE (BL-46/specs/035,
   2026-10-13):** dentro de `WRITE`, una mutación es `WRITE_TRIVIAL` solo si
   es reversible en un paso, no tiene ningún dato ambiguo que convenga
   revisar antes de persistir, y su target ya existe y su propiedad se
   verifica igual que en el camino `WRITE_REVIEWABLE`. `WRITE_TRIVIAL` sigue
   siendo gobernanza equivalente, no una segunda excepción ad hoc como
   `analyze_document`: toda mutación trivial se audita atómicamente junto
   con su efecto (`ActionProposalsRepository.create_self_authorized`, fila
   `consent_mode='self_authorized'` ya en estado terminal `executed`, sin
   `pending_confirmation` ni "¿Confirmas?"), vía `TrivialExecutor`
   (`src/domain/actions/trivial_executor.py`) — nunca el pipeline de
   confirmación (`claim_confirmation`/`ProposalExecutor`), que sigue siendo
   exclusivo de `WRITE_REVIEWABLE`. Alcance aprobado hoy (primera
   iteración, ampliar requiere su propio hallazgo/decisión): añadir una
   tarea TODO con solo título a una lista ya existente
   (`propose_todo_item` sin `description`/`priority`/`due_date`), marcar una
   tarea completada/reabierta (`propose_todo_item_complete`/`reopen`), y
   toda nota (`propose_note` — `Note` no tiene ningún campo estructurado de
   riesgo, es texto libre). Mover/eliminar una tarea, crear/renombrar/borrar
   una lista y el resto de dominios (vehículos, recordatorios, calendario,
   documentos) permanecen `WRITE_REVIEWABLE` sin cambios.

5. **SQL siempre parametrizado.** Solo `sqlalchemy.text()` con bind params.
   Nunca interpolación de strings. Toda query scoped por `user_id`.

6. **Prompts en Git, no en código.** Los prompts viven en `prompts/*.md`
   (identity, soul, tool_contract, channels/, skills/). No meter instrucciones
   críticas como strings anónimos en Python.

7. **Separación de DBs.** Agno persiste su runtime donde quiera
   (`agno_database_url`); el dominio usa `ancora_database_url` → schema `ancora`.
   AncoraMind Core jamás depende de las tablas internas de Agno.
   Despliegue acordado: Supabase aloja `ancora` (incluye dominio, ledger,
   propuestas, uso LLM y runtime-config); Railway aloja runtime Agno y Gateway.
   No usar las BD productivas como destino de fixtures/tests de integración.

8. **Datos no confiables = DATA, no INSTRUCTIONS.** Contenido de documentos,
   filenames, extracciones IA no pueden cambiar permisos ni instrucciones.

9. **El acceso LLM es una capability gobernada (target BL-23/specs/013).** Toda
   inferencia deberá pasar por `LLMAccess`, con ruta lógica versionada,
   `RuntimeConfigSnapshot`, `ExecutionContext`, budget, coste y correlación. No
   crear providers físicos directamente en domain/services/tools.

10. **Idempotencia Telegram ≠ rate limiting.** El target es
    `same bot_id + update_id => at most one Agent execution`. Duplicados reciben
    `2xx` sin IA; después de `agent_started` no hay replay automático.

11. **Observabilidad sin contenido personal (target BL-23/specs/013).** Usar
    OpenTelemetry + Collector privado + Grafana Cloud con allowlist de metadata.
    No prompts, mensajes, respuestas, documentos ni argumentos/resultados
    completos. La auditoría durable permanece en PostgreSQL.
    **Enmienda acotada (ADR-007, 2026-10-23):** esta regla sigue íntegra para
    el pipeline OTel/Grafana. Un pipeline separado hacia Phoenix puede recibir
    una copia **enmascarada** del contenido conversacional (retención 30 días,
    captura manual en el adaptador gobernado, nunca documentos, extracciones,
    voz ni secretos), detrás de flag OFF por defecto y fail-open. Activarlo en
    producción exige el gate de specs/046; no es un permiso general de captura.

---

## 3. Estructura del repositorio

```
src/
├── main.py              ← Entry point: AgentOS + Telegram + registro de tools
├── config.py            ← Pydantic Settings (.env). extra="ignore"
├── agent/               ← Capa Agno (infraestructura)
│   ├── ancora_agent.py  ← factory + ToolCallSafetyMixin/SafeOpenRouter/SafeOpenAILike (BL-16); composición GovernedModel
│   ├── llm_access.py / governed_model.py / governed_agent_factory.py /
│   │   governed_interaction_runner.py ← T7: LLMAccess + Agent por run
│   ├── instructions.py  ← assemble_instructions(): carga prompts/*.md → list[str]
│   ├── lifecycle.py     ← lifespan FastAPI: worker recordatorios auto-gated (BL-22)
│   ├── server.py        ← host/PORT/reload para local y Railway
│   ├── telegram_webhook.py ← helper de registro; telegram_admission.py ← endpoint T4
│   ├── context.py       ← legado; UserContext canónico está en security/
│   └── tools/           ← Thin adapters (UNA función por capability)
│       ├── system.py      notes.py      documents.py
│       ├── vehicles.py    maintenance.py (propose/execute)
│       ├── reminders.py   calendar.py    todos.py (propose/execute estricto)
├── domain/              ← Lógica de negocio (el producto — sin imports de Agno*)
│   ├── notes/ documents/ vehicles/ reminders/ calendar/ todos/ actions/ interactions/ llm_access/
│   └── (cada uno: models.py + service.py; calendar tiene provider.py Protocol;
│       reminders tiene worker.py sin dependencia de FastAPI; documents expone
│       DocumentExtractionPort — T9 abstrajo la extracción del runtime;
│       interactions/commands.py resuelve los comandos de bot `/new` y `/help`
│       antes de cualquier ejecución del Agent — BL-28)
├── repositories/        ← Acceso PostgreSQL (sqlalchemy async, text() parametrizado)
│   ├── database.py      ← init_database(), get_session() — llamar init al arrancar
│   └── notes, documents, vehicles, maintenance, reminders, calendar, todos, actions,
│       interactions, llm_usage (ledger/usage durable — specs/013)
├── storage/             ← base.py (DocumentStorage Protocol), local.py, supabase_storage.py,
│                           factory.py (DOCUMENT_STORAGE_BACKEND: local|supabase — ADR-002)
├── security/            ← user_context.py (UserContext.from_run_context)
├── notifications/       ← telegram.py (TelegramNotifier — entrega outbound BL-5/ADR-003)
│                           + markup.py (Markdown del modelo → HTML de Telegram, BL-29)
└── governance/          ← (metadata, riesgo — en desarrollo)

AGENTS.md                 ← Esta guía (jerarquía: manda junto con docs/architecture.md)
BACKLOG.md                ← Lista viva y priorizada de pendientes (fuente única de verdad)
prompts/                 ← Assets de IA versionados (identity, soul, tool_contract,
│                           channels/telegram.md, skills/)
migrations/              ← Alembic canónico (baseline + revisiones); init.sql
│                           refleja head para bootstrap fresh — BL-12/specs/013
scripts/                 ← run-e2e.sh + run-e2e.ps1 + telegram_webhook.py + runtime_config.py (admin T6)
                            + litellm_create_virtual_key.py (T11 Gateway)
                            + litellm_gateway_alias.py (ADR-005: publicar/otorgar/
                              retirar aliases versionados en caliente)
                            + run_evals.py (BL-8: validación determinista de catálogos)
specs/                   ← SDD: 001-runtime, 002-notes, 003-documents, 004-vehicle,
                            005-calendar, 006-vehicle-creation, 007-supabase,
                            008-railway-deployment, 009-integration-tests,
                            010-reminder-worker, 011-todo-lists, 012-fastapi-lifespan,
                            013-llm-access-governance (T2–T14 implementados localmente),
                            014-agentic-evals (base determinista) +
                            018-agentic-evals-execution-harness (harness aislado),
                            015-powershell-e2e (implementada),
                            016-health-dashboard (en curso — BL-33),
                            017-telegram-governed-pairing (implementada),
                            019-mypy-hardening + 020-mypy-ci-gate (gate global en
                            CI), 021-document-conversion-toolkit (Fase 1 lista para
                            implementar — BL-38), 022-llm-input-trust (primer
                            incremento local — BL-39),
                            023-audit-remediation (Fases 1–5 implementadas
                            localmente; Fase 6 en curso — BL-40),
                            024-recurring-events-reminders (eventos y
                            recordatorios recurrentes + snooze — en curso,
                            BL-41), 034-tool-call-safety (BL-16: filtro compartido
                            OpenRouter/OpenAILike; retirada upstream pendiente),
                            035-write-trivial-risk-tier (BL-46: subclasificación
                            WRITE_TRIVIAL/WRITE_REVIEWABLE — implementada
                            localmente), 036-telegram-proposal-presentation
                            (BL-48: contrato answer/proposal_text, renderer y
                            prompts — local, sin despliegue)
tests/unit/              ← 1421 tests
tests/integration/        ← 160 tests recolectados (159 pasan con PostgreSQL
                            dockerizado; 1 STT live se omite por diseño)
evals/                   ← Catálogos sintéticos versionados (BL-8/specs/014 + 018)
docs/                    ← architecture, governance, development, quick-start,
                           deployment-e2e, deployment-railway, runbooks-013
                           (operación specs/013), adding-tools (guía para nuevas
                           tools),
                           llm-security-hardening (prompt injection/contenido
                           no confiable — BL-39/specs/022-023),
                           production-security-privacy (GDPR/AI Act, ZDR,
                           gates de apertura pública — specs/028),
                           adr/ADR-001-agno-runtime.md,
                           adr/ADR-002-supabase-infrastructure.md,
                           adr/ADR-003-reminder-worker.md,
                           adr/ADR-004-telegram-admission-at-most-once.md,
                           adr/ADR-005-governed-llm-access-runtime-config.md,
                           adr/ADR-006-opentelemetry-observability.md
gateway/                 ← LiteLLM Proxy pilot (T11/T12): config sin secretos, circuit breaker + RPM/TPM
                           con imagen fijada por digest y compose local de validación;
                           store_model_in_db permite publicar aliases r2+ en caliente
                           (ADR-005 enmendado — nunca editar un alias en uso)
observability/           ← Manifiesto del OTel Collector privado (T10)
```

***\*Sin excepciones:*** `domain/` no importa Agno. La extracción documental
usa `DocumentExtractionPort` (T9); su adaptador Agno vive en `src/agent/`
y pasa por `LLMAccess`.

---

## 4. Convenciones de código

- **Tools = funciones Python planas async.** Agno las convierte en tools por el
  docstring y type hints. El docstring es la descripción que ve el LLM —
  escribirlo con cuidado (cuándo usar la tool, ejemplos de frases del usuario).
- **`run_context: RunContext`** como primer parámetro de toda tool → inyección
  automática de Agno (no va al schema del LLM).
- **Devolver strings formateados en español** desde las tools (el usuario habla
  español). Estructura: título en negrita, datos alineados, emojis moderados.
- **Resultados de repos:** modelos Pydantic con `model_config = {"from_attributes": True}`.
- **Pydantic v2:** para campos opcionales usar `X | None = None` (con
  `from __future__ import annotations` si hay shadowing de nombres).
  Evitar `Optional[X] = Field(default=None)` (bug de generación de schema).
- **Servicios de domain** reciben repositorios por constructor (inyección manual).
- **Config:** todo por env vars vía `Settings` en `config.py`. Nunca hardcodear
  credenciales ni URLs.
- **Comandos de bot:** se resuelven en `domain/interactions/commands.py` antes de
  cualquier ejecución del Agent (BL-28). Nunca llegan al LLM ni arrastran el
  historial al proveedor; sus replies son constantes en código (así el texto del
  usuario no puede convertirse en instrucción por esta vía). Añadir un comando =
  entrada en el mapa + reply constante + tests.
- **Formato de entrega:** las respuestas del modelo se renderizan a HTML de
  Telegram en `notifications/markup.py` (BL-29): todo el texto literal se escapa y
  las etiquetas salen sólo de una whitelist del módulo. Nunca declarar
  `parse_mode` en otro sitio ni interpolar contenido sin escapar; si Telegram
  rechaza el markup, la entrega reintenta en texto plano en vez de perderse.

### Proveedores LLM (factory en `ancora_agent.py`)

| `LLM_PROVIDER` | Clase Agno | API key env var | `LLM_BASE_URL` |
|---|---|---|---|
| `openai` | `OpenAIChat` | `OPENAI_API_KEY` | opcional |
| `openrouter` | `SafeOpenRouter` (Agno `OpenRouter`) | `OPENROUTER_API_KEY` | automático |
| `openai-like` | `SafeOpenAILike` (Agno `OpenAILike`) | `OPENAI_API_KEY` | **requerido** |

Modo Gateway (T11): con `LITELLM_PROXY_ENABLED=true` la tabla anterior se ignora
— `LLMAccess` y el AgentOS legado componen únicamente `SafeOpenAILike`
(subclase de `OpenAILike`, filtro de tool calls compartido con
`SafeOpenRouter` — BL-16/specs/034) hacia el
LiteLLM privado (`LITELLM_PROXY_BASE_URL` + `LITELLM_PROXY_VIRTUAL_KEY`,
fail-closed si faltan), usando el alias versionado del snapshot como `model`.
La virtual key se crea con `scripts/litellm_create_virtual_key.py`; los secretos
del provider viven sólo en el Gateway (`gateway/litellm-config.yaml` no contiene
secretos). Un Gateway caído ⇒ error de inferencia, nunca fallback directo.

Modelo default para acceso directo/desarrollo: `gpt-6-luna`. Con el Gateway,
producción usa GPT-6 Luna mediante el alias gobernado `ancoramind-default-r4`
en la revisión runtime 8; `ancoramind-default-r3` se conserva como candidato
histórico. Los modelos free de OpenRouter caducan — si hay
error 404, cambiar `LLM_MODEL` en `.env`.

**Cambiar el modelo físico (ADR-005, enmendado 2026-09-18):** con el Gateway
activo `LLM_PROVIDER`/`LLM_MODEL` se ignoran. El cambio se hace publicando un
alias versionado **nuevo** (`r2`, `r3`, …) con
`scripts/litellm_gateway_alias.py` y activando una revisión de runtime config
que apunte a él: sin redeploy y sin mutar el alias en uso. Prohibido editar un
alias existente (rompe la trazabilidad de `effective_gateway_route`). Ver
`docs/runbooks-013.md` §2.2.

---

## 5. Comandos

> Los comandos que usan `<` (redirección bash) **no funcionan en PowerShell**.
> Se indica la alternativa para cada shell cuando sea necesario.

```bash
# Activar venv (PowerShell)
.venv/Scripts/Activate.ps1

# Activar venv (Git Bash)
source .venv/Scripts/activate

# Tests unitarios
python -m pytest tests/unit/ -v

# Integration tests (160 recolectados — requieren PostgreSQL dockerizado;
# resultado vigente: 159 passed, 1 STT live skipped por diseño)
python -m pytest tests/integration/ -v

# Lanzar la app localmente (requiere .env + PostgreSQL/Supabase; webhook solo
# si se valida Telegram mediante una exposición HTTPS autorizada)
python -m src.main

# PostgreSQL (Docker)
docker compose up postgres -d
docker compose down

# Aplicar migraciones canónicas (PowerShell o Git Bash)
alembic upgrade head

# Bootstrap fresh alternativo (PowerShell)
Get-Content migrations/init.sql | docker compose exec -T postgres psql -U ancora -d ancoramind

# Bootstrap fresh alternativo (Git Bash)
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations/init.sql

# Instalar dependencias
pip install -e ".[dev]"

# Lint (gate global — también en CI)
ruff check src/ tests/ scripts/ migrations/

# Type checking (gate global en CI desde specs/020)
mypy src/
```

---

## 6. Modelo de datos (schema `ancora`)

| Tabla | Propósito | Notas |
|---|---|---|
| `notes` | Memoria canónica de notas | user_id, content |
| `documents` | Registro de documentos | storage_key → local/Supabase Storage, provenance |
| `ai_extractions` | Resultados IA (JSONB) | provider, model, prompt_version, confidence |
| `vehicles` | Vehículos del usuario | make, model, nickname, registration |
| `vehicle_maintenance` | Historial de mantenimiento | FK vehicle, FK source_document |
| `reminders` | Recordatorios | trigger_at, status, provenance |
| `calendar_events` | Eventos canónicos | provider_event_id (NoopCalendarProvider) |
| `action_proposals` | Gobernanza WRITE | pending_confirmation → confirmed → executed |
| `todo_lists` | Listas TODO canónicas | user_id, name, timestamps |
| `todo_items` | Tareas de una lista TODO | FK list ON DELETE CASCADE, status, prioridad, due_date, position |

**Tres tipos de memoria:** runtime/conversacional (Agno DB) ≠ soft personal
(auxiliar) ≠ **canónica (schema `ancora` — fuente de verdad, siempre gana)**.

---

## 7. Gobernanza (resumen)

- Clasificación de riesgo: `READ` < `WRITE` < `EXTERNAL_ACTION` < `DESTRUCTIVE`
- READ → directa. WRITE/EXTERNAL_ACTION/DESTRUCTIVE → ActionProposal + confirmación humana.
  No hay excepciones por reversibilidad: las mutaciones TODO de listas **e ítems**
  usan `propose_*` → confirmación → `execute_*`.
- Auditoría: action_proposals registra confirm/execute timestamps + provenance
  (`source_document_id`)
- Comandos de bot (`/new`, `/help`): control determinista, sin propuesta — no
  escriben datos canónicos ni llaman a proveedores. `/new` sólo abre una nueva
  generación de conversación, registrada en el ledger de interacciones.
- Detalle completo: `docs/governance.md`

---

## 8. Estado y roadmap

| Milestone | Estado |
|---|---|
| M1 Agent Runtime (Telegram+Agno+session) | ✅ |
| M2 Canonical Memory (notes) | ✅ |
| M3 Document Memory (storage+extraction) | ✅ |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ (worker outbound con FastAPI lifespan) |
| BL-21 Listas TODO multi-lista | ✅ (toda mutación gobernada) |
| BL-8 Evals agentic | 🔶 36 casos sintéticos, runner estático, harness aislado del Agent y harness Core de consentimiento; pendiente ejecución LLM real (T7) y scoring semántico (T8) — specs/014 + 018 |
| BL-18 Railway como sustituto de ngrok | 🔶 Servicio/dominio/webhook/healthcheck reales validados; pendiente Wait for CI + E2E M3–M5 (specs/008) |
| BL-25 Script E2E nativo PowerShell | ✅ `run-e2e.ps1` local/remoto con `.env` seguro (specs/015) |
| BL-23 Governed LLM Access + Telegram admission + OTel | 🔶 T2–T14 implementados; T14 fase 6 (cambio de modelo en caliente) validado en Railway (2026-09-19); pendientes: rollout Collector/Grafana, E2E completo y rotaciones (specs/013) |
| BL-33 Health signals + dashboard de salud | 🔶 Collector/Grafana base desplegados y sin nuevos 429; pendientes dashboard/alertas y matriz de degradación T7 (specs/016) |
| MVP usable | 🔶 E2E parcialmente validado (M1-M2 probado en Telegram; M3-M5 pendiente) |

**Backlog:** la lista viva y priorizada de pendientes está en `BACKLOG.md`
(fuente única de verdad). La prioridad P0 es BL-23/specs/013; después siguen
E2E de M3–M5, despliegue Railway (specs/008), OCR real, proveedor de calendario
real y evals agentic.

**Fuera de alcance (explícitamente "not yet"):** GraphRAG, vector search,
multi-agent, WhatsApp, web frontend, microservices, event sourcing.

---

## 9. Decisiones arquitectónicas clave

- **ADR-001:** Agno + AgentOS como runtime. Alternativas (Pydantic AI, LangGraph,
  custom loop) evaluadas y descartadas para el POC. No re-abrir el debate sin
  autorización. Si Agno bloquea un requisito: documentar → demostrar → proponer
  alternativas → pedir decisión.
- **ADR-004:** admission Telegram propiedad de AncoraMind, idempotencia durable
  y semántica at-most-once del Agent.
- **ADR-005:** `LLMAccess`, configuración runtime versionada y LiteLLM Proxy
  privado/fail-closed con OpenRouter upstream.
- **ADR-006:** OpenTelemetry + Collector privado + Grafana Cloud; telemetría de
  producto Agno desactivada al activar el pipeline propio.
- **n8n:** no consultar, migrar ni traducir (implementación anterior). Solo
  requisitos funcionales y aprendizajes de seguridad.

---

## 10. Al hacer cambios

**Gate de despliegue manual (decisión del propietario, 2026-10-11):** mantener
Wait for CI desactivado. Revisar checks del mismo SHA antes de desplegar y
registrar SHA/deployment/resultados; no reactivar la opción automáticamente.

1. **Añadir capability nueva** = models + repository + service + tool +
   registro en `_init_domain_tools()` (main.py) + tests + skill prompt si aplica.
   Seguir el patrón de `notes` (la más sencilla y completa).
   **Guía detallada paso a paso: `docs/adding-tools.md`.**
2. **Operación WRITE/EXTERNAL_ACTION/DESTRUCTIVE** → siempre par `propose_*` /
   `execute_*` con ActionProposal. La propuesta no escribe datos canónicos; el
   executor confirma, revalida autorización/propiedad, ejecuta y audita.
3. **Tests:** los unit tests mockean repositorios (`AsyncMock(spec=Repo)`).
   Ejecutar `pytest tests/unit/` antes de dar nada por terminado.
4. **Cambiar prompts/models/tool descriptions** = cambio evaluable (gobernanza).
   Anotarlo en el commit.
5. **Migraciones:** Alembic es la historia canónica desde BL-12/specs/013.
   Añadir una revisión en `migrations/versions/` y mantener `migrations/init.sql`
   equivalente a `head` para bootstrap fresh. Probar fresh install, upgrade sobre
   datos y downgrade de la última revisión.
6. **Jerarquía de docs:** si algo contradice entre documentos, este fichero y
   `docs/architecture.md` mandan sobre el resto.
7. **Cambios de inferencia/config/telemetry:** seguir specs/013. No añadir retries,
   fallbacks, providers directos, captura de contenido o bypass del Gateway sin
   actualizar la policy y sus acceptance tests.
8. **Cambiar el modelo físico:** publicar un alias versionado nuevo con
   `scripts/litellm_gateway_alias.py` (`publish` → `grant` → `verify`) y activar
   una revisión runtime que apunte a él. Nunca editar ni retirar un alias en uso;
   nunca escribir settings del Gateway por API/UI (ADR-005 enmendado).

---

## 11. Estilo de comunicación

Preferencia del propietario sobre cómo se comunican los agentes en este repositorio:

- **Respuestas moderadas de longitud.** Explicar qué se hizo y el resultado de la
  verificación, pero sin narrar cada paso ni pegar código ya editado en la respuesta.
- Ni exhaustivas ni telegráficas: un resumen claro de cambios + cualquier
  decisión/limitación relevante. El propietario pedirá más detalle si lo necesita.
- Estructura preferida: qué cambió → cómo se validó → puntos que requieren
  atención. Sin relleno ni secciones ceremoniales.
