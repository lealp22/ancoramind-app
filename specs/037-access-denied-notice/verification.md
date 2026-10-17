# Verification 037 — BL-52

Implementación y validación local seguida de rollout/E2E autorizado el
2026-10-17. El apartado local conserva la evidencia de aquella fase.

## Cobertura nueva

- `tests/unit/test_rejection_notice.py`: 17 casos (elegibilidad, rechazos no
  notificables, flag OFF por defecto, cifrado exclusivo del texto fijo).
- `tests/integration/test_access_notice.py`: 20 casos ASGI/PostgreSQL loopback
  `_test`, sin Telegram/proveedores. Rejected/payload NULL/cero IA, outbox antes
  de enviar, duplicados antes/después, ráfaga concurrente, cooldown durable,
  cuota global/capacidad pendiente y renovación tras ventana.
- Grupos, callbacks, ediciones, sin identidad/secreto inválido, flag OFF en
  admission o processor, rechazados por rate limit sin aviso adicional.
- Pending/revocado con mismo mensaje; aprobación posterior cancela aviso antiguo.
- Envío fallido definitivo/ambiguo sin retry, dos consumidores reclaman sólo una
  vez, crash tras claim y TTL sin reenvío. Fallo SQL del outbox revierte toda
  admission; nada externo se envía antes del commit.
- Migración: fresh Alembic → índice; downgrade última conserva datos y retira
  sólo índice; re-upgrade; upgrade de esquema previo con datos e `init.sql`
  compatible. Mantiene comprobaciones de RLS/search_path de revisiones previas.

## Gates ejecutados

- Unitarias globales: **1553 passed**.
- Integración PostgreSQL aislado: **203 passed, 1 STT live skipped** (opt-in
  forzado OFF). Incluye migraciones y regresiones de consentimiento/onboarding.
- Ruff global y mypy src: limpios (175 módulos). Diff check limpio.
- Avisos OTLP de pruebas sin Collector local localhost:4318; no invalida
  funcionalidad ni es evidencia sobre el Collector remoto.

En la fase local: no pruebas ni SQL contra producción, no cambio del `.env` operativo ni flag
remoto, no inferencia y no despliegue. Implementado no equivale a E2E real:
debe autorizarse rollout del SHA/migración/flag y comprobar Telegram, cooldown
y auditoría antes de declarar cierre operativo.

## Rollout y E2E autorizado — 2026-10-17

- SHA `65295ac02b32728d9c4207ecee64e980d6fb3c06`; checks `quality`,
  `integration`, `collector-config` success en ese mismo SHA, revalidados.
- Supabase canónico verificado por proyecto y head antes de migrar. Alembic
  ejecutó únicamente `0016_voice_guard_search_path → 0017_access_notice_index`:
  índice parcial presente y head 0017 comprobados después, sin fixtures SQL.
- Railway production: staged patch revisado con un único cambio,
  `TELEGRAM_ACCESS_NOTICE_ENABLED=true`. Aplicación autorizada, deployment
  `a20e86e1-93b1-4949-82e1-663ae290e162` SUCCESS, mismo SHA, una réplica.
  No se modificaron panel/pairing, allowlist, webhook, secretos ni runtime rev. 8.
- Playwright, cuenta evaluadora ya revocada, tres mensajes nuevos sintéticos:

| Paso | Interacción | Entrada Bot API | Resultado |
|---|---|---|---|
| Primer aviso | `7ab1eac0-6900-4ec3-9d65-a7a0fad5501a` | update `978199107`, mensaje `494`, 11:18:01.238480Z | aviso fijo recibido, salida `495`, delivered 11:18:03.240346Z |
| Dentro de cooldown | `dd8a28c3-6788-4307-8591-1b56b2ed7d00` | update `978199109`, mensaje `498`, 11:19:16.687709Z | silencio; cero logical_responses para esa interacción |
| Tras cooldown | `20ecfdbe-ba3f-49fb-9f72-b41046a87774` | update `978199114`, mensaje `505`, 11:37:43.915043Z | segundo aviso fijo recibido, salida `506`, delivered |

Las tres interacciones siguen `rejected/user_not_allowlisted`, payload NULL,
agent_started_at NULL, model/Gateway/tools 0 y cero eventos de uso LLM.
Autorización sigue revocada. El navegador muestra exactamente dos avisos para
tres entradas (IDs visuales 59–63, distintos de los Bot API); no se reprocesó
ningún update ni se amplió acceso para probar. Segundo mensaje a +75,449229 s;
renovación comprobada mucho después de los 300 s, no en el borde exacto.

Control positivo con cuenta autorizada: `/help`, interacción
`56215b95-a23a-4750-b725-25256564f1c7`, entrada `507`/update `978199115`,
salida `508`, completed; ayuda fija recibida sin aviso de rechazo y sin IA.
El Agent autorizado también funcionó en la campaña BL-49 (specs/038).

Salida operativa: flag de aviso permanece ON; panel y pairing permanecen
habilitados por decisión explícita del propietario, sin rollback automático.
Readiness 200 a 11:38:38Z, rev.8, componentes healthy excepto circuit unknown;
panel HTTPS 200, JSON panel/API pairing sin credenciales 401. Sin staged changes
al revisar el cierre. Navegador conservado abierto, borradores vacíos.

PASS del guion real acotado. No se provocaron presión global, fallos Telegram,
crash/recovery, expiración de pending, grupos ni secretos inválidos en producción;
esas ramas conservan cobertura local, no evidencia E2E nueva. No certifica
exactly-once externo ni toda la matriz de onboarding/aislamiento. BL-52 no usa
inferencia; la IA consumida por BL-49 se registra aparte. Sin evals T7 reales.
