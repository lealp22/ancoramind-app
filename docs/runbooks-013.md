# AncoraMind — Runbooks operativos specs/013 (BL-23)

> **Alcance:** flags, ledger/procesador Telegram, Governed LLM Access,
> Gateway LiteLLM y observabilidad aprobados en specs/013. Comandos con
> `<placeholders>`; sin secretos. Rollout pendiente en
> `docs/deployment-railway.md` §3; evidencia local en
> `specs/013-llm-access-governance/verification.md`.

## 0. Mapa rápido síntoma → runbook

| Síntoma | Ir a |
|---|---|
| AncoraMind no responde o Telegram no entrega respuesta | §1 Triage inicial |
| Cambiar el modelo físico sin redeploy | §2.2 Publicación en dos fases |
| Errores de inferencia con Gateway activo | §2 Gateway down |
| `429 No deployments available` del Gateway | §3 Circuit open |
| Runs `failed_controlled` con `CostGovernanceError` | §4 Budget exhausted |
| Filas `failed_ambiguous` tras restart/deploy | §5 failed_ambiguous |
| App sana pero sin trazas en Grafana | §7 Collector down |
| Revisión runtime mala activa | §8 Rollback de config |
| Cambio de cualquier secreto/token/key | §9.4 Rotación |

Estados: `accepted` (recuperable) → `agent_started` →
`response_ready` (recuperable) → `delivery_started` → `completed`.
`agent_started` / `delivery_started` nunca se reintentan: el recovery los
marca `failed_ambiguous`.

## 1. Triage inicial: AncoraMind no responde

**Objetivo:** identificar la capa averiada antes de reiniciar o cambiar
configuración. Registrar siempre UTC, `deployment_id`, servicio afectado y, si
existe, `correlation_id`/`telegram.update_id`; no copiar mensajes, prompts,
payloads ni secretos a tickets o logs.

| Observación | Diagnóstico probable | Acción inmediata |
|---|---|---|
| El deployment de `ancoramind-app` no está `SUCCESS`, se reinicia o no acepta HTTP | Aplicación / Railway | Revisar logs y diagnóstico del deployment; corregir la causa antes de redeployar. |
| `ancoramind-app` está sano, pero LiteLLM no responde a readiness | Gateway o su PostgreSQL | Seguir §2. |
| LiteLLM devuelve `429` con `No deployments available` / `NO_DEPLOYMENTS` | Circuit breaker abierto | Seguir §3; no reiniciar para "forzar" tráfico. |
| LiteLLM responde `200`, pero el bot no entrega respuesta | Aplicación, Telegram o interacción | Revisar logs de `ancoramind-app`, estado del webhook y la interacción; aplicar §5 si terminó en `failed_ambiguous`. |
| `failed_controlled` con `CostGovernanceError` | Límite de coste | Seguir §4. |
| Solo faltan trazas en Grafana, pero bot y Gateway funcionan | Observabilidad | Seguir §7; no es una caída funcional. |

### 1.1 Comprobaciones en Railway

1. Abrir **Deployments** de `ancoramind-app` y de `LiteLLM` en el entorno
   afectado. Ambos deben estar en `SUCCESS` antes de investigar el proveedor.
2. Revisar los logs del deployment más reciente, buscando códigos HTTP,
   `NO_DEPLOYMENTS`, errores de autenticación/configuración o reinicios. No
   registrar contenido personal de conversaciones.
3. Desde Railway shell/agent y por la red privada, comprobar el Gateway:

   ```powershell
   curl http://<servicio-litellm>.railway.internal:4000/health/readiness
   ```

   Un `200` confirma que el proxy está vivo, pero **no** que OpenRouter esté
   disponible; la siguiente inferencia o los logs del Gateway lo confirma.
4. Tras cualquier recuperación, enviar un único mensaje de prueba desde un chat
   autorizado y comprobar una sola llamada `POST /v1/chat/completions → 200` en
   LiteLLM. No reinyectar manualmente updates previos.

## 2. Gateway down (LiteLLM caído — fail closed)

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

### 2.1 Configuración efectiva del Gateway

El servicio Railway **LiteLLM** se ejecuta desde una imagen y lee su
configuración efectiva de la variable secreta `LITELLM_CONFIG_YAML`. El archivo
versionado `gateway/litellm-config.yaml` es la referencia revisable en Git y la
configuración usada en validación local, pero un push por sí solo no actualiza
el Gateway desplegado.

Esto afecta a los **settings de infraestructura y política** (circuit breaker,
retries, aliases base). Para cambiarlos:

1. Revisar y aprobar el cambio en `gateway/litellm-config.yaml`.
2. Copiar el mismo YAML, sin secretos, a `LITELLM_CONFIG_YAML` del servicio
   LiteLLM en Railway.
3. Guardar y redeplegar LiteLLM.
4. Confirmar `/health/readiness → 200`, los aliases esperados y un único
   `POST /v1/chat/completions → 200` de prueba.

No editar `LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `DATABASE_URL`,
`OPENROUTER_API_KEY` ni la virtual key de AncoraMind como parte de un cambio de
modelo. Las credenciales se rotan mediante §9.4.

**Importante:** nunca escribir settings (`general_settings`, `router_settings`,
`litellm_settings`) por API ni Admin UI. LiteLLM los persiste en
`LiteLLM_Config` y **sobrescriben** `gateway/litellm-config.yaml` en el
siguiente arranque, anulando en silencio la política aprobada de circuito,
retries y fallbacks. Sólo se usan las rutas `/model/*`.

### 2.2 Cambio de modelo en caliente (publicación en dos fases)

Con `store_model_in_db: true` un cambio de modelo físico **no requiere redeploy**.
Un alias existente nunca se edita ni se borra: se publica una **generación
nueva** (`r2`, `r3`, …) y una revisión de runtime config apunta a ella
(ADR-005, enmienda 2026-09-18).

```powershell
$env:LITELLM_PROXY_ADMIN_URL='http://<servicio-litellm>.railway.internal:4000'
$env:LITELLM_MASTER_KEY='<sk-master>'
$env:LITELLM_PROXY_VIRTUAL_KEY='<sk-virtual-ancoramind>'

# 1. Estado actual: qué hay y de dónde viene
python scripts/litellm_gateway_alias.py verify

# 2. Publicar la nueva generación (sin reiniciar el Gateway)
python scripts/litellm_gateway_alias.py --dry-run publish `
  --alias ancoramind-default-r2 --model openrouter/gpt-5.6-luna
python scripts/litellm_gateway_alias.py publish `
  --alias ancoramind-default-r2 --model openrouter/gpt-5.6-luna

# 3. Autorizar el alias en la virtual key (aditivo: conserva r1 para el rollback)
python scripts/litellm_gateway_alias.py grant --alias ancoramind-default-r2

# 4. Verificar publicación y, opcionalmente, una inferencia real
python scripts/litellm_gateway_alias.py verify --alias ancoramind-default-r2
python scripts/litellm_gateway_alias.py verify --alias ancoramind-default-r2 --smoke
```

5. Crear y activar la revisión de runtime config que apunte al alias nuevo
   (misma secuencia CAS de §8; el cambio alcanza a los runs nuevos sin reiniciar
   AncoraMind):

```powershell
$env:RUNTIME_CONFIG_ADMIN_TOKEN='<token>'
$env:RUNTIME_CONFIG_ADMIN_ACTOR='<operador>'
python scripts/runtime_config.py status --base-url <app-url>
python scripts/runtime_config.py validate --base-url <app-url> --config candidato.json
python scripts/runtime_config.py create-revision --base-url <app-url> `
  --config candidato.json --reason "<motivo>"
python scripts/runtime_config.py activate --base-url <app-url> `
  --revision <N> --expected-current-revision <M> --reason "<motivo>"
```

6. Confirmar una inferencia real de Telegram y el `effective_gateway_route`
   esperado en `ancora.llm_usage_events`.

**Rollback:** activar de nuevo la revisión anterior. El alias previo sigue
publicado y autorizado porque `grant` es aditivo; no hay que recrear la key.

**Retirada del alias antiguo (sólo tras cerrar la ventana de rollback):**

```powershell
python scripts/litellm_gateway_alias.py retire --alias ancoramind-default-r1
```

`retire` desautoriza el alias en la key y borra sus despliegues. Los aliases
base (`*-r1`) declarados en Git están protegidos: exigen `--allow-base` y no
deben retirarse salvo decisión explícita documentada.

**Garantías verificadas localmente (2026-09-18):** publicar `r2` mientras el
Gateway está en marcha, enrutar una petición a `r2` con el Gateway ya arrancado
(`Received Model Group=ancoramind-default-r2`), idempotencia de una segunda
publicación, `grant` aditivo y `retire` eliminando el despliegue sin afectar a
los aliases base.

**Ejecutado en Railway (2026-09-19, T14 fase 6):** secuencia completa validada
en producción — publicación de `ancoramind-default-r2` en caliente, `grant`
aditivo, revisión runtime 2 activada con CAS, mensaje real de Telegram con
`effective_gateway_route='ancoramind-default-r2'` y rollback bidireccional a la
revisión 1. Dos lecciones operativas que conviene recordar:

1. **`STORE_MODEL_IN_DB` como env var tiene precedencia sobre el yaml.** En
   Railway la variable estaba a `False` aunque
   `gateway/litellm-config.yaml` declaraba `store_model_in_db: true`: con el
   valor en `False`, `/model/new` no publica y los aliases de BD no se sirven.
   Comprobar la variable del servicio (no sólo el yaml) antes de cualquier
   cambio de modelo. Corrección aplicada el 2026-09-19 (`true` + redeploy).
2. **Operación sin secretos fuera de Railway:** con un token de API de
   workspace (revocable) y una clave SSH desechable registrada en Railway, los
   pasos 1–4 y el smoke se ejecutan *dentro* de los contenedores vía
   `railway ssh <servicio> -- python -` con scripts canalizados por stdin; la
   master key, la virtual key y el admin token se leen de las variables de
   entorno de su propio contenedor y nunca se imprimen (la virtual key puede
   leerse con prisma desde la BD del Gateway dentro del propio contenedor).
   Los pasos 5–6 se ejecutan desde el contenedor de la app contra
   `http://localhost:$PORT/admin/runtime-config/*` con
   `$RUNTIME_CONFIG_ADMIN_TOKEN`. Al terminar: `railway ssh keys remove`,
   borrar el par de claves, desinstalar la CLI si se instaló sólo para esto y
   revocar el token de API.

## 3. Circuit open (upstream degradado)

**Señales:** `429 No deployments available`; `allowed_fails`/`cooldown_time`
en `gateway/litellm-config.yaml`; upstream con 5xx/timeouts.

### 3.1 Cómo se activa el circuit breaker

No existe un botón ni una operación manual para abrirlo: LiteLLM lo activa
automáticamente por alias/upstream. La política aprobada es:

```yaml
router_settings:
  num_retries: 0
  allowed_fails: 3
  cooldown_time: 60
```

1. **CLOSED:** el Gateway envía solicitudes al upstream normalmente.
2. Tras **3 fallos consecutivos** del upstream dentro de la ventana del
   Gateway, pasa a **OPEN**.
3. Durante **60 segundos**, fast-faila con `429 No deployments available`
   (`NO_DEPLOYMENTS`) sin enviar más tráfico al upstream afectado.
4. Al terminar el cooldown, la primera solicitud es un probe
   **HALF_OPEN**. Si funciona, el circuito vuelve a **CLOSED**; si falla,
   vuelve a **OPEN** durante otro cooldown.

El breaker evita amplificar una incidencia del proveedor. No reiniciar LiteLLM
ni AncoraMind para intentar resetearlo: puede ocultar la causa y reanudar tráfico
antes de que el upstream se haya recuperado.

### 3.2 Respuesta operativa

1. Confirmar que LiteLLM sigue sano (`/health/readiness → 200`) y que los logs
   muestran `429`/`NO_DEPLOYMENTS`, no una caída del contenedor.
2. Confirmar fast-fail: durante el periodo OPEN no deben aparecer nuevas
   llamadas upstream exitosas/fallidas para ese alias.
3. Revisar OpenRouter: estado del proveedor/modelo, cuota y límite de la key.
   Nunca pegar la key en un ticket o log.
4. Esperar los **60 s** de cooldown y probar una sola solicitud autorizada.
   Si el probe falla, tratar el incidente como upstream aún degradado y repetir
   el ciclo; no generar una ráfaga de pruebas.
5. Mantener `num_retries: 0` y sin fallbacks cross-model durante el incidente.
   Tampoco desactivar `LITELLM_PROXY_ENABLED` para hacer bypass directo: el
   fail-closed es una garantía de seguridad y trazabilidad.
6. Para un incidente prolongado, preparar una revisión runtime que apunte a una
   **ruta alternativa ya provisionada y validada**; aplicar el cambio mediante
   CAS según §8. Nunca sobrescribir en caliente el alias actualmente en uso.
7. Cuando el probe tenga éxito, verificar una respuesta Telegram y un evento de
   uso con `provider=litellm` antes de cerrar el incidente.

## 4. Budget exhausted (hard stop de coste)

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

## 5. `failed_ambiguous` (crash/deploy tras efecto incierto)

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

## 6. Crash injection y reinicios (matriz local T13)

Cubierta por `tests/integration/test_hardening_013.py`:

| Escenario | Esperado |
|---|---|
| 20 deliveries concurrentes, mismo `update_id` | 1 interaction, 20 deliveries, 1 claim |
| N updates distintos, mismo chat | orden `received_at, update_id`, 1 run c/u |
| Caída tras `agent_started` (sin outbox) | `failed_ambiguous`, 1 run, 0 deliveries |
| Caída tras `delivery_started` | `failed_ambiguous`, sin reenvío |
| Restart con `response_ready` pendiente | delivery sin rerun del Agent |
| Retención vencida (`failed_ambiguous` + 8 días) | payload borrado, metadata conservada |

## 7. Collector down (observabilidad fail open)

**Señales:** app sana pero Grafana sin trazas; errores OTLP en el Collector.

1. La funcionalidad **no se detiene** (acceptance R). No reiniciar la app.
2. Revisar el servicio Collector (`observability/otel-collector.yaml`):
   memoria, cola, `GRAFANA_OTLP_*` y conectividad.
3. La auditoría sigue en PostgreSQL; Grafana nunca es fuente de verdad.
4. Tras recuperarlo, verificar un `correlation_id` E2E (acceptance I).

## 8. Rollback de configuración runtime

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

## 9. Pendientes explícitos del rollout (no cierran BL-23)

### 9.1 E2E Telegram en Railway

`alembic upgrade head` (0003) → registrar webhook → activar
`TELEGRAM_ADMISSION_ENABLED=true` → validar update real → activar
`TELEGRAM_PROCESSOR_ENABLED=true` y validar orden/duplicados/deploys.

### 9.2 Benchmark LiteLLM con clave real

p50/p95/p99 + TTFT directo vs Gateway; decidir SLO antes de cualquier retry
o fallback cross-model (hoy a 0 por decisión T12).

### 9.3 Grafana Cloud

Stack/región, `GRAFANA_OTLP_*`, dashboards (amplificación, budget,
fallback, circuit, latencia), alertas 60/80/90%, retención y acceso.

### 9.4 Rotación de secretos (procedimiento)

| Secreto | Rotación |
|---|---|
| `RUNTIME_CONFIG_ADMIN_TOKEN` | generar → Railway → verificar `status` 200 → revocar anterior |
| `TELEGRAM_PAYLOAD_ENCRYPTION_KEY` | nueva Fernet + `KEY_VERSION=N+1`; payloads viejos se purgan por retención |
| LiteLLM virtual key | `/key/delete` + `generate` → actualizar secreto → verificar `/v1/models` |
| Credenciales OTLP Grafana | rotar en Grafana → secretos del Collector → verificar ingesta |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | generar → Railway + `setWebhook` con `secret_token` → validar |

Ningún secreto vive en revisiones runtime, Git, logs o telemetría.
