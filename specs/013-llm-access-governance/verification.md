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
| Unit tests | ✅ T4 | 205 passed; admission/config/wiring cubiertos |
| Integration tests | ✅ T4 | 40 passed; ledger, admission HTTP, límites y migraciones |
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
| C | Cambio runtime → siguiente run usa nueva revisión sin redeploy | ⏳ | |
| D | Config inválida → last-known-good/bootstrap permanece | ⏳ | |
| E | Primary falla → no se supera attempt budget | ⏳ | |
| F | Circuit open → cero llamadas al upstream afectado | ⏳ | |
| G | Rate/budget agotado → no hay inferencia adicional | ⏳ | |
| H | Tool loop → fingerprint/budget lo detiene | ⏳ | |
| I | Interacción completa trazable por `correlation_id` | ⏳ | |
| J | Crash antes de `agent_started` → recuperable | ✅ T5 | `accepted` se lista y reclama ordenadamente |
| K | Crash después de `agent_started` → `failed_ambiguous`, sin replay | ✅ T5 | Recovery marca `restart_after_agent_started`; runner no vuelve a llamarse |
| L | Crash tras `response_ready` → delivery recuperable | ✅ T5 | Recovery conserva `response_ready` y entrega outbox existente |
| M | Crash durante delivery → no reenvío automático ambiguo | ✅ T5 | Recovery marca `restart_during_delivery`, sin `sendMessage` adicional |
| N | Grupo/canal Telegram → no alcanza el Agent | ✅ T4 | `non_private_chat`, `200`, sin payload ni llamada Agno |
| O | Usuario no allowlisted → no alcanza el Agent | ✅ T4 | `user_not_allowlisted`, `200`, sin payload ni llamada Agno |
| P | Extracción documental comparte config, budget y trace | ⏳ | |
| Q | Gateway caído → fail closed sin OpenRouter directo | ⏳ | |
| R | Collector caído → aplicación continúa | ⏳ | |
| S | Logs/traces no contienen contenido personal | ⏳ | |
| T | Activaciones concurrentes → compare-and-swap evita pisadas | ⏳ | |
| U | Run activo durante cambio → conserva revisión anterior | ⏳ | |
| V | Duplicate delivery → no consume rate limit | ✅ T4 | Duplicate se detecta antes del contador durable y conserva correlation ID |
| W | Rate limit superado → `2xx` y cero inferencias | ✅ T4 | burst/min/hora/cola ⇒ `rejected`, `200`, sin Agent |
| X | Tool call 12 → permitida si queda budget | ⏳ | |
| Y | Tool call 13 → rechazada por hard ceiling | ⏳ | |

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
- `TELEGRAM_PROCESSOR_ENABLED=false` por defecto. El adaptador
  `AgnoInteractionRunner` es temporal y T7 lo sustituirá por `LLMAccess` y un
  Agent per-run.

## Limitations and remaining evidence

- La causa exacta de las ~78 inferencias no se marcará como confirmada sin logs
  de Railway, sesión/run Agno y actividad detallada de OpenRouter del incidente.
- La garantía at-most-once cubre la ejecución del Agent y la persistencia lógica;
  Telegram `sendMessage` no ofrece exactly-once externo.
- Completar esta sección al cerrar la spec con cualquier limitación residual.
