# BL-8 / BL-48 — Camino incremental de evaluaciones

> Decisión del propietario: 2026-10-17. Primero preparar el motor compartido y
> realizar la campaña humana existente. Web, golden set y juez automático quedan
> registrados para retomarlos, no como requisitos para cerrar T7.

## Alcance y autorizaciones

### Decisión posterior — usabilidad, evidencia durable y revisión recuperable

**Implementación local specs/040 completada:** [contrato](../040-durable-eval-review/spec.md),
[operación reutilizable](../040-durable-eval-review/runbook.md) y
[verificación](../040-durable-eval-review/verification.md). `eval_console.py run`
lanza worker desacoplado y review reabrible, archivo sintético cifrado/autosave
por criterio, propuestas con payload/renderer Core, promoción manual Agent/juez.
No web/juez automático/credenciales/despliegues/inferencias nuevos. Falta setup
remoto único y aprobación del nuevo SHA/campaña; no sustituye resultados históricos.
1753 unitarias/1 skip Windows symlink,80,85 %;207 integraciones/1 STT skip; Ruff/mypy
limpios y prueba Linux offline de hijo desacoplado/review reconectada superada.

El propietario acepta sustituir la operación puntual con dos shells/claves por
ensayo por una preparación reutilizable y lanzamiento sencillo. Solicita guardar
revisiones como base para golden set y trazabilidad. Este incremento se prioriza
antes de otra campaña pagada; modifica la decisión anterior de no persistir
respuestas, **sólo para evidencia del harness con fixtures sintéticas**. No autoriza
captura de conversaciones/documentos reales ni contenido en logs/OTel/reportes
públicos. Clave más duradera y desconexión de consola son problemas distintos.

Propuesta de diseño para desarrollar esa decisión, todavía sin implementar:

- Ejecución y revisión separadas: guardar resultado sintético completo y hechos
  de tools/propuestas antes de pedir la primera etiqueta; reabrir revisión sólo
  lee el artefacto y no llama al modelo. Checkpoint por criterio, no sólo al acabar
  el caso. No repetir inferencia ni reanudar gasto automáticamente tras desconexión.
- Evidencia privada por run/case: input/contexto, salida particionada, argumentos/
  resultados sintéticos necesarios, propuesta con campos y presentación Core,
  checks deterministas, estados/error/costes y trazabilidad de SHA/huellas/ruta/
  snapshot/rúbrica. Conservar casos fallidos y no evaluados sin inventar etiquetas.
- Revisiones: identidad del revisor, fecha, criterio versionado, pass/fail/
  not_evaluated y motivo. Corregir una valoración crea revisión enlazada, sin
  borrar resultado original ni decisión anterior. Valoración humana no otorga
  consentimiento de negocio ni permisos para ejecutar otra campaña.
- Dos productos distintos: archivo de ejecuciones/revisiones y golden set curado.
  Pass y fail son candidatos útiles; promoción humana explícita, versionada y
  deduplicada, nunca automática por etiqueta. Separar regresión del Agent de
  pares respuesta/criterio/etiqueta usados para calibrar jueces; reservar validación
  independiente para evitar evaluar al juez con sus mismos ejemplos de ajuste.
- Corregir evidencia insuficiente del primer caso y mostrar español legible con
  controles de terminal escapados. No pedir al modelo duplicar bloque Core para
  suplir carencias de la interfaz. Fallo de observabilidad/rúbrica no equivale a
  fallo del modelo; not_evaluated sigue siendo diferente de fail.

Pendientes concretar almacenamiento/acceso, cifrado, retención y exportación;
no mantener contenido indefinidamente por defecto ni subirlo todo a Git. Material
seleccionado para golden set será sintético, revisado y sin secretos/datos personales.
Metadata operativa mantiene separación respecto al archivo privado de evidencia.
Las labels que hoy se guardan en reportes no bastan para recuperar la respuesta
que no fue persistida: no reconstruir el caso interrumpido como si fuera evidencia.

La imagen remota histórica continúa sin esa recuperación. No cambios remotos, nueva
clave duradera, inferencia o replay autorizados automáticamente por esta decisión;
duración/presupuesto de credencial se concretarán al implantar la operativa.
Web/juez automático siguen fuera de este incremento salvo decisión posterior.
La secuencia histórica de abajo se conserva como antecedente, no operativa objetivo.

- Mantener los cinco casos de `bl48-campaign-plan.json`; no ampliar a calendario
  ni otras categorías en esta campaña.
- Reserva estimada de **0,10 USD aceptada**. No equivale a autorización de
  ejecución, techo externo verificado ni aceptación de costes de Railway.
- Ejecución elegida: **dentro de la red privada de Railway**, mediante servicio
  temporal separado de `ancoramind-app`. Sin túneles, ngrok ni exposición local.
- El propietario será el revisor humano. Acceso a terminal, recursos, clave
  exclusiva, procedencia del snapshot y aprobación del plan/SHA/huellas aún deben
  resolverse. No crear recursos, claves, despliegues ni inferencias por esta nota.
- BL-8/T7 y BL-48 siguen abiertos; resultados semánticos `not_evaluated`.

**Continuación solicitada después:** el propietario pide avanzar incrementos 1–2.
Implementación local iniciada; no elimina aprobación exacta de SHA/huellas, CI,
límites externos ni presencia del revisor. Operación remota todavía no realizada.

## Ahora: incrementos 1 y 2

### 1. Conservar un motor compartido y preparar la operación puntual por shell

Ya existen `EvalCampaignRunner`, el puerto `CampaignReviewer` y
`TerminalCampaignReviewer`. No rehacer el motor ni duplicar las reglas por canal.
Separar/reutilizar también los controles hoy situados en el lanzador cuando una
segunda interfaz los necesite: aprobación, identidad, presupuesto y anti-replay.
Este motor pertenece al harness de evaluación; no es un nuevo servicio del Core
de negocio ni introduce subagentes en el bot.

Secuencia operativa (aprovisionamiento y comprobaciones sin modelo ya realizados):

1. Arrancar el servicio temporal **sin iniciar evaluaciones automáticamente**.
2. Entrar en una shell interactiva autorizada y comprobar TTY con una simulación
   sin modelo; un visor de logs o comando con stdin canalizado no basta.
3. Lanzar manualmente preflight y, solo tras la aprobación concreta, el script.
4. Revisar criterios de la misma ejecución, sin repetir inferencia para verlos.
5. Conservar reporte metadata-only y estado anti-replay antes de apagar el
   servicio. No relanzar ante resultado incierto ni borrar la reserva para repetir.

Preparación local implementada: imagen exclusiva con catálogo y manifiesto
sellado contrastable con checkout Git/CI externo; no copia `.git` ni secretos.
Arranque idle y estado exigido en mount real. Servicio y volumen exclusivos ya
creados con autorización posterior; arranque remoto recuperado por contexto
privado explícito (no selección de ruta GitHub corregida). El propietario aporta
mount válido/escribible, preflight remoto con identidad correcta y TTY
`console_ready`, sin inferencia ni aprobación. Pendientes clave limitada al alias,
scope/presupuesto externo, comprobación Gateway y aprobación/revisión de campaña.
Evidencia y límite de rebuild en [aprovisionamiento](railway-provisioning.md).
La reserva protege el mismo volumen, no es distribuida.
Sin dominio público, cron ni ejecución pagada en comandos de arranque/reinicio.
Acceso SSH no implica túnel de puertos, pero debe ser permitido en el entorno
del operador; no instalar herramientas ni registrar claves automáticamente.

Interfaz implementada: `p` / `f` / `x` más etiquetas completas, por **criterio**,
sin confirmar acciones del bot. Repregunta ante errata sin inferencia adicional;
vacío/EOF detiene. `--check-console` ejercita el revisor sin modelo ni aprobación.
Procedimiento y límites: [runbook Railway](railway-console-runbook.md).

### 2. Ejecutar y revisar la campaña humana existente

Seguir los gates de [preparación T7](t7-preparation.md): plan y snapshot
identificados, commit limpio/CI del mismo SHA, huellas de fuentes/casos, acceso
autorizado, clave exclusiva y límites externos verificados. Cada caso se ejecuta
una vez con herramientas simuladas; checks deterministas preceden al juicio
humano. Fallo/no evaluado detiene los casos siguientes; sin retry/reanudación.

Registrar evidencia técnica, etiquetas humanas y costes conocidos/desconocidos,
sin contenido en logs/reportes. No declarar éxito general, baseline calibrado ni
cierre de BL-48 solo por completar el lanzador o la revisión parcial.

## Después: incrementos registrados, no implementados ni autorizados para gasto

### Web opcional sobre el mismo motor

Herramienta operativa de evals, no frontend del producto. No bloquea T7. Un panel
permitiría iniciar explícitamente la campaña aprobada, revisar cada criterio y
obtener el reporte. Abrir/recargar la web no debe iniciar ni repetir inferencia.
La interfaz y el tipo de revisor (humano/juez) son decisiones independientes.

Si se expone una URL, publicar **solo el panel**, nunca el Gateway: autenticación,
autorización de revisor, protección CSRF/doble envío/concurrencia, render seguro
del texto y reglas de desconexión/reinicio. No guardar respuestas para revisión
posterior sin decisión explícita de privacidad/retención. No asumir terminal web
ni autenticación nativa incluida en el plan Railway. Requiere incremento propio.

### 3. Golden set humano y versionado

Separar casos del Agent (input/contexto/expectativas) de ejemplos para validar al
juez (respuesta sintética + etiquetas humanas por criterio). No exigir coincidencia
literal de redacción. Crear ejemplos buenos, malos, ambiguos y negativos;
los nueve `provisional_synthetic` actuales no son un golden set validado.
La campaña actual no conserva respuestas: convertir una salida concreta en
fixture requiere decisión explícita, no reconstruirla desde un reporte metadata.

### 4. Piloto y calibración de Jev

Jev es candidato opcional, no dependencia adoptada. Comprobar compatibilidad de
su **Decisions API** con `LLMAccess`/Gateway; no basta cambiar el alias de chat,
ni se permite bypass directo a OpenRouter. Modelo/preguntas/rúbrica versionados,
presupuesto y uso del juez separados del Agent. Calibrar significa contrastar
juicios y ajustar reglas, no entrenar el modelo. Reservar ejemplos de validación
no utilizados para ajustar preguntas/umbrales; medir falsos aprobados y cobertura,
no tratar probabilidades como garantías. Ver [propuesta Jev](../014-agentic-evals/jev-pilot-proposal.md).

### 5. Segunda opinión, todavía con humano

Comparar al humano y al juez sobre las mismas respuestas sintéticas; investigar
desacuerdos y respuestas ambiguas. Un error del juez queda `not_evaluated`, nunca
aprobado. Ninguna nota semántica anula fallos técnicos/de gobernanza.

### 6. Automatización acotada y posibles gates posteriores

Solo tras evidencia suficiente: ejecuciones desatendidas con presupuesto y
disparadores aprobados, métricas/reglas por criterio y revisión humana de dudas.
Cinco casos no garantizan comportamiento general ni reemplazan E2E real.
Definir comparación versionada entre candidatos/baselines: hoy el helper exige
idénticas ruta/revisión/rúbrica/juez; no usarlo sin más para comparar otro modelo.
No habilitar CI pagada, cron ni despliegue automático por esta decisión.