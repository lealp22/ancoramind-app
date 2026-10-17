# Spec 037 — Aviso de acceso no activo (BL-52)

Estado: desplegado y activo, 2026-10-17; E2E Telegram de aviso/cooldown y
usuario autorizado superado. Evidencia y límites en `verification.md`.

## Contrato

Ante un mensaje **nuevo**, con identidad completa, de chat privado autenticado,
rechazado por `user_not_allowlisted`, el Core puede enviar:

> 🔒 Tu acceso no está activo. Contacta con quien te invitó o con el administrador.

La interacción conserva `rejected`, su motivo y cero Agent/model/Gateway/tools.
No persiste el contenido rechazado ni descarga media. El aviso no concede
acceso ni es una propuesta. Es idéntico para desconocido, pending y revocado;
no promete canje si pairing está OFF. No cambia el procesamiento de `/pair`.

## Política de rollout y límites

- `TELEGRAM_ACCESS_NOTICE_ENABLED=false` por defecto, env var independiente de
  pairing. Se inyecta en admission y processor. OFF no reserva ni envía avisos.
- Prerrequisitos existentes de admission durable/cifrado y processor obligatorio
  para entregar. No usar el webhook nativo de Agno ni un envío HTTP directo.
- Un aviso **reservado** cada 300 s por bot y usuario **o** chat, 20 reservas en
  cualquier minuto global entre bots y 20 pendientes/en envío de menos de 300 s.
  Límites de política fijos versionados, no nuevos knobs por LLM/runtime.
- Todos los resultados consumen cooldown, incluidos envíos fallidos. No responder
  a grupos, callbacks, edits, identidad incompleta, secreto webhook inválido,
  rate-limit/capacidad u otros rechazos. Chat privado positivo igual al sender.
- Avisos pendientes caducan a los 300 s; si el usuario ya tiene autorización
  durable activa al procesar, se cancela el aviso antiguo. No garantizar ausencia
  de carrera si se aprueba justo después del claim y antes del envío externo.

## Arquitectura y estados

Service selecciona texto fijo y lo cifra. Dentro del mismo lock advisory de
admission: dedup bot/update → insert rejected + delivery audit → cuotas
durables → `logical_responses(response_kind='access_denied_notice')` y un chunk
pending → commit. Fallo de persistencia revierte todo y devuelve 503 sin envío.
Duplicate devuelve el registro existente sin reservar ni volver a responder.

El processor conserva la cola Agent restringida a accepted/response_ready.
Después del trabajo autorizado consulta sólo el outbox secundario de avisos.
Un `UPDATE ... WHERE pending` gana el claim sending y se confirma **antes** de
Telegram. No payload del usuario, LLM, herramientas, botones ni acciones.
Entrega deja delivered/failed en respuesta/chunk, nunca cambia rejected.

Crash antes del claim: se puede recuperar pendiente dentro de TTL. Después del
claim: no replay; al arrancar, sending se registra failed/AccessNoticeRecovery.
Telegram no ofrece idempotency key: preferir un aviso perdido a un reenvío
ambiguo. Mantener una réplica y recovery antes del polling (ADR-004).

## Persistencia

Sin tablas/estados nuevos ni migración de datos. Alembic
`0017_access_notice_index` añade sólo índice parcial por created_at para estos
avisos; `init.sql` equivalente. SQL usa literales de contrato, nunca contenido
interpolado, y bind params para identidad/tiempos/IDs. Cifrado y auditoría en
las tablas existentes; no contenido personal en logs/OTel.

No ampliar el modelo de permisos, la topología ni BL-48. El cuello de botella
de escritura del ledger bajo flood no queda resuelto: esta política acota
**notificaciones**, no es un firewall ni protección completa frente a DoS.

## Validación y salida

Ver `verification.md`. Pendiente rollout manual (CI del mismo SHA, migración,
flag específico) y E2E Telegram sin LLM con cuenta sin acceso; verificar primer
aviso, silencio durante cooldown, estado rejected y cierre autorizado. No
activar pairing/admin para probar sólo este aviso.
