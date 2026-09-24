# Verification: 016 — Health Signals and Dashboard

> **Fecha:** 2026-09-24 · **Estado:** 🔶 T1–T6 implementados localmente; T7
> requiere despliegue y evidencia en Railway/Grafana Cloud.

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

No se pudo ejecutar Pytest ni Ruff en esta estación el 2026-09-24: no existe
`.venv` del proyecto y los intérpretes disponibles son Python 3.10/3.11, mientras
que el proyecto requiere Python 3.12+. La validación pendiente tras preparar ese
entorno es:

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

1. Resolver los bloqueos anotados en `BACKLOG.md`: push autorizado del
   `observability/Dockerfile`, alineación de región del Collector con la app y
   creación de `GRAFANA_OTLP_ENDPOINT` y `GRAFANA_OTLP_AUTHORIZATION` como
   secretos de Railway.
2. Desplegar el Collector privado sin dominio público y configurar la app para
   exportar únicamente a `http://ancoramind-otel-collector.railway.internal:4317`.
   Verificar que el Collector valida su configuración y que la app permanece
   disponible si el Collector está caído.
3. Importar `observability/dashboards/ancoramind-health.json` y provisionar
   `observability/alerts/ancoramind-health-alerts.json` en Grafana Cloud.
4. Consultar las series recibidas en Grafana y normalizar los nombres Prometheus
   y labels reales antes de habilitar alertas. En particular confirmar los nombres
   derivados de `ancora.health.component`, `ancora.health.heartbeat` y
   `ancora.interactions.last_processed.age_seconds`; no asumir que el backend
   conserva exactamente los nombres del JSON local.
5. Ejecutar la matriz anterior en staging. Para cada fila conservar evidencia
   con UTC, entorno, `deployment_id`, servicio, query Grafana y resultado; las
   capturas deben contener sólo metadata operacional.
6. Probar recepción y resolución de cada alerta sin notificar durante ventanas
   de mantenimiento. Silenciar explícitamente la alerta de ausencia de admissions
   cuando el webhook/admission esté intencionadamente deshabilitado o no haya
   tráfico esperado; no modificar la expresión para ocultar una incidencia.
7. Registrar los resultados, las queries normalizadas, el UID del dashboard y
   las reglas efectivamente habilitadas en esta sección. Sólo entonces marcar T7
   como completada en `specs/016-health-dashboard/tasks.md` y `BACKLOG.md`.

## Criterios de aceptación pendientes

- El readiness público de AncoraMind no incluye secretos, identificadores de
  Telegram, contenido personal, `correlation_id`, prompts ni cuerpos de error.
- DB, Gateway, worker y processor se distinguen como señales independientes.
- Una caída de Collector/Grafana no degrada la capacidad funcional de la app.
- Las alertas consultan series realmente presentes en Grafana Cloud y están
  encaminadas a un destino operativo probado.