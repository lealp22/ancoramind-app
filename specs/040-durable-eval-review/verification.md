# Verificación — specs/040 (2026-10-18)

## Campaña real y corrección local de diagnóstico — estado vigente

- Workflow39173039736/control1c700339 publicó candidato7ea0cf06 en
  deployment085cb777-6e58-489b-93ef-c4596d68e0c7; GitHub summary
  deployed_idle_verified, MCP Online/1RUNNING/0crashed/sin pendingWork contrastados
  antes de campaña. Variables presentes por nombre, sin leer valores.
- Propietario autorizó una campaña5casos/nominal0,10USD/humano/cifrado7d;
  reportó run52759a15ad454050aef8b5c1a9b3f122 stopped/inference_started=true/5calls.
  Reporte metadata específico: single_proposal passed determinista+semántico,
  dos labels pass/3calls/estimated0,0035629999999999999USD/actualnull;
  mixed_read_proposal stopped/InvalidPresentationOutputError/not_evaluated;
  otros3not_started. No asignar costes cero al segundo caso ni total factura exacta.
- Causa histórica acotada: reply_from_run rechazó estructura terminal antes de
  construir la observación, por lo que no hay contenido/trace del segundo caso
  recuperables. No prueba de culpa modelo vs proveedor ni qué variante del guard.
  Pulsar p sí quedó guardado y el primer caso pasó. No fallo de setup demostrado.
- Regresiones rojas: status no exponía estado/error por caso; excepción perdía
  motivo estructural fijo. Incremento sólo harness captura TerminalDiagnostic
  tipado/allowlist sin texto y lo propaga en excepción eval; runner persiste razón,
  contadores/estado y uso no completado. Status revalida metadata con allowlist,
  reporta error histórico sin inventar motivo terminal si no se guardó.
- Caso mixto real del catálogo ejecutado offline con Model Agno guionizado:
  list_todo_lists → list_todo_items → propose_todo_item(priority=high) → present_reply,
  payload/Core/answer separados/veredicto correcto. Esto demuestra capacidad del
  harness, no corrige ni reproduce por sí solo la respuesta probabilística histórica.
- Variantes sin red: ausente/duplicada/noúltima/error/resultadonostring/payload
  inválido; estado AgnoERROR sin atribuir causa; campos privados/adicionales
  rechazados; HTTP503 test anterior sigue sin retries. Prueba integral cifrada
  primer caso3calls/pass+pass → segundo2calls/fallo → restantes no iniciados;
  status tras reabrir store preserva diagnóstico, no respuesta/labels nuevas;
  replay y promoción sin observación rechazados. No I/O canónico ni proveedores.
- Validación focal harness/presentación: **158 passed/1skip** Windows symlink.
  Global `pytest tests/unit/ -q --cov=src`: **1925 passed/1skip**, **80,98 %**;
  `ruff check src/ tests/ scripts/ migrations/` y `mypy src/` (**178 fuentes**)
  limpios. `scripts/run_evals.py`:36casos/6categorías/9provisionales válidos.
  **14 integraciones focales** processor/presentation pasan, DB dedicada
  `ancoramind_test` en127.0.0.1:5432/PostgreSQL Docker local fijada explícitamente,
  sin fixtures en productivas. No se repite toda la suite de integración.
  Diff limpio; warnings CRLF Git/Collector localhost4318 ausente conocidos,
  sin fallos ni cambio de telemetría. Sin cambios prompts/tools/models/proveedor/config productiva.
  Cambia huella de fuentes del harness (cambio evaluable); no aprobación nueva de gasto,
  commit/push/deploy/secretos leídos ni inferencia real por el agente.

## Implementación original — evidencia histórica

Implementación local terminada, sin commit/push del agente, despliegue, claves
nuevas ni inferencia pagada. El candidato Railway db0c59b no se modifica ni se
pretende recuperar contenido que nunca fue persistido. T7/BL-48 reales abiertos.

## Resultado

- **1753 unitarias passed, 1 skipped**, cobertura **80,85 %**.
  Skip nuevo: Windows no concede privilegio de crear symlink en esa prueba;
  rechazo de symlinks también comprobado en contenedor Linux offline.
- **207 integraciones PostgreSQL local passed, 1 skipped** (STT live por diseño).
  No base Railway/Supabase usada como fixtures. Se ejecutaron después del cambio
  de modelo/harness; no hay migraciones ni modificaciones de tablas.
- Ruff global limpio tras ajuste de longitud comentario; mypy src limpio en
  **177 archivos**. Catálogo estático válido36 casos/6 categorías/9 provisionales.
- `scripts/eval_console.py --help` ejecutado, sin credenciales/inferencia.
- Avisos conocidos OTel localhost4318 ausente durante unit tests, sin fallos;
  no se modifica telemetry ni se habilita captura de contenido.

## Pruebas nuevas/regresión

33 unitarias nuevas (incluido skip symlink): store/cipher/clave incorrecta,
secret markers/no secretos exportados, escritura atómica exclusiva, lock y
concurrencia, corrupción/cadena/truncado, retención/purga con tombstone/reserva;
revisión guardada por criterio antes de siguiente lectura, OSError y EOF no
inventan label, reapertura sin providers, historial/corrección y no reautorizar
inferencia tras fail/x; promoción explícita no evaluado rechazado, Agent/juez
distintos, provenance/fixture compatibles y separación development/validation;
renderer Core sobre payload TODO real sintético, validación scope/fecha/prioridad,
nombre propose sin pendiente no aprueba; lifecycle detached y gate aprobado exacto,
worker no restart, clave reutilizable sólo GET/scope/saldo/caducidad sin reset.

`test_eval_durable_campaign.py`: launcher/runner/checkpoints/reserva reales, fake
executor emite uso sintético, worker sin TTY espera en primera respuesta, review
se abre/cierra con evidencia persistida, criteriofail detiene otros4 casos y
replay rechaza antes de inferencia. Ejecutor/HTTP de ese test simulados, no coste.

Prueba Linux Docker con imagen local eval, `--network none`, fuentes actuales
copiadas **sólo a tmpfs /current** y estado tmpfs exclusivo: hijo desacoplado real
lanza reviewer sintético y sobrevive a desconexión/EOF del cliente de review,
guardar criterio0/reabrir store/criterio1 termina mismo hijo; promoción/export
juez y rechazo symlink superados. Sin provider/red/clave real. No demuestra
supervivencia a restart de Railway ni permite reanudar inferencia ambigua.

## Cambios evaluables y límites

- Cambia harness/modelado de tools/salida de observación: payload TODO validado,
  confirmación desde hechos, renderer Core simulado, Unicode legible seguro.
  Cambia fingerprint de fuentes; candidato nuevo requiere commit/CI/aprobación
  y despliegue exclusivamente eval. Prompts/producto y fixtures históricas intactos.
- Retención7d de artefactos brutos cifrados, purga manual explícita (sin cron).
  Golden curado retenido por decisión; exports sólo tras aceptar sanitización.
  No datos personales/documentales reales. Secret detector heurístico no es DLP.
- Revisión puede reabrirse sin coste. Seguir todos pass puede permitir al worker
  vivo avanzar dentro de la campaña aprobada; muerte/timeoutworker no reinicia.
  Espera humana máxima2h; clave reutilizable no amplía plan/presupuesto por sí sola.
- Locks/anti-replay son para un volumen/operador, no distribuidos. Lock huérfano
  requiere inspección manual; PID reutilizado puede no detectar identidad de proceso.
- Journal cifrado/enlazado no es firma externa ni protege contra rollback de
  todos los ficheros con su head. Sin nueva promesa de auditoría inmutable legal.
- Juez actual sólo recibe reply/criterio: export formato compatible incluye aviso
  de contrato insuficiente para criterios de tools/Core. Se conserva evidencia
  enriquecida, no juez ni calibración pagada/automática implementados.

## Pendiente remoto (no ejecutar automáticamente)

Recuperar metadata/revocar por alias de campaña anterior si no confirmado; no
inventar etiqueta del caso interrumpido. Decidir clave exclusiva7d/presupuesto y
configurar una sola vez como secretos del evaluador y Fernet aparte. Revisar SHA/CI
nuevos y publicar imagen/approval nuevos sin borrar reserva histórica. Realizar
una nueva campaña sólo con su decisión exacta; no reutilizar la autorización del
SHA db0c59b para este código. Runbook operativo en [runbook.md](runbook.md).