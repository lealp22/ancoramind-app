# Verification: 013 — Governed LLM Access and Telegram Admission

> **Estado:** ⏳ pendiente de implementación
> **Diseño aprobado:** 2026-09-13

---

## Environment

| Campo | Valor |
|---|---|
| Commit | Pendiente |
| Python | 3.12.10 |
| Agno | Baseline: 2.9.0 |
| LiteLLM | Pendiente |
| PostgreSQL | Docker `pgvector/pgvector:pg16` |
| Railway environment | Pendiente |
| Grafana Cloud region | Pendiente |

## Automated checks

| Check | Resultado | Evidencia |
|---|---|---|
| Unit tests | ✅ T9 | 315 passed; admission, config, LLMAccess, execution budget y extraction port cubiertos |
| Integration tests | ✅ T8 | 51 passed; ledger, admission, processor, runtime config, usage/coste y migraciones |
| Ruff | ✅ T4 | `ruff check src/ tests/ scripts/ migrations/` |
| mypy del alcance T2 | ✅ | 4 ficheros nuevos sin issues |
| mypy del alcance T3 | ✅ | domain, repository, config y tests nuevos sin issues |
| mypy del alcance T4 | ✅ | admission HTTP, wiring, repository, config y tests sin issues |
| Migration fresh install | ✅ | `0001` → `0002` sobre BD temporal vacía |
| Migration upgrade over existing data | ✅ | Schema sin versionar adoptado; nota semilla preservada |
| Migration downgrade | ✅ | `downgrade -1` conserva baseline/datos y retira specs/013 |
| Privacy tests | ⏳ | |
| LiteLLM latency benchmark | ⏳ | |
| Load/concurrency tests | ⏳ | |
| Crash-injection tests | ⏳ | |

## Acceptance matrix

| ID | Escenario | Resultado | Evidencia |
|---|---|---|---|
| A | Mismo update concurrente varias veces → una interaction y un Agent run | ✅ T5 local | Claim único + processor llama runner una vez; E2E Railway pendiente |
| B | Railway request IDs distintos + mismo update → duplicate delivery | ✅ T3 | Dos IDs Railway → dos deliveries, segunda `duplicate=true`, mismo `correlation_id` |
| C | Cambio runtime → siguiente run usa nueva revisión sin redeploy | ✅ T6 local | Manager cachea snapshot y CAS actualiza futuros runs; E2E Railway pendiente |
| D | Config inválida → last-known-good/bootstrap permanece | ✅ T6 | Payload inválido/secret-like crea 422 sin revisión ni cambio activo |
| E | Primary falla → no se supera attempt budget | ⏳ | |
| F | Circuit open → cero llamadas al upstream afectado | ⏳ | |
| G | Rate/budget agotado → no hay inferencia adicional | ✅ T8 local | Model/Gateway/coste bloquean antes del provider; timeout cancela el run; processor registra el límite sin replay |
| H | Tool loop → fingerprint/budget lo detiene | ✅ T8 local | HMAC canónico + hook async; Agno `StopAgentRun` corta la repetición sin una tercera inferencia |
| I | Interacción completa trazable por `correlation_id` | ⏳ | |
| J | Crash antes de `agent_started` → recuperable | ✅ T5 | `accepted` se lista y reclama ordenadamente |
| K | Crash después de `agent_started` → `failed_ambiguous`, sin replay | ✅ T5 | Recovery marca `restart_after_agent_started`; runner no vuelve a llamarse |
| L | Crash tras `response_ready` → delivery recuperable | ✅ T5 | Recovery conserva `response_ready` y entrega outbox existente |
| M | Crash durante delivery → no reenvío automático ambiguo | ✅ T5 | Recovery marca `restart_during_delivery`, sin `sendMessage` adicional |
| N | Grupo/canal Telegram → no alcanza el Agent | ✅ T4 | `non_private_chat`, `200`, sin payload ni llamada Agno |
| O | Usuario no allowlisted → no alcanza el Agent | ✅ T4 | `user_not_allowlisted`, `200`, sin payload ni llamada Agno |
| P | Extracción documental comparte config, budget y trace | ✅ T9 local | Port + adaptador `LLMAccess`; el run gobernado ve `model_calls`/`gateway_requests` crecer con la extracción |
| Q | Gateway caído → fail closed sin OpenRouter directo | 🔶 T7 parcial | Runs T5 usan LLMAccess; LiteLLM fail-closed llega en T11 |
| R | Collector caído → aplicación continúa | ⏳ | |
| S | Logs/traces no contienen contenido personal | ⏳ | |
| T | Activaciones concurrentes → compare-and-swap evita pisadas | ✅ T6 | Dos activaciones con mismo expected solo completan una; segunda 409 |
| U | Run activo durante cambio → conserva revisión anterior | ✅ T6 | Snapshots futuros por run y publish no muta snapshot hasta CAS correcto |
| V | Duplicate delivery → no consume rate limit | ✅ T4 | Duplicate se detecta antes del contador durable y conserva correlation ID |
| W | Rate limit superado → `2xx` y cero inferencias | ✅ T4 | burst/min/hora/cola ⇒ `rejected`, `200`, sin Agent |
| X | Tool call 12 → permitida si queda budget | ✅ T7 base | Factory per-run recibe hard ceiling 12 desde snapshot |
| Y | Tool call 13 → rechazada por hard ceiling | ✅ T7 base | Agent `tool_call_limit=12`; tool hooks/budget detallado llega en T8 |

## Production validation

- [ ] Webhook estable conserva `/telegram/webhook`.
- [ ] Duplicate delivery real de Telegram no repite Agent/LLM.
- [ ] Cambio de ruta/modelo real sin deployment.
- [ ] LiteLLM privado y sin superficie de administración pública.
- [ ] Fail-closed de Gateway validado.
- [ ] Collector/Grafana fail-open validado.
- [ ] Circuit open y cooldown validados.
- [ ] Coste real reconciliado con OpenRouter.
- [ ] Búsqueda por `correlation_id` reconstruye el flujo completo.
- [ ] No se detecta contenido sensible en Grafana o logs Railway.

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
  Mientras T11 no despliegue LiteLLM, el provider directo se permite solo dentro
  de esta frontera transitoria.
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

## Limitations and remaining evidence

- La causa exacta de las ~78 inferencias no se marcará como confirmada sin logs
  de Railway, sesión/run Agno y actividad detallada de OpenRouter del incidente.
- La garantía at-most-once cubre la ejecución del Agent y la persistencia lógica;
  Telegram `sendMessage` no ofrece exactly-once externo.
- Completar esta sección al cerrar la spec con cualquier limitación residual.
