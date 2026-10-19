# Verificación local — sesión acumulada de evals

## Incidencia session-init y corrección local — 2026-10-19

- Versión32474d5bdb264e0ff5f34a1435de69519b1d16ea publicada por propietario:
  CI39237715770 success; workflow39239239445 deployed_idle_verified,
  huella4d685a9925e6d28e94e0f90e775dc801d7d942e8aad28ea8bd308e6c82792cf2,
  deploymente30e1e80-fc2d-4cfd-b4b7-6652f667f349 Online/1RUNNING/0crashed/
  sin pendingWork comprobados sólo lectura GitHub/MCP. No otro despliegue por agente.
- Propietario reporta session-init --accept-session bloqueado con
  session_prior_execution_not_terminal/inference_started=false. Comprobación metadata
  posterior ejecutada por propietario: current_or_other/stopped y
  pre_session_db0c59b/running. Confirma el caso de orden incorrecto en ese histórico
  excluido; running es checkpoint persistido, no prueba de proceso aún activo.
  No se han exportado respuestas/args/claves ni leído el volumen por el agente.
- Bug reproducido offline: session_history comprobaba estado terminal ANTES de
  excluir PRE_SESSION_SHA=db0c59b. Un checkpoint histórico reservado/en curso (o
  estado ausente) de ese candidato conocido bloqueaba indebidamente la sesión,
  pese al contrato de separarlo de la clave reutilizable. El test previo sólo
  incluía histórico stopped, por lo que no detectaba esta rama.
- Regresión roja6fail/3pass: casos unitarios y recorrido CLI init completos, con
  ambos reportes/marker histórico coexistiendo. Fix mínimo: separar el SHA antiguo
  antes de exigir terminalidad, después de validar fichero/no symlink/tamaño/JSON
  objeto. No reescribir reportes/ledger/markers, inferir pass histórico, cambiar
  saldo, liberar reservas ni conceder replay. Desconocido/7ea0cf06/actual no terminal
  sigue bloqueado; nueva matriz12 variantes lo verifica. JSON no objeto falla fijo.
- Validación: **80 focales sesión/consola passed**; global **1991 passed/1skip**,
  cobertura **81,22 %**, Ruff global/mypy180/diff limpios. Integraciones no repetidas:
  sólo script import/tests/docs; CI previa de32474d5b sí pasó, no equivale a CI del fix.
  Warning conocido Collector localhost4318 ausente; sin cambio telemetría.
- Corrección sólo local, sin commit/push/deploy/inferencia/claves nuevas/lectura de
  secretos. La metadata del propietario confirma el mecanismo; no demuestra éxito
  remoto del fix aún sin publicar. Recheck focal21passed al recibir la evidencia.
  No borrar el reporte running ni editarlo a stopped para eludir el importador.

## Estado

Registro original previo a publicación32474d5b: base3f2e8b89/CI39219285248 verde era sólo diagnóstico.
El incremento inicial se validó localmente:
sin commit/push, CLI Railway local, credenciales leídas, mutaciones remotas, nuevas
claves ni inferencias por el agente. Autorización de gasto vigente0,10 acumulado,
no renovar por intento. No reabre run52759a15 ni inventa su salida faltante.

## Pruebas

- Ledger cifrado/atomic replace/fsync/lock y lease exclusivo. Scope excluye sólo
  diagnóstico/operativa allowlist; cambiar prompts/tools/casos/modelo bloquea.
  No es attestation de equivalencia semántica ni sandbox; código de publicación
  y candidato siguen Git/CI/revisión exacta.
- Importación reportes completos plan/cases, primerpassed/segundo presentación
  inválida con cinco eventos completados → reserva conservadora0,04. Otro error/
  uso incompleto queda uncertain y no replay. Falta/malformed/running/orphan bloquea.
- Reabrir/inicializar no renueva plazo ni límite y no crea clave. Cambio key hash,
  spend negativo/no finito/decreciente, scope/budget/reset/expiry/permisos rechazan.
- Reservas individuales y redondeo a la baja, sin liberación por metadata de coste
  menor/ausente. Baseline del Gateway evita que el gasto preexistente desaparezca.
  Concurrencia dos reservas no sobregira; lease existente no se limpia a ciegas.
- CLI init con acceptanceflag sólo GET/models/keyinfo; prepare no resuelve provider.
  Mismo source claim bloquea aunque cambie subset. Gates internos se ligan a SHA/
  huella/casos reales, no approval.json viejo. Legacy no cambia si no hay sesión.
- Recorrido real SDK/GovernedModel/SafeOpenAILike, HTTP MockTransport: checks pre y
  post en cada POST; agotamiento observado antes segundo GET de keyinfo bloquea
  antes transporte pagado; 503postcheck tras una respuesta consume reserva/error,
  no retry ni siguiente llamada. Otro recorrido de2casos+review cifrada completa
  con0,06 gasto inicial pasa donde la reserva de toda campaña fallaba.
- No cambio prompts/modelo/terminal guard, retries, calendarios/DB productiva.
  Nuevas fuentes implican huella/SHA nuevos para publicación, no nueva autorización
  económica dentro de mismo scope. Causa histórica exacta sigue desconocida.

## Resultado de verificación

- `pytest tests/unit/ -q --cov=src`: **1969 passed, 1 skipped**, **81,22 %**.
  Skip symlink Windows conocido; **44 pruebas nuevas** de sesión, recorrido real
  SDK/HTTP sintético incluido. Harness/presentación focal anterior198passed/1skip;
  últimas4 variantes incluidas en suite global final.
- `ruff check src/ tests/ scripts/ migrations/`, `mypy src/` (**180 fuentes**),
  `scripts/run_evals.py` (**36casos/6categorías/9provisionales**) y diff limpios.
- Paquete allowlist creado desde fuentes locales sin commit (no candidato aprobado),
  sello temporal validado, sin .git/.env/DB, consola empaquetada `--help` muestra
  session-init/session-status. Temporales eliminados. No build Docker ni publicación.
- Integraciones focales processor/presentation intentadas en DB dedicada local
  ancoramind_test/127.0.0.1:5432: **14 errores de setup**, ninguna prueba ejecutada.
  Docker daemon no disponible (named pipe dockerDesktopLinuxEngine ausente),
  PostgreSQL inaccesible. Bloqueo ambiental, no dar por passed ni usar DB remota.
  Última evidencia anterior:14focales pasaron para diagnóstico3f2e8b89, no esta fuente.
- Warning OTel localhost4318 ausente conocido; no fallo unitario ni cambio telemetry.
  SHA/CI exacta de este incremento siguen pendientes. No inferencia real, claves
  leídas, presupuesto externo alterado, campaña anterior relanzada ni CLI local.

### Atención antes de publicar

El import separa explícitamente el candidato histórico db0c59b (claves2h previas a
la nueva sesión) de la campaña7ea0cf06 con clave reutilizable. No borra ni reanuda
ese reporte/evidencia ni lo carga de nuevo al límite vigente. Cualquier otro
histórico no verificable bloquea; no se considera coste cero por estar incompleto.
La clave Gateway actual sigue aportando su gasto acumulado real observado aunque
un reporte provenga de otra clave. Esta separación de procedencia está probada
con ambos reportes coexistiendo; no requiere limpieza manual del volumen.