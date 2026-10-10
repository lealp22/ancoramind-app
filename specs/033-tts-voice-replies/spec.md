# specs/033 — Respuestas de voz opcionales en Telegram (TTS, BL-27)

> **Status:** mini-ADR / diseño (2026-10-11) — documento sin implementación
> de código, tal como pide el propio BL-27 ("crear mini-ADR/spec antes de
> implementar; no asumir que TTS es necesario"). Construido como el inverso
> de BL-26/specs/028 (STT), reutilizando sus patrones donde encajan y
> señalando explícitamente donde no.

## 1. Problema

BL-26 ya cubre voz **entrante**: nota de voz de Telegram → transcripción
gobernada → texto al Agent. La respuesta sigue siendo siempre texto. BL-27
pregunta si la respuesta debería poder ser también hablada
(`sendVoice`/`sendAudio`), y pide decidir proveedor, idiomas, coste,
moderación, retención, idempotencia y auditoría **antes** de tocar código.

## 2. Alcance de este incremento

Solo diseño. Ninguna migración, endpoint, dependencia nueva ni tool se
crea aquí. `tasks.md` deja fases futuras explícitas, ninguna marcada como
hecha.

## 3. Decisión de arquitectura — texto siempre, voz es un enriquecimiento best-effort

**La respuesta de texto nunca deja de enviarse.** TTS es un envío
*adicional*, no un sustituto: si la síntesis o el envío de voz falla, el
usuario ya tiene su respuesta por el canal que siempre ha funcionado. Esto
resuelve de raíz el requisito de "fallback a texto" del ítem original —
nunca hay un escenario en el que el fallback deba *activarse*, porque el
texto nunca se bloquea en espera de la voz.

Esto sitúa TTS en el mismo patrón que el acuse de BL-32
(`response_kind='ack'`, specs/032... — en realidad BL-32 sin spec propio,
ver `src/repositories/interactions.py::create_ack_response`), no en el de
`'agent_final'`: una fila `response_kind='voice'` independiente,
**posterior** a que `'agent_final'` ya esté `completed` (nunca compite con
la máquina de estados principal, nunca se envía antes de que el texto esté
confirmado entregado). Mismo mecanismo de idempotencia:
`INSERT ... ON CONFLICT (interaction_id, response_kind) DO NOTHING ...
RETURNING id` — un reproceso nunca duplica el audio. `chunk_count=1`
siempre: una respuesta hablada es un solo fichero, nunca se fragmenta como
el texto (`split_telegram_message` es inherentemente textual, no
generaliza a binario — confirmado en el código, no asumido).

**Punto de disparo:** después de que `finalize_response_delivery` marque
la interacción `completed` (texto ya entregado con éxito). Nunca antes, y
nunca si el texto falló — una respuesta hablada sin la base textual
correspondiente no tiene sentido ni es auditable del mismo modo.

## 4. Proveedor y ruta gobernada

**Mismo patrón que `GovernedSpeechAccess` (STT), en sentido inverso — una
clase hermana, no una reutilización literal:** `GovernedSpeechSynthesisAccess`
(nombre propuesto) resuelve una ruta lógica propia desde el snapshot de
configuración, nunca pasa por `AgnoLLMAccess.model_for()` (que solo
construye modelos de chat), y hace una llamada HTTP directa al LiteLLM
Proxy privado (`{base}/audio/speech`, el endpoint OpenAI-compatible de
síntesis — simétrico a `/audio/transcriptions` que ya usa STT). Igual
disciplina: registra el evento de uso en `LlmUsageRepository` *antes* de
llamar (estado `started`, para que un crash no pierda el gasto estimado) y
siempre finaliza en un `finally` (`completed`/`failed_ambiguous`), sin
reintentos, sin loguear el cuerpo crudo del proveedor.

**Config/gobernanza — campo hermano, no reutilización de `speech`:**
`RuntimeConfiguration.speech` (`SpeechRoutingConfig`) es un único campo
opcional para *una* ruta de voz (STT) — no es un diccionario de
capacidades de voz. Se necesita un campo hermano,
`RuntimeConfiguration.speech_output: SpeechRoutingConfig | None = None`
(mismo tipo, misma validación de coste que ya existe para `speech` en
`validate_runtime_limits`, duplicada para este campo), más un nuevo valor
en el `Literal` cerrado de `LogicalRoute.capabilities`
(`src/domain/runtime_config/models.py`) — hoy
`"text"/"vision"/"tool_calling"/"structured_output"/"embeddings"/"transcription"`,
añadir `"speech_synthesis"`. Esto es exactamente el mismo patrón aditivo
usado para `context_window_tokens`/`speech` — ningún campo existente
cambia de forma.

**Coste:** mismo mecanismo ya validado para STT
(`governance.speech.billing.rate_usd_per_second > 0` ⇒ exige
`cost_governance.daily_budget_usd`/`monthly_budget_usd`) replicado para
`speech_output`. `evaluate_cost_governance` no necesita ningún cambio — ya
agrega por `logical_route` de forma genérica; la nueva ruta participa
automáticamente en cuanto se declare.

## 5. Formato de entrega — `sendVoice` (OGG/Opus) con transcodificación

**Decisión confirmada con el propietario:** `sendVoice`, no `sendAudio` —
se entrega como nota de voz nativa (burbuja redonda, reproductor de
Telegram), no como un adjunto de audio genérico. La mayoría de proveedores
TTS devuelven mp3/wav/pcm, nunca Ogg/Opus directamente, así que hace falta
transcodificar antes de enviar.

- Reutiliza `ffmpeg` (ya documentado como dependencia de infraestructura
  para STT en `src/agent/voice_inspector.py`) — misma herramienta, sentido
  contrario: aquí se **codifica** a Ogg/Opus en vez de decodificarse desde
  él. No es reutilización de código (es la dirección opuesta del pipeline),
  pero sí de la dependencia binaria ya aprobada y ya presente en el
  despliegue.
- Mismas disciplinas que `FFmpegVoiceInspector`: proceso en
  `tempfile.TemporaryDirectory`, timeout acotado vía `asyncio.timeout`,
  `process.kill()` en `finally`, sin protocolos de red/shell en los
  argumentos de ffmpeg, límite de bytes de salida.
- Límites exactos de Telegram para `sendVoice` (tamaño máximo de fichero,
  si existe tope de duración propio más allá del límite general de la Bot
  API) **no están documentados en este repo** — a verificar contra la
  documentación oficial de Telegram en el momento de implementar, mismo
  criterio que specs/028 citó la documentación de `getFile`/Voice
  explícitamente como referencia externa revisada en una fecha concreta.
- `TelegramNotifier.send_voice()` (nuevo método propuesto) sigue
  exactamente el patrón ya existente de `send_document` (BL-38): POST
  multipart con `files={"voice": (filename, content, "audio/ogg")}`,
  misma clasificación `TelegramSendError(definitive=...)` (4xx definitivo,
  5xx/transporte/sin `message_id` ambiguo).

## 6. Límite de longitud del texto a sintetizar

Un texto de respuesta largo (listas, resúmenes extensos) sería lento y
caro de sintetizar íntegro. **Tope de caracteres de entrada a TTS**
(nuevo setting, análogo a `document_export_max_markdown_chars`): por
encima del tope, el envío de voz se omite silenciosamente — no se trunca
ni se envía un audio parcial que suene incompleto o engañoso — el texto
completo ya se entregó por su cuenta. Nunca es un error visible al
usuario; es, igual que el acuse de BL-32, una mejora best-effort que
simplemente no aplica en ese caso.

## 7. Moderación de contenido

El texto a sintetizar es la propia respuesta final del Agent, que ya pasó
por toda la disciplina existente de contenido (prompt/instrucciones,
`notifications/markup.py` para el render a Telegram). No se añade ninguna
capa de moderación nueva específica de audio — sintetizar en voz el mismo
texto que ya se envía en texto no introduce un vector de contenido nuevo.
Lo único nuevo a vigilar es el **límite de longitud** (§6), no el
contenido en sí.

## 8. Retención de audio

**Nunca se persisten bytes de audio sintetizado**, ni temporal ni
permanentemente más allá de la vida del propio envío — mismo principio ya
aplicado a la voz entrante en BL-26 ("no se persisten bytes de audio,
nunca"). El texto que origina el audio ya está persistido como
`response_kind='agent_final'` (fuente de verdad); el audio es
100% derivado y transitorio, se sintetiza, se envía y se descarta de
memoria. La fila `logical_responses` de `response_kind='voice'` almacena
solo metadata de entrega (igual que `'ack'`), nunca el audio ni siquiera
cifrado — no hay nada sensible nuevo que proteger ahí más allá del hecho
de que se envió voz.

## 9. Idiomas/voz

Una sola voz/idioma fijo por configuración (español, el idioma principal
de la app) en este primer incremento — no seleccionable por el usuario
todavía. Selección de voz por usuario queda como extensión futura
explícita, no un requisito de este diseño.

## 10. Preferencia por usuario — gap real, resuelto con alcance acotado

**Hallazgo de la investigación:** no existe hoy ningún almacén de
preferencias por usuario en el repo (`src/domain/preferences/` solo tiene
`timezone.py`, y su propio código documenta que la tabla
`ancora.user_preferences` todavía no existe). La voz entrante (BL-26) se
gobierna por un flag global (`TELEGRAM_VOICE_ENABLED`), sin granularidad
por usuario. BL-27 pide "preferencia explícita por usuario" para TTS, pero
construir ese almacén de preferencias desde cero es un ítem en sí mismo,
no algo que este incremento deba asumir como gratis.

**Decisión:** v1 usa el mismo patrón que BL-26 — un flag global
(`TELEGRAM_TTS_ENABLED`, default `false`), sin preferencia por usuario
todavía. Si/cuando exista un almacén de preferencias genérico (useful
también para otras cosas, p. ej. selección de voz, zona horaria real en
vez del `user_timezone` global actual), TTS se vuelve el primer consumidor
natural de un campo `tts_enabled` por usuario — pero construir ese almacén
en este incremento sería alcance no pedido. Se registra como pendiente
explícito, no como una limitación oculta.

## 11. No-objetivos de este documento

- No implementa `GovernedSpeechSynthesisAccess`, `TelegramNotifier.send_voice`,
  el campo `speech_output` ni ningún tool/wiring.
- No decide el proveedor/modelo TTS concreto (OpenAI TTS, ElevenLabs vía
  Gateway, u otro) — requiere spike contra el Gateway real, igual criterio
  que BL-30 Fase 2 (sin Gateway desplegado, no se puede verificar en esta
  sesión).
- No construye un almacén de preferencias por usuario — queda señalado
  como su propio pendiente (§10).
- No fija los límites exactos de `sendVoice` de Telegram — a verificar
  contra documentación oficial al implementar.

## 12. Criterios de cierre de este documento (ya cumplidos)

1. Decisión de disparo (después de `completed`, nunca compite con el
   texto) y de independencia de outbox (`response_kind='voice'`, mismo
   patrón que `'ack'`) explícitas y justificadas con el código real.
2. Ruta gobernada y gasto diseñados como campo hermano aditivo, nunca
   reutilizando `speech` tal cual.
3. Formato de entrega decidido con el propietario (`sendVoice` + ffmpeg).
4. Moderación, retención, longitud e idiomas resueltos o explícitamente
   diferidos con su razón.
5. El gap de preferencia por usuario señalado como pendiente real, no
   ocultado.
6. `tasks.md` con fases futuras, ninguna implementada.
