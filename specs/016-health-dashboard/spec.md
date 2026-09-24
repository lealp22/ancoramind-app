# Spec: 016 — Health Signals & Health Dashboard

> **Backlog:** BL-33
> **Status:** en curso (2026-09-23)
> **Target:** que la salud de AncoraMind se vea a simple vista — señales de
> salud en la aplicación + dashboard Grafana versionado — sin alterar la policy
> de privacidad, el fail-open ni el backend decididos en ADR-006.

---

## Contexto

Análisis de observabilidad (2026-09-23): Grafana, Langfuse y dashboard de
salud. Conclusiones registradas en BACKLOG (BL-33 y BL-8):

- **Fase 1 (no cambia):** el rollout comprometido de BL-23 — Collector privado +
  Grafana Cloud en Railway — sigue siendo el plan y el backend vigente.
- **Fase 2 (este spec):** hoy `/health` (proporcionado por AgentOS) devuelve
  `{"status":"ok"}` y sólo prueba que el proceso escucha. No existe señal alguna
  de conectividad PostgreSQL/Supabase, worker de recordatorios, interaction
  processor, Gateway/circuit breaker, cola de admission o revisión de runtime
  config. El dashboard de ADR-006 no puede construirse sin esas señales.
- **Fase 3 (diferida):** stack OSS local (prometheus + tempo + grafana) como
  espejo de desarrollo vía compose profile — decisión diferida, no bloqueante.
- **Fase 4 (registrada en BL-8):** Langfuse self-hosted queda anotado como
  **candidato para evals en local**, no como pieza de observabilidad de
  producción (solapa con Grafana en modo metadata-only o exigiría enmendar
  ADR-006 si capturara contenido).

## Requirement

### Must Have

1. **Endpoint de salud detallado** `GET /health/readiness` — metadata-only,
   sin secretos, devuelto como JSON con el estado de: conectividad
   PostgreSQL/Supabase, heartbeat del reminder worker, estado del interaction
   processor, profundidad de cola de admission (global pendiente y por chat),
   alcanzabilidad del Gateway LiteLLM y estado del circuit breaker, revisión
   activa de runtime config y edad de la última interacción procesada.
   Opcionalmente bearer-gated reutilizando `RUNTIME_CONFIG_ADMIN_TOKEN`.
2. **Health metrics por OTel** — vía la facade `MetadataTelemetry` existente
   (fail-open, sin scraping Prometheus nuevo): heartbeat del worker, queue
   depth, circuit state, config revision, recordatorios entregados/vencidos y
   resultado del probe de DB. Sólo atributos bounded (enums/estados), sin IDs de
   alta cardinalidad en labels de métricas.
3. **Dashboard Grafana versionado** en `observability/dashboards/` (JSON en
   Git, importable a Grafana Cloud y a un stack OSS futuro) con vista "salud a
   simple vista": status lights (app/DB/Gateway/worker/circuit), tráfico de
   interacciones, duplicados absorbidos por idempotencia, rechazos de
   admission, latencia p50/p95 de runs del Agent y de tools, tokens y coste
   USD/día con % de budget, errores por `error.type`, fallos/retries de
   delivery, recordatorios entregados/vencidos y revisión de config activa.
4. **Alertas** definidas y documentadas: circuit open, spend sobre umbral
   (diario/mensual), spike de errores de delivery, worker sin heartbeat > N
   minutos, 0 interacciones en N horas.
5. **Privacy tests** extendidos si se añaden atributos nuevos a la allowlist
   (`SPAN_ATTRIBUTE_ALLOWLIST` / `METRIC_ATTRIBUTE_ALLOWLIST`).

### Won't Have (este incremento)

- Stack Grafana OSS/Prometheus/Tempo self-hosted (fase 3, diferida).
- Langfuse en cualquier modalidad (candidato BL-8; ver BACKLOG).
- Endpoint de métricas Prometheus: las métricas siguen saliendo por OTLP al
  Collector.
- Cambiar el backend Grafana Cloud o el manifiesto del Collector (ADR-006).
- Exponer contenido personal, prompts, mensajes ni secretos en
  readiness/metrics/dashboard.

## Design

```text
lifespans (worker / processor / runtime config) ─┐
Telegram admission + repos                        ─┼→ HealthRegistry (in-process, volatile)
LLMAccess / circuit breaker                      ─┘         │
                                                            ├→ GET /health/readiness (JSON metadata-only)
                                                            └→ gauges/counters OTel → Collector → Grafana
```

- `src/agent/health.py` (o similar): registro in-process donde cada lifespan/
  worker/circuito publica su última señal; el GET no hace I/O nueva salvo un
  probe opcional y acotado de DB/Gateway.
- **Semántica de fallo:** `/health` de AgentOS/Railway queda intacto como gate
  de deploy; `/health/readiness` es informativo y nunca bloquea tráfico. Las
  health metrics heredan el fail-open del exporter OTLP (un Collector caído
  no afecta ni al arranque ni a la operación).
- **Cardinalidad/privacidad:** reutilizar los enums ya allowlisted
  (`ancora.status`, `ancora.admission.status`, `ancora.delivery.status`,
  `ancora.circuit.state`…); los IDs correlativos (correlation_id,
  interaction_id) siguen siendo sólo atributos de span, nunca labels de
  métricas.
- **Dashboard como artefacto evaluable:** el JSON del dashboard se versiona en
  `observability/dashboards/` junto al manifiesto del Collector; cualquier
  cambio de panel/alerta se anota como cambio evaluable (gobernanza).

## Success Criteria

1. `GET /health` permanece intacto y devuelve `2xx` con Collector caído, DB
   caída o worker parado (fail-open demostrado en tests).
2. `GET /health/readiness` refleja correctamente worker, processor, DB,
   Gateway, circuit, cola y config revision (unit tests con fakes +
   verificación en entorno real Railway o local).
3. Las health metrics exportan atributos exclusivamente de la allowlist; los
   privacy tests lo demuestran y fallan ante un atributo de contenido.
4. El dashboard JSON existe versionado y, importado en Grafana Cloud con el
   pipeline T10 activo, muestra la vista de salud con datos reales.
5. Las alertas están definidas en el propio dashboard y documentadas en el
   runbook (`docs/runbooks-013.md`).
6. `pytest tests/unit/` y Ruff verdes.
