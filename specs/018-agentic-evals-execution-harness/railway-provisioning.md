# T7 — Aprovisionamiento inicial Railway (2026-10-17)

## Autorización y resultado

El propietario autorizó explícitamente crear el servicio temporal separado y su
volumen, aceptando el coste de Railway. No autoriza por este paso claves Gateway,
inferencias, etiquetas humanas ni cambios en bot/Gateway/BD/runtime config.

**Resultado parcial:** servicio y volumen creados; arranque idle **no validado**.
Último despliegue `CRASHED`, sin bucle de reinicio ni inferencia. No declarar el
evaluador listo por la existencia del servicio o un estado anterior `SUCCESS`.

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

- Dockerfile path actual `/evals/Dockerfile`.
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

## Bloqueo y evidencia

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

## Continuación acotada

Resolver primero selección real de Dockerfile con metadata de build/plataforma
o soporte Railway. Si requiere cambiar layout/config del repo, preparar un
incremento explícito y CI del nuevo SHA, no mutar el candidato ni migrar el bot
silenciosamente. No publicar imagen/código del repo como atajo.

Después: comprobar build con `COPY evals/` y sellado, log `idle_manual_only` con
SHA/huella correctos y réplica running; verificar mount/preflight y TTY autorizado.
Sólo entonces preparar clave restringida, scope/budget y campaña humana, con gates
separados. **T7c-remoto, T7b y BL-48 permanecen abiertos**.