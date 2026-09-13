# Verification: 013 — Governed LLM Access and Telegram Admission

> **Estado:** ⏳ pendiente de implementación
> **Diseño aprobado:** 2026-09-13

---

## Environment

| Campo | Valor |
|---|---|
| Commit | Pendiente |
| Python | Pendiente |
| Agno | Baseline: 2.9.0 |
| LiteLLM | Pendiente |
| PostgreSQL | Pendiente |
| Railway environment | Pendiente |
| Grafana Cloud region | Pendiente |

## Automated checks

| Check | Resultado | Evidencia |
|---|---|---|
| Unit tests | ⏳ | |
| Integration tests | ⏳ | |
| Ruff | ⏳ | |
| Migration fresh install | ⏳ | |
| Migration upgrade over existing data | ⏳ | |
| Migration downgrade | ⏳ | |
| Privacy tests | ⏳ | |
| LiteLLM latency benchmark | ⏳ | |
| Load/concurrency tests | ⏳ | |
| Crash-injection tests | ⏳ | |

## Acceptance matrix

| ID | Escenario | Resultado | Evidencia |
|---|---|---|---|
| A | Mismo update concurrente varias veces → una interaction y un Agent run | ⏳ | |
| B | Railway request IDs distintos + mismo update → duplicate delivery | ⏳ | |
| C | Cambio runtime → siguiente run usa nueva revisión sin redeploy | ⏳ | |
| D | Config inválida → last-known-good/bootstrap permanece | ⏳ | |
| E | Primary falla → no se supera attempt budget | ⏳ | |
| F | Circuit open → cero llamadas al upstream afectado | ⏳ | |
| G | Rate/budget agotado → no hay inferencia adicional | ⏳ | |
| H | Tool loop → fingerprint/budget lo detiene | ⏳ | |
| I | Interacción completa trazable por `correlation_id` | ⏳ | |
| J | Crash antes de `agent_started` → recuperable | ⏳ | |
| K | Crash después de `agent_started` → `failed_ambiguous`, sin replay | ⏳ | |
| L | Crash tras `response_ready` → delivery recuperable | ⏳ | |
| M | Crash durante delivery → no reenvío automático ambiguo | ⏳ | |
| N | Grupo/canal Telegram → no alcanza el Agent | ⏳ | |
| O | Usuario no allowlisted → no alcanza el Agent | ⏳ | |
| P | Extracción documental comparte config, budget y trace | ⏳ | |
| Q | Gateway caído → fail closed sin OpenRouter directo | ⏳ | |
| R | Collector caído → aplicación continúa | ⏳ | |
| S | Logs/traces no contienen contenido personal | ⏳ | |
| T | Activaciones concurrentes → compare-and-swap evita pisadas | ⏳ | |
| U | Run activo durante cambio → conserva revisión anterior | ⏳ | |
| V | Duplicate delivery → no consume rate limit | ⏳ | |
| W | Rate limit superado → `2xx` y cero inferencias | ⏳ | |
| X | Tool call 12 → permitida si queda budget | ⏳ | |
| Y | Tool call 13 → rechazada por hard ceiling | ⏳ | |

## Production validation

- [ ] Webhook estable conserva `/telegram/webhook`.
- [ ] Duplicate delivery real de Telegram no repite Agent/LLM.
- [ ] Cambio de ruta/modelo real sin deployment.
- [ ] LiteLLM privado y sin superficie de administración pública.
- [ ] Fail-closed de Gateway validado.
- [ ] Collector/Grafana fail-open validado.
- [ ] Circuit open y cooldown validados.
- [ ] Coste real reconciliado con OpenRouter.
- [ ] Búsqueda por `correlation_id` reconstruye el flujo completo.
- [ ] No se detecta contenido sensible en Grafana o logs Railway.

## Limitations and remaining evidence

- La causa exacta de las ~78 inferencias no se marcará como confirmada sin logs
  de Railway, sesión/run Agno y actividad detallada de OpenRouter del incidente.
- La garantía at-most-once cubre la ejecución del Agent y la persistencia lógica;
  Telegram `sendMessage` no ofrece exactly-once externo.
- Completar esta sección al cerrar la spec con cualquier limitación residual.
