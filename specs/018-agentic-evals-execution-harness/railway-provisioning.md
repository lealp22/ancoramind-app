# T7 — Aprovisionamiento inicial Railway (2026-10-17)

## Autorización y resultado

El propietario autorizó explícitamente crear el servicio temporal separado y su
volumen, aceptando el coste de Railway. No autoriza por este paso claves Gateway,
inferencias, etiquetas humanas ni cambios en bot/Gateway/BD/runtime config.

**Resultado actualizado:** arranque idle validado mediante paquete privado con
Dockerfile de evals en la raíz, deployment `54892e8d-84be-422a-b5a4-e4a2f4dfc7b9`
`SUCCESS`, **1 running / 0 crashed**. El fallo de selección de ruta desde GitHub
no está corregido internamente: se evita con contexto explícito (detalle al final).
Montaje, preflight remoto y TTY comprobados por el propietario (salidas aportadas
en conversación); pendientes clave/scope/budget y aprobación/ejecución de campaña.

## Identidad y recursos

- Proyecto `ancoramind-app`: `b291bc34-c75d-4a8a-9f82-d3d7cf32aeef`.
- Entorno `production`: `79202202-e66e-4778-8ce3-6aa975c212d5`.
- Servicio **ancoramind-evals**: `79f8f0c2-1ba1-4fea-9e89-d4b672b23efc`.
- Volumen **ancoramind-evals-state**: `b88f8940-dd92-430f-8d6f-a4adb2b455c8`,
  100 MB, mount `/eval-state`, región `europe-west4-drams3a`.
- Repo `lealp22/ancoramind-app`, raíz `/`, commit **fijado**
  `db0c59be0b2eeb807d4222aeb5a62b622d90b200`; no seguir nuevos pushes.
- [CI de ese SHA](https://github.com/lealp22/ancoramind-app/actions/runs/39068058584):
  `success`; jobs `quality`, `integration`, `collector-config` superados.
- Preflight local con checkout limpio: `preflight_valid`, sin inferencia.
  Huella fuente `108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82`;
  plan/casos/snapshot sin cambios respecto a T7.

Configuración del nuevo servicio, verificada por API y vista de detalles:

- Dockerfile path actual `evals/Dockerfile`; variable de selección conserva
  `/evals/Dockerfile`. Entorno de build actual V2 (la prueba V3 → V2 no corrigió
  la ruta GitHub; se conserva tras el despliegue manual, no se atribuye el éxito a V2).
- Start `python /app/scripts/eval_service.py`, restart `NEVER`, una réplica.
- Límites por réplica: 1 vCPU, 1 GB; sin cron ni healthcheck HTTP.
- Sin dominio público, TCP proxy, tracing ni claves/cadenas de conexión del bot.
- Sólo seis variables no secretas: `AGNO_TELEMETRY`, `ANCORA_EVAL_BUILD_SHA`,
  `ANCORA_EVAL_BUILD_SOURCE`, `ANCORA_EVAL_REQUIRE_VOLUME`,
  `ANCORA_EVAL_STATE_DIR`, `RAILWAY_DOCKERFILE_PATH` (actual `/evals/Dockerfile`).
  Sin `ANCORA_EVAL_GATEWAY_KEY` ni flags de aprobación de inferencia.

La creación se hizo en dos pasos porque `update-service` no puede configurar una
instancia todavía `staged-create`: primero servicio vacío/volumen/variables,
después source/config. Antes de cada apply se revisó el diff: sólo recursos del
evaluador, ninguna eliminación ni cambio en otros servicios. Sin CLI/SSH nuevos,
túneles, claves o secretos consultados. No se ejecutó una shell en el servicio.

## Bloqueo inicial y evidencia histórica

1. Asignar `railwayConfigFile=/evals/railway.json` fue **rechazado** por la API:
   Config as Code deprecado, servicios nuevos no pueden activarlo. Confirmado en
   [documentación](https://docs.railway.com/config-as-code) y UI. Los legacy
   continúan hasta 2026-12-01 según Railway; no se migra el proyecto en este paso.
2. Se aplicaron los ajustes equivalentes directamente al servicio nuevo. El
   campo `build.dockerfilePath` aparece en API/UI/detalles del deployment como
   `evals/Dockerfile` (posteriormente `/evals/Dockerfile`).
3. Sin embargo, los logs de build muestran instalación de `ffmpeg`, `libpq-dev`,
   `gcc` y `COPY alembic.ini`, `COPY migrations/`, `COPY specs/`, instrucciones
   del **Dockerfile raíz**, no del de evals. No hay `COPY evals/` ni paso de sellado
   `eval_source.py`. Eso explica que no esté preparado el contenido del evaluador.
4. Establecer además la variable documentada `RAILWAY_DOCKERFILE_PATH` y después
   normalizar ambas rutas a `/evals/Dockerfile` no corrigió el build observado.
   No afirmar que la deprecación, precedencia del JSON raíz o caché sea la causa
   exacta: la contradicción entre configuración y build está probada, su causa
   interna no. No seguir probando variantes sin diagnóstico verificable.
5. El proceso idle falla cerrado: log estructurado `status=eval_service_blocked`,
   `inference_started=false`. En los dos primeros intentos Railway llegó a mostrar
   `SUCCESS` aunque `replicaStatus` tenía 0 running/1 crashed. El último ya muestra
   `CRASHED`. No confiar sólo en la etiqueta global de despliegue.

| Deployment | Cambio del intento | Resultado comprobado |
|---|---|---|
| `e5dccee6-5f65-4a50-bccf-cd3fd4083859` | Ajustes directos, ruta `evals/Dockerfile` | Build raíz; `eval_service_blocked`, sin inferencia |
| `9d481e7d-b20b-4a57-bce4-deb7f9caada5` | Añadir variable de selección documentada | Mismo build raíz; bloqueo seguro |
| `a308909d-760b-436e-80c6-3ee58cc5365f` | Ambas rutas absolutas `/evals/Dockerfile` | Mismo build raíz; **CRASHED**, sin inferencia |

Dos consultas de diagnóstico **sólo lectura** al agente Railway agotaron el timeout
sin respuesta/threadId; no son diagnóstico ni evidencia de corrección. No se
delegaron cambios ni se relajó la comprobación de identidad para permitir arrancar.

Bot conserva deployment `a23f2892-0f00-4d74-a1d3-4cd0f704eae2`; Gateway conserva
`bf1c29d3-2332-4868-bd25-782bbbf095eb`. Ninguno se redesplegó en esta operación.
Sin staged changes al último control. El volumen sigue aprovisionado y puede
generar coste aunque el proceso esté detenido; no borrarlo automáticamente.

## Recuperación: contexto de build explícito, sin cambiar el código bajo prueba

Continuación autorizada por el propietario para resolver el Dockerfile:

- Se comprobó por GitHub API que `evals/Dockerfile` del commit fijado existe y es
  idéntico al local. Snapshot de variables confirma ruta/SHA/huella correctos.
- Consulta directa `ServiceInstance.builder` devuelve `RAILPACK`, mientras config
  de entorno/manifiesto muestra `DOCKERFILE`. **No es prueba causal suficiente**:
  el Collector operativo presenta también `RAILPACK` internamente. Enum legacy de
  API no admite `DOCKERFILE`; intentar ese valor devuelve error. No se modifican
  servicios ajenos para forzar ese campo.
- `railwayConfigFile=null`, `resolvedFileConfig.configFile=null` y
  `fileManifest={}`: no hay evidencia de JSON legacy activo en el evaluador.
  Cambios exploratorios del selector/ruta se revirtieron antes de desplegar;
  sin cambios pendientes ajenos ni selección temporal Railpack aplicada.
- Un build explícito por `serviceInstanceDeployV2`, mismo SHA,
  `2ee8cea6-1d8f-4d27-a312-08f8ad6603a6`, repitió las instrucciones raíz y
  `eval_service_blocked`. Sólo cambiar buildEnvironment V3 → V2 produjo
  `fe8616cd-ab48-4ce3-87a3-2eab9076d61c`, mismo fallo. No hacer más variaciones.
- La frontera reproducible del fallo queda en **despacho/contexto de build**:
  fuente/ruta/config son correctos, pero se analiza la receta raíz del bot.
  La causa interna concreta de Railway sigue sin confirmarse; no atribuirla a
  `.dockerignore`, caché, CaC o builder legacy sin evidencia adicional.

Solución alternativa aplicada:

1. Crear archivo privado desde `git archive db0c59b…`, sólo `src/`, `scripts/`,
   `prompts/`, `evals/`, `pyproject.toml` y `README.md`. Sin `.git`, `.env`, datos,
   credenciales, tests ni `railway.json` raíz del bot. Añadir **copias exactas**
   de `evals/Dockerfile` y su ignore como `Dockerfile` / `.dockerignore` raíz.
   No se modifica ningún archivo de código/config bajo evaluación.
2. Recalcular huella en el paquete antes del build: coincide exactamente con
   `108c410d…71e6c82`, fuentes del SHA CI-verde `db0c59b…`. Build y preflight local
   sin red superados; log idle con identidad correcta y proceso vivo.
3. Enviar ese archivo al endpoint autenticado privado `/project/.../environment/.../up`,
   mismo usado por CLI, exclusivamente para `ancoramind-evals`. Se utilizó sesión
   autorizada del navegador, **sin instalar CLI, abrir puertos locales, crear
   túneles, extraer tokens ni publicar código/imágenes**.
4. Artefacto realmente desplegado: 236 archivos, 312867 bytes, SHA-256
   `8298a1fed8c235d22f727b13ac97603de47b7474d6ab757c55d7fbfbce6c760f`.
   Deployment **`54892e8d-84be-422a-b5a4-e4a2f4dfc7b9`**, subida manual, no GitHub:
   su metadata no aporta commitHash; la correlación al commit se demuestra por
   paquete/huella/sello y log runtime, no se inventa provenance GitHub.
5. Logs Railway: `COPY evals/` y `RUN ... eval_source.py` completados; log runtime
   `idle_manual_only`, `inference_started=false`, SHA `db0c59b…` y huella esperada.
   Estado estable `SUCCESS`, **1 running / 0 crashed**, sin pending work.
   Digest imagen: `sha256:83e82168dd00840633ee7c1ec34f5d6f7a92b9355d34505c730823de556bebe4`.

Preparación reproducible añadida localmente: `scripts/prepare_eval_build.py`.
Acepta commit completo, huella externa y output absoluto; allowlist de tipos de
fuentes, archivos regulares, sin traversal/symlinks/overwrite. Tar/gzip determinista;
no sube, conecta ni concede aprobación. Es una versión más estricta del paquete
manual: excluye Markdown auxiliares de `evals/` que no usa el runtime. Por ello
su hash binario no equivale al desplegado, aunque conserva la misma huella de
fuentes: ejemplo db0c59b → 297024 bytes,
`0f5e60c48210aebd0cc13748bf94d0cafc1b8833115871b3cba2f27ba9b7c4f5`.
La nueva utilidad **no está en el contenedor db0c59b**. No actualizar el sello
del contenedor al SHA local de documentación/herramientas ni marcarlo GitHub.

Validación de la continuación: **1660 unitarias passed**, cobertura **80,58 %**,
Ruff global y mypy (175 fuentes) limpios; catálogos válidos 36 casos/9 ejemplos
provisionales. Build del paquete de la utilidad y preflight `--network none`
superados con huella original; 13 pruebas nuevas de empaquetado (determinismo,
allowlist, traversal/symlink, identidad y no overwrite). No se repitieron
integraciones PostgreSQL en esta continuación (sin cambios de dominio/BD);
última evidencia anterior 207 passed/1 STT live skipped, no resultado nuevo.
Avisos de Collector local ausente en tests, sin fallos ni cambio de telemetry.
Sin commit/push del agente; nuevo script/docs locales no están desplegados.

## Verificación remota por el propietario — sin inferencia

El propietario confirma acceso a la shell de `ancoramind-evals` y aporta las
salidas de los tres comandos del runbook. Evidencia suministrada por el operador,
no una nueva ejecución remota del agente ni un nuevo despliegue:

- Mount: `mount_valid=true`, `writable=true`, `inference_started=false`.
  Se validó un montaje real con el validador del harness y permiso de escritura;
  no prueba adicional de persistencia tras reinicio ni escritura de reserva.
- Preflight: `preflight_valid`, `worktree=clean`, `identity_source=sealed_image`,
  SHA `db0c59be0b2eeb807d4222aeb5a62b622d90b200` y huella fuente
  `108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82`.
- Plan `8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139`,
  revisión 8, ruta `ancoramind-default` / `ancoramind-default-r4`, cinco casos
  previstos. Snapshot checksum
  `e2663c6ab9e2666f41ba3d5399d05feb8a0d4141de0d2d74fdcfca19b3afdb25`,
  fingerprint `a41f255f1b4022bc5ac1c7efb35a02d82fb4ec2396d71f4991fea1db15f7cccc`;
  casos `abddf11d06c5233ca97ddf016938ae759f698b740588167c5a9079dc5d137474`.
- Presupuesto candidato: 0,02 USD estimados/caso, **0,10 USD estimados total**;
  no techo de facturación ni verificación del límite externo. Por caso:
  120 s, 6 model calls/requests, 12 tools, 1024 output tokens, un intento por
  model call, sin espera de cola. Plan sin ampliaciones.
- Consola: `console_ready`, `inference_started=false`, `approval_granted=false`.
  Comprueba el revisor real con texto fijo sintético, no evalúa respuesta LLM.
- Siguen `gateway_access=not_checked`,
  `approval_status=pending_separate_approval`, `semantic_status=not_evaluated`.

Quedan superados los subgates acceso shell/mount/preflight/TTY de T7c-remoto,
**no T7c completo, T7b ni BL-48**. Sin nuevas claves, flags, aprobación de campaña
ni inferencia a partir de estas salidas. El commit local de documentación no
sustituye la identidad db0c59b del contenedor.

## Continuación y límite operativo

No utilizar un nuevo build GitHub o aplicar cambios a ciegas: el source del
servicio sigue fijado al commit antiguo y la ruta personalizada puede reproducir
el fallo. Para reconstruir, utilizar paquete explícito verificado o resolver antes
el defecto de plataforma. Redeploy que reutilice la imagen correcta debe comprobar
deployment/digest; no seleccionar una imagen de los intentos fallidos.

Bot y Gateway conservan los deployments registrados arriba. Sin dominio/keys,
flags de inferencia o secretos nuevos. Servicio queda **encendido idle**, con coste
de cómputo y volumen, no apagado automáticamente. No se han ejecutado evals LLM.

Preflight/mount y TTY real comprobados por el propietario según evidencia arriba.
Siguiente gate: autorización específica para clave exclusiva/expirable sólo r4,
scope y presupuesto externo, comprobación Gateway sin inferencia y aprobación
ligada a la identidad desplegada, sólo entonces campaña humana. No reutilizar el
generador genérico de clave del bot: incluye aliases base y no configura expiración.
**T7c-remoto, T7b y BL-48 permanecen abiertos**.

### Autorización posterior: clave/acceso sin modelo

El propietario autoriza preparar clave exclusiva/expirable, verificar presupuesto
externo y acceso sin inferencia. **No creada todavía**: no hay ejecución de shell
remota disponible en las herramientas del agente; no se extraen credenciales ni
se instalan CLI/túneles para sustituirla. Se preparan helpers del operador con
tests, sin deploy: [procedimiento de acceso](gateway-access-runbook.md).
Clave candidata sólo r4, caducidad 2 h, 0,10 USD sin reset, concurrencia 1,
lectura exclusivamente `/models`, `/v1/models`, `/key/info`; inferencia bloqueada.
El propietario debe ejecutarlos en shells existentes y devolver sólo metadata.
Pricing/enforcement en inferencia y aprobación/campaña siguen sin verificar;
no se trata el presupuesto nominal como garantía de facturación.

### Plan anterior (superado parcialmente por la recuperación)

Resolver primero selección real de Dockerfile con metadata de build/plataforma
o soporte Railway. Si requiere cambiar layout/config del repo, preparar un
incremento explícito y CI del nuevo SHA, no mutar el candidato ni migrar el bot
silenciosamente. No publicar imagen/código del repo como atajo.

Build con `COPY evals/`, sellado, log `idle_manual_only` con SHA/huella correctos y
réplica running ya comprobados; mount/preflight y TTY confirmados por propietario.
Sólo entonces preparar clave restringida, scope/budget y campaña humana, con gates
separados. **T7c-remoto, T7b y BL-48 permanecen abiertos**.