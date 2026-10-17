# T7 — Servicio temporal privado y revisión por shell

> Implementación local 2026-10-17. Servicio/volumen creados posteriormente;
> arranque recuperado con paquete de build explícito, sin clave nueva ni inferencia.
> El propietario ha pedido avanzar con incrementos 1–2; eso no genera etiquetas
> humanas ni elimina los gates de SHA/CI, snapshot, presupuesto externo y acceso.
> Estado/evidencia: [aprovisionamiento inicial](railway-provisioning.md).

## Qué arranca

- Imagen prevista `evals/Dockerfile`, raíz del repositorio como build context.
  **Corrección tras aprovisionar:** Railway rechaza activar `/evals/railway.json`
  para servicios nuevos por deprecación de Config as Code. Se aplican ajustes
  directamente al servicio separado; el JSON queda como referencia, no contrato
  de aprovisionamiento automático. No reutilizar config del bot. Build GitHub
  no respeta la ruta personalizada; la instancia actual usa paquete privado
  explícito y está idle. No reconstruir desde GitHub sin resolver ese fallo.
- `scripts/eval_service.py` verifica identidad y espera SIGTERM/SIGINT, sin
  importar el Agent, abrir puertos ni consultar el Gateway. Una réplica,
  restart `NEVER`, sin cron, dominio, TCP proxy ni healthcheck HTTP.
- El operador entra por shell interactiva y lanza el script **manualmente**.
  Una sesión SSH no es un túnel de puertos, pero necesita permiso del entorno
  del operador. No instalar CLI/SSH ni registrar claves automáticamente.

## Identidad sin copiar `.git` ni secretos

El Dockerfile específico tiene allowlist de contexto: código, scripts, prompts,
catálogo y metadata de paquete. No copia `.git`, `.env`, datos ni tests.
`scripts/eval_source.py` calcula la misma huella en checkout y contenedor,
normalizando CRLF. Incluye Python, prompts, catálogos JSON, `pyproject.toml`,
Dockerfile de eval y su ignore específico.

1. Revisar/comitear el cambio, ejecutar gates y comprobar CI del **mismo SHA**.
   No comitear ni desplegar automáticamente. No redeploy del bot para este ensayo.
2. Obtener preflight desde checkout limpio con el comando del runbook T7.
3. Build args: `ANCORA_EVAL_BUILD_SOURCE` igual a `source_fingerprint` aprobado;
   `ANCORA_EVAL_BUILD_SHA` igual al SHA aprobado (o `RAILWAY_GIT_COMMIT_SHA`
   suministrado por Railway al build). Sin valores válidos o contenido distinto,
   el build falla. No usar args para secretos ni crear flags de aprobación en build.
4. El build escribe un manifiesto interno. Es **un sello de contenido, no firma
   ni prueba de checkout limpio**. `identity_source=sealed_image` lo distingue;
   `worktree=clean` solo indica integridad del paquete con ese sello. La prueba
   de commit limpio/CI es externa y la aprobación de ejecución exige SHA y huella
   exactos. Una imagen de desarrollo con checkout sucio sirve solo para pruebas
   sin modelo, nunca como candidato aprobado.
5. Comparar preflight dentro/fuera del contenedor. Un cambio detectado antes de
   cada caso detiene la campaña. Este incremento cambia la huella de fuentes:
   volver a aprobarla después del commit, no reutilizar huellas anteriores.

## Preparación Railway — arranque recuperado, campaña pendiente

**Actualización:** arranque validado y réplica running en deployment
`54892e8d-84be-422a-b5a4-e4a2f4dfc7b9` mediante contexto explícito. Pendientes
preflight/mount/TTY remotos y acceso al Gateway. No ejecutar campaña todavía.

Para reconstruir un paquete sin cambios no comiteados ni inferencia, usar la
utilidad local (no incluida en la imagen db0c59b) y SHA/huella previamente validados:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
python "$root\scripts\prepare_eval_build.py" `
  --sha db0c59be0b2eeb807d4222aeb5a62b622d90b200 `
  --source-fingerprint 108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82 `
  --output "$root\tmp\eval-build.tar.gz"
```

No sube ni despliega: la subida privada autenticada es una operación separada,
autorizada por servicio, sin publicar un registry ni instalar CLI automáticamente.
El paquete deja el Dockerfile de evals en raíz y conserva su ruta original para
la huella; excluye receta/config raíz del bot. Ver evidencia/provenance del
artefacto realmente desplegado en `railway-provisioning.md`.

En el proyecto/entorno autorizado que contiene el Gateway, servicio temporal
separado del bot. Sin cambios en `ancoramind-app`, Gateway, BD ni runtime config.
Antes de crear/desplegar: acordar coste de cómputo/volumen y ventana de uso; los
0,10 USD aceptados son reserva **del modelo**, no presupuesto de infraestructura.
Revisar staged diff si se usa staging; no mezclar cambios ajenos al ensayo.

- Conectar el repo confirmado y fijar SHA CI-verde; configuración eval propia.
  Sin autodeploy de futuras ramas/cambios que puedan interrumpir la sesión.
- Adjuntar **un volumen exclusivo en `/eval-state`** y una sola réplica.
  Nunca reutilizar volúmenes/BD productivos. La imagen exige mount real antes
  de reservar/conectar; no basta una variable que diga que es persistente.
  Por defecto `ANCORA_EVAL_STATE_DIR=/eval-state`. Una imagen sellada exige mount
  aunque se quite `ANCORA_EVAL_REQUIRE_VOLUME`; no apuntar a otra carpeta.
- No copiar variables del bot. Sólo clave eval exclusiva/r4 con expiración,
  presupuesto externo verificado y URL privada en `ANCORA_EVAL_GATEWAY_URL` /
  `ANCORA_EVAL_GATEWAY_KEY`. No imprimir ni pegar secretos; ver advertencia T7
  sobre el script legacy de virtual keys, que no sirve sin cambios.
- Validar alcance con GET `/v1/models` autorizado antes de inferencia. Presupuesto
  externo no se verifica mediante un flag local ni un GET de modelos.

## Sesión manual (rutas dentro del contenedor)

Primero comprobar terminal con respuesta sintética fija, sin key, red, reserva
ni autorización de inferencia:

```sh
python /app/scripts/execute_eval_campaign.py --check-console
```

Responder `p` + Enter si la prueba se ve y funciona. Resultado `console_ready`,
`inference_started=false`, `approval_granted=false`. Pipe/terminal ausente debe
fallar. No usar transcript/grabación de consola.

Preflight puro:

```sh
python /app/scripts/execute_eval_campaign.py \
  --snapshot /app/evals/response_style/runtime-rev8-snapshot.json \
  --plan /app/evals/response_style/bl48-campaign-plan.json
```

Sólo después del scope/budget externo y aprobación exacta de los valores/flags
del runbook T7, en presencia del propietario:

```sh
python /app/scripts/execute_eval_campaign.py \
  --snapshot /app/evals/response_style/runtime-rev8-snapshot.json \
  --plan /app/evals/response_style/bl48-campaign-plan.json \
  --state-dir /eval-state --execute
```

El script presenta cada criterio; acepta `p/pass`, `f/fail`,
`x/not_evaluated`, sin distinguir mayúsculas. Una errata repregunta sin inferencia;
vacío/EOF detiene. Fallo o no evaluado corta los casos siguientes. Un `fail`
conserva estado `failed` aunque los criterios restantes queden no evaluados.
La valoración no concede consentimiento a ninguna acción del bot.

## Final y resultado incierto

Conservar/exportar sólo `.report.json` (metadata) y mantener `.reserved.json`
en el mismo volumen; no borrar reservas para reejecutar. La creación exclusiva
bloquea dos lanzamientos con igual plan sobre ese volumen, incluidos nuevos
contenedores. **No es una garantía global/distribuida**: otro volumen, otra ruta
o plan modificado no comparte la marca. Un solo operador/volumen, sin replays.

Ante corte de SSH, error o checkpoint incompleto, no relanzar inferencia; revisar
estado conservadoramente como parcial/no evaluado. No reanudar una campaña pagada
sin nueva decisión específica. El reporte nunca guarda respuesta/input/contexto.
Una vez obtenido el reporte, detener la instancia mediante la operación soportada
por Railway; no sólo cerrar SSH. Conservar el volumen/estado acordado y revocar la
clave eval tras la ventana. Volumen y servicio pueden tener costes separados.

Incremento 2 sigue pendiente hasta ejecución real y etiquetas del propietario.
Web/golden set/Jev se mantienen diferidos; ver `incremental-roadmap.md` y la
propuesta existente `specs/014-agentic-evals/jev-pilot-proposal.md`.

## Evidencia local — 2026-10-17

- `pytest tests/unit/ -q --cov=src`: **1647 passed**, cobertura **80,58 %**.
- `pytest tests/integration/ -q`: **207 passed, 1 skipped** (STT live omitida
  por diseño), solo PostgreSQL local, sin fixtures en bases productivas.
- Ruff global limpio; `mypy src/` limpio en 175 archivos. Catálogo estático:
  36 casos/6 categorías y 9 ejemplos provisionales; no son evaluaciones LLM.
- Imagen de desarrollo `ancoramind-evals:t7-dev` construida. Build corresponde
  a fuentes todavía sin commit: no candidata a aprobación de inferencia.
- Con `--network none`: preflight `preflight_valid`, scope no comprobado,
  `inference_started=false`; arranque `idle_manual_only` y SIGTERM exit 0;
  PTY Linux real con respuesta sintética fija y entrada `p`/`P`, `console_ready`.
  La entrada automática se usa **sólo para esta prueba fija sin modelo**, nunca
  para sustituir al revisor de la campaña. Ausencia de `.env`, `.git`, datos/tests
  comprobada en el contenedor.
- Prueba con flags/clave **sintéticos**, sin red: sin mount rechaza antes de
  reservar; con volumen aislado y sin TTY se detiene antes de conectar y retiene
  reporte/reserva; otro contenedor con el mismo volumen recibe `FileExistsError`
  antes de conectar. Volumen/contenedores de esta prueba eliminados al terminar.
- Consulta Railway **solo lectura**: no existe servicio evaluador ni staged
  changes en el entorno inspeccionado. No se consultan secretos, instalan CLI,
  crean claves/recursos, despliegan cambios ni ejecutan inferencias.
- Durante la suite se observó un aviso de exportación OTel a Collector local
  no disponible (`localhost:4318`); no falló ningún test. No se modifica el
  pipeline de observabilidad como parte de este incremento.

Sin commit/push por el agente ni CI del nuevo SHA. Alcance local completado;
campaña T7 real y BL-48 siguen pendientes, semántica `not_evaluated`.