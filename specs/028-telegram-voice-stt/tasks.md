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
- [ ] Claims/descartes condicionales y concurrencia (V20–V30).
- [ ] Cerrar executor pendiente en BL-40/specs/023; sin bypass legacy. Documentar
  diagnóstico del flag/botones por separado; voz no exige que aparezcan botones.

## T6 — Acceso STT gobernado físico

- [ ] Verificar docs/compatibilidad actuales del Gateway y proveedor antes de elegir.
- [x] Config versionada backward-compatible; tarifa/política por duración/alias nuevo.
- [ ] Petición STT, reservas/gasto agregado, ledger, auditoría errores (V11–V16/V19).
- [x] Adaptador single-attempt sin fallback directo; tests HTTP sin inferencia.

T5: ejecutores deterministas para capacidades canónicas existentes y borrado
documental, compartidos por voz/texto/botones; integración/adversariales en
`test_proposal_executor.py`. No proveedor externo de calendario: solo Noop actual.
T6: imagen fijada validada offline mediante `scripts/verify_stt_gateway.py`,
endpoint real del proxy y upstream simulado con un único envío. Config compatible
`openai/<model-id>` + api_base OpenRouter; falta verificar upstream autorizado,
alias y tarifa reales. No dar por cerrado benchmark/piloto ni toda la matriz V.
Inspector limpia temporales en success/error/cancel; SIGKILL requiere tmpfs efímero.

## T7 — Validación y piloto (requiere autorización de inferencia/despliegue)

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
- [ ] Activación gradual explícita, runbook/rollback por flag y cierre de BL-26.