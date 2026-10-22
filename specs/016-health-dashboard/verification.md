# Verification: 016 — Health Signals and Dashboard

## Dashboard v2 — paneles de tools (2026-10-22, preparado, NO importado)

`observability/dashboards/ancoramind-health.json` pasa de v1 a **v2** con dos
paneles nuevos en una fila propia (`y: 29`), sin mover los 11 existentes:

| Panel | Serie |
|---|---|
| Tools invocadas | `ancora_tool_calls_total` por `ancora_tool_name` y `ancora_tool_outcome` |
| Latencia p95 por tool | `ancora_tool_call_duration_milliseconds_bucket` por `ancora_tool_name` |

Origen: el hook `src/agent/tool_budget_hooks.py` ya emite el contador
`ancora.tool.calls` y el histograma `ancora.tool.call.duration` con
`ancora.tool.name` y `ancora.tool.outcome` (atributos de la allowlist de métricas).
El dashboard v1 no mostraba nada de esto. Útil en la demo para ver qué tools usa el
Agent, incluida `search_web` si está activa. Solo metadata: ni argumentos ni
resultados.

**Estado: los nombres de serie están INFERIDOS, no confirmados.** Siguen la
convención de los paneles ya importados (`.` → `_`, contadores `_total`, histogramas
de ms `_milliseconds_bucket`), pero el dashboard v1 ya tuvo dos nombres mal supuestos
(`ancora_health_heartbeat_total`, `ancora_telegram_admissions_total`) y no hay
evidencia en el repo de que estas series existan en Grafana Cloud. El test
`test_tool_panels_match_the_metrics_the_hook_emits` solo protege contra un renombrado
en el hook.

### Comprobación antes de reimportar (Grafana → Explore, datasource `grafanacloud-prom`)

1. `ancora_tool_calls_total` → ¿devuelve series? Si no, buscar el nombre real con
   `{__name__=~"ancora_tool.*"}`.
2. `count by (ancora_tool_name, ancora_tool_outcome) (ancora_tool_calls_total)` → las
   etiquetas deben llamarse exactamente así.
3. `ancora_tool_call_duration_milliseconds_bucket` → ¿existe? Si falta el sufijo
   `_milliseconds`, probar `{__name__=~"ancora_tool_call_duration.*"}`.
4. Sin tráfico reciente puede no haber muestras: provocar una interacción con una tool
   de lectura (autorizada, coste ≈ 0,0034 USD) o consultar con ventana de 24 h. Una
   serie vacía **no** es cero ni prueba de fallo.

Si algún nombre difiere, corregir el JSON **y** `test_tool_panels_match_the_metrics_the_hook_emits`
antes de importar. Reimportar sobrescribe el v1 por UID: exportar antes una copia.

## Incremento demo — 2026-10-17 (no cierra T7)

Reutilizado el Collector privado existente y confirmado el datasource
`grafanacloud-prom`. Dashboard `ancoramind-health` **v1 importado**, 11 paneles,
con salud/revisión/heartbeats reales visibles. Corregidos en el JSON versionado
los contadores `ancora_health_heartbeat_total` y `ancora_telegram_admissions_total`,
con regresión en `tests/unit/test_health_dashboard.py`.

Las 17 expresiones responden 200/success; ello no demuestra que todas tengan
muestras. Circuit/budget-exceeded/coste real/tokens no tienen muestras en 24 h;
no se sustituyen por cero. Las señales event-driven dependen del tráfico.
Alertas, degradación y rotación siguen pendientes, sin cambios en esta sesión.

Dashboard: https://tinyvan1950.grafana.net/d/ancoramind-health/ancoramind-c2b7-salud-operativa

Detalle de SHA/checksum, entorno, límites y gates locales:
`specs/008-railway-deployment/mvp-release-campaign.md`.
El estado fechado debajo es el histórico anterior a esta importación.

> **Fecha inicial:** 2026-09-24 · **Actualizado:** 2026-10-15 · **Estado:** 🔶
> T1–T6 implementados localmente; T7 tiene evidencia de despliegue e ingestión
> base Railway/Grafana Cloud, pero dashboard/alertas aún requieren normalización,
> provisioning y prueba de notificación.

## Evidencia local

| Check | Resultado |
|---|---|
| Registro in-process y `GET /health/readiness` metadata-only | ✅ Implementado y cubierto por unit tests focales |
| Readiness sin I/O request-time | ✅ El handler sólo devuelve `HealthRegistry.snapshot()` |
| Probes acotados DB/Gateway y estados de tasks | ✅ Monitor de background fail-open |
| Fallo DB/Gateway sin detalles privados | ✅ Estado `degraded`; no se retienen cuerpos, credenciales ni excepciones |
| Task de worker/processor terminada | ✅ El monitor la marca `degraded` |
| Fallo inesperado de una dependencia del monitor | ✅ Se registra sólo un warning y el monitor continúa; la cancelación se propaga normalmente |
| Dashboard y reglas de alertas versionados | ✅ JSON válido; nombres/labels quedan pendientes de normalización contra series reales |

## Evidencia local adicional — 2026-09-30 (T7 parcial)

Una prueba de regresión en `tests/unit/test_health_monitor_lifecycle.py` combina
un fallo de la fachada de métricas (medidor local que falla al publicar las
transiciones `healthy` → `degraded`, con invocaciones verificadas), base de datos
inaccesible y task del worker terminada: el monitor sigue vivo,
`/health/readiness` responde `200` y publica
ambos componentes como `degraded` sin filtrar el detalle privado. No hubo
Collector/OTLP real, despliegue ni cambios en las rutas de producción. Esta
prueba no sustituye la matriz operativa ni cierra T7/BL-33.

Validación local (2026-09-30): `python -m pytest tests/unit/ -q` → **552 passed**;
`python -m pytest tests/integration/ -q` → **71 skipped** (sin PostgreSQL);
`python -m ruff check src/ tests/ scripts/ migrations/` → limpio;
`python -m mypy src/` → limpio (107 módulos); `git diff --check` → limpio.
OTel advirtió de que no había Collector en `localhost:4318`; no afectó a los
resultados de los tests.

El 2026-09-24 no se pudo ejecutar Pytest ni Ruff en esa estación: no existía
`.venv` del proyecto y los intérpretes disponibles son Python 3.10/3.11, mientras
que el proyecto requiere Python 3.12+. Una vez preparado el entorno, los
comandos de validación local son:

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests/unit/test_health.py tests/unit/test_health_monitor_lifecycle.py tests/unit/test_health_alerts.py -q
python -m pytest tests/unit/ -q
ruff check src/ tests/ scripts/ migrations/
```

## Matriz reproducible de degradación

Estas pruebas son operativas: se ejecutan únicamente en un entorno autorizado.
No copiar contenido de Telegram, prompts, payloads, tokens ni respuestas de
probes a tickets, logs o capturas.

| Escenario | Inyección controlada | Comportamiento esperado | Evidencia mínima para T7 |
|---|---|---|---|
| PostgreSQL inaccesible | Cortar temporalmente la conectividad de `ANCORA_DATABASE_URL` o usar una instancia de staging detenida | La app sigue atendiendo; el monitor marca `database=degraded`; `/health/readiness` sigue `200`; no se reintenta ni bloquea una request | UTC, `deployment_id`, respuesta redactada de readiness antes/después, logs sin secretos y serie de componente degradado |
| LiteLLM Gateway inaccesible | Detener sólo el servicio Gateway de staging o bloquear su hostname privado | La app sigue atendiendo capacidades que no necesitan LLM; el monitor marca `gateway=degraded`; no hay fallback directo al provider | UTC, `deployment_id`, estado de ambos servicios, readiness de app y Gateway, serie/alerta de Gateway |
| Worker o processor detenido | Provocar una terminación controlada de la task en staging, sin matar el proceso de la app | El monitor marca `reminder_worker` o `interaction_processor` como `degraded`; readiness permanece informativo y `200` | UTC, `deployment_id`, componente afectado, captura de la métrica y evidencia del estado de la task sin datos de usuario |
| Collector u OTLP inaccesible | Retirar temporalmente la conectividad app→Collector o las credenciales de exportación sólo en staging | La funcionalidad y el shutdown de la app continúan; puede faltar telemetría remota durante la ventana; no deben aparecer datos personales en logs | UTC, `deployment_id`, estado Railway de app/Collector, logs sanitizados y confirmación de recuperación de exportación |

Para revertir cada inyección, restaurar la conectividad o servicio original y
confirmar primero que el componente vuelve a `healthy` en readiness; después
confirmar la serie correspondiente en Grafana. Nunca usar producción para una
prueba destructiva sin una ventana de mantenimiento aprobada.

## Procedimiento de cierre T7 (Railway + Grafana)

Los pasos de infraestructura 1 y 2 se validaron el 2026-10-15: el Collector
privado está desplegado junto a la app en `europe-west4-drams3a`, el datasource
es `grafanacloud-prom` y Grafana recibe las series base. El procedimiento de
consulta y diagnóstico queda en `docs/runbooks-013.md` §7.

Revalidación de solo lectura del deployment
`c26640ef-f836-423d-8050-e9d408edecda`: Collector online, una réplica y cero
fallos recientes. Sus logs no contienen `429`, `ResourceExhausted`, `Throttle`
ni `Exporting failed`. Los `429` encontrados al consultar el historial pertenecen
a deployments anteriores y terminan el 2026-10-11. Se considera resuelto el
incidente de exportación; esto no completa por sí solo dashboard, alertas ni la
matriz de degradación de T7.

1. Repetir las consultas base de §7.2 del runbook y registrar UTC, commit,
   deployment y resultado sin contenido personal.
2. Importar `observability/dashboards/ancoramind-health.json` y provisionar
   `observability/alerts/ancoramind-health-alerts.json` en Grafana Cloud.
3. Consultar cada serie y label usados por los paneles/reglas, y normalizarlos
   contra muestras reales antes de habilitar alertas. Las métricas confirmadas
   hoy son `ancora_health_component`, `ancora_health_heartbeat_total` y
   `ancora_runtime_config_revision`; no asumir que las métricas event-driven
   tienen muestras cuando no hubo tráfico.
4. Ejecutar la matriz anterior en staging. Para cada fila conservar evidencia
   con UTC, entorno, `deployment_id`, servicio, query Grafana y resultado; las
   capturas deben contener sólo metadata operacional.
5. Probar recepción y resolución de cada alerta sin notificar durante ventanas
   de mantenimiento. Silenciar explícitamente la alerta de ausencia de admissions
   cuando el webhook/admission esté intencionadamente deshabilitado o no haya
   tráfico esperado; no modificar la expresión para ocultar una incidencia.
6. Registrar los resultados, las queries normalizadas, el UID del dashboard y
   las reglas efectivamente habilitadas en esta sección. Sólo entonces marcar T7
   como completada en `specs/016-health-dashboard/tasks.md` y `BACKLOG.md`.

## Criterios de aceptación pendientes

- El readiness público de AncoraMind no incluye secretos, identificadores de
  Telegram, contenido personal, `correlation_id`, prompts ni cuerpos de error.
- DB, Gateway, worker y processor se distinguen como señales independientes.
- Una caída de Collector/Grafana no degrada la capacidad funcional de la app.
- Las alertas consultan series realmente presentes en Grafana Cloud y están
  encaminadas a un destino operativo probado.