# 040 — Evaluaciones recuperables y golden set curado

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