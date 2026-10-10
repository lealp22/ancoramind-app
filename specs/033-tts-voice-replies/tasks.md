# Tasks — specs/033 / BL-27

> Mini-ADR (2026-10-11). **Ninguna tarea de este fichero está
> implementada.** Bloqueado por: Gateway real desplegado (para el spike de
> proveedor TTS, igual que BL-30 Fase 2), y por la decisión de alcance de
> T6 (preferencia por usuario) antes de T3.

## T1 — Runtime config: campo hermano `speech_output`

- [ ] `RuntimeConfiguration.speech_output: SpeechRoutingConfig | None = None`
      (spec.md §4) — mismo tipo que `speech`, campo aditivo.
- [ ] Nuevo valor `"speech_synthesis"` en el `Literal` de
      `LogicalRoute.capabilities`.
- [ ] Validador análogo al de `speech` en `validate_runtime_limits`: ruta
      debe tener la capacidad `"speech_synthesis"`; tarifa > 0 exige
      `cost_governance.daily_budget_usd`/`monthly_budget_usd`.
- [ ] Test de compatibilidad aditiva (checksum no cambia cuando el campo
      está ausente/`None`), mismo patrón que `speech`/`context_budget`.

## T2 — Spike de proveedor (bloqueado por Gateway real)

- [ ] Confirmar qué proveedor accesible vía LiteLLM Proxy expone un
      endpoint `/audio/speech` OpenAI-compatible, coste real por carácter/
      segundo, idiomas/voces disponibles en español.
- [ ] Documentar hallazgos en este spec antes de fijar el alias de ruta
      (mismo criterio que BL-30 Fase 2: sin Gateway desplegado, no se
      puede verificar en esta sesión).

## T3 — `GovernedSpeechSynthesisAccess`

- [ ] Nueva clase en `src/agent/speech_access.py` (o módulo hermano),
      espejo de `GovernedSpeechAccess`: resuelve `speech_output` del
      snapshot, llama a `{base}/audio/speech`, registra uso antes/después
      vía `LlmUsageRepository`, sin reintentos, `failed_ambiguous` por
      defecto.
- [ ] Tope de caracteres de entrada (spec.md §6) — por encima, omitir el
      envío de voz sin error visible.

## T4 — Transcodificación y entrega Telegram

- [ ] Transcodificación a Ogg/Opus vía `ffmpeg` (spec.md §5): proceso en
      directorio temporal, timeout acotado, límite de bytes de salida,
      sin protocolos de red/shell.
- [ ] `TelegramNotifier.send_voice()` — mismo patrón que `send_document`
      (multipart, `TelegramSendError` definitivo/ambiguo).
- [ ] Verificar límites reales de `sendVoice` contra la documentación
      oficial de Telegram (tamaño/duración) antes de fijar los topes de
      configuración.

## T5 — Outbox independiente `response_kind='voice'`

- [ ] Repositorio: `create_voice_response()`/`mark_voice_delivery_outcome()`
      — mismo patrón que `create_ack_response`/`mark_ack_delivery_outcome`
      (BL-32): `ON CONFLICT (interaction_id, response_kind) DO NOTHING`,
      nunca toca `telegram_interactions.status`, `chunk_count=1` siempre.
- [ ] Disparo tras `finalize_response_delivery` (interacción `completed`),
      nunca antes — spec.md §3.
- [ ] Flag `TELEGRAM_TTS_ENABLED` (default `false`), mismo patrón que
      `TELEGRAM_VOICE_ENABLED`.
- [ ] Tests: envío único con flag activo; no duplica en reproceso; un
      fallo de síntesis o envío no afecta el estado `completed` ya
      alcanzado por el texto; texto por encima del tope de caracteres
      omite la voz sin error.

## T6 — Preferencia por usuario (pendiente separado, fuera de alcance inicial)

- [ ] Decidir si se construye un almacén de preferencias por usuario
      genérico (`ancora.user_preferences` o similar) antes o junto con
      TTS, dado que hoy no existe ninguno (spec.md §10) — ítem propio,
      coordinado con cualquier otro consumidor futuro (selección de voz,
      zona horaria real por usuario en vez del `user_timezone` global).
- [ ] Hasta entonces, v1 queda gobernada solo por el flag global.

## T7 — E2E real con Telegram (bloqueado por BL-18)

- [ ] Validar contra una cuenta de Telegram real, mismo criterio que el
      resto del pipeline documental/voz.
