# specs/032 — API de aplicación multicanal para clientes web/backend (BL-36)

> **Status:** diseño (2026-10-10) — documento sin implementación de código.
> Sigue bloqueado por el cierre operativo de BL-23 y coordinado con BL-24
> (ver §5). Prioridad P2.

## 1. Problema

AncoraMind solo es alcanzable hoy desde Telegram. BL-36 pide una API HTTP
versionada para que una página web, app móvil o un BFF pequeño ofrezca los
mismos casos de uso — conversación, documentos, propuestas/confirmación —
sin duplicar lógica de negocio: debe atravesar la misma admisión, identidad
confiable, `GovernedInteractionRunner`, `LLMAccess`, budgets,
propuestas/confirmaciones y auditoría que Telegram, nunca un atajo directo
al modelo, a las tools o a los repositorios.

El propio backlog marca dos condiciones previas no cumplidas aún: cierre
operativo de BL-23 (specs/013 — Collector/Grafana reales, E2E completo) y
coordinación con BL-24 (specs/017 — identidad/autorización). Este documento
no las resuelve; diseña con ellas en mente para no construir algo que haya
que deshacer cuando se aborden.

## 2. Alcance de este incremento

Solo diseño. Investigación del acoplamiento real a Telegram (resumida en
§3) y decisiones de arquitectura (§4–§8) para que una implementación futura
tenga un plan concreto en vez de partir de cero. **Ningún código, migración
ni endpoint se crea en este incremento.**

## 3. Estado real del acoplamiento a Telegram (hallazgos)

Investigado directamente en el código, no asumido desde el texto original
del backlog — dos de las asunciones de ese texto no se sostienen (§3.5):

### 3.1 Ledger de interacciones

`ancora.telegram_interactions` (`migrations/versions/0002_llm_governance.py`):
`UNIQUE (bot_id, telegram_update_id)` es la dedup real de admisión;
`chat_id`/`telegram_user_id` son columnas Telegram-shaped. La máquina de
estados (`InteractionStatus`, `src/domain/interactions/models.py`) y el
mapeo excepción→estado terminal en `processor.py::_run_agent` **ya son
genéricos** — no necesitan tocarse:

| Excepción | Estado terminal |
|---|---|
| `AttachmentResolutionError`, `CostGovernanceError`, `EmergencyStopActiveError` | `FAILED_CONTROLLED` (determinista, antes de cualquier efecto) |
| `ExecutionBudgetExceededError`, excepción desconocida tras el claim, `OutboxPersistenceError`, `DeliveryStateConflict` | `FAILED_AMBIGUOUS` (efecto incierto, nunca se reintenta) |
| `TelegramSendError(definitive=True)` | `FAILED_DEFINITIVE` |
| `TelegramSendError(definitive=False)` | `FAILED_AMBIGUOUS` |

`claim_agent_start_with_run_id` (`repositories/interactions.py`) — un único
`UPDATE ... WHERE status='accepted' RETURNING ...` — es el mecanismo real
de at-most-once. Generaliza sin cambios de lógica, solo de nombres de
columna.

### 3.2 `GovernedInteractionRunner`/`ExecutionContext`

`ExecutionContext.telegram_update_id: int` (`src/domain/llm_access/models.py`)
es **obligatorio y no opcional** hoy; `prepare_execution_context()`/`run()`
(`src/agent/governed_interaction_runner.py`) lo exigen como argumento
posicional y re-validan su coincidencia. Es un bloqueo **mecánico**, no solo
de nomenclatura: ningún canal no-Telegram puede invocar el runner hoy sin
inventar un entero falso.

### 3.3 Identidad

`UserContext.from_run_context` (`src/security/user_context.py`): hoy
`user_id` **es literalmente** `str(telegram_user_id)` — el docstring dice
"Telegram chat ID", una imprecisión ya existente (en realidad es
`telegram_user_id`, no `chat_id`) a corregir junto con el resto. Hay un
campo `channel: str = "telegram"` ya declarado pero sin ningún uso real
(nada lo lee para bifurcar comportamiento) — vestigial, no plumbing real.
Existe además un fallback que reinterpreta el `session_id` con el prefijo
`tg:{entity}:{chat_id}` cuando `run_context.user_id` llega vacío — un
segundo lugar, independiente de `commands.py`, que asume ese formato.

### 3.4 BL-24/pairing (specs/017)

La autorización durable de BL-24 está keyed directamente por
`telegram_user_id`. **No existe ningún concepto de "principal" durable
independiente de canal** en el repo hoy. Esto confirma que "coordinar con
BL-24" es un gap de diseño real (§5), no una reutilización trivial de tablas
ya genéricas.

### 3.5 Correcciones a la asunción original del backlog

El texto original de BL-36 asumía que action_proposals/propose_*/execute_*
"ya son channel-agnostic". **Investigado y confirmado que NO lo son
completamente**: la ruta de consentimiento gobernada vigente
(`mark_presented`, `claim_confirmation`, `discard_pending_for_chat`, etc. en
`src/repositories/actions.py`) usa `ConsentPrincipal(user_id, bot_id,
chat_id)`, y la tabla `action_proposals` tiene columnas `bot_id`/`chat_id`
propias; `claim_confirmation` rechaza con `PRINCIPAL_MISMATCH` si no
coinciden. Un canal genérico necesitará tocar también este modelo, no solo
el ledger — ver §6.

### 3.6 Medios

`TelegramMediaResolverPort` (`src/domain/interactions/processor.py`) ya es
un `Protocol` trivialmente extensible; `ResolvedTelegramMedia` — el DTO que
de verdad consume el Agent vía `agent.arun(images=..., files=...)` — ya es
agnóstico de canal (bytes + metadata). Solo `TelegramAttachment` (con
`file_id` de la Bot API) es Telegram-shaped.

### 3.7 Autenticación

Cero infraestructura OIDC/JWT/sesión en el repo (`pyproject.toml` no
declara ninguna librería de ese tipo). Todos los admin APIs existentes
(`runtime_config_admin.py`, `telegram_pairing_admin.py`,
`emergency_stop_admin.py`, `admin_dashboard.py`) usan un único bearer
secreto estático por superficie (`hmac.compare_digest`) — adecuado para un
operador humano, no para una API multiusuario con revocación/scopes.

## 4. Principios de diseño (no negociables, igual que el resto del repo)

- **Migraciones aditivas, nunca reemplazo en un solo paso.** Cada
  generalización (ledger, `ExecutionContext`, consentimiento) añade columnas
  /campos opcionales nuevos y conserva los Telegram-shaped existentes como
  "extensión específica de canal" nullable — mismo patrón ya usado para
  `context_window_tokens`/`speech` en `RuntimeConfiguration`. Nunca se rompe
  una revisión ya persistida ni un checksum histórico.
- **Sin ruta de atajo.** Todo endpoint nuevo reutiliza
  `GovernedInteractionRunner`/`LLMAccess`/`propose_*`→`execute_*` ya
  existentes; cero inferencia o escritura canónica directa desde la capa
  HTTP nueva.
- **`UserContext`/identidad nunca viene del LLM** — se resuelve siempre del
  principal autenticado en la capa HTTP, igual que hoy se resuelve de
  `RunContext`/Telegram.

## 5. Identidad/principal independiente de canal (coordinación con BL-24)

**Decisión propuesta, a confirmar explícitamente antes de implementar —
no es un hecho consumado de este documento:**

Introducir `AncoraPrincipal` (UUID durable) y una tabla de vínculo
`channel_identities (channel, external_identity, principal_id, linked_at,
linked_by)`. La identidad Telegram actual (`telegram_user_id`) se convierte
en una fila más de esa tabla, no en un caso especial. `user_id` en
`UserContext` pasa a ser `str(principal_id)` en vez de
`str(telegram_user_id)` directamente — cambio que toca toda la cadena de
`UserContext`→repositorios scoped por `user_id`, por lo que debe migrarse
con cuidado (doble-escritura/backfill, no un `ALTER` destructivo).

La vinculación de una cuenta web a la misma identidad que Telegram ocurre
solo mediante un proceso explícito y auditable — no por nombre, email ni
heurística del LLM. BL-24 debería, en una revisión futura de specs/017,
referenciar `principal_id` en vez de `telegram_user_id` directamente en su
tabla de autorización durable; **esa migración de BL-24 queda fuera de
alcance de este documento** y se registra como su propio ítem coordinado
(ver tasks.md T1).

## 6. Generalización del ledger y el consentimiento

- `ancora.telegram_interactions` gana `channel VARCHAR(31) NOT NULL
  DEFAULT 'telegram'` y `external_interaction_id VARCHAR(255) NULL`
  (backfill: `external_interaction_id = telegram_update_id::text` para
  filas existentes). Nueva unicidad `UNIQUE (channel, bot_id,
  external_interaction_id)` — se mantiene `bot_id` en la clave para no
  romper la semántica actual por-bot de Telegram; un canal HTTP usa un
  `bot_id` lógico fijo propio (p. ej. `0`) o un valor dedicado, a decidir en
  la implementación.
- `ExecutionContext` gana `channel: str` + `external_interaction_id: str |
  None`; `telegram_update_id: int | None` pasa a opcional — el adaptador
  Telegram sigue poblándolo para no romper la telemetría/correlación
  existente (`ancora.telegram_update_id` ya en uso en spans/logs).
- `ConsentPrincipal`/`action_proposals` ganan un `channel_scope_id: str`
  genérico (p. ej. `f"{channel}:{chat_id}"` para Telegram,
  `f"web:{session_id}"` para HTTP) además de `bot_id`/`chat_id`, que quedan
  como columnas nullable específicas de Telegram. `claim_confirmation`
  compara por el nuevo campo genérico.
- Nuevo esquema de `session_id` para el canal HTTP, independiente del
  prefijo `tg:` ya asumido en `commands.py` y en el fallback de
  `UserContext` — candidato: `api:{principal_id}[:generation]`.

## 7. Autenticación v1 (acotada, no OIDC)

**Decisión propuesta:** tokens de API hasheados y revocables por
`AncoraPrincipal`, mismo patrón ya usado para los códigos de invitación de
BL-24 (alta entropía, solo hash en reposo, TTL/revocación explícita,
emisión que devuelve el valor una única vez). Un cliente BFF presenta
`Authorization: Bearer <token>`; AncoraMind resuelve `principal_id` del
token, nunca de un header que el cliente controle libremente.

OIDC/sesión de navegador **no es responsabilidad de AncoraMind en v1** — el
propio backlog recomienda que el navegador hable con un BFF y el BFF con
AncoraMind; la validación de sesión de usuario final vive en el BFF. Validar
JWTs de un proveedor OIDC externo queda como *Should Have* explícito para
una revisión posterior si aparece un frontend first-party sin BFF, no como
bloqueante del v1.

## 8. Contrato de endpoints (v1, sin cambios respecto al texto original del backlog)

- `POST /api/v1/interactions` — texto + `session_id` opcional + referencias
  a adjuntos ya subidos; `Idempotency-Key` obligatorio; `202` con
  `interaction_id`/`correlation_id`/estado. No mantiene la petición HTTP
  abierta durante la inferencia.
- `GET /api/v1/interactions/{id}` — estado + progreso metadata-safe +
  respuesta final solo al propietario. Polling es suficiente para v1;
  WebSocket/SSE queda diferido a cuando exista el outbox de eventos de
  BL-32.
- Endpoints de documentos (subir/consultar) y de `ActionProposal`
  (listar/confirmar/rechazar) reutilizan `DocumentService`/
  `ActionProposalsRepository` ya existentes a través del `propose_*` →
  `execute_*` vigente.
- CORS deny-by-default, límites de body/adjuntos, rate/concurrency limits
  por principal (mismo mecanismo que hoy limita por `chat_id`/`user_id`
  Telegram), OpenAPI versionado, errores sin contenido personal ni rutas
  físicas/modelos/secrets.

## 9. No-objetivos de este documento

- No implementa ninguna migración, endpoint ni cambio de `ExecutionContext`.
- No decide todavía el nombre final de columnas/tablas — son candidatas a
  perfeccionar en el spec de implementación cuando se autorice el primer
  incremento de código.
- No resuelve la migración de BL-24 a `principal_id` — se registra como
  coordinación pendiente, no como trabajo de este spec.
- No compromete streaming de tokens en tiempo real ni canales adicionales
  (Discord/Slack/WhatsApp/Email) — siguen diferidos según el propio
  BACKLOG.md.

## 10. Criterios de cierre de este documento (ya cumplidos)

1. Hallazgos de acoplamiento real documentados con referencias a archivos
   concretos, incluida la corrección sobre `action_proposals`.
2. Decisiones de arquitectura explícitas para ledger, `ExecutionContext`,
   consentimiento, identidad/principal y autenticación, cada una marcada
   como "a confirmar" cuando aplica.
3. `tasks.md` con las fases de implementación futuras, ninguna marcada
   como hecha.
4. `BACKLOG.md` BL-36 actualizado para referenciar este spec.
