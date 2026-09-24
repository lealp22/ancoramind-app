# Tasks — Spec 016: Health Signals & Health Dashboard

> **Backlog:** BL-33 · abierto 2026-09-23

## Fase de diseño/verificación

- [x] T1 · `HealthRegistry` in-process (heartbeats de worker/processor,
      circuit state, config revision, probe de cola de admission) + unit tests
      con fakes.
- [x] T2 · `GET /health/readiness` metadata-only (opcionalmente
      bearer-gated con `RUNTIME_CONFIG_ADMIN_TOKEN`); `/health` de AgentOS
      intacto. Unit tests de respuesta y de no-exposición de secretos.
- [x] T3 · Health metrics por la facade OTel (gauges/counters bounded:
      heartbeat, queue depth, circuit state, config revision, recordatorios
      entregados/vencidos, probe DB). Extender privacy tests si hay atributos
      nuevos en la allowlist.
- [x] T4 · Dashboard `observability/dashboards/ancoramind-health.json`
      (status lights, tráfico/idempotencia/admission, latencias p50/p95,
      tokens/coste USD y % budget, errores por `error.type`, delivery
      retries, recordatorios, config revision) importable a Grafana Cloud.
- [x] T5 · Alertas versionadas en `observability/alerts/` (circuit open, hard
      stop de coste, spike de delivery, worker sin heartbeat y 0 admissions en
      seis horas), con tests estructurales y runbook. Queda normalizar PromQL
      frente a los nombres finales de Grafana Cloud durante T7.
- [x] T6 · Docs: `docs/deployment-railway.md` (variables y validación del
      readiness), `docs/development.md`, Spec/runbook y BACKLOG actualizados.
- [ ] T7 · `verification.md`: matriz fail-open (Collector caído / DB caída /
      worker parado), verificación en Railway con Collector activo y captura
      del dashboard renderizado con datos reales.
