# Verification: 013 — Governed LLM Access and Telegram Admission

> **Estado:** 🔶 T2–T13 implementados y validados localmente; el rollout
> Railway de LiteLLM privado y admission/processor Telegram está validado el
> 16 de septiembre de 2026. Collector/Grafana, dashboards/alertas, benchmark
> con clave real, pruebas E2E negativas/duplicados y rotación real siguen
> pendientes. **BL-23 permanece abierto.**
> **Diseño aprobado:** 2026-09-13 · **Hardening local T13:** 2026-09-14

---

## Environment

| Campo | Valor |
|---|---|
| Commit desplegado | `086f1fa2d7fec7bea14d059f024d5581593f4af4` (`fix(ledger): type nullable cost parameters`) |
| Python | 3.12.10 |
| Agno | Baseline: 2.9.0 |
| LiteLLM | `v1.100.1` fijado por digest `a3715fa7…c62bf` |
| PostgreSQL | Supabase canónico `ancoramind_project` + PostgreSQL privado del Gateway Railway |
| Railway environment | `ancoramind-app` / `production` / `europe-west4-drams3a` |
| Grafana Cloud region | Pendiente |

## Automated checks

| Check | Resultado | Evidencia |
|---|---|---|
| Unit tests | ✅ T12 | 352 passed; admission, config, LLMAccess, budget, extraction port, privacidad OTel, modo Gateway y gobernanza de coste cubiertos |
| Integration tests | ✅ T12 | 52 passed; ledger, admission, processor, runtime config, usage/coste y agregación de spend por día/mes/ruta |
| Ruff | ✅ T4 | `ruff check src/ tests/ scripts/ migrations/` |
| mypy del alcance T2 | ✅ | 4 ficheros nuevos sin issues |
| mypy del alcance T3 | ✅ | domain, repository, config y tests nuevos sin issues |
| mypy del alcance T4 | ✅ | admission HTTP, wiring, repository, config y tests sin issues |
| Migration fresh install | ✅ | `0001` → `0002` sobre BD temporal vacía |
| Migration upgrade over existing data | ✅ | Schema sin versionar adoptado; nota semilla preservada |
| Migration downgrade | ✅ | `downgrade -1` conserva baseline/datos y retira specs/013 |
| Privacy tests | ✅ T10 | Allowlist, logs JSON sin mensaje/args, no IDs en metric labels y Collector redactado |
| Hardening T13 (load/crash/retención) | ✅ T13 local | `tests/integration/test_hardening_013.py`: 7 passed (duplicados, burst ordenado, crash agent/delivery, recovery response_ready, purga, orden estable) |
| LiteLLM latency benchmark | ⏳ | Gateway real desplegado; pendiente comparar p50/p95/p99 y TTFT con OpenRouter directo usando una clave real |
| Load/concurrency tests | ✅ T13 local | Ver fila anterior; E2E Railway pendiente |
| Crash-injection tests | ✅ T13 local | Ver fila anterior; reinicios/deploys reales pendientes |

## Acceptance matrix

| ID | Escenario | Resultado | Evidencia |
|---|---|---|---|
| A | Mismo update concurrente varias veces → una interaction y un Agent run | 🔶 E2E parcial | Un update real recorrió admission → claim → Agent → outbox → Telegram una vez; la concurrencia/duplicados reales siguen pendientes |
| B | Railway request IDs distintos + mismo update → duplicate delivery | ✅ T3 | Dos IDs Railway → dos deliveries, segunda `duplicate=true`, mismo `correlation_id` |
| C | Cambio runtime → siguiente run usa nueva revisión sin redeploy | ✅ T6 local | Manager cachea snapshot y CAS actualiza futuros runs; E2E Railway pendiente |
| D | Config inválida → last-known-good/bootstrap permanece | ✅ T6 | Payload inválido/secret-like crea 422 sin revisión ni cambio activo |
| E | Primary falla → no se supera attempt budget | ✅ T12 local | Retries Gateway/LiteLLM a 0 verificados con el Gateway real; num_retries=0 sin fallbacks; el budget ya valida 2 attempts/call como techo para su evolución |
| F | Circuit open → cero llamadas al upstream afectado | ✅ T12 local | Con `allowed_fails:2`/`cooldown_time:10` y upstream muerto: 3 fallos abrieron el circuit; 429 `No deployments available` fast-fail sin llamadas al upstream; tras cooldown el probe volvió al upstream (HALF_OPEN→CLOSED) |
| G | Rate/budget agotado → no hay inferencia adicional | ✅ T8 local | Model/Gateway/coste bloquean antes del provider; timeout cancela el run; processor registra el límite sin replay |
| H | Tool loop → fingerprint/budget lo detiene | ✅ T8 local | HMAC canónico + hook async; Agno `StopAgentRun` corta la repetición sin una tercera inferencia |
| I | Interacción completa trazable por `correlation_id` | ✅ T10 local | Spans/logs metadata-only para admission, queue, Agent, LLM, tools y delivery; IDs excluidos de labels de métricas |
| J | Crash antes de `agent_started` → recuperable | ✅ T5 | `accepted` se lista y reclama ordenadamente |
| K | Crash después de `agent_started` → `failed_ambiguous`, sin replay | ✅ T5 | Recovery marca `restart_after_agent_started`; runner no vuelve a llamarse |
| L | Crash tras `response_ready` → delivery recuperable | ✅ T5 | Recovery conserva `response_ready` y entrega outbox existente |
| M | Crash durante delivery → no reenvío automático ambiguo | ✅ T5 | Recovery marca `restart_during_delivery`, sin `sendMessage` adicional |
| N | Grupo/canal Telegram → no alcanza el Agent | ✅ T4 | `non_private_chat`, `200`, sin payload ni llamada Agno |
| O | Usuario no allowlisted → no alcanza el Agent | ✅ T4 | `user_not_allowlisted`, `200`, sin payload ni llamada Agno |
| P | Extracción documental comparte config, budget y trace | ✅ T9 local | Port + adaptador `LLMAccess`; el run gobernado ve `model_calls`/`gateway_requests` crecer con la extracción |
| Q | Gateway caído → fail closed sin OpenRouter directo | ✅ local + Railway wiring | `LITELLM_PROXY_ENABLED=true` con URL privada y virtual key; la app arranca sólo con ambos secrets y el update real atravesó LiteLLM privado. La caída real del Gateway sigue pendiente como prueba controlada |
| R | Collector caído → aplicación continúa | ✅ T10 local | Setup/export/shutdown OTel fail-open; test simula fallo de exporter y el Collector config valida con endpoint dummy |
| S | Logs/traces no contienen contenido personal | ✅ T10 local | Allowlist, JSON sin mensaje/args, redacción Collector y privacy tests bloquean prompts/mensajes/respuestas/args/results |
| T | Activaciones concurrentes → compare-and-swap evita pisadas | ✅ T6 | Dos activaciones con mismo expected solo completan una; segunda 409 |
| U | Run activo durante cambio → conserva revisión anterior | ✅ T6 | Snapshots futuros por run y publish no muta snapshot hasta CAS correcto |
| V | Duplicate delivery → no consume rate limit | ✅ T4 | Duplicate se detecta antes del contador durable y conserva correlation ID |
| W | Rate limit superado → `2xx` y cero inferencias | ✅ T4 | burst/min/hora/cola ⇒ `rejected`, `200`, sin Agent |
| X | Tool call 12 → permitida si queda budget | ✅ T7 base | Factory per-run recibe hard ceiling 12 desde snapshot |
| Y | Tool call 13 → rechazada por hard ceiling | ✅ T7 base | Agent `tool_call_limit=12`; tool hooks/budget detallado llega en T8 |

## Production validation

- [x] Webhook estable conserva `/telegram/webhook`: admission propia respondió
  `200` el 16 de septiembre de 2026 sin cambiar la URL pública.
- [ ] Duplicate delivery real de Telegram no repite Agent/LLM.
- [ ] Cambio de ruta/modelo real sin deployment mediante la API admin/CAS.
- [x] LiteLLM privado y sin superficie de administración pública: servicio
  `LiteLLM` en `europe-west4-drams3a`, sin dominio ni TCP proxy; aliases
  `ancoramind-default-r1`, `ancoramind-fast-r1` y `ancoramind-vision-r1`
  confirmados al arrancar.
- [x] Gateway privado usado por un update real: LiteLLM registró
  `POST /v1/chat/completions → 200`; el usage durable registró
  `provider=litellm`, `effective_gateway_route=ancoramind-default-r1`,
  `retry_count=0` y `fallback_used=false`.
- [ ] Fail-closed de Gateway validado mediante caída controlada en Railway.
- [ ] Collector/Grafana fail-open validado.
- [ ] Circuit open y cooldown validados en Railway.
- [ ] Coste real reconciliado con OpenRouter.
- [x] Búsqueda por `correlation_id` reconstruye un flujo real sin contenido:
  `c76dd55a-54cd-41f4-96d2-29e2ac5d226c` tuvo una delivery HTTP, un Agent
  run, un usage event LiteLLM, outbox cifrada y un chunk Telegram completado.
- [ ] No se detecta contenido sensible en Grafana o logs Railway.

## Railway rollout evidence (2026-09-16)

- El schema canónico Supabase `ancoramind_project` fue adoptado y migrado a
  `ancora.alembic_version = 0003_telegram_admission_indexes`. Las tablas del
  ledger, runtime config, outbox y usage existen; ambos índices de admission
  existen. Los datos previos se conservaron (2 notas, 1 vehículo y 1 propuesta).
- `ancoramind-app` ejecuta el commit `086f1fa2d7fec7bea14d059f024d5581593f4af4`.
  GitHub Actions del mismo commit finalizó correctamente, incluidos unit e
  integration tests PostgreSQL Docker.
- Gateway: LiteLLM `v1.100.1` fijado por digest, Postgres y Redis están
  co-localizados con AncoraMind en `europe-west4-drams3a`. LiteLLM no tiene
  dominio público ni TCP proxy. La virtual key exclusiva está en Railway como
  secreto y no se registra en Git ni en esta evidencia.
- T4 admission se validó con una interacción real `accepted`: payload cifrado
  (Fernet key version 1), fingerprint presente, delivery HTTP `200` y cero
  model/Gateway/tools/outbox mientras el processor estaba desactivado.
- T5 processor se validó con un update real posterior: la interacción
  `c76dd55a-54cd-41f4-96d2-29e2ac5d226c` siguió
  `accepted → agent_started → response_ready → delivery_started → completed`.
  Persistió una respuesta lógica cifrada de un chunk, recibió Telegram message
  ID y registró exactamente un `llm_usage_events` y un resumen de interacción
  con `config_revision=1`, `model_call_count=1` y
  `gateway_request_count=1`.
- El primer update T5 anterior al fix de ledger conserva contadores agregados a
  cero; no se reescribió retrospectivamente para preservar la auditoría. El
  fix posterior sincroniza usage y summary en una transacción y está cubierto
  por integración PostgreSQL en CI.

## T2 — Migration strategy verification (2026-09-13)

- Alembic 1.19.1 configurado con version table `ancora.alembic_version`.
- `0001_ancora_baseline` crea/adopta idempotentemente las 10 tablas pre-specs/013.
- `0002_llm_governance` añade 8 tablas y tres columnas/indexes/constraint sobre
  `action_proposals` sin modificar filas existentes.
- `0003_telegram_admission_indexes` añade índices parciales para ventanas de
  usuario y capacidad `accepted`; `head` se mantiene equivalente a `init.sql`.
- `migrations/init.sql` puede ejecutarse dos veces y después adoptar `head` sin
  pérdida de datos.
- Los tests crean y eliminan bases `ancoramind_migration_<uuid>`; no tocan la BD
  de desarrollo, Supabase ni Railway.
- La imagen Docker incluye `alembic.ini` y `migrations/`; CI/lint cubren los
  scripts de migración.

## T3 — Interaction ledger verification (2026-09-13)

- `TelegramInteractionsRepository.admit()` inserta de forma atómica una
  interacción por `UNIQUE(bot_id, telegram_update_id)` y registra **cada** HTTP
  delivery en `telegram_deliveries` dentro del mismo commit.
- El UUID de `telegram_interactions.id` es el `correlation_id` estable: todos los
  duplicados apuntan a la misma interacción.
- `claim_agent_start()` usa `UPDATE ... WHERE status = 'accepted' RETURNING`;
  veinte claims concurrentes devuelven exactamente un ganador.
- `TelegramPayloadCipher` cifra el JSON normalizado mediante Fernet y conserva
  un fingerprint HMAC SHA-256 no reversible. Sin
  `TELEGRAM_PAYLOAD_ENCRYPTION_KEY` falla cerrado: no hay persistencia en claro.
- Estados terminales normales borran ciphertext/key version inmediatamente;
  `failed_ambiguous` conserva como máximo siete días y
  `purge_expired_payloads()` elimina después solo el payload, no la metadata.

## T4 — Telegram admission endpoint verification (2026-09-13)

- Con `TELEGRAM_ADMISSION_ENABLED=true`, `main.py` entrega un `base_app` a
  AgentOS y usa `on_route_conflict="preserve_base_app"`; AncoraMind es dueño de
  `POST /telegram/webhook` sin cambiar la URL pública.
- El endpoint valida `X-Telegram-Bot-Api-Secret-Token` con comparación constante;
  secret inválido devuelve `403` sin abrir sesión. JSON/update_id inválido devuelve
  `400`, y un fallo previo al commit durable devuelve `503`.
- Admission activado falla al arrancar si faltan DB, bot ID, secret Telegram,
  clave Fernet o allowlist no vacía. Este modo es fail-closed.
- Private chat y allowlist se evalúan antes de cifrar/persistir payload. Grupos,
  canales, usuarios no autorizados y updates no soportados reciben `200` con
  interaction `rejected`/`ignored`, sin inferencia.
- Las ventanas y capacidades durables usan PostgreSQL bajo advisory lock:
  burst 5/10 s, 10/minuto, 120/hora, 20 `accepted` globales y 5 por chat.
  Duplicados se resuelven antes de esos contadores y no consumen cuota.
- T4 no reclama ni ejecuta el Agent: T5 debe consumir `accepted` con el claim
  atómico y crear la respuesta lógica/outbox.

## T5 — Processor, state machine and response outbox verification (2026-09-13)

- `InteractionProcessor` procesa `accepted` y `response_ready` ordenados por
  chat/fecha/update, con lock por chat, lock por usuario y semáforo global 2.
- El claim `accepted → agent_started` registra `agno_run_id` y
  `agno_session_id` antes de invocar el runner. Una excepción posterior se marca
  `failed_ambiguous`; no se reintenta el Agent.
- La salida final se cifra y persiste en `logical_responses`; después crea filas
  `pending` por chunk antes de marcar `delivery_started` y llamar `sendMessage`.
  La respuesta lógica cifrada se conserva como auditoría durable y no se exporta
  a telemetry.
- Cada chunk pasa por `pending → sending → completed`; 4xx de Telegram es
  `failed_definitive`, fallo de transporte/respuesta incierta es
  `failed_ambiguous`, y ninguno se reenvía automáticamente.
- Al arrancar, `agent_started` y `delivery_started` se convierten a
  `failed_ambiguous`; `accepted` y `response_ready` continúan de forma segura.
- El streaming visible está desactivado. Durante un run se refresca
  `sendChatAction(typing)` sin contenido.
- `TELEGRAM_PROCESSOR_ENABLED=false` por defecto. T7 sustituyó el adaptador
  temporal por `GovernedInteractionRunner`, `LLMAccess` y un Agent por run.

## T6 — RuntimeConfigManager and admin API verification (2026-09-14)

- `RuntimeConfiguration` usa schemas Pydantic cerrados con `extra="forbid"` en
  routing, budgets, concurrencia, admission, gateway y observabilidad.
- Checksum SHA-256 canónico y estable; `validate_runtime_config()` bloquea claves
  sensibles sin persistirlas.
- `RuntimeConfigManager` mantiene snapshot in-memory last-known-good: bootstrap
  secret-free sin I/O, y revisión activa tras `initialize()`.
- CAS atómico con auditoría append-only; rollback usa la misma ruta con motivo
  prefijado.
- Admin API con Bearer obligatorio, actor obligatorio, sin CORS y sin tools LLM.
- Invalidación multi-proceso queda explícitamente pendiente: swap directo con
  una réplica y `LISTEN/NOTIFY` en incremento posterior.

## T7 — Governed LLM Access and per-run Agent verification (2026-09-14)

- `ExecutionContext` se propaga mediante `ContextVar`; un `GovernedModel`
  llamado sin contexto falla cerrado antes de alcanzar el provider.
- `GovernedInteractionRunner` captura un `RuntimeConfigSnapshot` una vez por
  run, crea `ExecutionBudget`, propaga `correlation_id`, `traceparent`, revisión
  y `run_id` explícito mediante `RunContext.metadata`.
- `GovernedAgentFactory` crea un Agent por run con ID lógico estable
  `ancoramind-governed`, `tool_call_limit` del snapshot y retries explícitos a
  cero. Cambios de runtime posteriores afectan únicamente a nuevos runs.
- `AgnoLLMAccess` resuelve la ruta lógica del snapshot y compone el mixin
  gobernado sobre la clase física existente, preservando `SafeOpenRouter`.
  El provider directo era la excepción transitoria hasta T11; con
  `LITELLM_PROXY_ENABLED=true` (modo Gateway implementado en T11) la frontera
  compone únicamente `OpenAILike` hacia el LiteLLM privado y no conoce
  secretos del provider.
- Cada model turn gobernado genera `llm_call_id`, registra revisión, rutas,
  provider/model, tokens, latencia, TTFT y `error_class` en
  `ancora.llm_usage_events`. Una caída de auditoría es fail-open y no expone
  contenido personal.
- El webhook legado AgentOS y la creación directa de Agent en documentos siguen
  siendo excepciones transitorias: el primero hasta activar T4/T5 y el segundo
  hasta T9. No se consideran evidencia de cobertura universal de LLMAccess.

## T8 — Execution Budget verification (2026-09-14)

- `ExecutionBudget` aplica deadline total, 6 model calls, 8 Gateway requests,
  12 tools y dos attempts Gateway por llamada lógica. Los retries/fallbacks de
  Gateway permanecen en cero hasta T11/T12, pero su techo ya se valida.
- `GovernedInteractionRunner` usa `asyncio.wait_for` con el tiempo restante del
  budget; el timeout se convierte en `ExecutionBudgetExceededError`.
- El processor registra una violación como `failed_ambiguous` con el límite
  concreto (`error_detail_code`) y nunca reejecuta un Agent que pudo invocar
  tools con efectos.
- `GovernedAgentFactory` instala un hook async de Agno. El hook calcula HMAC de
  nombre + JSON canónico de argumentos con una clave Railway/derivada; no guarda
  ni exporta argumentos. La repetición tras éxito se bloquea y un fallo solo
  admite un segundo intento.
- En Agno 2.9.0 `StopAgentRun` se importa de `agno.exceptions`. La prueba real
  con `Agent.arun()` confirma que el hook async se espera para una tool async y
  que una tool repetida termina el loop sin una tercera model call.
- Pricing opcional versionado por alias Gateway estima el coste antes de llamar
  y reconcilia coste basado en tokens tras la respuesta; `llm_usage_events`
  persiste estimado, actual y fuente sin contenido personal.

## T9 — Document extraction port verification (2026-09-14)

- `DocumentExtractionPort` y `DocumentExtractionOutcome` viven en
  `src/domain/documents/extraction.py` sin ninguna dependencia de Agno; un test
  de regresión inspecciona el fuente de `DocumentService` y falla si reaparece
  un import del runtime o un silenciamiento de excepciones.
- `DocumentService` ya no construye `agno.agent.Agent`: solicita la extracción
  al port y persiste en `ai_extractions` el provider/model reales devueltos por
  la inferencia (no constantes del servicio).
- El adaptador `AgnoDocumentExtractionAdapter` resuelve el modelo por
  `LLMAccess`. Dentro de un run gobernado reutiliza el `ExecutionContext` del
  run: mismo snapshot, deadline, contadores model/Gateway, coste y trace; el
  test con un `GovernedModel` real demuestra que la extracción consume
  `model_calls`/`gateway_requests` del run (acceptance P).
- Fuera de un run gobernado (webhook AgentOS legado) el adaptador crea un
  contexto bootstrap standalone con budget propio por la misma frontera
  `LLMAccess`, fail-closed si no hay frontera standalone configurada; no escribe
  `llm_usage_events` porque `interaction_id` tiene FK a `telegram_interactions`
  y no existe interacción que referenciar.
- Los fallos de inferencia dejan metadata observable y acotada
  (`error_class`, provider, model, document_id) sin contenido del documento ni
  prompt; Agno absorbe errores de modelo en `RunOutput(status=error)` y el
  adaptador los mapea a `AgentRunError` sin exponer el texto de la excepción.
- El consumo del prompt de extracción (versión 1.0) y sus instrucciones no
  cambió respecto a la implementación pre-T9.

## T11 — LiteLLM Proxy pilot verification (2026-09-14)

- Modo Gateway implementado sin bypass: con `LITELLM_PROXY_ENABLED=true`,
  `Settings` falla cerrado si falta `LITELLM_PROXY_BASE_URL` o
  `LITELLM_PROXY_VIRTUAL_KEY`. `AgnoLLMAccess.model_for` y el AgentOS legado
  componen únicamente `OpenAILike` hacia el `/v1` privado del Gateway, usando
  el alias versionado del snapshot (`ancoramind-*-rN`) como `model` y la
  virtual key como credencial. Los tests cubren alias/URL/key/label/traceparent
  y que ni el model ni el key del provider directo se usan en ese modo.
- `gateway/litellm-config.yaml` no contiene secretos (todo vía `os.environ/...`)
  y expone exactamente los tres aliases del bootstrap del runtime config.
  `gateway/Dockerfile` fija la imagen por digest
  (`ghcr.io/berriai/litellm@sha256:a3715fa7…c62bf`) y fuerza
  `NO_DOCS`/`NO_REDOC`/`NO_OPENAPI`; el `CMD` no repite el entrypoint `litellm`.
- Validación local reproducible (`gateway/docker-compose.litellm.yml`:
  PostgreSQL 16 aislado + LiteLLM): readiness 200; `/docs`, `/redoc` y
  `/openapi.json` devuelven 404; `/v1/models` lista sólo los tres aliases;
  `/key/generate` crea una virtual key restringida a esos aliases.
- Fail-closed verificado con el Gateway real y una OPENROUTER_API_KEY dummy:
  virtual key inválida ⇒ 401 `token_not_found_in_db` del propio LiteLLM;
  virtual key válida ⇒ 401 desde OpenRouter con
  `Received Model Group=ancoramind-default-r1`, demostrando enrutado por el
  Gateway y ausencia de bypass directo. LiteLLM informa
  `Available Model Group Fallbacks=None` (retries/fallbacks en 0).
- `scripts/litellm_create_virtual_key.py` crea la key exclusiva
  AncoraMind/environment contra un proxy healthy; la key se imprime una sola
  vez y se guarda como secreto Railway `LITELLM_PROXY_VIRTUAL_KEY`, nunca en
  Git ni en revisiones runtime.
- Pendiente de rollout Railway explícito: PostgreSQL dedicado del Gateway,
  servicio LiteLLM privado, benchmark p50/p95/p99+TTFT con clave real y
  revisión de superficies productivas. El estado actual de Railway
  (`ancoramind-app` con deployment `NEEDS_APPROVAL` desde 2026-09-12) se
  inspectó en modo lectura y no se crearon recursos de pago.

## T10 — OpenTelemetry and privacy verification (2026-09-14)

- `AGNO_TELEMETRY=false` se fija antes de importar Agno en `src.main` y en la
  imagen Docker. Los tres constructores de `Agent`, y `AgentOS`, reciben
  `telemetry=False`; AgentOS también recibe `tracing=False` para no activar su
  pipeline propio. Tests de factory/wiring lo comprueban explícitamente.
- `src/observability/telemetry.py` es la única fachada de telemetría: acepta
  exclusivamente una allowlist de metadata técnica. `correlation_id`, IDs Agno,
  Telegram y Railway pueden ser atributos de spans/logs, pero se eliminan de las
  etiquetas de métricas para evitar cardinalidad no acotada.
- Los logs se serializan como JSON metadata-only: no llaman a `getMessage()` ni
  serializan `record.msg` o argumentos posicionales. Así, incluso un f-string o
  una excepción con datos del provider no salen por este formatter.
- Spans y métricas cubren webhook/admission, espera de cola, Agent run, modelo,
  tools, límites de budget y envío Telegram. Modelo/tools exportan sólo rutas,
  provider/model, tokens, coste, latencia, status y error class; nunca prompts,
  mensajes, respuestas, documentos ni argumentos/resultados.
- `traceparent` W3C generado por el run se propaga como header hacia el
  Gateway/provider transitorio; no se depende de la telemetría de Agno para esa
  correlación.
- El SDK crea exporter OTLP gRPC sólo si `OTEL_EXPORTER_OTLP_ENDPOINT` existe.
  Configuración, exportación y shutdown son fail-open; un test fuerza un fallo
  de exporter y confirma que el objeto de telemetría queda utilizable.
- `observability/otel-collector.yaml` está validado contra
  `otel/opentelemetry-collector-contrib:0.138.0` con endpoint/credencial dummy.
  Incluye `memory_limiter`, borrado defensivo de claves de contenido, `batch` y
  cola/retry acotados antes de Grafana. No se desplegó un Collector Railway ni
  se contactó Grafana Cloud: eso exige secrets y rollout explícito.
- Los privacy tests prueban allowlist, exclusión de IDs de labels de métricas,
  logs sin texto/args y que el context manager OTel no altera las excepciones de
  negocio instrumentadas.

## Limitations and remaining evidence

- La causa exacta de las ~78 inferencias no se marcará como confirmada sin logs
  de Railway, sesión/run Agno y actividad detallada de OpenRouter del incidente.
- La garantía at-most-once cubre la ejecución del Agent y la persistencia lógica;
  Telegram `sendMessage` no ofrece exactly-once externo.
- Completar esta sección al cerrar la spec con cualquier limitación residual.

## T13 — Hardening, runbooks and closure verification (2026-09-14)

- **Suite local nueva**: `tests/integration/test_hardening_013.py` (7 tests,
  PostgreSQL Docker real, sin servicios externos):
  - 20 deliveries concurrentes del mismo `update_id` → 1 interaction, 20
    deliveries, claim único (A/B bajo carga).
  - Burst de 5 updates distintos en el mismo chat → 5 runs ordenados,
    exactamente-once, 5 deliveries.
  - Crash tras `agent_started` → `recover_once` marca `failed_ambiguous`
    (`restart_after_agent_started`); `run_once` posterior no ejecuta el
    Agent ni envía nada (J/K).
  - Crash tras `delivery_started` → `failed_ambiguous`, sin reenvío (M).
  - Restart con `response_ready` pendiente → delivery sin rerun del Agent,
    estado final `completed` (L).
  - `failed_ambiguous` + 8 días → `purge_expired_payloads` borra
    ciphertext/version y conserva fingerprint + metadata.
  - `list_recoverable_work` estable entre ciclos (mismo orden por consulta;
    el orden primario es `(chat_id, received_at, update_id)`).
- **Hallazgo documentado**: filas admitidas en el mismo milisegundo no
  garantizan orden por `update_id` (el `ORDER BY` usa `received_at` primero);
  el contrato exigible es estabilidad + exactamente-once por chat, no
  ordenación causal por `update_id`.
- **Runbooks**: `docs/runbooks-013.md` (§0 mapa síntoma→runbook, §1 Gateway
  down, §2 circuit open, §3 budget, §4 ambiguous, §5 matriz crash local,
  §6 Collector, §7 rollback CAS, §8 checklist rollout + rotación).
- **No cierra BL-23**: pendientes E2E Railway, rotación real de secretos,
  Grafana/dashboards, benchmark con clave real y `verification.md` con
  evidencia real (ver `docs/runbooks-013.md` §8).
## T12 — Reliability and cost governance verification (2026-09-14)

- **Circuit breaker (CLOSED/OPEN/HALF_OPEN)**: `gateway/litellm-config.yaml`
  declara `router_settings.allowed_fails: 3` y `cooldown_time: 60` (igual al
  runtime config `gateway.cooldown_seconds`). Validado localmente con un
  contenedor LiteLLM DB-less y un upstream muerto (`circuit-test-r1`):
  - 3 llamadas consecutivas ⇒ `code=500` `upstream_connection_error`
    (CLOSED, intentos reales al upstream).
  - 4ª/5ª llamada ⇒ `code=429` `NO_DEPLOYMENTS` (OPEN, fast-fail **sin
    ninguna llamada al upstream**).
  - Tras 12 s (> `cooldown_time=10`) ⇒ 6ª llamada ⇒ `code=500`
    `upstream_connection_error` (HALF_OPEN ⇒ CLOSED, probe al upstream).
  Esto demuestra que el Gateway impide llamadas al upstream afectado mientras
  el circuit está abierto y respeta la transición automática.

- **Rate limits por virtual key/ruta**: `model_info.rpm/tpm` por alias en el
  config canónico; el script `scripts/litellm_create_virtual_key.py` crea la
  key con `rpm_limit`/`tpm_limit`/`max_parallel_requests` (defaults 60/250000/4).
  Enforcement verificado localmente: key con `rpm_limit=2` ⇒ 3ª petición
  `429` en <50 ms **sin tocar el upstream**.

- **Spend logs y cost governance**: `ancora.llm_usage_events` persiste coste
  estimado/real por llamada (sin contenido). `LlmUsageRepository.summarize_spend`
  agrega por día/mes/ruta (coste real con precedencia sobre el estimado).
  `CostGovernanceConfig` en el runtime config declara `external_hard_limit_usd`,
  umbrales 60/80/90%, `daily_budget_usd`, `monthly_budget_usd` y
  `route_monthly_budgets_usd`. Invariante: rutas de pago exigen `pricing` +
  `cost_governance` + `max_estimated_cost_usd` (validación en
  `RuntimeConfiguration.validate_runtime_limits`).

- **Evaluación al inicio del run**: `GovernedInteractionRunner.run` llama a
  `evaluate_cost_governance(config, spend_summary)` **antes** de crear el
  Agent o cualquier inferencia. Alertas metadata-only en contadores
  `ancora.cost_governance.alert` (60%/80% del límite externo); hard stop
  `CostGovernanceError` mapeado a `failed_controlled` con `error_detail_code`
  (`external_monthly_hard_stop`, `daily_budget_exhausted`,
  `monthly_budget_exhausted`, `route_monthly_budget_exhausted`) — **nunca
  replay** y **cero inferencia**.

- **Hard limit externo (OpenRouter 100%)**: el hard stop interno al 90%
  preserva el 10% restante; opcionalmente la virtual key puede llevar
  `max_budget`+`budget_duration` como backstop en el Gateway. OpenRouter
  expone `GET /api/v1/key` con `limit`/`limit_remaining` y usage
  diario/semanal/mensual para reconciliación en el rollout.

- **Contabilidad de fallbacks internos (OpenRouter)**: investigación en la
  API reference de OpenRouter confirma que el response incluye `usage.cost`/
  `cost_details` del intento servido, un objeto de routing con `attempt` y el
  endpoint seleccionado; `usage` refleja **sólo el intento final** (fallbacks
  internos no suman tokens/coste duplicados). La verificación con clave real
  queda pendiente del rollout Railway.

- **Retry/fallback cross-model**: decisión explícita de mantener 0 por ahora.
  El attempt budget ya reserva 2 attempts por llamada lógica para esa
  evolución sin amplificar el volumen; requiere benchmark T11 con clave real
  y datos de fallos reales antes de habilitar.
