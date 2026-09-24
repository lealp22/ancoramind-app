# Tasks — Spec 016: Health Signals & Health Dashboard

> **Backlog:** BL-33 · abierto 2026-09-23

## Fase de diseño/verificación

- [ ] T1 · `HealthRegistry` in-process (heartbeats de worker/processor,
      circuit state, config revision, probe de cola de admission) + unit tests
      con fakes.
- [ ] T2 · `GET /health/readiness` metadata-only (opcionalmente
      bearer-gated con `RUNTIME_CONFIG_ADMIN_TOKEN`); `/health` de AgentOS
      intacto. Unit tests de respuesta y de no-exposición de secretos.
- [ ] T3 · Health metrics por la facade OTel (gauges/counters bounded:
      heartbeat, queue depth, circuit state, config revision, recordatorios
      entregados/vencidos, probe DB). Extender privacy tests si hay atributos
      nuevos en la allowlist.
- [ ] T4 · Dashboard `observability/dashboards/ancoramind-health.json`
      (status lights, tráfico/idempotencia/admission, latencias p50/p95,
      tokens/coste USD y % budget, errores por `error.type`, delivery
      retries, recordatorios, config revision) importable a Grafana Cloud.
- [ ] T5 · Alertas (circuit open, spend > umbral, spike de errores de
      delivery, worker sin heartbeat, 0 interacciones en N horas) definidas
      en el dashboard y documentadas en `docs/runbooks-013.md`.
- [ ] T6 · Docs: `docs/deployment-railway.md` (variables y validación del
      readiness), `docs/development.md`, AGENTS/BACKLOG actualizados.
- [ ] T7 · `verification.md`: matriz fail-open (Collector caído / DB caída /
      worker parado), verificación en Railway con Collector activo y captura
      del dashboard renderizado con datos reales.
