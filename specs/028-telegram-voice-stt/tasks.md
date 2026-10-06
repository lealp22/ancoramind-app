# Tasks — specs/028 / BL-26

## T1 — Alcance, contratos y aceptación (este incremento)

- [x] 5 minutos; respuesta textual; voice original; sin TTS/archivo documental.
- [x] Coste derivado por duración y tarifa versionada, sin techo USD STT manual extra.
- [x] Consentimiento verbal Sí/No ligado a propuesta y principal por Core.
- [x] Contratos propuestos, estados durables, privacidad y matriz V01–V36.
- [x] Identificar dependencia del flag/executor de consentimiento existente.
- [ ] Aprobar límites operativos propuestos (10 MiB), inspector/decoder y timeout
  en T2; no asumir que el benchmark o proveedor ya están seleccionados.

## T2 — Contratos ejecutables y política pura (siguiente incremento)

- [ ] Modelos/Protocol domain/STT sin SDKs físicos; cálculo Decimal de facturación.
- [ ] Tests U V03–V08, V11–V13, V22–V23; parser Sí/No y procedencia diferenciada.
- [ ] Seleccionar inspección determinista de OGG/Opus acotada; documentar dependencia
  sólo tras verificar necesidad/compatibilidad con Windows/Python 3.12 y deploy.
- [ ] No habilitar normalización voz en producción antes del flujo seguro completo.

## T3 — Persistencia y preparación exclusiva

- [ ] Diseño final de subestados/tabla y uso STT; migración + init.sql + tests V33.
- [ ] Claim preparación/transiciones/resultado cifrado/recover sin replay (V17–V19).
- [ ] Retención equivalente al payload, limpieza de temporales y metadata-only V31.

## T4 — Canal y processor con STT fake

- [ ] Normalización voice/procedencia, flag OFF, límites y descarga streaming.
- [ ] Separar voz de documentos y de agent_started; timeout operacional explícito.
- [ ] Captura snapshot/contexto antes de STT y continuidad reservas con Agent.
- [ ] U/I V01–V10, V15, V32 con red/proveedor mockeados.

## T5 — Consentimiento y ejecución

- [ ] Resolver Sí/No antes de Agent; sin callback/comando sintético como control.
- [ ] Evidencia original/current, entrega antes de accepted_at, caducidad/generación.
- [ ] Claims/descartes condicionales y concurrencia (V20–V30).
- [ ] Cerrar executor pendiente en BL-40/specs/023; sin bypass legacy. Documentar
  diagnóstico del flag/botones por separado; voz no exige que aparezcan botones.

## T6 — Acceso STT gobernado físico

- [ ] Verificar docs/compatibilidad actuales del Gateway y proveedor antes de elegir.
- [ ] Config versionada backward-compatible; tarifa/política por duración/alias nuevo.
- [ ] Petición STT, reservas/gasto agregado, ledger, auditoría errores (V11–V16/V19).
- [ ] Un intento end-to-end, sin fallback directo. Tests sin credenciales/inferencia.

## T7 — Validación y piloto (requiere autorización de inferencia/despliegue)

- [ ] Unit suite, integration PostgreSQL, Ruff, mypy y matriz specs/013 afectada.
- [ ] Benchmark sintético/consentido; fijar métricas/umbrales antes de medir.
- [ ] E2E V34–V36 con evidencia metadata-only, ejecución del consentimiento real.
- [ ] Activación gradual explícita, runbook/rollback por flag y cierre de BL-26.