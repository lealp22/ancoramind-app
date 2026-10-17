# Verification 037 — BL-52

Implementación y validación **local**, 2026-10-17; producción sin cambios.

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

No pruebas ni SQL contra producción, no cambio del `.env` operativo ni flag
remoto, no inferencia y no despliegue. Implementado no equivale a E2E real:
debe autorizarse rollout del SHA/migración/flag y comprobar Telegram, cooldown
y auditoría antes de declarar cierre operativo.
