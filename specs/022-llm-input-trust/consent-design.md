# Diseño P0 — consentimiento de mutaciones (BL-39)

> Decisión de diseño local, 2026-09-30; **no implementada**. No habilitar
> mutaciones gobernadas basándose solo en este documento. `AGENTS.md` y
> `docs/architecture.md` mantienen la jerarquía normativa.

## Contrato y UX

Un texto del documento, una nota, la respuesta de una tool o el historial
pueden sugerir una propuesta, pero **no** constituir consentimiento. El
consentimiento es una interacción distinta, admitida por el canal, posterior
a la **entrega** de la descripción de la propuesta. No basta con que el LLM
llame a `execute_*` ni con que `actions_repo.confirm(user_id, proposal_id)`
encuentre una fila.

- La propuesta presenta al usuario operación, destino, parámetros relevantes,
  identificador UUID completo y caducidad; no se incluye contenido personal en
  observabilidad. El payload persistido queda inmutable; si hay que cambiarlo,
  se crea otra propuesta. La respuesta que la presenta debe estar entregada
  (`logical_response`/delivery completados), no solo generada. Si la respuesta
  se trunca, no contiene la propuesta o se pierde, no existe presentación
  verificable: pedir una propuesta nueva. No deducir entrega por `response_ready`.
  La presentación debe producirse desde el payload canónico mediante salida
  determinista (no fiarse de que el LLM relate fielmente la propuesta); registrar
  la asociación propuesta/respuesta en Core al preparar la outbox. Una
  propuesta creada y no incluida en una entrega verificada no es confirmable.
- «Sí» aislado (se admiten solo variantes de capitalización y puntuación
  terminal acordadas en tests) identifica una propuesta **solo cuando existe
  exactamente una** propuesta vigente, pendiente y presentada al mismo usuario
  y chat/bot. Si hay cero, no ejecuta; si hay dos o más, se pide selección con
  IDs y resumen, sin invocar al Agent. No elegir la última ni tomar una pista
  del historial. El texto de confirmación explícita será `Sí <UUID-completo>`;
  se compara con una propuesta vigente presentada al mismo principal.
  «Sí, y además ...», texto citado/reenviado/editado, caption, adjunto o
  callback no admitido no son confirmaciones; nunca se extrae un «sí» de
  contenido de terceros. No aceptar múltiples IDs ni confirmación por índice.
- Toda confirmación se resuelve **antes del LLM**, en el procesador de
  interacciones, leyendo exclusivamente el mensaje autenticado admitido y
  conservado cifrado en el ledger. No pasar un booleano/ID de permiso en el
  prompt ni aceptar `proposal_id`, `user_id` o un token procedentes del LLM
  como prueba. Si no se puede descifrar, consultar el ledger o comprobar la
  entrega, fallo cerrado.
- Caducidad inicial: **15 minutos desde la entrega verificada**, siempre que
  la propuesta siga pendiente y su origen sea una interacción auténtica. La
  expiración se evalúa con tiempo de PostgreSQL en el claim; reintento tardío
  requiere nueva propuesta y nueva confirmación. «Sí» aceptado antes de que
  se entregase la propuesta no autoriza nada, aunque se procese después.
  `/new` no revive ni renueva propuestas; al reiniciar conversación se
  invalidan las anteriores de ese chat (no apoyarse en la sesión Agno para
  comprobarlo). Cambiar identidad/bot/chat invalida la vinculación.

## Evidencia y estados durables

El Core recibe un principal tipado resuelto por el canal (`user_id`, `channel`,
`bot_id`/`chat_id` para Telegram) y una referencia a una interacción admitida;
`domain/` no importa Agno ni Telegram SDK. El adaptador comprueba admisión
private-chat/allowlist, identidad de remitente y pertenencia de la interacción;
en Core se verifica de nuevo contra el ledger. En el rollout Telegram
`user_id` es `str(telegram_user_id)`; **no** confundir con
`source_interaction_id` ni con el `session_id` o el `chat_id` de otro usuario.
La transición debe comparar `bot_id`, `telegram_user_id`, `chat_id`,
`telegram_update_id`, `accepted_at`, ID de la propuesta, `source_interaction_id`
y el hash del payload persistido. Las columnas opcionales ya existentes
(`source_interaction_id`, `arguments_fingerprint`, `idempotency_key`) están
sin rellenar en `ActionProposalsRepository.create`: hacerlas obligatorias para
nuevas propuestas antes de admitir un `execute_*`. Propuestas legacy sin
procedencia o hash: **no ejecutables**; solicitar regeneración.

Modelo objetivo: propuesta `pending_confirmation` → `confirmed` (evidencia
vinculada y consumida) → `executing` → `executed` / `failed_definitive` /
`failed_ambiguous`; `expired`/`discarded` terminan sin ejecución. `confirmed`
no es una licencia reutilizable ni se concede por una llamada a tool. La
evidencia durable lleva ID de interacción confirmante, propuesta y hash del
payload, usuario/canal/identidad externa, instantes de aceptación y consumo,
estado y motivo tipado. Restricciones únicas en interacción confirmante y
propuesta; la operación de claim usa bloqueo de fila o `UPDATE ... WHERE
status='pending_confirmation' ... RETURNING`, en una transacción, con
idempotencia que funciona entre procesos. Cada interacción puede autorizar
**una** propuesta; no confirmar varias con un único «Sí». También se debe
registrar cuál respuesta entregada presentó exactamente qué propuesta, en vez
de buscar UUID arbitrarios en un texto redactado por el LLM.

El Core revalida tipo de operación, pertenencia y payload en el punto de
mutación. La evidencia no se pasa como argumento controlable por el modelo:
la ejecución recibe el contexto seguro de la interacción confirmante. Para
ser independiente de Agno, un futuro adaptador REST/CLI debe proporcionar
una interacción autenticada equivalente; si no existe, se rechaza. La ruta
AgentOS heredada carece de esta evidencia: **deshabilitarle todas las tools
de mutación o la propia ruta hasta que tenga un adaptador equivalente**. Un
hook del Agent o un prompt adicional no sustituyen el guard en Core.

## Semántica de efectos y fallos

1. Claim y consumo único son durables antes de todo efecto no transaccional.
   Para WRITE PostgreSQL, usar **la misma sesión y transacción** para claim,
   mutación canónica y estado `executed`; el repositorio no debe hacer un
   `commit()` privado entre operaciones. Un fallo previo al commit permite
   rollback de ambas operaciones; un commit de resultado incierto exige
   reconciliar por clave idempotente, nunca repetir ciegamente la mutación.
2. EXTERNAL_ACTION: tras validar, registrar `executing` e idempotency key
   durables antes de llamar al proveedor. Si el proveedor acepta idempotencia,
   usar la misma key; si no, un timeout/crash/resultado incierto queda
   `failed_ambiguous` y bloquea replay. El proveedor de calendario actual es
   `NoopCalendarProvider`, pero el contrato no puede presuponerlo siempre.
   El resultado local posterior al efecto externo puede fallar: no prometer
   rollback del proveedor. Reconciliación manual/auditada, sin retry del Agent.
3. Errores validados y anteriores a cualquier efecto pueden ser definitivos;
   tras fallo/consumo no reutilizar «Sí» ni `confirmed` como permiso para otro
   intento. Para reintentar, nueva propuesta y nuevo evento de consentimiento.
   Un estado incierto jamás se transforma automáticamente en `pending`.
4. Duplicados `bot_id + update_id`, carreras, nuevos runs con el mismo mensaje
   y ejecuciones repetidas de `execute_*` no crean más de un efecto. No
   confundir este claim con el presupuesto de tools ni con rate limiting.

## Inventario y migración obligatoria

| Superficie actual | Riesgo / tratamiento P0 |
|---|---|
| `execute_vehicle`, `execute_vehicle_maintenance`, `execute_reminder`, `execute_calendar_event`, `execute_todo_list`, `execute_todo_item` | Todos llaman `actions_repo.confirm()` desde el LLM sin evento confirmante; reemplazar por **una** capability Core de claim/ejecución y validación por tipo de operación. Probar también ramas rename/delete, update/status/move/delete de TODO. |
| `remember_note` | Escritura canónica directa; convertir a propuesta + ejecución con el mismo contrato. No inferir consentimiento del texto de una nota recuperada. |
| `analyze_document` / `DocumentService.ingest` | Almacena original, metadatos y extracción automáticamente. Según `AGENTS.md` también es WRITE: acordar presentación de propuesta ligada al adjunto/bytes preparados, sin persistirlo antes de consentir. No permitir que el Agent invente o cambie los bytes/filename entre propuesta y ejecución. Sin excepción aprobada. |
| `RemindersWorker` | Efecto outbound de un recordatorio previamente confirmado: modelar como cumplimiento de la autorización original, con deduplicación de entrega; revisar por separado, no usar un «Sí» del worker. |
| AgentOS legacy, API/CLI futuras, llamada directa a service/repo | No confiar en `RunContext` no gobernado ni proteger únicamente el registro de tools. Core debe imponer la frontera, incluida la ruta heredada; bootstrap administrativo/migración de datos necesita un contrato explícito separado. |

Hoy `ActionProposalsRepository.create/confirm/mark_executed` hacen commits
independientes; `mark_executed` ni siquiera filtra por estado `confirmed`.
Los repositorios de notes/vehicles/TODO/calendar/reminders también hacen
commits propios. Refactorizar los límites de transacción **antes** de declarar
que el consumo y el WRITE local son atómicos. No aplicar un guard parcial a un
solo ejecutor y anunciar P0 cerrado. Migración Alembic + `migrations/init.sql`
equivalente a head; upgrade con datos legacy, fresh install y downgrade
probados. Mantener inmutables `user_id`, tipo, payload y procedencia de la
propuesta en DB; no usar fingerprint de contenido como dato de telemetría.

## Acceptance tests requeridos para cerrar P0

- Parser determinista: una vigente presentada → «Sí» válido; varias → pedir
  ID; ID ajeno/no presentado/expirado/no UUID, contenido citado, respuesta
  anterior, adjunto y sin consentimiento → cero mutaciones / cero tool executes.
- Mismo evento duplicado y dos confirmaciones concurrentes contra la misma
  propuesta (sesiones/procesos distintos) → a lo sumo un claim y un efecto;
  usuario, bot, chat y payload cruzados → rechazados. `/new` invalida pendientes.
- Crash/rollback en cada frontera (antes/después del claim, antes/después del
  commit, tras enviar al proveedor); resultado ambiguo → sin replay automático;
  audit y reconciliación idempotente. Pruebas con PostgreSQL real.
- Tests parametrizados **para cada** `execute_*` y cada rama de TODO; notes e
  ingesta sin bypass; ruta legacy rechazada. Pruebas Telegram + harness Agent
  solo después de los unit/integration; un catálogo estático no prueba el
  comportamiento del Agent ante una inyección.