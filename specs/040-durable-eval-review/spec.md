# 040 — Evaluaciones recuperables y golden set curado

> **Enmienda posterior specs/042:** el propietario autorizó sesión acotada con
> límite0,10USD **acumulado**, no permiso repetido por SHA. El nuevo modo opt-in
> implementa ese contrato con mismo scope/key/ledger y reserva por caso, manteniendo
> manualidad/anti-replay/CI. Las exigencias por candidato de esta spec describen el
> modo legacy; no imponerlas como nueva ronda de consentimiento dentro de sesión.
> Ver [specs/042](../042-eval-validation-session/spec.md).

## Decisión y alcance

El propietario aprueba el incremento local de usabilidad y conservación de
evidencia/revisiones sintéticas. No nueva inferencia, despliegue, credencial ni
ampliación de presupuesto por implementar. Sustituye para este modo la prohibición
anterior de persistir respuestas: sólo artefactos privados cifrados, no logs/OTel.
El intento interrumpido de db0c59b no se reconstruye ni se etiqueta retroactivamente.

## Contrato

1. Motor EvalCampaignRunner/LLMAccess existente, una ejecución por plan/candidato,
   dominio y repositorios productivos intactos. La revisión no llama a proveedores.
2. Antes del humano, evidencia durable: caso/contexto/rúbrica, respuesta, hechos
   sintéticos de tools/propuestas, renderer Core real sobre payload sintético,
   checks deterministas y procedencia/uso metadata. No secreto de Gateway/cifrado.
3. Archivo en volumen privado, Fernet independiente del bot, eventos inmutables
   secuenciales autenticados/enlazados, escritura exclusiva y fsync, lock por
   operación. Reportes públicos sólo allowlist metadata. Retención7 días por
   defecto, purga explícita conserva tombstone/reserva para impedir replay.
4. Ejecutor desacoplado de SSH (worker local al contenedor, sin cron/web/puertos):
   arranque idle, lanzar explícitamente. Desconectar revisión no relanza inferencia.
   Worker espera revisión guardada; si muere, estado incierto sin restart/replay.
5. Cada criterio guarda inmediatamente reviewer/time/label/comment; correcciones
   enlazan revisión previa. Evidencia no cambia; pass/fail/no evaluado separados.
   Sólo pasar todos los criterios permite siguiente caso; fail/x detiene como hoy.
6. Golden set NO automático: promoción manual con aceptación sintético/sanitizado,
   conjunto Agent separado de conjunto juez, versión/contenido/run/review ligados.
   Juez sólo criterios pass/fail evaluados; no promover no evaluados. Artefacto
   exportable para Git sólo tras revisión; no entrenamiento/calibración automática.
7. Consola Unicode legible con controles/bidi/format escapados; nombres de tools
   no prueban propuesta. Guardar payload real de simulación y comprobarlo; cero
   escritura canónica. No inventar campos esperando leerlos del input natural.
8. Config inicial reutilizable: secretos en env del servicio, no en argv/reportes;
   generar y configurar clave exclusiva7d es operación posterior del propietario.
   Aprobación exacta del nuevo SHA/huellas/plan y contenido sintético por candidato;
   existencia de clave no autoriza gasto ni crea aprobación al arrancar.

## No objetivos

Panel web, juez automático, acceso personal real, DB nueva, CI pagada, retomar
inferencia ambigua, prometer determinismo del modelo o techo exacto de factura.
No sustituir una prueba de Core/Telegram E2E por el renderer simulado del harness.

## Prueba mínima

Interrupción tras respuesta y tras un criterio; reabrir sin modelo y sin perder
labels; cambios históricos; corrupción/clave incorrecta/symlinks/concurrencia;
checkpoint antes de humano incluso fallo técnico; payload incorrecto/trivial no
cuenta propuesta; renderer fecha/prioridad; golden Agent/juez distintos sin
secretos/no evaluados; aprobación y replay preservados; worker idle/detach sin
consola y tests sin inferencia real.

## Incremento local — diagnóstico terminal seguro tras campaña real (2026-10-18)

La campaña autorizada del candidato7ea0cf06, run52759a15ad454050aef8b5c1a9b3f122,
pasó el primer caso y se detuvo en el segundo con InvalidPresentationOutputError.
La observación se guardaba después de validar el cierre, por lo que el segundo
caso no conserva respuesta ni hechos terminales recuperables. No reconstruirlos.

El incremento captura únicamente metadata estructural antes de propagar el rechazo:
reason fijo (`missing_terminal`, `multiple_terminals`, `terminal_not_last`,
`terminal_tool_error`, `terminal_result_not_string`, `invalid_terminal_payload`),
número de herramientas/presentaciones y estado Agno normalizado. El runner añade
llamadas registradas y número de eventos de uso no completados por caso, aunque
execute falle. Se conserva en checkpoint/journal cifrado; status publica sólo la
proyección revalidada, estado técnico/semántico y clase de error allowlist.

No guarda texto rechazado, mensajes, argumentos, resultados de tools ni excepciones
del proveedor; no amplía captura de contenido. La excepción sigue siendo subtipo
del rechazo terminal; reporte conserva la clase InvalidPresentationOutputError.
reply_from_run, terminal tool, prompts/providers y permisos/retries no cambian.
Estado ERROR/eventos de uso fallidos son hechos, no prueba de causa/modelo culpable.

Compatibilidad histórica: sin diagnóstico guardado, status devuelve null y nunca
inventa el motivo. No crea observación, etiqueta ni golden del caso fallido. Cambia
huella del harness: nuevo SHA/CI/publicación y aprobación independiente antes de
cualquier ejecución real; la autorización única anterior está consumida. No
repetir caso/campaña para verificar este cambio offline ni borrar reservas.