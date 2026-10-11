# Acuse de botones Telegram — BL-39/40 — 2026-10-11

## Contrato y alcance

Se completa `answerCallbackQuery`, separado de confirmación y ejecución:

- `callback_query.id` normalizado como `callback_query_id` opcional, opaco,
  ASCII imprimible sin espacios y máximo 256 caracteres (límite defensivo local,
  **no** límite documentado por Telegram). Un valor inválido se descarta sin
  truncar/eco. El campo no se toma de mensajes normales.
- Solo se conserva en el payload cifrado de interacciones admitidas; no nuevas
  columnas, no migración. Payloads previos sin ID mantienen el flujo Core.
- `TelegramResponseSender.answer_callback_query()` → `TelegramNotifier`, request
  mínimo con el ID, sin texto, popup, URL ni anuncio de éxito.
- Timeout HTTP de 2 s y timeout async exterior de 2 s. Una llamada por intento
  de procesamiento, sin retry programado. Error/400 expirado/429/5xx/JSON inválido
  no afecta al resultado de consentimiento/ejecución ni dispara inferencia.
- Logging propio solo mensaje fijo/status/clase: no id, token, URL, body o
  texto de excepción. No etiquetas/métricas nuevas con el identificador.
- Acuse antes del claim y de la mutación. Un acuse aceptado **no** confirma la
  propuesta: la respuesta persistida de Core informa del resultado real.
- Todos los updates `callback_query` admitidos se resuelven por el camino
  determinista: flags OFF/datos inválidos nunca llegan al Agent/comandos.
  No reingesta de documentos/voz del mensaje antiguo que contiene el botón.
- Private-chat/allowlist/secret/idempotencia de admission permanecen intactos.
  Un rechazado por admission no es procesado ni recibe acuse por este camino.

## Duplicados, reinicios y límite aceptado

El mismo bot/update duplicado comparte una interacción durable. Tras completed
no se vuelve a procesar; recuperar response_ready solo entrega su outbox sin
reacusar. Una segunda pulsación con update nuevo recibe acuse propio, pero el
claim ya consumido no ejecuta otra vez.

El acuse es transitorio/best-effort: no se introduce outbox, tabla ni claim durable
para él. Si dos procesadores leen simultáneamente la misma interacción accepted,
o hay un crash después del acuse y antes de persistir respuesta, el acuse puede
repetirse. No constituye una garantía at-most-once de la **petición de acuse**.
La ejecución Core sigue at-most-once por sus locks/claims; integración valida
procesadores independientes concurrentes. No se reejecuta una acción para
reparar un acuse ni se reabre una interacción terminal.

Colas/caídas pueden retrasar el acuse hasta que el ID haya expirado en Telegram;
el notifier falla best-effort. No se mueve al webhook antes de la persistencia
durable ni se añade una nueva acción al flujo de admission.

## Evidencia local

- Nuevos tests unitarios: normalización/acotado/cifrado, compatibilidad sin ID,
  ID falso en mensaje, falta identidad/payload, request mínimo, timeout, JSON
  inválido/array, errores de proveedor sin eco, orden acuse→Core, flag OFF,
  callbacks inválidos y recovery de respuesta sin acuse.
- Nuevos tests integración PostgreSQL: propuesta→entrega→callback cifrado;
  confirm/discard/expired/invalid/disabled × ack exitoso/fallido; duplicate
  admission, doble pulsación y procesadores concurrentes sin doble mutación.
- 1300 unit passed, cobertura 79.46% (gate 75%); 155 integration passed,
  1 skipped (live smoke STT). BD dedicada `ancoramind_callback_ack_test` local.
- Sin requests Telegram reales, inferencia, rollout ni cambios en BD remotas.
  Cambio staged del propietario en `test_legacy_consent_boundary.py` preservado.

## Checklist E2E (pendiente, con el propietario)

Prerequisitos: mismo SHA con CI quality/integration/collector-config verdes,
deploy manual explícito, admission/processor activos y consentimiento gobernado
ON verificados; chat privado autorizado. Redis no es necesario para esta tarea.
No registrar contenido personal, IDs de callback ni secretos en evidencia.

| Caso | Resultado esperado |
|---|---|
| Proponer nota sintética, pulsar Sí | Indicador desaparece; respuesta Core de éxito; una nota/acción ejecutada |
| Pulsar No | Indicador desaparece; propuesta discarded; cero escritura canónica |
| Pulsar de nuevo un botón ya resuelto | Acuse de nueva pulsación; no segunda ejecución |
| Esperar TTL (15 min), pulsar Sí | Rechazo de caducidad; cero escritura |
| Varias propuestas, confirmar botón específico | Solo se ejecuta su propuesta; el resto sigue pendiente |
| Varias propuestas, enviar «Sí» sin ID | Core pide selección; cero ejecución |
| `/new`, después pulsar un botón viejo | Propuesta no pendiente; cero ejecución |
| Confirmar por texto | Mismo Core; ningún answerCallbackQuery para un mensaje normal |

El éxito del acuse HTTP y el resultado canónico se comprueban por separado:
callbacks confirm/discard no ejecutan Agent ni inferencia. No simular caídas de
Telegram/Gateway en producción ni reinyectar updates personales para probarlo.

BL-39/40 y BL-23 permanecen abiertos por rollout, E2E y demás gates operativos.

## Referencia oficial

Telegram Bot API: https://core.telegram.org/bots/api#callbackquery y
https://core.telegram.org/bots/api#answercallbackquery. El cliente mantiene el
indicador hasta recibir answerCallbackQuery; el acuse puede omitir texto y el
método devuelve True al tener éxito. No se documenta allí un máximo de 256
caracteres para el ID: ese tope pertenece exclusivamente a esta implementación.
