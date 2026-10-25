# 050 · Servicio de evals bajo demanda con resultados en PostgreSQL

> Estado: **sólo documentada (2026-10-25). No se implementa todavía.**
> Origen: conversación sobre spec 049 (runner ligero). Las decisiones de la sección
> «Decisiones del propietario» son suyas; lo marcado «abierto» no está decidido.

## Objetivo

Poder ejecutar la batería de evals sin depender del ordenador local y consultar los
resultados desde `/admin/dashboard`. Como efecto útil: comparar cómo responde un modelo
candidato con el actual sobre los mismos casos, para decidir un cambio con datos.

## Decisiones del propietario

1. **Resultados en PostgreSQL**, en el schema `ancora` de producción.
2. **Servicio nuevo `ancoramind-evals`** que el propietario enciende, usa y apaga a mano.
   El coste de dejarlo encendido se considera menor. No se diseña el apagado.
3. **Sin el volumen cifrado del evaluador antiguo** (specs 040–045): no se necesita.
4. **OpenRouter directo con una clave aparte**, con límite de gasto propio. Se descarta
   por ahora el presupuesto del Gateway; se reconsidera si resulta necesario.
5. El modelo de la prueba se fija a mano para cada ejecución (hoy `LLM_MODEL` del `.env`
   del runner, que **no** sigue al Gateway).

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
6. **Servicio `ancoramind-evals`**: imagen/arranque que ejecute el runner y termine.
   Reutilizar o sustituir el servicio existente `ancoramind-evals` (hoy idle, de las specs
   040–045) es una decisión abierta.
7. **Tests** unitarios de repositorio y rutas (mocks) y de integración contra PostgreSQL
   local dockerizado, nunca contra producción.

## Modelo de datos (propuesta, sin decidir)

- `eval_runs`: id, fecha, SHA, modelo del Agent, modelo del juez, casos, aprobados,
  tokens y costes (real y estimado), si paró por presupuesto.
- `eval_case_results`: run, caso, categoría, estado, tools observadas, uso, duración,
  veredictos del juez por criterio.
- Para comparar modelos basta con filtrar por `agent_model` sobre el mismo conjunto de
  casos; haría falta además registrar el **SHA del catálogo** para no comparar suites
  distintas.

## Decisiones abiertas

- **Credencial de escritura.** El runner necesitaría `ANCORA_DATABASE_URL` de producción.
  La conexión habitual del runtime es `postgres` (omite RLS). Alternativa: un rol propio
  con `INSERT`/`SELECT` sólo sobre las tablas de evals. Cuál usar es de seguridad y es
  tuyo.
- **Contenido.** Hoy no se guardan prompts ni respuestas. Guardarlos en producción
  permitiría revisar un caso desde el dashboard, pero los casos son sintéticos y aun así
  quedarían en la base de producción. Decidir si se guarda sólo metadata (como ahora) o
  también texto.
- **Servicio existente.** Reutilizar `ancoramind-evals` o crear otro.
- **Clave y límite de OpenRouter.** Crear la clave aparte y fijar el límite en OpenRouter;
  no consta que exista.
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
