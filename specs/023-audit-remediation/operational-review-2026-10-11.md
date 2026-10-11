# Revisión operativa — BL-23/39/40 — 2026-10-11

## Alcance y decisiones

- Solo lectura remota: inventario Railway, GET acotados sin credenciales,
  SELECT metadata-only en Supabase y diagnóstico del agente Railway restringido
  a lectura. Sin inferencia, updates Telegram, DDL, rotaciones ni cambios remotos.
- Wait for CI desactivado deliberadamente por el propietario; control manual
  sobre el mismo SHA antes del despliegue. No es un hallazgo de seguridad abierto.
- Supabase contiene el schema `ancora`: datos canónicos, propuestas,
  interacciones/outbox, uso LLM y revisiones runtime. Runtime Agno y Gateway en
  Railway según la separación acordada. No migrar tablas por esta revisión.
- Credenciales/valores efectivos ocultos para las herramientas Railway; no
  copiar secretos al chat, evidencias o logs. No inferir un valor de su presencia.

## Evidencia observada

| Control | Resultado y límite |
|---|---|
| Commit de app desplegada | `e25bfc40deafdf975f1f82bd3e9b7c0b3b60b0e9`, deployment `8a583667-4584-4297-ac73-b1a3cd66623a`; revisión local base `9166f55` |
| Salud Railway | App, LiteLLM, Postgres y Collector Online; Redis y litellm-postgres Offline; no fallos en la ventana consultada de 1 h |
| `/health` | GET → 200, sin `x-railway-fallback` |
| `/health/readiness` | GET → 200, observado `2026-10-11T17:18:13Z`; app/DB/Gateway/processor/worker/runtime-config healthy; circuit unknown; revisión activa 2 |
| REST AgentOS | GET `/config`, `/sessions`, `/memories`, `/eval-runs`, `/docs`, `/redoc`, `/openapi.json` → 401 sin bearer |
| Control plane | GET `/admin/runtime-config/status`, `/admin/emergency-stop/status` → 401 sin bearer |
| Gateway/Collector | Sin dominios ni proxies TCP públicos en el inventario consultado |
| Supabase Alembic | `0012_document_content_hash` |
| Runtime Supabase | Revisión 2; default `ancoramind-default-r2`, fast `ancoramind-fast-r1`, vision `ancoramind-vision-r1` |
| Budget de interacción | 12 tools, 6 model calls, 8 Gateway requests, 120 s, 1024 output tokens, coste máximo estimado 0.10 USD |
| Cost governance | 1 USD/día, 20 USD/mes, límite externo configurado 20 USD, alertas 60/80%, hard stop 90%; no reconciliado con OpenRouter real |
| Consent flag | `GOVERNED_CONSENT_ENABLED` no figura en variables de app; default código false. Valor efectivo no comprobado dentro del proceso |
| Flags/env/URLs DB | Valores ocultos: no se certifica APP_ENV, flags efectivos o destinos de AGNO/ANCORA por mera presencia; Supabase sí tiene ledger/runtime-config comprobados por SELECT |
| Gateway DB | Diagnóstico de referencias Railway: DATABASE_URL apunta a `Postgres`, no al servicio apagado `litellm-postgres` |
| Redis | REDIS_URL referencia `Redis` Offline; pendiente verificar si el Gateway usa esa referencia para algún control, no reactivado |
| Exportación Grafana | Diagnóstico acotado del agente Railway: 6 errores de exportación de métricas HTTP 429 entre 15:47 y 15:59 UTC; exportación reintentada, recepción completa no certificada |
| Staged changes | Verificación posterior directa: no hay cambios staged |

El diagnóstico del agente Railway no tuvo acceso a valores; su informe es
evidencia limitada, no una auditoría completa del Gateway. Online/readiness no
certifican aliases autorizados, circuit breaker, coste, privacidad o recepción
en Grafana. No se reprodujeron ataques ni envíos de usuario en producción.

## Incremento local

Las APIs legacy de confirmación y auditoría rechazan sin I/O. No hay
`execute_*` en el catálogo de Agent gobernado, singleton o eval Agent. La vía
válida conserva `claim_confirmation` y `ProposalExecutor` con consumo único.
Los adaptadores legacy permanecen como compatibilidad de imports, rechazados.
Cambian los prompts para describir el flujo Core, no herramientas inexistentes.

El harness físico ya no puede declarar confirmación humana basándose en una
llamada del modelo: rechaza casos legacy `confirm_pending_action`/required
`execute_*` antes de resolver un modelo. La migración del catálogo de
confirmación a un harness Core queda pendiente (BL-8). Validar JSON del catálogo
no es ejecutar evals ni probar resistencia real a prompt injection.

## Validación

Se valida en la BD Docker dedicada `ancoramind_consent_security_test` sobre
localhost; no se modifica `ancoramind` ni BD remotas. Las variables de tests
anulan conexiones de app, Telegram/processor y exportador OTel; smoke STT real OFF.

- Primera suite unit: 1263 passed.
- Primera integración completa: 143 passed, 1 skipped, 1 failed (timeout STT
  de 50 ms antes de alcanzar el mock del proveedor).
- Repetición aislada de ese caso: 1 passed (2.30 s). No se cambia el timeout
  productivo ni se oculta el fallo inicial. La repetición completa pasó después.
- Ruff limpio; mypy limpio (164 módulos); catálogo estático 27 casos/6 categorías.
- Resultado final tras revisión del harness: **1263 unit passed** (67.65 s),
  **144 integration passed, 1 live smoke skipped** (131.54 s); Ruff/mypy limpios,
  catálogo 27 casos/6 categorías válido y `git diff --check` limpio. Ninguna
  inferencia real forma parte de estos resultados.
- Revisión final tras retirar los adaptadores simulados ya inaccesibles:
  **1263 unit passed con cobertura 79.20%** (gate 75%), y **38 integration
  passed** en las suites de propuestas/consentimiento/ejecución. Ruff/mypy,
  catálogo y diff limpios; todos los archivos cambiados revisados sin conflictos.

## Siguientes gates (no ejecutados)

1. Revisar todos los checks del SHA a desplegar y acordar rollout de
   `GOVERNED_CONSENT_ENABLED`: OFF ya no tiene fallback de mutaciones al LLM.
2. Verificar settings efectivos, claves/allowlist/limits y config Gateway sin
   revelar secretos, mediante acceso autorizado dentro del entorno.
3. E2E Telegram sintético de propuestas, Sí/No, botones, expiración, varias
   propuestas, `/new` y replay; completar `answerCallbackQuery`.
4. Acceso Grafana: investigar 429, comprobar series/trazas y privacidad metadata-only.
5. Pruebas de caída Gateway/Collector y crash/recovery en staging aislado;
   no detener servicios productivos para obtener evidencia.
6. Evals adversariales reales con corpus sintético/tools sin I/O y presupuesto
   explícito; reconciliación coste y rotaciones con procedimiento por secreto.

BL-23/39/40 siguen abiertos hasta el rollout y la evidencia pendiente.