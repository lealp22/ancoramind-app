# 041 — Publicación manual del evaluador desde GitHub

## Decisión

El propietario autoriza implementar un botón GitHub Actions para actualizar
explícitamente el candidato del evaluador. Ordenador gestionado: no instalar ni
ejecutar Railway CLI local. Runner GitHub remoto efímero sí; no nuevas inferencias,
claves LLM, recursos, migraciones ni despliegues reales por implementar.

## Aceptación

- Sólo `workflow_dispatch` desde main, SHA completo de un commit de main y CI
  push/main del MISMO SHA completada correctamente (jobs quality/integration/
  collector-config). Último intento; error/incompleto/cancelled no despliegan.
- Preparar desde git archive con helper existente/allowlist, sin ejecutar código
  del candidato. Sin `.env`, `.git`, datos, tests ni configuración raíz del bot.
  Root Dockerfile es copia exacta de evals/Dockerfile; huella y hash registrados.
- Secret Railway sólo en paso de despliegue, GitHub environment específico,
  CLI versionada instalada sólo en runner remoto. Token proyecto/entorno NO
  servicio: destino fijo por código y no configurable por inputs. No token cuenta.
- No instalar paquetes del candidato con secretos; no evaluar/SSH ni leer datos
  del volumen. Confirmación explícita de ausencia de campaña/review activa.
- Leer inventario no secreto y rechazar drift en startCommand/volumen/réplica/
  exposición o staged changes. Modificar sólo build SHA/huella/selector del evaluador
  sin redeploy por variable; una subida a servicio existente, no create/reconnect.
- No actualizar pin GitHub vía connect (generaría otro build); publicación por
  upload conserva fuente histórica fijada sin autodeploy. Identidad efectiva es
  paquete/sello/log runtime, no inventar commitHash de un upload.
- Esperar deployment EXACTO devuelto por upload, SUCCESS + running y log idle con
  SHA/huella exactos e inference_started=false. Sólo cola/build no es éxito.
  Comparar otros deployments/volumen antes/después; sin prints de logs arbitrarios.
- Sin retries mutantes, rollback, cancel automático ni replay de campañas.
  Concurrencia1 y cancel-in-progress=false; reporte de incertidumbre/deployment ID
  si timeout. No borrar reservas/reportes; secretos de modelo nunca en workflow.

### Enmienda autorizada — borrador vacío (2026-10-18)

El propietario autoriza sustituir la exigencia de staged=null: el schema Railway
declara `environmentStagedChanges: EnvironmentPatch!` y devuelve un borrador
STAGED incluso con `patch: {}`. Sólo se acepta ese objeto exactamente vacío (no
null, lista ni ramas vacías), id UUID y environmentId correctos. Se cruza con
`environmentPendingWork`: exactamente una fila EnvironmentPatch/staged del mismo
id/entorno, sin hijos ni otra operación. Missing/errors/estado desconocido o en
curso y cualquier contenido bloquean antes de escribir/subir. Ambos controles
se repiten al verificar el despliegue, sin aplicar/descartar el borrador.

Esto cambia deliberadamente el contrato de lectura: se solicita `patch` y se
comprueba exclusivamente en memoria. Un borrador no vacío puede contener secretos;
no se imprime, persiste, adjunta a errores ni incluye en resúmenes. PendingWork
se consulta sólo con metadata, sin `changes`, valores ni actor. No es permiso
para leer variables live, volumen, inferir ni reintentar operaciones mutantes.

### Corrección tras guardar variables sin desplegar — sentinel sin borrador (2026-10-18)

Tras Alt+Deploy, la API del entorno observado devuelve un objeto no-null con
`id: "<empty>"`, `status: "STAGED"`, environmentId exacto y `patch: {}`, junto con
`environmentPendingWork: []`. No es null ni un UUID residual: es el sentinel de
ausencia de borrador, omitido por el contrato anterior. Run39171845184 bloquea
antes de variable set/upload aunque no hay cambios reales. Se acepta esta segunda
combinación **exacta**, manteniendo el caso previo UUID + única fila matching.
No se acepta UUID + lista vacía ni sentinel + fila alguna; tampoco id vacío,
null/missing, otras grafías, patch no vacío/malformado, otro entorno/estado o errores.
Mismo guard pre/post-upload y check_only, sin aplicar/descartar ni imprimir patch.
Fixture saneada y pruebas integrales cubren ambos estados y sus transiciones.

### Contrato de réplicas y comprobación sin subida (2026-10-18)

`ServiceInstance.numReplicas` es legacy/nullable; no equivale por sí solo al total.
Conforme a CLI5.70.0 `service_summary.rs`/`regions.rs`, comprobar primero el
`latestDeployment.meta.serviceManifest.deploy.multiRegionConfig`: una región y
entero uno explícito; sin mapa, count explícito del manifiesto o campo legacy
explícito uno. No default null→1, no aceptar estados malformados/multi-región ni
contradicciones con legacy no-null distinto de uno. Manifest/meta no se reportan.
La evidencia es de la configuración del despliegue consultado, no un lock contra
cambios simultáneos en el dashboard; mantener recheck post-upload e identidad.

Input manual opcional `check_only` (default false): mismo paquete/CI/consentimiento
idle y validaciones preflight, pero retorna `preflight_verified_no_upload` antes
de variable set/up. No es un despliegue ni garantiza permisos de escritura/build.
Errores de inventario separan identidad/start/réplicas/exposición/volumen mediante
reason fijos sin eco de configuración. Sin mutaciones para «arreglar» drift.

### Recuperación sin deployment y diagnóstico seguro (2026-10-23)

El servicio existente puede recuperarse si `latestDeployment` es **null explícito**
y `activeDeployments` es exactamente `[]`. No se interpreta un campo ausente,
objeto vacío, estado desconocido ni despliegue en curso como ausencia segura.
En ese caso se consulta sólo por lectura `environment(id, projectId) { id projectId
config(decryptVariables:false) }`: la API expone un scalar de configuración live,
no una selección de campos del servicio. Puede incluir valores cifrados y configuración
ajena: todo queda sólo en memoria; nunca logs, archivos, resúmenes ni errores crudos.
Se proyectan únicamente deploy/startCommand/multiRegionConfig, volumeMounts y flags
de creación/borrado del servicio fijo. Identidad exacta, comando idle, volumen único
esperado y **una región con entero uno explícito** son obligatorios. Se mantiene
la verificación de inventario, exposición/tracing/cron, borrador vacío y pendingWork.
No default null→1, ni fuentes de evidencia de recuperación para estados desconocidos.
Después de subir sigue siendo obligatorio deployment exacto SUCCESS/RUNNING,
manifiesto válido e identidad idle del candidato; null post-upload nunca es éxito.

Workflow permite el lifecycle script únicamente de `@railway/cli@5.70.0` y ejecuta
`check-cli` sin token antes del paso autenticado. No supone que el aviso npm del
intento anterior probara un bloqueo: npm11.19 sólo avisaba de scripts no revisados.
Fallos de comandos reportan fase allowlist y código de salida entero/null;
timeout/error de arranque no exponen stdout/stderr, argumentos, rutas ni excepciones.
No retries mutantes, fallback de credenciales, nuevos recursos, campaña ni reset
de claves/presupuesto. Es recuperación por upload del servicio/volumen existentes,
no reconnect de la fuente histórica ni rollback automático. Aún requiere CI/nueva
ejecución manual; las pruebas offline no demuestran recuperación en Railway.

Diagnóstico posterior al run39948532960: `command_error_category` contiene sólo
una categoría fija derivada de códigos/prefijos CLI5.70.0, o `unclassified`.
No contiene mensajes/hints/códigos arbitrarios, longitudes, hashes ni valores.
`status --json` conserva reporter humano en errores: se cubren ambas formas.
La clasificación no autoriza repetir, omitir guards ni cambiar token/scope;
authorization_denied no demuestra por sí solo expiración de la credencial.
RAILWAY_NO_TELEMETRY/RAILWAY_NO_AUTO_UPDATE se fijan en el proceso hijo para
evitar envío secundario de errores crudos y mantener el binario fijado.

## No objetivos y límites

No arreglar dispatcher interno Railway, promover golden, configurar presupuesto,
rotar claves, reactivar Wait for CI, publicar imágenes/código en registry, acceder
por túnel o instalar software local. No control distribuido contra shell/operador
que ignore confirm_idle. Token entorno puede afectar otros servicios si se filtra;
control workflow/protecciones GitHub es parte de seguridad, no scope criptográfico
por servicio. Coste build/cómputo Railway y runner GitHub distinto de coste modelo.

## Prueba

Unitarias: gates SHA/ref/event/CI pagination/jobs; paquete/huella; comandos destinos;
inventario drift; log y deployment exacto; fallos no relanzan; workflow sin push/PR,
secret sólo último paso y versiones fijadas. Packaging real offline sobre commit
actual, sin subir artefactos ni comandos Railway reales en local. Ruff/mypy/tests.