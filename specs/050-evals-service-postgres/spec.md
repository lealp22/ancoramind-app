# 050 · Servicio de evals bajo demanda con resultados en PostgreSQL

> Estado: **sólo documentada (2026-10-25). No se implementa todavía.**
> Origen: conversación sobre spec 049 (runner ligero). Las decisiones de la sección
> «Decisiones del propietario» son suyas; lo marcado «abierto» o «a valorar» no está
> decidido. Actualizada el mismo día con las cuatro decisiones pendientes.

## Objetivo

Poder ejecutar la batería de evals sin depender del ordenador local y consultar los
resultados desde `/admin/dashboard`. Como efecto útil: comparar cómo responde un modelo
candidato con el actual sobre los mismos casos, para decidir un cambio con datos.

## Decisiones del propietario

1. **Resultados en PostgreSQL**, en el schema `ancora` de producción.
2. **Servicio `ancoramind-evals`** que el propietario enciende, usa y apaga a mano. La
   intención es **reutilizar el servicio existente**, pero valorando la situación en el
   momento de construirlo (ver «Reutilizar el servicio existente»). El coste de dejarlo
   encendido se considera menor. No se diseña el apagado.
3. **Sin el volumen cifrado del evaluador antiguo** (specs 040–045): no se necesita.
4. **OpenRouter directo con una clave aparte**, con límite de gasto propio. Se descarta
   por ahora el presupuesto del Gateway; se reconsidera si resulta necesario.
5. El modelo de la prueba se fija a mano para cada ejecución (hoy `LLM_MODEL` del `.env`
   del runner, que **no** sigue al Gateway).
6. **Rol propio de base de datos** para el runner, con permisos sólo sobre las tablas de
   evals (no la conexión `postgres` del runtime).
7. **Se guarda el texto** de prompts y respuestas en la base de producción, además de las
   métricas.
8. **Clave de OpenRouter aparte con su límite.** Hay que crearla; no consta que exista.

## Qué hay hoy (verificado en el repo)

- `scripts/run_evals_light.py` escribe una línea por pasada en `evals/runs/ledger.jsonl`
  (SHA, modelos, casos, aprobados, tokens, coste real y estimado, y por caso estado,
  tools, uso, duración y veredicto por criterio). **Sin prompts ni respuestas.**
- `scripts/report_evals.py` lee ese fichero y agrega estabilidad por caso.
- El dashboard (`src/agent/admin_dashboard.py`, `admin_dashboard_static/dashboard.html`)
  tiene 4 pestañas y rutas `GET /admin/dashboard/api/...` con bearer propio. Lee del schema
  `ancora` mediante repositorios (p. ej. `src/repositories/finops.py`).
- Último head de Alembic: `0017_access_notice_index`.
- La migración `0015_ancora_rls_hardening` activó RLS y revocó permisos a `PUBLIC` sobre las
  tablas que existían entonces. Una tabla nueva no hereda el RLS: hay que activarlo en su
  propia migración (comprobar si algún test lo exige).

## Qué habría que construir

1. **Migración** `0018_...` con una o dos tablas (ver «Modelo de datos») y RLS activado.
   Mantener `migrations/init.sql` equivalente a `head`. Probar instalación limpia,
   actualización sobre datos y bajada de la última revisión (regla del repo).
2. **Repositorio** nuevo en `src/repositories/` con SQL parametrizado (`text()` y bind
   params), sin interpolar cadenas.
3. **Rutas** de sólo lectura en `admin_dashboard.py` con la autenticación existente y
   ventana acotada, siguiendo el patrón de `/api/finops` (404 si el panel está
   desactivado, 401 sin token, 422 si el rango es inválido).
4. **Pestaña** nueva en `dashboard.html`. `tests/unit/test_admin_dashboard_layout.py`
   fija hoy 4 pestañas y 4 paneles: hay que actualizarlo. El HTML no puede escribir datos
   del servidor como HTML (hay un test que lo vigila).
5. **Escritura desde el runner**: una función que, tras cada pasada, inserte en la BD en
   lugar de (o además de) el fichero. Con el runner en Railway no hay disco persistente,
   así que el fichero deja de servir como registro.
6. **Servicio `ancoramind-evals`**: cambiar el arranque para que ejecute el runner y
   termine. Se intenta reutilizar el existente (ver «Reutilizar el servicio existente»).
7. **Tests** unitarios de repositorio y rutas (mocks) y de integración contra PostgreSQL
   local dockerizado, nunca contra producción.

## Modelo de datos (propuesta, sin decidir)

- `eval_runs`: id, fecha, SHA, modelo del Agent, modelo del juez, casos, aprobados,
  tokens y costes (real y estimado), si paró por presupuesto.
- `eval_case_results`: run, caso, categoría, estado, tools observadas, uso, duración,
  veredictos del juez por criterio, y (decisión 7) el texto de entrada, la respuesta
  (`answer` y `proposal_text`) y el criterio evaluado.
- Para comparar modelos basta con filtrar por `agent_model` sobre el mismo conjunto de
  casos; haría falta además registrar el **SHA del catálogo** para no comparar suites
  distintas.

## Implicaciones de las decisiones 6–8

- **Rol propio (6).** Nada en el repo crea roles hoy (`init.sql` sólo concede permisos al
  rol `ancora`). Habría que crear un rol con `INSERT`/`SELECT` sólo sobre las tablas de
  evals. Como las tablas tendrán RLS activado y sin políticas (patrón de la migración
  0015, que un test vigila), un rol sin `BYPASSRLS` no vería ninguna fila: hace falta una
  política específica para ese rol o un rol con `BYPASSRLS` limitado por permisos. Esto
  choca con `test_rls_migration.py` (`CREATE POLICY` no debe aparecer en esa migración;
  una migración nueva sí podría). **A resolver al construirlo.**
- **Texto en producción (7).** Los casos son sintéticos, pero el texto de la respuesta es
  salida de un modelo con datos inventados. Guardarlo sólo en tablas de evals, nunca en
  tablas de usuario. Fijar una retención (p. ej. purga por fecha) o dejarlo explícitamente
  sin límite. Las trazas de Phoenix tienen su propia regla (ADR-007); esta tabla no la
  hereda ni la sustituye.
- **Clave aparte (8).** Se crea en OpenRouter con límite propio; el runner la lee de su
  entorno, nunca del `.env` del bot. No consta que exista.

## Reutilizar el servicio existente (a valorar al construir)

Hoy, en Railway (proyecto `ancoramind-app`), `ancoramind-evals` existe, con último
despliegue `SUCCESS` (2026-10-23) y un volumen `ancoramind-evals-state` de 100 MB en
`/eval-state`. Del repo:

- `evals/Dockerfile` arranca `scripts/eval_service.py`, que sólo queda a la espera y no
  ejecuta nada; `evals/railway.json` fija `restartPolicyType: NEVER`.
- La imagen exige un volumen montado (`ANCORA_EVAL_REQUIRE_VOLUME=1`) y un árbol limpio.
  `tests/unit/test_eval_service.py` fija esa receta (variable, `CMD`, sin `EXPOSE`).
- El despliegue va por el workflow manual `deploy-evals.yml` (spec 041).

Consecuencias para reutilizarlo: hay que cambiar el `CMD`, quitar o relajar la exigencia
de volumen (decisión 3) y actualizar esos tests. El volumen puede quedarse sin usar o
retirarse (borrarlo es destructivo; decidirlo aparte). Si al construir el cambio resulta
mayor que crear un servicio nuevo, se crea uno nuevo. No se ha comprobado el estado de las
variables del servicio.

## Decisiones abiertas

- **Comparar modelos.** Fijar un procedimiento: mismo catálogo, mismo juez, mismo número
  de pasadas, y cómo leer el ruido (el juez y los casos inestables miden mal con una sola
  pasada; ver medidas en spec 049).

## Fuera de alcance

- Volumen cifrado, campañas con ledger firmado y revisión humana de las specs 040–045.
- Lanzar la ejecución desde el dashboard (el encendido es manual).
- Infraestructura de red team (ver sección condicionada en spec 049).

## Riesgos conocidos

- Los costes que informa OpenRouter varían entre llamadas casi iguales (8× en un par
  medido); el presupuesto debe contar el coste real y no una tarifa fija.
- Un servicio que no termina al acabar la tanda seguiría gastando; el runner termina con
  `os._exit` porque `loop.close()` se cuelga en Windows. En Linux (Railway) no se ha
  probado.
- Sin disco persistente, una tanda interrumpida pierde lo no insertado: insertar por
  caso o por pasada, no sólo al final.
