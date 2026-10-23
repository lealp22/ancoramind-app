# ADR-006 — OpenTelemetry como estándar de observabilidad

> **Status:** Accepted; implementación base completada el 2026-09-14 (T10).
> El Collector privado y la ingesta de métricas base en Grafana Cloud se
> validaron en Railway producción el 2026-10-15. La normalización/provisioning
> completo de dashboard y alertas sigue pendiente en Spec-016.
> **Contexto:** AncoraMind necesita explicar y controlar el flujo Telegram →
> Agent → tools → Gateway → provider sin registrar indiscriminadamente datos
> personales.

---

## Contexto

El estado previo usaba logs textuales y telemetría de producto de Agno habilitada
por default. T10 introduce logs JSON metadata-only, trazas/métricas OTel propias,
correlación por `correlation_id` y un manifiesto de Collector versionado. Grafana
Cloud sigue siendo el backend inicial, pero el código no se acopla a ese vendor.

## Decisión

1. **Estándar** — OpenTelemetry API/SDK y convenciones compatibles.
2. **Pipeline** — AncoraMind y LiteLLM envían OTLP por red privada a un
   OpenTelemetry Collector upstream en Railway.
3. **Backend inicial** — Grafana Cloud. Cambiarlo requiere sustituir exporter,
   dashboards y alertas, no reinstrumentar la aplicación.
4. **Auditoría durable** — PostgreSQL conserva interacciones, config y usage
   mínimos; Grafana no es fuente de verdad.
5. **Fail open** — Collector/Grafana no bloquean Telegram, Core o inferencia.
6. **Telemetría Agno** — se desactiva en Agent, AgentOS y environment.
7. **Privacidad** — allowlist de metadata; no se exportan prompts, mensajes,
   respuestas, documentos, extracciones ni argumentos/resultados completos.
   *Enmienda (2026-10-23, ADR-007):* aplica a este pipeline (Collector/Grafana),
   que sigue sin contenido. El pipeline separado de Phoenix puede recibir contenido
   enmascarado bajo las condiciones de ADR-007.
8. **Correlación** — `correlation_id`, IDs Railway/Telegram/Agno/Gateway/provider,
   ruta, revisión, tokens, coste, latencia, errores y circuit state.
9. **Cardinalidad** — IDs solo como atributos de spans/logs, nunca labels de
   métricas no acotadas.
10. **Collector** — redacción/allowlist, memory limiter, batch y cola/retry
    acotados antes de exportar.
11. **Sampling inicial** — 100% metadata-only durante hardening; errores,
    fallbacks, budgets y circuits conservarán prioridad en una política futura.
12. **Implementación T10** — `src/observability/` aplica allowlist estricta;
    las métricas excluyen IDs de alta cardinalidad y los logs no serializan ni el
    mensaje ni argumentos posicionales. El exporter OTLP es opcional y fail-open.

## Separación de responsabilidades

```text
PostgreSQL responde: qué interacción/config/acción quedó registrada.
Grafana responde: cómo se ejecutó y qué ocurrió técnicamente.
```

La pérdida de una trace es aceptable; la pérdida de auditoría canónica no.

## Consecuencias

### Positivas

- Trazas vendor-neutral de extremo a extremo.
- Control sobre datos, sampling, redacción, retención y destinos.
- Cambio futuro de Grafana sin cambios de dominio/runtime.
- Alertas de amplificación, coste, repetición, fallback y circuit.

### Negativas

- Tercer servicio Railway y configuración adicional.
- Dashboards/alertas siguen siendo artefactos dependientes de Grafana.
- Se requieren privacy tests y control de cardinalidad.
- La observabilidad puede perder eventos durante caídas; no es auditoría durable.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Solo logs Railway | No ofrece trazas distribuidas ni pipeline portable |
| Telemetría Agno como sistema principal | Salida a tercero sin control suficiente del pipeline |
| SDK específico de Grafana en aplicación | Acoplamiento innecesario al backend |
| Exportación directa sin Collector | Menor control central de redacción/retries/destinos |
| Grafana Alloy inicial | Collector upstream es más neutral; Alloy se evaluará si aporta ventaja concreta |
| Stack Grafana/Tempo/Loki self-hosted | Complejidad prematura para el MVP |
| Capturar prompts/respuestas | Riesgo de privacidad incompatible con minimización |

## Re-evaluación

Reabrir si Grafana Alloy aporta una capacidad necesaria no disponible en el
Collector upstream, el volumen exige tail/adaptive sampling especializado o los
requisitos legales obligan a cambiar backend, región o retención.
