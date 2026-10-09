# Tasks — specs/032 / BL-36

> Documento de diseño (2026-10-10). **Ninguna tarea de este fichero está
> implementada.** Bloqueado por el cierre operativo de BL-23 y coordinado
> con BL-24 (specs/032/spec.md §5). Orden recomendado: T1 antes que
> cualquier otra, porque T2–T4 dependen de qué forma tome el principal.

## T1 — Decisión de identidad/principal (coordinada con BL-24)

- [ ] Confirmar explícitamente con el propietario el diseño de
      `AncoraPrincipal` + `channel_identities` (spec.md §5) antes de tocar
      ninguna tabla.
- [ ] Decidir la estrategia de migración de `UserContext.user_id` de
      `str(telegram_user_id)` a `str(principal_id)` sin romper los
      repositorios ya scoped por `user_id` (doble-escritura/backfill vs.
      vista de compatibilidad — a decidir en su propio spec de
      implementación, no aquí).
- [ ] Decidir si BL-24 (specs/017) se revisa en el mismo incremento para
      que su autorización durable referencie `principal_id`, o si queda
      como ítem separado explícito.
- **Listo cuando:** existe un spec de implementación aprobado para el
  principal, con migración concreta — este documento (specs/032) no lo
  resuelve, solo lo plantea.

## T2 — Migración aditiva del ledger de interacciones

- [ ] `channel VARCHAR(31) NOT NULL DEFAULT 'telegram'` +
      `external_interaction_id VARCHAR(255) NULL` en
      `ancora.telegram_interactions` (o su sucesora si T1 decide renombrar
      la tabla), con backfill de filas existentes.
- [ ] Nueva unicidad `(channel, bot_id, external_interaction_id)`.
- [ ] Repositorio: generalizar `admit_with_limits`/
      `claim_agent_start_with_run_id` para aceptar el par genérico sin
      cambiar su lógica de UPDATE atómico (spec.md §3.1 — ya es genérica).
- **Listo cuando:** una fila Telegram ya persistida sigue validando/
  consultándose sin cambio de comportamiento (test de regresión de
  compatibilidad, mismo criterio que los campos aditivos de
  `RuntimeConfiguration`).

## T3 — Generalizar `ExecutionContext`/`GovernedInteractionRunner`

- [ ] `ExecutionContext.channel: str` + `external_interaction_id: str |
      None`; `telegram_update_id` pasa a `int | None` (compatibilidad, no
      ruptura).
- [ ] `GovernedInteractionRunner.prepare_execution_context()`/`run()`
      aceptan el par genérico; el adaptador Telegram sigue pasando
      `telegram_update_id` igual que hoy.
- **Listo cuando:** los tests existentes de `test_governed_interaction_runner.py`
  siguen en verde sin cambios de comportamiento Telegram; un test nuevo
  cubre un `channel="api"` sintético.

## T4 — Generalizar consentimiento (`ConsentPrincipal`/`action_proposals`)

- [ ] `ConsentPrincipal` gana `channel_scope_id: str`; `action_proposals`
      gana la columna correspondiente (aditiva, nullable).
- [ ] `claim_confirmation`/`_claim_rejection` comparan por el campo
      genérico en vez de `bot_id`/`chat_id` directamente (que quedan como
      metadata específica de Telegram).
- **Listo cuando:** las pruebas de `PRINCIPAL_MISMATCH` existentes siguen
  en verde; un test nuevo cubre el caso de un canal no-Telegram.

## T5 — Endpoint de admisión HTTP + autenticación por token

- [ ] `POST /api/v1/interactions` — mismo patrón de admisión que
      `telegram_admission.py` (valida, persiste `accepted`, nunca invoca al
      Agent directamente), pero resolviendo identidad desde un token
      hasheado por `AncoraPrincipal` (spec.md §7) en vez de un bearer
      compartido.
- [ ] Modelo de token: emisión (devuelve el valor una vez), revocación,
      TTL — mismo patrón que los códigos de invitación de BL-24.
- **Listo cuando:** un token revocado no admite ninguna interacción nueva
  (test de regresión); duplicados por `Idempotency-Key` devuelven `202`
  sin ejecutar el Agent de nuevo.

## T6 — Polling, documentos y propuestas

- [ ] `GET /api/v1/interactions/{id}` (estado + respuesta final al
      propietario únicamente).
- [ ] Endpoints de documentos reutilizando `DocumentService`/
      `DocumentStorage` ya existentes.
- [ ] Endpoints de `ActionProposal` (listar/confirmar/rechazar)
      reutilizando `propose_*`/`execute_*` sin ruta mutante paralela.
- **Listo cuando:** otro principal no puede leer estado/respuesta/
  adjuntos/propuestas de uno distinto (test de aislamiento explícito).

## T7 — OpenAPI, CORS, rate limiting, versionado

- [ ] Esquema OpenAPI publicado y versionado; CORS deny-by-default; límites
      de body/adjuntos; rate/concurrency por principal (mismo mecanismo que
      hoy limita por `chat_id`/`user_id` Telegram).
- [ ] Errores sin contenido personal, rutas físicas, modelos ni secrets.
- **Listo cuando:** un test de contrato valida el esquema contra la
  implementación real.

## T8 — E2E con cliente de referencia (Railway)

- [ ] Un cliente de referencia sin Telegram completa: conversación,
      documento, consulta READ y propuesta/confirmación WRITE.
- [ ] Duplicados ejecutan el Agent como máximo una vez.
- **Listo cuando:** se cumple el criterio de cierre original de BL-36 en
  BACKLOG.md.
