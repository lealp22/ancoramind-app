# AncoraMind — Runbooks operativos specs/013 (BL-23)

> **Alcance:** flags, ledger/procesador Telegram, Governed LLM Access,
> Gateway LiteLLM y observabilidad aprobados en specs/013. Comandos con
> `<placeholders>`; sin secretos. Rollout pendiente en
> `docs/deployment-railway.md` §3; evidencia local en
> `specs/013-llm-access-governance/verification.md`.

## 0. Mapa rápido síntoma → runbook

| Síntoma | Ir a |
|---|---|
| Errores de inferencia con Gateway activo | §1 Gateway down |
| `429 No deployments available` del Gateway | §2 Circuit open |
| Runs `failed_controlled` con `CostGovernanceError` | §3 Budget exhausted |
| Filas `failed_ambiguous` tras restart/deploy | §4 failed_ambiguous |
| App sana pero sin trazas en Grafana | §6 Collector down |
| Revisión runtime mala activa | §7 Rollback de config |
| Cambio de cualquier secreto/token/key | §8.4 Rotación |

Estados: `accepted` (recuperable) → `agent_started` →
`response_ready` (recuperable) → `delivery_started` → `completed`.
`agent_started` / `delivery_started` nunca se reintentan: el recovery los
marca `failed_ambiguous`.

## 1. Gateway down (LiteLLM caído — fail closed)

**Señales:** errores de inferencia en todos los runs; el Gateway no responde
a `/health/readiness`; `llm_usage_events` deja de crecer.

1. Confirmar desde la shell Railway (red privada, nunca público):

```powershell
curl http://<servicio-litellm>.railway.internal:4000/health/readiness
```

2. Revisar deployment, logs y DB dedicada del servicio LiteLLM.
3. **No crear bypass directo**: con `LITELLM_PROXY_ENABLED=true` la app falla
   cerrada por diseño. Un provider directo exigiría cambio de código + spec.
4. Con el Gateway caído, verificar el backlog `accepted` en PostgreSQL y
   avisar del retraso; no reinyectar updates.
5. Tras SUCCESS, validar un único update de prueba (`provider=litellm` en
   `llm_usage_events`) antes de cerrar.

## 2. Circuit open (upstream degradado)

**Señales:** `429 No deployments available`; `allowed_fails`/`cooldown_time`
en `gateway/litellm-config.yaml`; upstream con 5xx/timeouts.

1. Confirmar fast-fail: cero llamadas al upstream afectado (acceptance F).

## 3. Budget exhausted (hard stop de coste)

**Señales:** `failed_controlled` con `error_class= CostGovernanceError` y
`error_detail_code` en (`external_monthly_hard_stop`,
`daily_budget_exhausted`, `monthly_budget_exhausted`,
`route_monthly_budget_exhausted`); contador
`ancora.cost_governance.hard_stop`.

1. **No reinyectar el run**: el hard stop es determinista y pre-inferencia.
2. Consultar el spend agregado (fuente: `ancora.llm_usage_events`, real con
   precedencia sobre estimado).
3. Reconciliar el límite externo antes de tocar techos:

```powershell
curl https://openrouter.ai/api/v1/key `
  -H "Authorization: Bearer <OPENROUTER_API_KEY>"
```

comparar `limit`/`limit_remaining` y usage diario/semanal/mensual.
4. Subir techos solo mediante revisión runtime CAS con actor/motivo:

```powershell
$env:RUNTIME_CONFIG_ADMIN_TOKEN='<token>'
$env:RUNTIME_CONFIG_ADMIN_ACTOR='<operador>'
python scripts/runtime_config.py activate --base-url <app-url> `
  --revision <N> --expected-current-revision <M> --reason "<motivo>"
```

5. Ante consumo anómalo, revisar `model_call_count`/`gateway_request_count`
   por `correlation_id` antes de ampliar budgets (posible incidente).

## 4. `failed_ambiguous` (crash/deploy tras efecto incierto)

**Señales:** filas `failed_ambiguous` (`restart_after_agent_started`,
`restart_during_delivery`, `agent_run_failed_after_claim`, ...).

1. **No reejecutar el Agent ni reenviar el chunk.**
2. Inspeccionar metadata (nunca descifrar contenido salvo necesidad
   justificada):

```sql
SELECT status, error_class, error_detail_code, agno_run_id,
       model_call_count, gateway_request_count, tool_call_count,
       estimated_cost, actual_cost, completed_at
FROM ancora.telegram_interactions WHERE id = '<correlation_id>';
```

3. Si existe `logical_responses` pendiente y el chunk sigue `pending`, el
   delivery puede continuar; si está `sending`, no reenviar.
4. Responder al usuario solo con mensaje nuevo (nuevo `update_id`); el
   ledger marcaría el original como `duplicate` de todos modos.
5. Payloads `failed_ambiguous` se purgan a los 7 días; la metadata queda.

## 5. Crash injection y reinicios (matriz local T13)

Cubierta por `tests/integration/test_hardening_013.py`:

| Escenario | Esperado |
|---|---|
| 20 deliveries concurrentes, mismo `update_id` | 1 interaction, 20 deliveries, 1 claim |
| N updates distintos, mismo chat | orden `received_at, update_id`, 1 run c/u |
| Caída tras `agent_started` (sin outbox) | `failed_ambiguous`, 1 run, 0 deliveries |
| Caída tras `delivery_started` | `failed_ambiguous`, sin reenvío |
| Restart con `response_ready` pendiente | delivery sin rerun del Agent |
| Retención vencida (`failed_ambiguous` + 8 días) | payload borrado, metadata conservada |

## 6. Collector down (observabilidad fail open)

**Señales:** app sana pero Grafana sin trazas; errores OTLP en el Collector.

1. La funcionalidad **no se detiene** (acceptance R). No reiniciar la app.
2. Revisar el servicio Collector (`observability/otel-collector.yaml`):
   memoria, cola, `GRAFANA_OTLP_*` y conectividad.
3. La auditoría sigue en PostgreSQL; Grafana nunca es fuente de verdad.
4. Tras recuperarlo, verificar un `correlation_id` E2E (acceptance I).

## 7. Rollback de configuración runtime

Toda activación usa CAS: ante `409`, releer `status` y reintentar.

```powershell
$env:RUNTIME_CONFIG_ADMIN_TOKEN='<token>'
$env:RUNTIME_CONFIG_ADMIN_ACTOR='<operador>'
python scripts/runtime_config.py status --base-url <app-url>
python scripts/runtime_config.py validate --base-url <app-url> --config candidato.json
python scripts/runtime_config.py activate --base-url <app-url> `
  --revision <N> --expected-current-revision <M> --reason "<motivo>"
python scripts/runtime_config.py rollback --base-url <app-url> `
  --revision <M> --expected-current-revision <N> --reason "<motivo>"
```

Reglas: revisión inválida nunca sustituye la last-known-good; runs activos
conservan su snapshot; payloads con secretos se rechazan (422).

## 8. Pendientes explícitos del rollout (no cierran BL-23)

### 8.1 E2E Telegram en Railway

`alembic upgrade head` (0003) → registrar webhook → activar
`TELEGRAM_ADMISSION_ENABLED=true` → validar update real → activar
`TELEGRAM_PROCESSOR_ENABLED=true` y validar orden/duplicados/deploys.

### 8.2 Benchmark LiteLLM con clave real

p50/p95/p99 + TTFT directo vs Gateway; decidir SLO antes de cualquier retry
o fallback cross-model (hoy a 0 por decisión T12).

### 8.3 Grafana Cloud

Stack/región, `GRAFANA_OTLP_*`, dashboards (amplificación, budget,
fallback, circuit, latencia), alertas 60/80/90%, retención y acceso.

### 8.4 Rotación de secretos (procedimiento)

| Secreto | Rotación |
|---|---|
| `RUNTIME_CONFIG_ADMIN_TOKEN` | generar → Railway → verificar `status` 200 → revocar anterior |
| `TELEGRAM_PAYLOAD_ENCRYPTION_KEY` | nueva Fernet + `KEY_VERSION=N+1`; payloads viejos se purgan por retención |
| LiteLLM virtual key | `/key/delete` + `generate` → actualizar secreto → verificar `/v1/models` |
| Credenciales OTLP Grafana | rotar en Grafana → secretos del Collector → verificar ingesta |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | generar → Railway + `setWebhook` con `secret_token` → validar |

Ningún secreto vive en revisiones runtime, Git, logs o telemetría.

2. Verificar el upstream y los límites de la key (`GET
   https://openrouter.ai/api/v1/key`: `limit`/`limit_remaining`).
3. No tocar `num_retries` ni añadir fallbacks en caliente (política T12: 0).
4. Esperar el cooldown (60 s); el primer request tras el cooldown hace de
   probe (HALF_OPEN → CLOSED). Si el upstream sigue caído, vuelve a OPEN.
5. Solo ante incidente prolongado, activar revisión runtime con ruta
   alternativa ya provisionada (ver §7), nunca editar el alias en uso.
