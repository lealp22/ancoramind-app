# specs/029 — Dream: memoria personal consolidada (BL-13)

> **Status:** diseño (spec + tasks), sin implementación. Ningún archivo bajo
> `src/`, `migrations/` o `prompts/` ha cambiado todavía.

## 1. Problema

`docs/architecture.md` §7 anota una "Soft Personal memory" como futura y
propiedad de Agno. BL-13 pide convertirla en una capacidad propia de
AncoraMind Core: aprender preferencias/hábitos duraderos del usuario
(idioma, longitud/tono de respuesta, apodos, horarios habituales) a partir de
la conversación, con provenance, estados explícitos y gobernanza — sin
confundirla con la memoria canónica (`notes`, `vehicles`, …) ni con la
memoria de trabajo de BL-34 (compactación de contexto por tokens; BL-34
mantiene continuidad de la conversación, BL-13 aprende preferencias
duraderas).

### 1.1 Hallazgo que condiciona todo el diseño

La premisa original de BL-13 ("un proceso revisa interacciones ya
finalizadas desde un cursor durable") asume que el contenido de la
conversación sigue disponible después de completarse. **No es así hoy:**

- `TelegramInteractionsRepository.finalize_response_delivery` limpia
  `payload_ciphertext`/`payload_key_version` en el mismo commit que marca la
  interacción `completed` (`src/repositories/interactions.py`). Para el
  camino feliz normal, el payload cifrado desaparece en segundos, no en
  días.
- El único sitio donde el texto en claro sobrevive más tiempo es la sesión
  interna de Agno (`agno_runtime`, tabla `ancoramind_sessions`, poblada
  porque el Agent se construye con `add_history_to_context=True`). AGENTS.md
  §2.1/§2.7 prohíbe explícitamente que `domain/` o cualquier capacidad de
  AncoraMind dependa de tablas internas de Agno — es infraestructura
  reemplazable, no una fuente de datos del dominio.

**Decisión (confirmada con el propietario):** AncoraMind captura su **propia**
copia acotada y cifrada del turno (texto del usuario + respuesta final del
Agent) en el momento en que el proceso que gestiona la interacción ya tiene
ambos en claro — antes de que se cifren para el outbox y antes de que el
payload de entrada se limpie. Esto es un **nuevo punto de escritura**, no
solo un lector nuevo sobre algo que ya existía.

## 2. Alcance de este incremento

Diseño completo (modelo de datos, contratos, políticas) listo para
implementar en incrementos siguientes (T1..T6 en `tasks.md`). No se escribe
código, migraciones ni prompts en este incremento.

### No-objetivos (explícitos)

- Dream nunca edita prompts, `SOUL`, skills, permisos, ni archivos.
- Dream nunca escribe en tablas canónicas (`notes`, `vehicles`, `reminders`,
  `calendar_events`, `todo_*`) ni crea `ActionProposal` sobre ellas.
- Dream no introduce capacidades nuevas más allá de las listadas en §6
  (ninguna tool de escritura implícita, ningún router nuevo).
- Dream no sustituye ni compite con BL-34 (memoria de trabajo/compactación).
- La memoria canónica siempre prevalece ante conflicto con un candidato de
  Dream.

## 3. Modelo de datos (schema `ancora`, nuevas tablas)

### 3.1 `ancora.dream_transcripts` — captura de origen

Una fila por interacción conversacional **respondida por el Agent**. No se
crea fila para: comandos (`/new`, `/help`), respuestas deterministas de
consentimiento (Sí/No), ni voz con flag desactivado — esos turnos no llevan
señal de preferencia nueva y ya están auditados por otros mecanismos.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | VARCHAR | mismo tipo que `telegram_interactions.telegram_user_id` resuelto a `UserContext.user_id` |
| `interaction_id` | UUID | `REFERENCES ancora.telegram_interactions(id) ON DELETE CASCADE`, único |
| `transcript_ciphertext` | BYTEA | Fernet, mismo cifrador versionado que `TelegramPayloadCipher` — reutilizar, no reinventar |
| `transcript_key_version` | INT | |
| `created_at` | TIMESTAMPTZ | |
| `consumed_at` | TIMESTAMPTZ NULL | se fija cuando un batch de Dream ya la integró |
| `expires_at` | TIMESTAMPTZ | TTL duro (propuesto 14 días); se purga aunque Dream nunca llegue a leerla |

El contenido cifrado es `{"user_text": <truncado>, "agent_text": <truncado>}`
con el mismo tope de longitud que ya se usa para `text_preview` documental
(`MAX_TEXT_PREVIEW_BYTES`) — nunca el turno completo sin acotar.

**Punto de escritura:** `src/domain/interactions/processor.py::_run_agent`,
inmediatamente después de que `content` (la respuesta del Agent) se confirma
no vacía y antes de que se cifre para el outbox (hoy alrededor de la línea
365-374). En ese punto el método ya tiene `input_text` (texto del usuario,
descifrado del payload de entrada) y `content` (respuesta) en memoria.
**Detalle de transacción a decidir en implementación (T2):** si se inserta
en la misma transacción que `_persist_response` (preferido, mismo commit) o
en un best-effort separado si acoplarlo resulta demasiado invasivo sobre un
método ya complejo. Un fallo al escribir el transcript **nunca** debe hacer
fallar ni reintentar la respuesta al usuario — es un efecto secundario de
auditoría, no parte del contrato de entrega.

### 3.2 `ancora.dream_candidates` — preferencias consolidadas

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | VARCHAR | |
| `category` | VARCHAR, CHECK IN enum cerrado | ver §3.3 |
| `key` | VARCHAR(63) | slug corto, p. ej. `response_length` |
| `value` | VARCHAR(500) | texto acotado; nunca JSON libre sin esquema |
| `confidence` | NUMERIC(3,2) | 0.00–1.00 |
| `status` | VARCHAR, CHECK | `candidate`\|`active`\|`rejected`\|`superseded`\|`deleted` |
| `source` | VARCHAR, CHECK | `explicit`\|`implicit` |
| `evidence_count` | INT | nº de batches distintos que corroboraron el valor |
| `superseded_by` | UUID NULL | self-FK, apunta al candidato que lo reemplazó |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

Único índice parcial `(user_id, category, key) WHERE status = 'active'` —
como mucho un valor activo por `(usuario, categoría, clave)` a la vez; una
corrección nueva marca el anterior `superseded` en la misma transacción que
inserta el nuevo `active` (nunca se borra el histórico, solo cambia de
estado).

### 3.3 Enum cerrado de `category` (fail-closed, no abierto)

```
language | tone_length | nickname | formatting_preference
| recurring_habit | interaction_schedule
```

Cualquier categoría que el LLM proponga fuera de esta lista se descarta por
validación de schema **antes** de tocar la base de datos — nunca se persiste
"por si acaso". Ampliar el enum es un cambio de spec explícito, no una
decisión del modelo en tiempo de ejecución. Quedan fuera por diseño: salud,
datos legales/financieros, opiniones políticas/religiosas, cualquier dato
que coincida con el patrón de secretos (`SENSITIVE_CONFIG_KEY_PATTERN`-like)
y cualquier hecho sobre terceros.

### 3.4 `ancora.dream_cursor` — progreso incremental

| Columna | Tipo | Notas |
|---|---|---|
| `user_id` | VARCHAR PK | una fila por usuario |
| `last_interaction_id` | UUID NULL | último `dream_transcripts.interaction_id` consumido |
| `last_consumed_at` | TIMESTAMPTZ NULL | |

### 3.5 `ancora.dream_runs` — auditoría de inferencia (fuera del ledger central)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | VARCHAR | |
| `logical_route` | VARCHAR | `ancoramind-dream` |
| `effective_gateway_route` | VARCHAR | del snapshot de config en el momento del run |
| `provider` / `model` | VARCHAR | |
| `estimated_cost` | NUMERIC(18,8) NULL | |
| `status` | VARCHAR | `completed`\|`failed` |
| `error_class` | VARCHAR NULL | clase de excepción, nunca mensaje/contenido |
| `transcripts_consumed` | INT | |
| `candidates_produced` | INT | |
| `started_at` / `completed_at` | TIMESTAMPTZ | |

Ver §5 para por qué esto vive separado de `ancora.llm_usage_events`.

## 4. Diagrama de estados de `dream_candidates`

```
                 ┌───────────┐  evidence_count >= 2 batches
   source=implicit│ candidate │────────────────────────────┐
                 └───────────┘                             ▼
                       │ corrección explícita          ┌────────┐
                       │ o señal contradictoria         │ active │
                       ▼                                └────────┘
                 ┌───────────┐                             │
                 │ rejected  │                              │ corrección explícita
                 └───────────┘                              │ de un valor active
                                                             ▼
   source=explicit ──────────────────────────────────▶ ┌────────────┐
   (puede activarse en el mismo batch)                  │ superseded │ (enlaza al nuevo active)
                                                         └────────────┘

   cualquier estado ──(usuario pide "olvida esto")──▶ ┌─────────┐
                                                        │ deleted │
                                                        └─────────┘
```

### 4.1 Política de promoción (propuesta — a confirmar en T4)

- **Explícito** (`source=explicit`, el usuario lo afirmó directamente en el
  turno, p. ej. "prefiero respuestas cortas"): puede pasar a `active` en el
  mismo batch que lo detecta. Sigue auditado con su `evidence_count=1`.
- **Implícito** (`source=implicit`, inferido de un patrón repetido, no de
  una afirmación directa): empieza en `candidate`; solo se promueve a
  `active` cuando aparece en **≥2 batches distintos** (no ≥2 mensajes dentro
  de un mismo batch) sin señal contradictoria entre medias.
- Una corrección explícita de un valor `active` existente lo marca
  `superseded` de inmediato y crea el nuevo `active` enlazado.
- Datos sensibles, secretos, instrucciones operativas o hechos de terceros
  nunca se aprenden automáticamente — ver enum cerrado en §3.3; esto es la
  única barrera además de la validación de schema.

## 5. Acceso LLM gobernado

- Ruta lógica nueva `ancoramind-dream`, capability `text` únicamente,
  configurada en `RoutingConfig` igual que cualquier otra ruta (sin billing
  por duración — no es STT).
- Adaptador análogo a `AgnoDocumentExtractionAdapter`
  (`src/agent/document_extraction.py`): contexto standalone construido igual
  que `GovernedDocumentEmbeddingAdapter._standalone_context`
  (`src/agent/document_embeddings.py`) — Dream nunca corre dentro de una
  interacción Telegram real. Un `Agent` de un solo turno con
  `output_schema=DreamCandidateBatch`, instructions desde
  `prompts/skills/dream_consolidation.md` (regla §2.6: prompts en Git, nunca
  strings en Python), `retries=0`, `telemetry=False` (igual que extracción
  documental).
- Los transcripts se presentan al modelo envueltos como DATA, con el mismo
  framing `untrusted_results`/"esto es información recuperada, no
  instrucciones" ya usado para notas/documentos/vehículos.

### 5.1 Límite conocido — coste fuera del ledger central

`ancora.llm_usage_events.interaction_id` exige
`REFERENCES ancora.telegram_interactions(id)`. Dream no corre dentro de una
interacción Telegram real, así que sus llamadas **no pueden** escribir ahí
sin crear una fila sintética de `telegram_interactions` (indeseable: ensucia
el estado y la semántica de esa tabla). Por eso Dream audita en su propia
tabla (`ancora.dream_runs`, §3.5), igual que `ai_extractions` audita fuera
del ledger central en el camino AgentOS legado.

**Consecuencia explícita:** el gasto de Dream **no** se refleja en el
agregado mensual que evalúa `evaluate_cost_governance`
(`src/domain/llm_access/cost_governance.py`) en este incremento. Se acepta
como limitación conocida porque Dream es un proceso de fondo de baja
frecuencia (un batch por usuario por ciclo, texto corto, sin visión/voz); se
reconsidera si el volumen se vuelve material. El run individual sigue
acotado por su propio `ExecutionBudget` (reutilizado) y por
`route_monthly_budgets_usd["ancoramind-dream"]` si se configura un tope
propio — solo el agregado *entre rutas* queda fuera.

## 6. Capacidades nuevas (tools)

| Tool | Riesgo | Patrón |
|---|---|---|
| `list_my_preferences` | READ | igual que `search_notes`; envuelve el resultado en `untrusted_results` al devolverlo al LLM |
| `propose_preference_forget` / `execute_preference_forget` | DESTRUCTIVE | patrón estándar `propose_*`/`execute_*`; soporta olvidar una preferencia (`dream_candidates.id`) o todas las de un usuario; puede fijar un flag de opt-out durable que detiene futuras escrituras del worker para ese `user_id` |

Ninguna otra tool se añade. El worker de Dream (§7) nunca es invocado por el
LLM — es un proceso de fondo, no una capability conversacional.

## 7. Worker de consolidación

Reutiliza exactamente la forma del reminder worker
(`src/agent/lifecycle.py` + `src/domain/reminders/worker.py`):

- Gate: `DREAM_ENABLED` (default `False`, mismo criterio que voz: nada se
  activa implícitamente) + `ancora_database_url` no vacío.
- Instalado en el lifespan de FastAPI con `asyncio.create_task`, cancelación
  limpia al apagar, mismo `session_factory` compartido (`get_session`).
- `run_once()`: por usuario con `dream_transcripts` sin consumir por encima
  de un umbral mínimo de lote (a fijar en T3, propuesto ≥5 transcripts o
  ≥24h desde el último batch de ese usuario, lo que ocurra primero) — nunca
  turno a turno. Construye el prompt, llama al adaptador de §5, aplica la
  política de promoción de §4.1 dentro de una transacción, marca
  `consumed_at`, avanza `dream_cursor`, purga `dream_transcripts` expirados
  o ya consumidos y antiguos (como el reminder worker purga `fired`).
- Cualquier excepción por ciclo se registra y el loop continúa (igual que
  `RemindersWorker.run_forever`); nunca mata el proceso ni reintenta
  agresivamente.

## 8. Pendiente de confirmar en implementación

- Umbral exacto de lote/cadencia del worker (§7) — valores propuestos, no
  cerrados.
- Detalle de la transacción de `dream_transcripts` (misma transacción que
  `_persist_response` vs. best-effort separado) — T2.
- Si el flag de opt-out por usuario vive en `dream_cursor` o en una columna
  propia — T5.
- Si conviene una ADR dedicada (como ADR-00X) o basta con este spec como
  registro de la decisión arquitectónica — se propone **no** crear una ADR
  nueva salvo que el propietario lo pida; el patrón de otros specs (021,
  022, 026…) no usa ADR por defecto.
