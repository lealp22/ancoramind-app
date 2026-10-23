# Actualizar el evaluador desde el navegador

## Qué queda resuelto

Workflow **Actualizar evaluador**, sólo manual. Railway CLI5.70.0 se instala en
un runner GitHub Linux efímero, **nunca en el ordenador del propietario**.
El SHA elegido sigue siendo decisión explícita; empaquetado/huella/subida/verificación
son automáticos. Publicación no es campaña: arranca en espera, no llama al modelo.

**Primer rollout verificado (2026-10-18):** SHA
`7ea0cf06002d76692f230d189c43e8f9f5e742b1`, CI39163986626 verde,
check_only39164426466 y publicación39165134464 correctos. Deployment
`b4305cc0-3ddd-404e-8dbc-a3b002103b1f`, Online/SUCCESS,1 RUNNING/0 crashed,
volumen conservado y resto de servicios sin cambios según verificación del workflow;
sin inferencia. Setup secreto realizado por propietario. No repetir para esta versión.
Detalle y límites: [verification.md](verification.md). Preparación única inferior
se mantiene como referencia para configurar el mecanismo, no como tarea pendiente.

## Preparación única (navegador)

1. Comitear/subir workflow/helper/tests/docs a `main`; esperar **CI verde**.
   También se exige CI verde del commit que contiene el código de publicación,
   aunque el SHA candidato sea anterior. No reactivar Wait for CI de Railway.
2. En Railway, proyecto **ancoramind-app → Settings → Tokens**: crear un **Project
   Token del entorno production**, con nombre identificativo para publicación evals.
   No usar token de cuenta/workspace, clave Gateway/LLM ni token Telegram.
3. En GitHub, repo **Settings → Environments → New environment**:
   `ancoramind-evals-deploy`. Restringir sus deployment branches a `main`.
   Si el plan lo permite, configurar aprobación humana requerida. Si la protección
   no está disponible en este repo/plan, anotarlo: no asumir que existe.
4. Dentro de ese environment, añadir **environment secret**
   `RAILWAY_EVALS_DEPLOY_TOKEN` con el token creado. No variable pública ni fichero
   Git; no pegarlo en chat, comentarios, inputs del workflow o shell local.
5. Mantener acceso de escritura a main/workflows restringido. Permisos Actions:
   workflow solicita sólo `contents: read` y `actions: read` al GITHUB_TOKEN.
   No permisos de escritura/PR/forks, no secretos en checkout/preparación/npm.

**Alcance real:** el Project Token es de **entorno**, NO exclusivo de un servicio.
Si se filtra o alguien modifica el código de publicación con acceso al secreto,
podría afectar otros servicios del entorno. Destino fijo + código revisado +
protección environment reducen riesgo, no equivalen a aislamiento criptográfico
por servicio. No se crea un proyecto/entorno nuevo ni se migra el volumen para
evitar este límite. Token debe revocarse desde Railway si deja de utilizarse.

Setup de una sola vez, sin CLI en el ordenador. Uso consume build/cómputo Railway
y minutos de runner GitHub según plan; no inferencia LLM. No activar campañas por
el simple hecho de publicar el código.

## Cada actualización

**Si se han añadido secretos/configuración al evaluador:** revisar que sólo afecta
a sus variables y, desde Details de Railway, mantener **Alt** al pulsar **Deploy**
para confirmar sin redespliegue (comportamiento documentado por Railway en
<https://docs.railway.com/deployments/staged-changes>). El contenedor actual no
recibe esas variables hasta el siguiente despliegue. Después iniciar **un nuevo**
workflow de main con el helper corregido y CI verde, nunca «Re-run jobs» del viejo.
Guardar configuración no autoriza campaña ni crea `/eval-state/approval.json`.
No cambiar el pin GitHub ni usar Deploy Latest Commit para aplicar estos secretos.

1. Confirmar que no hay campaña **ni revisión operativa** en curso. Actualizar el
   contenedor mata workers locales al contenedor; evidencia persistida no equivale
   a poder continuar inferencias. Revisar estado desde operativa specs/040 si duda.
2. Copiar el **SHA completo40caracteres** de un commit perteneciente a main cuya
   CI push/main esté completada en verde. No rama, tag, SHA corto o PR-only.
3. Repo **Actions → Actualizar evaluador → Run workflow**.
   - Branch del workflow: **main**.
   - `candidate_sha`: pegar SHA completo.
   - Marcar `confirm_idle` sólo tras comprobar ausencia de campaña/revisión activa.
    - `check_only` es opcional (default desmarcado): comprueba paquete y destino
      sin escribir variables ni subir/desplegar. Resultado esperado en ese modo:
      **`preflight_verified_no_upload`**, no `deployed_idle_verified`.
   - Pulsar **Run workflow**. No push automático ni cron para publicar.
4. Leer resumen del workflow. Éxito es **`deployed_idle_verified`**, con SHA,
   huella, CI run/attempt y deployment ID. `prepared_no_upload` o `uploaded_not_verified`
   **no** significa desplegado/verificado.

Primer candidato posible ya comiteado: `f9e08ae70d37765e5c82ee07d1a478a8488d3295`,
CI39129319862 verde y huella`d5e781673aa037a6cc54d88a6abc088759d54de870f3de06b133a05cc8b2389a`.
El workflow no estará en GitHub hasta el siguiente commit; su propia CI también
debe pasar. Elegir ese nuevo SHA o uno anterior válido es decisión del operador.
No ejecutar helper `publish` localmente; requiere Linux runner y credencial env.

## Qué hace y qué no hace

- Helper de control procede del commit de main que ejecuta workflow; **no ejecuta
  scripts del candidato en el runner ni instala sus dependencias con secretos**.
  Fuente candidata se lee con git archive. Comprueba CI de candidato/control,
  último run/attempt y jobs quality/integration/collector-config del SHA exacto.
- Reutiliza `prepare_eval_build.py`: archivos regulares allowlist, Dockerfile eval
  copiado a raíz e ignore idéntico; no receta/config raíz bot, `.git`, `.env`,
  datos/tests. Hash preparado es del tar/gzip determinista, **no** del tar adicional
  que genere Railway CLI ni del digest final de imagen. Identidad efectiva se
  comprueba de nuevo con el log del contenedor.
- CLI sólo en runner; destinos proyecto/production/servicio evaluador **fijos**.
  No admite cambiar esos IDs desde inputs. Lee inventario metadata, exige réplica1,
  mount del volumen existente `/eval-state`, start idle, sin dominio/cron/tracing,
  sin cambios pendientes ni deployment previo aún construyéndose.
  Réplica verificada por mapa regional explícito del manifiesto (una región/una
  réplica); el campo legacy numReplicas puede ser null. No se sustituye null por
  uno sin evidencia, ni se confunde una instancia RUNNING con configuración.
- Railway conserva un borrador STAGED vacío: no hay que aplicarlo ni descartarlo.
  Helper acepta únicamente `patch: {}` exacto y pendingWork con ese mismo borrador,
  sin hijos ni otra operación. Lee patch sólo en memoria; aunque pudiera contener
  secretos, no lo imprime ni persiste. No basta con «0 cambios» en la UI.
- Escribe sólo `ANCORA_EVAL_BUILD_SHA`, `ANCORA_EVAL_BUILD_SOURCE` y
  `RAILWAY_DOCKERFILE_PATH=Dockerfile` **en el evaluador**, con skip-deploys. No
  lee secretos del servicio ni toca Gateway/claves/config runtime/telemetría.
- Sube una vez el contexto específico y espera **su deploymentId exacto**: SUCCESS,
  instancia RUNNING y log `idle_manual_only`, SHA/huella correctos,
  `identity_source=sealed_image` e `inference_started=false`.
- Comprueba después mismo volumen y IDs de últimos deployments de otros servicios
  sin cambios. Si hay un deploy concurrente ajeno no asegura éxito global; indica
  resultado no verificado sin atribuir causalidad ni tocar ese otro servicio.
- No ejecuta SSH/modelo/tests de integración remotos, no lee `/eval-state`, no borra
  reservas ni reinicia automáticamente una campaña o un build fallido. Permiso de
  publicar candidato no concede aprobación de gasto/inferencia.

**Pin/source Railway:** upload no es GitHub build. Se conserva la asociación
histórica GitHub fijada y no se llama a `connect` (eso dispararía otro build).
La UI puede seguir mostrando el pin anterior; la versión real de este upload se
demuestra con SHA/huella del sello, resumen y logs del deployment devuelto. No
usar *Redeploy from GitHub* para actualizar ni activar autodeploy como atajo.
No se inventa `commitHash` cuando la metadata del upload no lo tiene.

**Contrato de confianza:** el candidato de main se construye/ejecuta en Railway;
CI verde no demuestra que código malicioso sea seguro. Aprobar sólo commits
revisados, especialmente Dockerfile/startup y cambios a workflow/helper. El
GITHUB_TOKEN de lectura no concede autorización al modelo. No hay bypass a las
políticas de software/red del ordenador gestionado.

## Si algo falla

- **Sin staged changes no significa sin pendingWork.** Pueden existir deployments
  NEEDS_APPROVAL de otros servicios tras un push. Caso39248955747/68ae6654:
  bot y collector aguardaban aprobación, mientras el evaluador seguía Online.
  El guard bloquea correctamente aunque el patch sea `{}`. Si no se desean esos
  despliegues, propietario selecciona **Skip** en cada tarjeta Pending del commit
  exacto (dashboard puede indicar contribuidor externo), nunca Remove del activo
  SUCCESS ni Deploy/Approve a ciegas. Verificar pendingWork vacío y lanzar un
  nuevo workflow del mismo candidato/CI; no necesita parche ni nuevo push.
  El helper no cancela ni aprueba otros servicios y no ignora su trabajo pendiente.
- Secreto ausente → configurar environment secret; no instalar CLI local.
- SHA/CI incorrectos → esperar/corregir CI y lanzar manualmente con SHA aprobado;
  no usar un run anterior exitoso para ocultar un último intento fallido.
- `eval_deploy_pending_changes_or_wrong_environment`, drift o deployment en curso:
  inspeccionar Railway; helper **no aplica** staged changes ni arregla config.
  `unmergedChangesCount: null` explícito es válido en production: es metadata de
  comparación entre entornos, no la señal de staged work. Campo ausente, valor
  inválido o contador distinto de cero siguen bloqueando. La consulta independiente
   `environmentStagedChanges` es obligatorio en el schema Railway: exigir null era
   un error del helper, no un problema a resolver pulsando Deploy/Apply. Desde la
    enmienda de specs/041, un borrador STAGED con patch exactamente `{}` pasa sólo
    si es la única fila de pendingWork, mismo id/entorno y sin hijos. Tras confirmar
    variables sin desplegar, también es válido el sentinel exacto `id: "<empty>"`,
    estado STAGED/entorno correcto/patch `{}` y pendingWork `[]`; no UUID + lista vacía
    ni sentinel con filas. El helper antiguo rechaza ese estado legítimo con
    `eval_deploy_pending_work_cannot_be_verified` (run39171845184). No recrear claves,
    borradores o cambios para forzar el UUID: hace falta publicar el fix del helper,
    CI verde y nuevo Run workflow desde main. El candidato puede seguir siendo
    7ea0cf06 con su CI exacta; el código de publicación debe ser el nuevo main.
    Cualquier patch
   con contenido, APPLYING/estado desconocido/operación adicional o respuesta
   incompleta bloquea. Con este borrador vacío no hace falta cambiar Railway:
   publicar el helper corregido, esperar CI verde y lanzar una nueva ejecución
   manual desde main. El SHA antiguo sigue ejecutando el guard antiguo si se usa
   «Re-run jobs». Si hay cambios reales, revisarlos sin aplicar/descartar trabajo ajeno.
- El antiguo `eval_deploy_service_or_volume_drift` agrupaba causas diferentes;
  tras la corrección posterior a b0b6beb9 los reasons son específicos: `eval_deploy_start_command_drift`,
  `eval_deploy_replica_configuration_drift`, `eval_deploy_replica_evidence_unavailable`,
  `eval_deploy_exposure_schedule_or_tracing_drift` o `eval_deploy_volume_drift`.
  El campo legacy numReplicas=null observado no es drift si hay manifiesto explícito
  con una región/réplica. No modificar la escala para forzar ese campo a uno.
  `preflight_verified_no_upload` con check_only es sólo lectura: confirma el
  inventario, no el build ni la autorización del token para escribir/subir.
- Build/subida fallida/timeout → consultar deployment ID del resumen/dashboard.
  Puede haberse iniciado aunque falte confirmación. **No volver a pulsar a ciegas**.
  Sin retries mutantes, rollback o borrado automático. Variables de build pueden
  haber quedado actualizadas aunque falle upload; no ejecutan por sí mismas una
  campaña. Revisar antes de otra publicación.
- Logs crudos/errores CLI se capturan en memoria y no se vuelcan a Actions para no
  exportar contenidos. Resumen sólo metadata y reason estable. Diagnóstico profundo
  queda en Railway privado y con alcance acotado, no exportar evidencia sintética.
- Workflow serializa publicaciones, no bloquea una shell externa. `confirm_idle`
  es una afirmación humana, no un lock distribuido contra campañas concurrentes.
  Cerrar Actions no garantiza cancelar un build ya recibido por Railway.

## Recuperar el servicio tras quedar sin despliegue (2026-10-23)

No crear otro servicio, borrar/recrear el volumen, cambiar claves, reiniciar la
sesión/presupuesto, usar Deploy Latest Commit ni reconnect del pin histórico.
El publicador anterior dependía del manifiesto del último deployment y no admitía
la ausencia de deployment. El incremento local permite recuperarlo con evidencia
explícita de la configuración live y cero activeDeployments, no por defaults.

1. Publicar el helper/workflow corregidos en main y esperar su CI exacta verde.
   No mezclar cambios locales ajenos. El candidato puede ser otro SHA de main con
   su propia CI verde; el código de publicación debe ser la nueva revisión.
2. Nueva ejecución **Run workflow**, SHA candidato completo, confirm_idle sólo si
   no hay campaña/revisión en curso y `check_only=true`. Esperar
   `cli_verified_without_token` y `preflight_verified_no_upload`.
   Evidencia esperada sin deployment: `live_configuration_single_region_no_deployment`.
   Esto valida lectura/configuración, no permisos de escritura ni disponibilidad del build.
3. Si pasa, nueva ejecución manual con el mismo candidato y `check_only=false`.
   Arranca únicamente `eval_service.py` idle. Éxito sólo `deployed_idle_verified`,
   deployment exacto SUCCESS/RUNNING, SHA/huella y `inference_started=false`.
4. Un fallo sigue sin autorizar repetición ciega. Guardar phase/reason/código e ID
   si existe; consultar historial antes de otro intento. No iniciar una campaña
   para «probar» la recuperación. Volumen conservado no certifica su contenido:
   no se consulta ni altera evidencia, ledger o reservas durante publicación.

El preflight lee el scalar `config(decryptVariables:false)` sólo cuando el último
deployment es null explícito. No imprime ni persiste configuración/cifrados ni
variables de otros servicios. Fallan cerrado región/réplica desconocida, volumen
distinto, comando incorrecto, trabajo pendiente o cualquier respuesta incompleta.
No hay lock distribuido contra cambios concurrentes de otro operador.

Diagnóstico nuevo: `phase` separa cli_version/inventory/pending_work/
recovery_configuration/metadata_variables/upload/deployment_poll/idle_identity_logs;
`command_exit_code` es entero o null si timeout/no arrancó el proceso. No es un
mensaje crudo del proveedor. Un fallo en cli_version ocurre sin exponer el token;
no rotar credenciales para arreglarlo. El aviso npm observado con npm11.19 no
demostraba script bloqueado: la causa exacta del intento histórico sigue abierta.

## Referencias

- [GitHub: ejecutar manualmente un workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [Railway: deploy CLI/Project Token](https://docs.railway.com/cli/deploying)
- [Railway: up y salida JSON](https://docs.railway.com/cli/up)
- [Railway: variable set --skip-deploys](https://docs.railway.com/cli/variable)
- [Guía oficial GitHub Actions + Project Token + CLI](https://blog.railway.com/p/github-actions)
- [CLI5.70.0: réplica del manifiesto antes del campo legacy](https://github.com/railwayapp/cli/blob/v5.70.0/src/commands/output/service_summary.rs)
- [CLI5.70.0: campos reales de status](https://github.com/railwayapp/cli/blob/v5.70.0/src/gql/queries/strings/EnvironmentInstances.graphql)
- [Contexto histórico del workaround](../018-agentic-evals-execution-harness/railway-provisioning.md)
- [Ejecución/revisión recuperable](../040-durable-eval-review/runbook.md)