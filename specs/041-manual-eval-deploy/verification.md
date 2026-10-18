# Verificación — 2026-10-18

## Primer rollout real verificado — estado vigente

- Candidato y código de publicación:
  `7ea0cf06002d76692f230d189c43e8f9f5e742b1` (main).
  [CI39163986626](https://github.com/lealp22/ancoramind-app/actions/runs/39163986626),
  attempt1, completed/success comprobado por GitHub sólo lectura.
- [Check-only39164426466](https://github.com/lealp22/ancoramind-app/actions/runs/39164426466):
  success, `preflight_verified_no_upload` a20:41:17Z, sin inferencia.
- [Publicación39165134464](https://github.com/lealp22/ancoramind-app/actions/runs/39165134464):
  success, `deployed_idle_verified` a20:52:25Z, inference_started=false.
  Resumen aportado por propietario y contrastado con log público del workflow.
  Deployment exacto **`b4305cc0-3ddd-404e-8dbc-a3b002103b1f`**;
  preflight_verified=true, replica_evidence=deployment_manifest_single_region,
  other_services_unchanged=true, volume_preserved=true.
- Identidad de fuentes comprobada por el workflow mediante sello y log idle:
  `3c0585730a9e30f641a468d1e5e388498fc6328d2368cc8403ee94e089de31f8`.
  SHA256 archivo preparado:
  `6bdf34f623b92e20841896d94c82de69d2d4139a9d2f8e95a85a5fc9f5e17cb4`.
  Este hash no es digest de imagen ni hash del tar adicional de Railway CLI.
- Comprobación independiente MCP sólo lectura: evaluador **Online/SUCCESS**, mismo
  deployment, **1 RUNNING / 0 crashed**, sin issues ni pendingWork. Volumen existente
  b88f8940-dd92-430f-8d6f-a4adb2b455c8,100MB, montado en `/eval-state`; sin dominios,
  TCP proxy, cron ni tracing. No se leen variables, volumen o evidencia sintética.
- Pin GitHub histórico sigue db0c59b en config por diseño: upload no reconecta
  source ni inventa commitHash. La versión efectiva del contenedor es el nuevo
  SHA probado mediante paquete/sello/log, no ese pin de la UI.
- Se cierra **publicación manual del evaluador specs/041**, no campaña BL-8/BL-48:
  no inferencia, clave exclusiva nueva, recuperación histórica ni validación de
  revisión durable remota por este despliegue. No repetir el workflow para cerrar
  esta evidencia. Sólo docs actualizadas localmente; sin mutaciones Railway,
  instalación/ejecución CLI local, dispatch o inferencia por el agente.

## Revisión integral tras b0b6beb9 — incremento anterior

- Run [39160757789](https://github.com/lealp22/ancoramind-app/actions/runs/39160757789),
  19:52:47–19:53:03Z, candidato/publicación
  `b0b6beb9b2826d0a8ddca26bc735095979f73d80`, CI39160304725. Preparación y guard de
  borrador vacío pasan; `eval_deploy_service_or_volume_drift` bloquea antes de
  variable set/upload. Evaluador sigue en deployment54892e8d/db0c59b.
- Causa probada read-only API: `serviceInstance.numReplicas=null`, pero
  `latestDeployment.meta.serviceManifest.deploy` tiene numReplicas=1 y
  multiRegionConfig=`europe-west4-drams3a:{numReplicas:1}`. Start correcto,
  sin cron/domains/tracing; volumen correcto/no eliminado; SUCCESS, una instancia
  RUNNING. No drift real observado. El fixture sintético previo sólo usaba count=1.
- Investigación web: guía oficial recomienda Actions/Project Token/railway up;
  CLI5.70.0 `service_summary.rs` consulta mapa de regiones del manifiesto antes de
  legacy. `EnvironmentInstances.graphql` sí pide meta e instances; `deployment list`
  sí devuelve lista JSON; `up --detach --json` devuelve deploymentId sin esperar
  build; `logs --json --lines` usa NDJSON con message/atributos. Variable set
  skip-deploys/flags de destino y Dockerfile root/ARG contrastados con fuente/docs.
- Fix local: evidencia explícita de una región/réplica desde manifiesto; legacy
  explícito uno como compatibilidad, nunca null→1 por defecto. Missing/malformed/
  multi-región/múltiple/legacy contradictorio bloquean. Diagnósticos de inventario
  específicos/allowlist sin eco. Nuevo check_only opcional (default false) ejecuta
  preflight y retorna `preflight_verified_no_upload` sin variable set/up.
- Fixture `tests/unit/fixtures/railway_eval_inventory.json`: proyección saneada de
  API con mismos campos seleccionados por CLI5.70.0, no stdout capturado ejecutando
  CLI. Otros servicios reducidos a ids, meta sólo réplica; sin variables/logs/prompt.
  Regresión falla antes del fix con el error real. Prueba completa usa Railway
  adapter y subprocess mocked con contratos JSON reales, no FakeRailway.status;
  verifica hasta SUCCESS/running/log identidad y guard pre/post; rama check_only
  sólo hace --version/status/api, drift nunca escribe. No prueba token de escritura.
- Prueba real **offline**, sin inferencia: git archive b0b6beb9, allowlist,
  fingerprint `50466b7d36c045501019c3fc3855561f263f1f6d7f36d1bfd0cdcc8aa2057a19`,
  sello/identidad verificados. Docker ejecuta ese contexto montado read-only con
  dependencias de imagen local `ancoramind-evals:t7-root-context`, sin red, sin
  credenciales/env-file y tmpfs temporal. Proceso vivo/log idle exacto superados;
  contenedor eliminado y temp borrado. **No build Dockerfile fresh**: falta base
  python3.12-slim local; no atribuir al candidato digest de imagen cacheada.
- Alternativas investigadas: volver a source GitHub requiere reabrir fallo
  histórico de selección Dockerfile; GHCR por digest evita upload pero añade
  registry/credenciales/cambio source y requiere decisión separada (no ejecutado).
  Mantener vía oficial CLI runner evita esa migración, no prometer que verificación
  offline cubra permisos/dispatcher/build remoto. No CLI local, dispatch, subida,
  secretos consultados, modificación del volumen ni inferencia en esta sesión.
- Validación final del fix: **127 focales**, **1867 unitarias/1 skip**, **80,85 %**
  cobertura, Ruff global y mypy177 sin errores. Se incluyen 17 variantes adversas
  de manifest/réplicas, count explícito sin regiones, recorridos del adapter hasta
  éxito y check_only sin mutaciones, reasons específicos sin eco y rama de CLI
  flag. No integraciones repetidas al no cambiar src/schema; CI exacta del nuevo
  commit sigue requerida. Commit/push y primer rollout aún pendientes.

## Corrección autorizada del borrador vacío — incremento anterior

- Run [39157815349](https://github.com/lealp22/ancoramind-app/actions/runs/39157815349),
  SHA `da351546a1c53b61985b8184efe289b118336c05`, CI39150725443 verde: preparación
  correcta, bloqueo antes de mutaciones por existencia del mismo borrador STAGED.
- Introspección read-only de la API pública Railway `/graphql/v2`: campo
  `environmentStagedChanges` devuelve **EnvironmentPatch!**, no nullable. Por tanto
  el guard «cualquier respuesta no-null bloquea» no puede funcionar con ese contrato.
  No hay evidencia para exigir al propietario eliminar un registro residual.
- Consulta acotada con sesión navegador existente comprobó patch exactamente `{}`
  del id `3f9536e6-9ad4-4b64-bd0b-2876f1c7b724`. Se procesa en memoria y sólo se
  devuelve el booleano de vacío; no imprimir ni persistir patch/valores. Query
  conjunta metadata pendingWork confirma única fila EnvironmentPatch/staged mismo
  id y entorno, children=[]; no operaciones adicionales. No mutación Railway.
- Propietario autorizó explícitamente esta nueva comprobación, con pruebas y sin
  deploy. El helper acepta sólo ese caso estricto, no patch=null/lista/cadenas ni
  ramas vacías como `services:{}`. Bloquea ausente/error/inconsistencia/estado no
  STAGED, contenido real, hijos/otro trabajo; repite guard pre/post publicación.
  No consulta `changes`/actor/variables live ni escribe summary con contenido patch.
- Cambia el contrato anterior de lectura de metadata solamente. Las secciones
  históricas inferiores registran lo probado entonces, no el comportamiento actual.
  El borrador vacío no requiere Apply/Deploy/Discard. Nuevo commit/push/CI y nueva
  ejecución manual pendientes; no re-run del workflow viejo, subida ni inferencia.
- Validación: regresión STAGED/`{}` falló antes del fix con contadores cero/null;
  después **92 focales** (helper + packaging), **1832 unitarias/1 skip**, cobertura
  **80,85 %**, Ruff global y mypy177 limpios. Guard real contrastado por query
  read-only: patch vacío, mismo entorno y única fila sin hijos; no se usa CLI local
  ni se publica. Tests verifican rechazo de contenido/tipos/estados/campos
  desconocidos, otras operaciones/hijos, recheck post-upload sin retry, y ausencia
  de valores sintéticos privados en stdout/stderr/summary. No cambia src/schema;
  integraciones no repetidas. Aceptación remota de publicación aún no demostrada.

## Intentos Actions y corrección del contador nullable

Registro histórico de la corrección anterior; su exigencia de staged=null queda
sustituida por la enmienda anterior y specs/041/spec.md.

- SHA `7957ba70e7eda09014594889befd9ef52e1a9005`: definición aceptada y
  preparación CI/archivo correctas. Run `39146799866` bloqueado por token ausente;
  propietario configuró el secreto. Run `39149868659` (17:30:07–17:30:22Z)
  bloqueado por `eval_deploy_pending_changes_or_wrong_environment`, antes de
  modificar variables o subir código. No inferencia.
- Diagnóstico por lectura API con sesión de navegador ya autenticada, sin CLI
  local ni extraer credenciales: production devuelve `unmergedChangesCount: null`.
  La query Project del CLI fijado 5.70.0 incluye ese campo nullable. El fixture
  anterior sólo usaba cero; `None != 0` rechazaba el entorno legítimo.
- Corrección local: aceptar exclusivamente null explícito o entero cero;
  ausente/malformado/no-cero sigue bloqueando. Se conserva íntegra la consulta
  independiente `environmentStagedChanges { id status }`, sin leer patch/secretos.
  STAGED/APPLYING no-null sigue bloqueando, sin excepciones por cero cambios.
- Estado posterior a aquel intento: `environment-status` y lectura API confirman
  patch `3f9536e6-9ad4-4b64-bd0b-2876f1c7b724`, STAGED, iniciado 17:33:47.047Z,
  0 cambios según pendingWork. `get-staged-changes`/`describe-environment` en cambio
  muestran null/sin cambios: no confundir presentación vacía con ausencia de
  registro. Origen no confirmado; creado después del run, no atribuido al helper.
  No aplicado/descartado. Sigue siendo bloqueo real para el siguiente intento.
- Evaluador continúa en `54892e8d-84be-422a-b5a4-e4a2f4dfc7b9`, identidad histórica
  db0c59b; volumen y resto de servicios sin modificaciones por esta investigación.
  La publicación final y resolución humana del staged work siguen pendientes.
- Prueba antes de corregir: publicación sintética con null reproduce rechazo;
  booleano False revela aceptación indebida por igualdad con cero. Después:
  **64 focales** (publicación + packaging), **1804 unitarias/1 skip**, **80,85 %**
  cobertura, Ruff global limpio y mypy **177** archivos sin errores. Tests cubren
  cero/null, ausente/no-cero/tipos inválidos y STAGED/APPLYING con ambos contadores.
  Sin integraciones repetidas (no cambia src/schema); sin push/despliegue/inferencia.

## Corrección del workflow tras publicar 9125484

GitHub rechazó la definición antes de ejecutar jobs: `runner.temp` no está
disponible en `jobs.<job_id>.env`. Sustituido por `$RUNNER_TEMP/eval-candidate`
expandido por la shell en ambos pasos prepare/publish; misma ruta temporal,
sin cambios de destino, secretos ni permisos. La validación YAML anterior no
detectaba restricciones de contextos de Actions. Nueva prueba de regresión
reproduce el fallo antes del cambio y comprueba ambos pasos después.
Validación de la corrección:39 pruebas focales y1792unitarias/1skip superadas,
80,85 % cobertura, Ruff global limpio y diff sin errores. No cambia código src;
resultado mypy anterior sigue vigente. Sin CLI local, secreto nuevo ni despliegue.
Aceptación remota de la definición pendiente del nuevo commit/push; no es un
fallo de token Railway ni evidencia de un despliegue realizado.

## Implementación inicial — registro histórico

- `.github/workflows/deploy-evals.yml`: botón **Actualizar evaluador**, SHA explícito,
  confirmación idle, sólo main/manual, environment `ancoramind-evals-deploy`,
  GITHUB_TOKEN sólo lectura. Actions fijadas por SHA, CLI5.70.0 únicamente runner
  GitHub alojado; secreto Railway sólo paso publish, no inputs/shell local.
- `scripts/deploy_eval_candidate.py`: gates CI mismo SHA/último attempt/jobs y
  control-code CI, archive/helper existente, huella y reporte allowlist, destino
  fijo evaluador, variables sello con skip-deploys, una subida con deploymentId,
  espera SUCCESS/running/idle identidad, comparación volumen/otros deployments.
- No scripts de candidato ejecutados en runner, no dependencias de candidato
  instaladas con secretos, no SSH/evals ni escritura/lectura de contenido volumen.
- Pin GitHub histórico no se reconecta: preservar autodeploy desactivado y evitar
  otro build con selector problemático. Identidad upload por sello/log, no metadato
  GitHub inventado.

## Pruebas iniciales — registro histórico

- **1791 unitarias passed / 1 skipped**, cobertura **80,85 %** (gate75 %).
  El skip corresponde a symlink Windows preexistente de specs/040, no a este workflow.
- **38 tests nuevos** del despliegue: ref/event/runner/idle/SHA, CI run/attempt/jobs/
  pagination/control code, archive/allowlist sin ejecución candidata, metadata sin
  secretos, destinos/variables fijos, CLI output/credenciales acotados, staged patch
  sin leer patch/variables, drift, error/timeout sin retry, running/log/ID exactos,
  YAML parseado sólo dispatch y secreto último paso/Actions por SHA.
- Focales incluyendo packaging/service:62 passed. Ruff global y mypy src177limpios.
- Prueba real **sin upload** sobre commit `f9e08ae70d37765e5c82ee07d1a478a8488d3295`:
  ancestry main, CI run39129319862 attempt1/job names por GitHub API sólo GET
  (autenticación `gh` ya disponible, sin extraer token), git archive real, contexto
  allowlist, huella/sellado/identidad sealed_image comprobados. Archivo temporal
  eliminado. No comandos Railway CLI ejecutados/instalados localmente.
  - source fingerprint `d5e781673aa037a6cc54d88a6abc088759d54de870f3de06b133a05cc8b2389a`
  - tar/gzip preparado `ef264280c3a2fa8e338bcefb0e0d532870d22361835c783ef7569afc986e1692`
  - hash del archivo preparado, NO prueba de artefacto subido/digest imagen.
- Contratos CLI contrastados en documentación y fuentes del release5.70.0
  (`5ba0b00c62d7fd5cdade53f0c3869ed4ba1de2e1`): flags project/service/environment,
  detach+json devuelve deploymentId, variable set skip-deploys, status con
  serviceInstances/volumeInstances, deployment list e idle JSON logs flatten.
- No se repiten integraciones PostgreSQL: sin src/domain/repositories/schema/
  prompts/runtime cambiados. Último resultado vigente specs/040207passed/1STTskip.
  El siguiente commit ejecutará CI completa antes de autorizar publicación.
- Aviso OTel localhost4318 ausente durante unit tests, sin fallos ni cambios telemetry.

## Pendientes iniciales — registro histórico

No se ha instalado CLI en equipo gestionado, creado token/environment/secreto,
ejecutado workflow/deployment ni inferencia. No commit/push por agente.
El primer workflow real verificará permisos del token/API y resultados de Railway;
tests con fake CLI no demuestran ese rollout. Se requiere configuración inicial
del propietario por navegador y CI verde del código de publicación y candidato.
Token proyecto limita al entorno, no servicio; disponibilidad de protection rules
depende del plan GitHub. No declarar garantía distribuida de confirm_idle, ni que
CI verde demuestre seguridad de código de un candidato no revisado.

Estado consultado sólo lectura antes de implementar: evaluador sigue en deployment
`54892e8d-84be-422a-b5a4-e4a2f4dfc7b9`/SHA db0c59b, volumen100MB `/eval-state`,
sin staged changes; no cambiado por este incremento. Bot/Collector f9e08ae ajenos
a esta publicación local. Campaña histórica no recuperada/repetida ni claves
antiguas confirmadas/revocadas por añadir el botón.