# Verificación — 2026-10-18

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

## Implementado localmente

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

## Pruebas

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

## Pendientes que no se certifican con tests locales

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