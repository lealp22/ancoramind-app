# Verification: 016 — Health Signals and Dashboard

## Dashboard actualizado vía MCP de Grafana (2026-10-22)

Con el servidor MCP de Grafana (solo lectura de series + una escritura del
dashboard) se contrastaron las consultas con las series reales de
`grafanacloud-prom` y se aplicó el cambio al dashboard `ancoramind-health`
(versión 2 en Grafana; la 1, "Initial save" del 2026-10-17, queda en el historial y
es restaurable). El `version` del JSON del repo (3) y el de Grafana (2) son
contadores distintos. Dos cambios:

1. **Panel de coste corregido.** "Coste y tokens LLM" consultaba
   `ancora_llm_actual_cost_usd_total` y `ancora_llm_total_tokens_total`, que **no
   existen** en Grafana: solo se emiten si el proveedor devuelve uso, y hoy no lo
   hace. Ahora es "Coste estimado LLM (USD)" sobre `ancora_llm_estimated_cost_usd_total`
   (con muestras: 0,246 USD en 7 días, 0,0097 en 24 h) y su descripción dice que es
   una estimación, no facturación.
2. **Dos paneles de tools nuevos** (`y: 29`), sin mover los 11 existentes:

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

**Nombres de serie CONFIRMADOS** contra Grafana el 2026-10-22: existen
`ancora_tool_calls_total` y `ancora_tool_call_duration_milliseconds_bucket`, con las
etiquetas `ancora_tool_name` y `ancora_tool_outcome`, y con muestras reales en 7 días
(`present_reply`, `list_todo_lists`, `list_todo_items`, `list_pending_proposals`,
`propose_todo_item`, `find_vehicle`, etc.). Las tools sin uso en la ventana tienen la
serie pero valor 0/`NaN`: en la gráfica simplemente no se dibujan. `search_web` no
aparece porque el servicio desplegado aún no la incluye (deployments de Railway
pendientes). El test `test_tool_panels_match_the_metrics_the_hook_emits` protege
contra un renombrado en el hook.

### Series del dashboard que no tienen muestras (no es un error de nombre)

Comprobado con `list_prometheus_metric_names` en 30 días. No existen y no se
presentan como cero:

| Serie | Motivo |
|---|---|
| `ancora_llm_actual_cost_usd_total`, `ancora_llm_total_tokens_total` | Solo se emiten si el proveedor devuelve uso (`governed_model.py`) |
| `ancora_execution_budget_exceeded_total` | Evento: no se ha excedido ningún presupuesto |
| `ancora_cost_governance_hard_stop_total` | Evento: no ha habido corte duro de coste |
| `ancora_gateway_circuit_state` | **Ver el hallazgo siguiente** |

### Hallazgo: el estado del circuit breaker nunca se publica como `open`

`HealthRegistry.set_circuit_state` es la única fuente de `ancora_gateway_circuit_state`,
y su **único** llamador (`src/agent/health.py:272`, el monitor) lo invoca siempre con
`"unknown"`. Con `"unknown"` la métrica vale 0 y el componente queda `unknown`. Por
tanto:

- El panel "Estado del circuit breaker" no puede mostrar nunca un circuito abierto.
- La alerta `max(ancora_gateway_circuit_state{ancora_circuit_state="open"}) > 0`
  (`observability/alerts/ancoramind-health-alerts.json`, regla 1) **no puede dispararse**
  con el código actual, aunque el Gateway abra su circuito.

Es una limitación del código, no de la consulta. **No se ha corregido**: hacerlo
exige leer el estado real del circuito del Gateway (LiteLLM), una decisión de
diseño que toca BL-33/T7, fuera de la ventana de alcance del 2026-10-17. Mientras
tanto, la señal fiable de caída del Gateway es `ancora_health_component{ancora_health_component="gateway"}`,
que sí se actualiza con el probe.

### Alertas en Grafana

`alerting_rules_read(list)` devuelve vacío: **no hay reglas provisionadas** en
Grafana Cloud. Las cinco reglas versionadas siguen sin importar. Estado de sus
series: `ancora_telegram_deliveries_total` (solo estado `completed` en 7 días),
`ancora_health_heartbeat_total` y `ancora_telegram_admissions_total` existen;
`ancora_cost_governance_hard_stop_total` y `ancora_gateway_circuit_state` no (ver
arriba). No se han creado alertas.

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