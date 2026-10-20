# Tasks — specs/028 / BL-26

## T1 — Alcance, contratos y aceptación (este incremento)

- [x] 5 minutos; respuesta textual; voice original; sin TTS/archivo documental.
- [x] Coste derivado por duración y tarifa versionada, sin techo USD STT manual extra.
- [x] Consentimiento verbal Sí/No ligado a propuesta y principal por Core.
- [x] Contratos propuestos, estados durables, privacidad y matriz V01–V36.
- [x] Identificar dependencia del flag/executor de consentimiento existente.
- [ ] Aprobar límites operativos propuestos (10 MiB), inspector/decoder y timeout
  en T2; no asumir que el benchmark o proveedor ya están seleccionados.

## T2 — Contratos ejecutables y política pura (implementado localmente)

- [x] Modelos/Protocol en `src/domain/speech/`, sin SDKs físicos; cálculo Decimal
  con redondeo racional exacto, independiente de precisión Decimal ambiental.
- [x] Tests de contratos/política U V03–V08 (parciales, sin decoder/stream real),
  V11–V13, V22–V23; parser vocal independiente y procedencia diferenciada.
- [x] Seleccionar `ffprobe`/FFmpeg como candidato de inspección física; ver
  `inspection-design.md`. Sin binario disponible ni nueva dependencia instalada:
  verificación real Windows/container y decoder quedan pendientes de T4.
- [x] No habilitar normalización voz ni modificar consentimiento escrito/runtime.

## T3 — Persistencia y preparación exclusiva

- [x] Tabla `voice_preparations`, metadata/reserva/intención STT durable; migración
  0011 + init.sql equivalente + tests fresh/upgrade/downgrade validados en PostgreSQL.
- [x] Claim preparación/transiciones/resultado cifrado/recover sin replay;
  tests PostgreSQL de persistencia/concurrencia/recuperación validados (2026-10-06).
- [x] Sin columna audio; cifrado/transcripción con expiración <=24 h, limpieza
  terminal por trigger y purge explícito user-scoped. Ambiguos <=7 días y sin
  prolongar plazo existente. SQL parametrizado; repr sin ciphertext.
- [x] Ejecutar pruebas PostgreSQL/migraciones: 13 pasan; suite integration completa
  109 pasa. T3 validado a nivel persistencia, sin afirmar E2E STT/Agent operativo.
- [x] Integrar recovery/purge con lifecycle en T4, identificando dueño muerto;
  metadata-only/limpieza de temporales reales V31 se verifican al añadir inspector.

## T4 — Canal y processor con STT fake

- [x] Normalización voice/procedencia, flag OFF, límites y descarga streaming.
- [x] Separar voz de documentos y de agent_started; timeout propuesto 60 s,
  configurable hasta 120 s y limitado por el presupuesto de ejecución compartido.
- [x] Captura snapshot/contexto antes de STT y continuidad reservas con Agent.
- [x] U/I de canal, streaming, preparación, duplicados, cancelación y regresión.
  Inspección/STT son simulados: no afirmar cobertura física completa V01–V10/V31.
- [x] Inspector/decoder físico y pruebas reales/temporales: 12 pasan en Docker.

Recovery adquiere bloqueo transaccional PostgreSQL en sesión dedicada; mientras
el worker mantiene su conexión, otra instancia no cierra su preparación. El
bloqueo se conserva hasta completar el flujo/claim del Agent; muerte de conexión
permite cierre sin replay. Purge también funciona con voz OFF desde lifecycle.
El bootstrap rechaza VOICE_ENABLED=true hasta disponer de adaptadores físicos;
no existe fake STT en producción. Sí/No vocal se responde sin Agent ni ejecución
hasta T5; comandos/callbacks transcritos nunca se interpretan como control.

## T5 — Consentimiento y ejecución

- [x] Resolver Sí/No antes de Agent; sin callback/comando sintético como control.
- [x] Evidencia original/current, entrega antes de accepted_at, caducidad/generación.
- [ ] Claims/descartes condicionales y concurrencia (V20–V30). **Parcial
  (2026-10-11, unit):** V27/V29/V30 — propuesta ajena/reenviada/editada/
  mezclada, executor apagado o sin ejecutor determinista, y el guardado de
  evidencia (nunca desde documentos/historial) — cubiertos en
  `tests/unit/test_voice_consent_handling.py` (15 tests) a nivel de
  `InteractionProcessor._handle_voice_consent`, mockeando los repositorios.
  **V25/V26/V28 siguen pendientes** — son carreras reales de PostgreSQL
  (dos «Sí» concurrentes, generación/caducidad cambiando mientras STT
  procesa) que exigen el locking real de
  `ActionProposalsRepository.resolve_voice_consent`; no se pueden cubrir
  con mocks sin fingir el resultado.
- [x] Cerrar executor pendiente en BL-40/specs/023; sin bypass legacy. Documentar
  diagnóstico del flag/botones por separado; voz no exige que aparezcan botones.

**Sincronización de doc (2026-10-09):** este checkbox seguía sin marcar aunque
el executor ya está cerrado desde la actualización del 2026-10-06 (ver nota de
T5 más abajo): `_execute_claimed()` (`src/domain/interactions/processor.py:924`)
ejecuta vía `ProposalExecutor` (`src/domain/actions/executor.py`) para los tres
caminos de confirmación — botón/ID (`_claim_and_report`), «Sí» a secas
(`_resolve_bare_confirmation`) y «Sí»/«No» por voz (`_handle_voice_consent`) —
sin que ninguno pase por el Agent/LLM. `SUPPORTED_MUTATIONS` cubre notas,
vehículo+mantenimiento, recordatorio+snooze, evento de calendario y las seis
mutaciones de TODOs; `ProposalExecutor.SUPPORTED` añade `delete_document`.
No se encontró ningún camino alternativo que ejecute una propuesta `confirmed`
sin pasar por este executor.

## T6 — Acceso STT gobernado físico

- [ ] Verificar docs/compatibilidad actuales del Gateway y proveedor antes de elegir.
- [x] Config versionada backward-compatible; tarifa/política por duración/alias nuevo.
- [x] Petición STT, reservas/gasto agregado, ledger, auditoría errores (V11–V16/V19) — nivel unit.
- [x] Adaptador single-attempt sin fallback directo; tests HTTP sin inferencia.

T5: ejecutores deterministas para capacidades canónicas existentes y borrado
documental, compartidos por voz/texto/botones; integración/adversariales en
`test_proposal_executor.py`. No proveedor externo de calendario: solo Noop actual.
T6: imagen fijada validada offline mediante `scripts/verify_stt_gateway.py`,
endpoint real del proxy y upstream simulado con un único envío. Config compatible
`openai/<model-id>` + api_base OpenRouter; falta verificar upstream autorizado,
alias y tarifa reales. No dar por cerrado benchmark/piloto ni toda la matriz V.
Inspector limpia temporales en success/error/cancel; SIGKILL requiere tmpfs efímero.

**Auditoría de errores V14/V16/V19 (2026-10-08, nivel unit):**
`tests/unit/test_voice_preparation_service.py` (9 tests nuevos) ejercita
`VoicePreparationService.prepare()` extremo a extremo con repo/inspector/STT
mockeados — antes sólo estaba cubierto el cifrado/repositorio, nunca el método
completo. V14 (presupuesto agregado agotado vía
`ExecutionBudget.reserve_model_call`): cero peticiones STT, fallo no ambiguo
(nada se envió). V16 (timeout y fallo de Gateway tras enviar): ambos quedan
`ambiguous=True` con exactamente un intento (`assert_awaited_once`), sin
reintento. V19 (`persist_transcript` devuelve `None` tras STT exitoso): queda
ambiguo sin repetir la llamada STT. Además se cubrieron `call_id` no
coincidente (nunca se persiste), fallo de `mark_downloaded` (controlado, no
ambiguo) y "otro worker ya reclamó la preparación" (retorna `None` sin
excepción). De paso se confirmó que `evaluate_cost_governance` ya se evalúa
antes de cada run de voz vía `prepare_execution_context`
(`src/domain/interactions/processor.py:487`) y que `GovernedSpeechAccess`
(`src/agent/speech_access.py`) ya persiste en el ledger (`LlmUsageRepository`)
antes de enviar y al finalizar — T6 estaba más avanzado de lo que marcaba el
checkbox; faltaba la cobertura de test de esos caminos de error, ya añadida.
949 unit tests passing, Ruff y `mypy src/` limpios (mypy no cubre `tests/`,
igual que en el resto del repo). **Pendiente de infra:** V17/V18/V20–V30
(concurrencia/recuperación real) requieren PostgreSQL — no se tocan aquí.

**Verificación de docs/compatibilidad Gateway/proveedor (2026-10-08, parcial —
sin credenciales/infra):** confirma y refina la nota ya existente arriba.
(1) El adaptador nativo `openrouter/` de LiteLLM Proxy **no** soporta
`/audio/transcriptions` — la lista de proveedores documentada para ese
endpoint es `openai, azure, vertex_ai, gemini, deepgram, groq, fireworks_ai,
ovhcloud, mistral` (sin OpenRouter). La ruta actual del proyecto
(`openai/<model-id>` + `api_base` apuntando a OpenRouter, ya usada en
`scripts/verify_stt_gateway.py`) es la elección correcta, no un atajo: usa el
adaptador genérico `openai` de LiteLLM (cliente oficial de OpenAI, que añade
automáticamente los endpoints relevantes incluido `audio/transcriptions`)
contra un `api_base` compatible, en vez del adaptador dedicado que no
cubre audio. (2) OpenRouter sí expone un endpoint STT compatible con el
formato OpenAI (SDK oficial `docs/client-sdks/{python,typescript,go}/sdks/
stt/`), con `create_transcription`/`create_transcription_multipart`, límite
documentado de **25 MB** por archivo (holgado frente al tope propio de 10
MiB de `SpeechInputPolicy`), `response_format` `json`/`verbose_json` y
parámetros opcionales (`language`, `diarize`, `keyterms`, `temperature`,
`timestamp_granularities`) que el adaptador actual no usa (minimalista a
propósito). El identificador de modelo exige prefijo de proveedor, ej.
`openai/whisper-large-v3` — coincide exactamente con el doble prefijo que ya
usa `verify_stt_gateway.py` (`openai/openai/whisper-large-v3`: el primer
`openai/` selecciona el adaptador de LiteLLM, el segundo es el slug del
modelo en el catálogo de OpenRouter). **Sigue sin verificar** (requiere
credenciales/infra, fuera de alcance sin autorización): si el upstream real
de OpenRouter acepta ese `api_base` genérico sin rechazar la petición,
tarifa/latencia reales de `whisper-large-v3-turbo`, y si LiteLLM Proxy añade
algún comportamiento propio no documentado al reenviar audio multipart. No se
ha fijado ni publicado ningún alias de Gateway para `speech` (no existe en
`gateway/litellm-config.yaml` todavía) — queda pendiente de decisión conjunta
con el benchmark de T7.

## T7 — Validación y piloto (requiere autorización de inferencia/despliegue)

- [x] Autorización ampliada del propietario para audio personal/Telegram/producción
  MVP (2026-10-07); supersede alcance de privacidad inicial, no gates técnicos.
- [ ] Validar en PostgreSQL aviso durable ante fallo STT ambiguo y completar aviso
  tras recuperación si el proceso cae antes de persistir outbox; nunca retranscribir.

- [x] Registrar autorización explícita del propietario (2026-10-07) para un
  smoke con voz artificial vía OpenRouter y aceptación de privacidad acotada.
  Sin audio personal/Telegram/producción; gates públicos en `preflight-smoke.md`.
  No implica ejecución ni tarifa/Gateway/credenciales ya verificados.

Preflight público y smoke opt-in preparados (2026-10-07): ver `preflight-smoke.md`.
HTTP simulado + ledger/preparación PostgreSQL validados. Privacidad, tarifa final,
inferencia upstream y coste real aún pendientes; no activar opt-in implícitamente.

- [ ] Unit suite, integration PostgreSQL, Ruff, mypy y matriz specs/013 afectada.
- [ ] Benchmark sintético/consentido; fijar métricas/umbrales antes de medir.
- [ ] E2E V34–V36 con evidencia metadata-only, ejecución del consentimiento real.
  V34 parcial (2026-10-20, ver `verification.md`); V35 planificado sin ejecutar:
  `v35-e2e-plan.md`; V36 abierto.
- [ ] Activación gradual explícita, runbook/rollback por flag y cierre de BL-26.