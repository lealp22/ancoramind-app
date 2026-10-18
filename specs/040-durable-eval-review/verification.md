# Verificación local — specs/040 (2026-10-18)

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