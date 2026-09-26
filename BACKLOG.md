# BACKLOG — AncoraMind

> Lista viva y priorizada de trabajo pendiente. Fuente única de verdad para
> "qué queda por hacer". Los `specs/*/tasks.md` son el registro histórico de
> "qué se hizo" (no editarlos una vez completados).
>
> Convención: cuando un item pasa a "en curso", se le asigna un número de spec
> (`specs/00X-...`) y se trabaja con SDD (spec.md → tasks.md → implementación).
> Al completarse, se tacha aquí con fecha y se enlaza su spec.

Última actualización: 2026-09-26

---

## Estado actual (snapshot)

| Milestone | Estado |
|---|---|
| M1 Agent Runtime (Telegram+Agno+session) | ✅ |
| M2 Canonical Memory (notes) | ✅ |
| M3 Document Memory (storage+extraction) | ✅ (specs/003 documentada retroactivamente) |
| M4 Vehicle vertical slice | ✅ |
| M5 Calendar & Reminders | ✅ |
| BL-21 Listas TODO multi-lista | ✅ (toda mutación gobernada — specs/011) |
| BL-8 Evals agentic | 🔶 Base determinista implementada: 15 casos sintéticos + runner; pendiente evaluación contra Agent/modelo gobernado — specs/014 |
| BL-18 Sustituir ngrok por Railway | 🔶 Servicio, dominio HTTPS, webhook y healthcheck reales validados en Railway; falta activar Wait for CI y completar E2E Telegram M3–M5 — specs/008 |
| BL-23 Governed LLM Access, Telegram admission y OTel | 🔶 T2–T14 implementados; fase 6 (cambio de modelo en caliente) validada en Railway (2026-09-19); pendiente verificar matriz A–Y completa (caída Gateway/circuit, Collector/Grafana, benchmark con clave real, reconciliación de costes, rotación) — specs/013 |
| BL-25 Script E2E nativo PowerShell | ✅ Validación/configuración y flujo local/remoto implementados — specs/015 |
| BL-33 Health signals + dashboard de salud | 🔶 en curso — specs/016 (fase 2 del análisis de observabilidad 2026-09-23) |
| MVP usable | 🔶 E2E en curso (M1–M2 + M3 txt validados en Railway; M3 visión y M4–M5 pendientes — BL-1) |

Tests: 455 unit + 64 integration — Ruff limpio en
`src/ tests/ scripts/ migrations/`

---

## P0 — Hardening transversal de ejecución e inferencia

### BL-23 · Governed LLM Access, Telegram Admission and Observability 🔶 T2–T14 implementados localmente — specs/013 + ADR-004/005/006

Convertir el acceso a LLM y la entrada Telegram en capabilities gobernadas:

```text
Telegram → admission/idempotency → Agno → logical route
→ LiteLLM Proxy → OpenRouter → provider/model
```

Incluye idempotencia durable por `update_id`, semántica at-most-once del Agent,
private-chat/allowlist reales, rate/concurrency limits, execution budget,
configuración runtime versionada y cacheada, rutas lógicas, LiteLLM privado y
fail closed, coste/circuit breaker, y OpenTelemetry Collector + Grafana Cloud.
La telemetría de producto de Agno está desactivada con la observabilidad propia.
Defaults aprobados: 120 s, 6 model calls, 12 tool calls como hard safety
ceiling, 8 requests Gateway y concurrencia global 2.

**Estado (2026-09-24):** T2 aporta Alembic y el schema reproducible. T3 aporta el
ledger reusable: identidad durable `UNIQUE(bot_id, telegram_update_id)`, auditoría
de cada delivery Railway, `correlation_id` estable, claim atómico
`accepted → agent_started`, payload Telegram normalizado/cifrado con Fernet y
purga por retención. T4 instala, detrás de `TELEGRAM_ADMISSION_ENABLED=false` por
defecto, el endpoint propio estable: secret, private-chat, allowlist fail-closed,
deduplicación durable, rate/cola PostgreSQL y `2xx` solo tras commit. T5 debe
conectar el processor/Agent al claim; mientras tanto el rollout flag no se activa
en producción. **Actualización T5:** processor in-process auto-gated que reclama
`accepted`, aplica locks chat/usuario + semáforo global 2, persiste outbox cifrada
antes de delivery, refresca `typing` sin streaming y marca estados post-efecto
como `failed_ambiguous` tras restart. **Actualización T6:**
control plane runtime con schemas cerrados `extra="forbid"`, checksum SHA-256,
revisiones inmutables, CAS con conflicto `409`, bootstrap sin secrets,
snapshot in-memory last-known-good y API administrativa Bearer con actor
obligatorio. `LISTEN/NOTIFY` queda para un incremento posterior con una réplica.
**Actualización T7:** el processor gobernado captura snapshot y contexto por run,
compone un Agent por run con `run_id` explícito, retries 0 y ceiling 12; cada
model turn pasa por `LLMAccess`/`GovernedModel` y persiste metadata de uso sin
contenido personal. El provider directo sigue limitado a esta frontera hasta
LiteLLM/T11; la extracción documental se migra en T9 y AgentOS legado persiste
solo mientras T4/T5 sigan apagados. **Actualización T8:** el budget aplica
deadline de 120 s, techos de model/Gateway calls, límite de 12 tools, HMAC de
argumentos canónicos y bloqueo de repetición; `StopAgentRun` corta el loop tras
una tool rechazada. Pricing opcional versionado permite coste estimado/real sin
I/O por call; agotamiento queda auditado como `failed_ambiguous` sin replay. **Actualización T9:** la extracción documental ya
no crea `agno.agent.Agent` en el dominio: `DocumentService` usa el port
`DocumentExtractionPort`, cuyo adaptador Agno pasa por `LLMAccess`. Dentro de un
run gobernado comparte snapshot, budget, coste y trace (el usage se audita bajo
la interacción); en el path AgentOS legado usa un contexto bootstrap standalone
sin filas de usage (no existe interacción referenciable). `ai_extractions`
registra provider/model reales y los fallos dejan metadata observable sin
contenido. **Actualización T10:** Agno product telemetry queda desactivada en
Agent, AgentOS, entorno local y Docker. `src/observability/` emite JSON y OTel
metadata-only con allowlist; el exporter OTLP al Collector privado es opcional y
fail-open. El manifiesto `observability/otel-collector.yaml` aplica redacción,
memory limiter, batch y cola/retry antes de Grafana. Falta crear el servicio
Collector privado y dashboards/alertas en Railway mediante rollout explícito. **Actualización T11:** el pilot del LiteLLM Gateway está implementado y
validado localmente: `gateway/` fija la imagen por digest, expone sólo los
aliases versionados, desactiva Swagger/Redoc/OpenAPI (404 verificado) y mantiene
retries/fallbacks en 0. Con `LITELLM_PROXY_ENABLED=true`, `LLMAccess` y el
AgentOS legado componen únicamente `OpenAILike` hacia el Gateway privado con la
virtual key exclusiva (`scripts/litellm_create_virtual_key.py`); fail-closed
verificado con el Gateway real (key inválida ⇒ 401 del Gateway; upstream dummy ⇒
401 sin bypass). Falta el rollout Railway (PostgreSQL dedicado + servicio
privado), el benchmark con clave real y la revisión de superficie productiva.
**Actualización T12:** implementada la gobernanza de coste y fiabilidad:
`CostGovernanceConfig` (límite externo + umbrales 60/80/90 + budgets día/mes/ruta)
con invariante en rutas de pago; el runner evalúa el spend al inicio del run
con hard stop `failed_controlled` sin replay; el Gateway declara circuit
breaker (`allowed_fails`/`cooldown_time`, transiciones CLOSED/OPEN/HALF_OPEN
validadas localmente) y RPM/TPM por alias + por virtual key (enforcement 429
verificado); retries/fallbacks mantienen 0 por decisión documentada.
**Actualización T13:** hardening verificable localmente —
`tests/integration/test_hardening_013.py` (20 duplicados → 1 claim, burst
ordenado exactamente-once, crash tras `agent_started`/`delivery_started` →
`failed_ambiguous` sin replay/reenvío, `response_ready` recuperable, purga de
retención, orden estable) — y runbooks operativos en `docs/runbooks-013.md`.
**Actualización rollout Railway (2026-09-16):** Supabase canónico migrado a
Alembic head `0003_telegram_admission_indexes`, LiteLLM privado + Postgres +
Redis co-localizados en `europe-west4-drams3a`, sin dominio/TCP proxy; la app
opera fail-closed con virtual key exclusiva. T4 admission y T5 processor están
activos y un update E2E real quedó trazado por `correlation_id`, con outbox
cifrada, delivery Telegram completada y un uso LiteLLM persistido. El commit
`086f1fa` corrigió además la sincronización transaccional del resumen de uso
(`config_revision`, model/Gateway counts y costes) y pasó CI completo.
**Actualización paso 1 Railway (2026-09-18):** duplicados y negativas
validados con updates sintéticos: `978199899` reenviado 2 veces →
1 interacción `completed` (`8dc1bbe3-05b7-43c8-b947-9d0ac20d0142`,
model=1/gw=1, segunda delivery `duplicate=true`, cero IA extra);
grupo `978199900` → `rejected`/`non_private_chat` e intruso `978199901` →
`rejected`/`user_not_allowlisted`, ambos `200` con cero IA (A/B/V/N/O ✅).
**Actualización cambio de modelo en caliente (2026-09-18, ADR-005 enmendado):**
la enmienda documenta que la publicación del alias Gateway (decisión 9 /
`design.md` §11) nunca se había implementado —`RuntimeConfigManager.activate()`
sólo hacía el CAS en PostgreSQL— y fija una política aditiva: los aliases base
`*-r1` viven en `gateway/litellm-config.yaml` y nunca se mutan; un cambio de
modelo publica una generación nueva (`r2+`) en la BD del Gateway
(`store_model_in_db: true`) mediante `scripts/litellm_gateway_alias.py`
(`publish`/`grant`/`verify`/`retire`, con guards de alias base e idempotencia).
La vía de cambio sin redeploy queda implementada y verificada localmente
(T14 fases 1–5) y **validada en Railway el 2026-09-19 (fase 6)**: publicación
de `ancoramind-default-r2` en caliente (tras corregir `STORE_MODEL_IN_DB` de
`False` a `true`), `grant` aditivo, revisión runtime 2 activada con CAS,
mensaje real de Telegram con `effective_gateway_route='ancoramind-default-r2'`
(`config_revision=2`, `cost_source='pricing_snapshot'`) y ensayo de rollback
bidireccional a la revisión 1. Evidencia en `tasks.md` T14 fase 6.
Pendientes: caída/circuit del Gateway en Railway, Collector/Grafana +
dashboards/alertas, benchmark con clave real, reconciliación de costes y
rotación real. **BL-23 permanece abierto**
hasta verificar la matriz A–Y completa.
Ver `specs/013-llm-access-governance/`.

**Actualización rollout Collector/Grafana (2026-09-24):** el servicio
`ancoramind-otel-collector` existe en Railway como **staged-create** con source
`lealp22/ancoramind-app@main` y `dockerfilePath=observability/Dockerfile`
(Dockerfile nuevo que fija `otel/opentelemetry-collector-contrib:0.138.0` y
copia el manifiesto versionado; CI valida la config con valores dummy). Nada
desplegado: la patch está staged y **pendiente de `accept-deploy` con
confirmación explícita**. Bloqueos abiertos en este punto:
1. **Push a `origin/main` fallido (403 `Write access to repository not
   granted`)** — las credenciales HTTPS locales no tienen escritura; sin el
   push del Dockerfile en `main`, Railway no puede buildar.
2. **Secretos `GRAFANA_OTLP_ENDPOINT` / `GRAFANA_OTLP_AUTHORIZATION` sin
   crear** en el servicio Collector (stack Grafana Cloud pendiente de
   provisionar; la región del stack consta como "Pendiente" en
   `verification.md`).
3. **Región del servicio Collector en `us-west2`** mientras el resto del
   proyecto está en `europe-west4-drams3a`; el private networking funciona
   cross-region, pero debe alinearse en el dashboard antes del deploy (las
   herramientas de automatización disponibles no permiten cambiar región).
4. Tras deploy del Collector: añadir `OTEL_EXPORTER_OTLP_*` a la app
   (solo tras validar el Collector), verificar fail-open con `/health` y
   comprobar en Grafana que llegan únicamente atributos allowlisted.
Los pasos 1–4 bloquean el cierre de la matriz A–Y (entradas Collector/Grafana)
y, con ella, de BL-23; dashboards/alertas (BL-33/specs/016) consumen este
resultado.

**Criterio de cierre:** matriz A–Y de specs/013 verificada: un mismo update
ejecuta el Agent como máximo una vez, el modelo cambia sin redeploy, ningún run
supera su budget, LiteLLM falla cerrado, la interacción es trazable por
`correlation_id` y no se exporta contenido personal.

### BL-24 · Onboarding de usuarios Telegram mediante invitaciones gobernadas
`ALLOWED_TELEGRAM_USER_IDS` permite una allowlist técnica, pero no es un proceso
práctico de alta para un grupo de evaluadores aún no definido: no se debe abrir
el bot a cualquier usuario ni pedir a cada persona que averigüe su Telegram ID.

Diseñar e implementar un flujo de **pairing gobernado**: un operador crea una
invitación/código temporal, de un solo uso o con cupo explícito; la persona lo
canjea en un chat privado con el bot; el backend muestra la solicitud al operador
y exige aprobación antes de vincular el `telegram_user_id` observado en el update
autenticado a una identidad/autorización durable. El código es una credencial de
onboarding, no un sustituto de los controles existentes de secret de webhook,
private-chat, rate limiting, idempotencia ni auditoría de BL-23.

Decidir en el spec el canal de emisión/solicitud (web mínima, herramienta/admin
CLI u otro mecanismo), el modelo de roles/grupos, aprobación/rechazo, expiración,
rotación, revocación inmediata y recuperación ante canje duplicado o concurrente.
Secretos/códigos deben almacenarse con hash, TTL y estado explícito; nunca se
registran en claro. Las operaciones administrativas y toda mutación de
autorización deben ser auditables con actor, timestamps y motivo. Mantener
fail-closed: una solicitud pendiente, rechazada, expirada o revocada no llega al
Agent. Añadir pruebas de replay, carrera de doble canje y revocación de una sesión
ya autorizada.

**Prioridad P0:** desbloquea pruebas controladas con múltiples personas y debe
integrarse con la admission durable de `specs/013`, no mediante un bypass de la
allowlist actual.

---

## P1 — Cerrar el MVP (validación)

### BL-1 · E2E Telegram de M3–M5
Probar en Telegram con credenciales reales: subir documento → extracción,
registrar vehículo + mantenimiento (propose/execute), crear recordatorio y
evento de calendario (propose/execute).
**Pausa operativa (2026-09-07):** alerta de seguridad de red al usar ngrok;
no retomar el canal hasta disponer de una alternativa autorizada (BL-18).
Mientras tanto, validar los flujos mediante integration tests sin Telegram:
la capa de repositorios ya está cubierta (specs/009, 16 tests + fix jsonb);
los flujos service/tool con LLM real siguen requiriendo este E2E.
**Criterio de cierre:** los 5 flujos probados y documentados en el
`verification.md` del spec correspondiente.

**Actualización 2026-09-20:** diagnosticado el fallo de M3 en el processor
gobernado: normalizaba únicamente texto y descartaba adjuntos, por lo que una
imagen recibía `200` pero no respuesta. Corrección local implementada y cubierta:
referencias Telegram cifradas, descarga posterior al claim, tamaño/MIME acotados,
ingesta automática y renderizado PDF transitorio. La extracción visual selecciona
la ruta lógica `ancoramind-vision`; falta publicar `ancoramind-vision-r2` con
`openrouter/qwen/qwen3.6-35b-a3b`, activar una revisión runtime por CAS y repetir
el E2E real antes de marcar M3 como validado.

**Actualización 2026-09-20 (validación E2E txt ✅):** primer flujo E2E completo
validado en Telegram/Railway (BL-18 activo): documento .txt → archivado +
extracción IA persistida + respuesta con resumen en el chat. Tres capas de bug
corregidas y desplegadas: (1) prompt v1.1 sin contenido ni schema (commit
`25e8743`), (2) migración `0004_ai_extractions_schema` aplicada a prod — la tabla
pre-baseline carecía de `schema_version` (42703 en INSERT, commit `f77402d`),
(3) `model_dump()` en modo Python filtraba `datetime.date` no serializable a
JSONB — `TypeError` que mataba el run tras la inferencia pagada (commit
`86673c7`, `mode="json"`). Evidencia en prod: `telegram_interactions.status`
`completed`, fila en `ai_extractions` (prompt_version 1.1, confidence 0.96) y
usage event bajo la interacción. Pendiente en M3: ruta visión (imagen/PDF)
tras el rollout de Qwen r2; M4–M5 siguen pendientes de E2E.

### BL-18 · Sustituir ngrok por Railway 🔶 en curso — specs/008
La alerta de tráfico tipo C2 hace no recomendable seguir usando ngrok en esta
red sin autorización. **Decisión (2026-09-08): Railway** como despliegue
gestionado conectado a GitHub; Supabase permanece como PostgreSQL y Storage.
Hecho: runtime compatible con `PORT`, Dockerfile, healthcheck, `railway.json`,
CI GitHub Actions, helper de webhook seguro y documentación. **Evidencia Railway
(2026-09-19):** servicio `ancoramind-app` en `production`, rama `main`, deployment
`SUCCESS` del commit `9d7999b`, dominio HTTPS estable
`https://ancoramind-app-production.up.railway.app`, `/health` → `200`, 34 variables
de producción y webhook Telegram registrado sin updates pendientes. LiteLLM sigue
privado sin dominio/TCP proxy.

**Pendiente:** el servicio tiene `checkSuites: false`, por lo que falta activar
**Wait for CI** (y decidir protección de `main`); también falta repetir y documentar
el E2E Telegram de M3–M5. Por esos criterios BL-18 **no está cerrado todavía**.
**Nota (2026-09-09):** al desplegar se activará también el worker de
recordatorios (BL-5 / ADR-003 / specs/010): variables `REMINDER_WORKER_*`
opcionales (defaults válidos); su entrega es **outbound** y funciona desde el
primer deployment saludable, sin esperar al registro del webhook. Ver
`docs/deployment-railway.md` §8.
**Criterio de cierre:** dominio HTTPS Railway estable, CI/CD operativo y E2E
Telegram ejecutado sin alertas ni túneles desde el equipo local.

### ~~BL-25 · Script E2E nativo para PowerShell~~ ✅ implementado — specs/015 (2026-09-19)
`scripts/run-e2e.ps1` ofrece `-Check`, `-Reset`, carga literal y segura de `.env`,
validación de provider/Storage/DB/Gateway, PostgreSQL local + bootstrap, ngrok y
webhook para flujo local. `-PublicBaseUrl` registra el webhook contra un dominio
HTTPS desplegado (Railway) sin iniciar ngrok, Docker ni la app local. Tests cubren
configuración válida, provider inválido, `.env` no ejecutable y URL pública con
path rechazada. Ver `specs/015-powershell-e2e/verification.md`.

### BL-22 · Migrar reminder worker a FastAPI lifespan ✅ implementado — specs/012
`src/main.py::_register_reminder_worker` usa `app.add_event_handler(...)`,
que la versión instalada de FastAPI ya no expone (`AttributeError` al
importar `src.main` con worker habilitado — detectado 2026-09-10 durante
BL-21). Migrar a `lifespan` (`@asynccontextmanager`, pasado a
`FastAPI(lifespan=...)` o al `AgentOS.get_app()` si lo soporta): arrancar
`asyncio.create_task(worker.run_forever(...))` al entrar y cancelarlo
limpiamente al salir. Mantener los auto-gates actuales
(`REMINDER_WORKER_ENABLED` + `ANCORA_DATABASE_URL` + `TELEGRAM_TOKEN` con
sus logs de motivo). **Criterio de cierre:** `python -c "from src.main
import app"` sin `AttributeError` (con worker habilitado y deshabilitado);
suites unit + integration verdes; Ruff limpio. Toca `main.py` + tests del
wiring (nuevo o existentes de specs/010). **Prioridad P1** — sin esto la app
no arranca con el worker activo (regresión vs specs/010).
**Hecho (2026-09-10):** `src/agent/lifecycle.py` envuelve el lifecycle previo
de AgentOS/Starlette, preserva los tres auto-gates, crea la task por instancia
en `app.state` y la cancela limpiamente; `main.py` ya no usa
`add_event_handler` ni estado global. 3 tests de lifecycle; 171 unit passing,
Ruff y mypy del alcance limpios; integración ejecutada sin fallos pero omitida
sin PostgreSQL/Docker. Ver `specs/012-fastapi-lifespan/`.

### BL-33 · Health signals + Dashboard de salud 🔶 en curso — specs/016

Materializa la **fase 2** del análisis de observabilidad (2026-09-23): el
`/health` actual (AgentOS) sólo prueba que el proceso escucha. Se añade
`GET /health/readiness` (DB, reminder worker, interaction processor,
Gateway/circuit breaker, cola de admission, revisión de runtime config, edad
de la última interacción) y health metrics metadata-only por el pipeline OTel
existente, más el dashboard Grafana **versionado en
`observability/dashboards/`** con vista de salud a simple vista y alertas
(circuit open, spend, errores de delivery, heartbeat, silencio de tráfico).
Grafana Cloud permanece como backend (ADR-006). Fuera de este incremento: stack
OSS local (fase 3, diferida) y Langfuse (registrado como candidato BL-8).
El dashboard complementa —no sustituye— el rollout pendiente del
Collector/Grafana de BL-23.

---

## P2 — Funcionalidad para "usable de verdad"

### BL-6 · OCR/vision real para extracción de documentos 🔶 en curso
La extracción visual está implementada localmente: imagen directa o PDF renderizado
con PyMuPDF (máximo 3 páginas) → ruta lógica `ancoramind-vision` → salida
estructurada. Los contenidos siguen siendo DATA, no INSTRUCTIONS. Pendiente:
publicar/autorizar `ancoramind-vision-r2` con Qwen en Railway, activar la revisión
runtime, benchmark de precisión/coste/latencia y E2E Telegram con PDF e imagen.
**Nota triage TODO (2026-09-20):** los PDFs escaneados ya fluyen por la ruta
visual (PyMuPDF rasteriza páginas con o sin capa de texto — el "fallback OCR"
propuesto ya está cubierto por diseño). Refinamientos a evaluar en el benchmark:
detectar capa de texto para preferir extracción textual (más barata) en PDFs
digitales y reservar visión para escaneados; política explícita para PDFs de
más de 3 páginas; OCR dedicado solo si la ruta visual no alcanza precisión.

### BL-7 · Proveedor de calendario real
Implementar un `CalendarProvider` real (Google Calendar, CalDAV o similar)
tras el Protocol existente. NoopCalendarProvider queda como default para dev.

### BL-26 · Notas de voz entrantes y transcripción gobernada (STT)
Permitir que una nota de voz de Telegram se procese como un mensaje conversacional:
descargar el audio autorizado por Telegram, transcribirlo y pasar **solo el texto
resultante** al mismo flujo de admission/processor/Agent que usa un mensaje escrito.
El audio y su transcripción son datos personales no confiables. La transcripción
es el mensaje conversacional del usuario y puede expresar solicitudes funcionales;
se trata como input no confiable y nunca puede elevar permisos, modificar políticas
ni sustituir la identidad y confirmación resueltas por el Core. No se exporta a
logs/OTel y se somete a retención/cifrado equivalentes o más estrictos que el
payload Telegram de specs/013.

**Diseño requerido:** no crear clientes físicos de STT desde domain/services/tools.
Definir un `SpeechToTextPort` y una capability gobernada con ruta lógica versionada,
`RuntimeConfigSnapshot`, `ExecutionContext`, presupuesto por duración/tamaño, uso y
coste auditables, correlación y fail-closed. La descarga de `file_id` y conversión
del audio vive en la capa Telegram/agent; el dominio recibe un puerto y texto
transcrito etiquetado como DATA. Preservar `same bot_id + update_id => at most one
Agent execution`, incluidos fallos tras descargar/transcribir; no reintentar ni
reproducir automáticamente una transcripción ambigua. Definir límites explícitos
de duración, tamaño, MIME/codec y política para audio sin habla o ilegible.
El pipeline debe ser desacoplado y comprobable por etapas
(`accepted → downloaded → transcoding/transcribing → transcribed → agent_started`),
con estados durables suficientes para distinguir fallo seguro de resultado
ambiguo. Sus señales de progreso serán eventos internos tipados y metadata-only,
proyectados a la outbox por BL-32; ningún hook recibe o exporta audio/transcripción
salvo el componente autorizado que la necesita.

**Modelo inicial recomendado para benchmark:** `openai/whisper-large-v3-turbo`.
En OpenRouter figura con formatos habituales de Telegram (incluido `ogg`) y coste
de $0.000003/s (~$0.00018/min), muy inferior a `mistralai/voxtral-mini-transcribe`
($0.003/min), `microsoft/mai-transcribe-2` ($0.10/h ≈ $0.00167/min) y
`fish-audio/transcribe-1` ($0.0001/s = $0.006/min). Antes de fijarlo, comparar
exactitud y latencia con un corpus sintético/consentido de notas cortas en español,
ruido, nombres/matrículas y code-switching. MAI-Transcribe 2 es el candidato de
calidad/funcionalidad si hicieran falta diarización, timestamps por palabra o
keyword biasing; Voxtral Mini es alternativa intermedia. No usar modelos de chat
para STT ni bypass del Gateway/política de inferencia.

**Criterio de cierre:** E2E de nota de voz privada allowlisted → una sola
transcripción auditada → un solo Agent run → respuesta textual; rechazos de tipo,
tamaño/duración, usuario/grupo no autorizado y error STT no consumen Agent ni
dejan contenido en telemetría. Añadir unit, integration, evals y evidencia de
coste/latencia real antes de activar en producción.

**Prioridad propuesta: P2.** Puede subir a P1 tras cerrar BL-23, pues mejora de
forma directa el uso cotidiano del asistente.

### BL-27 · Respuestas de voz opcionales en Telegram (TTS) — análisis previo
**La respuesta textual ya está implementada:** el processor de specs/013 persiste
una `logical_response` cifrada y la entrega por `TelegramNotifier.send_text()` →
Bot API `sendMessage`. Por tanto, recibir voz y responder con texto no requiere
otra capability de salida.

Evaluar por separado la respuesta **hablada**: síntesis TTS del texto final,
entrega como `sendVoice`/`sendAudio`, preferencia explícita por usuario y fallback
a texto. Requiere decidir proveedor/modelo, idiomas/voces, coste/latencia, formato
Telegram, moderación de contenido, retención de audio, límites de longitud,
idempotencia de delivery y cómo persistir/auditar `response_kind='voice'` sin
guardar contenido en telemetría. Debe pasar por una capability gobernada y no
introducir un provider directo ni reenvíos ambiguos. Crear mini-ADR/spec antes de
implementar; no asumir que TTS es necesario para entregar el valor de BL-26.

### BL-21 · Listas TODO (múltiples listas por usuario) ✅ implementado — 2026-09-10
Permitir al usuario crear y gestionar **listas de tareas (TODO)** con nombre
personalizado (ej. "Trabajo", "Personal", "Compras", "Proyecto X").
Cada lista contiene items con: título, descripción opcional, estado
(pending/done), prioridad opcional, fecha límite opcional y orden manual.
Operaciones: crear/renombrar/eliminar lista; añadir/editar/mover/eliminar
item; marcar done/pending; reordenar (drag-and-drop lógica); listar items
con filtros (estado, prioridad, fecha). Diferencia clave con `reminders`:
no hay trigger temporal automático ni worker — es gestión activa iniciada
por el usuario. Requiere: modelos (`todo_lists`, `todo_items`), repositorio,
servicio, tools (`propose_`/`execute_` para WRITE), prompts/skill, tests
unit + integration, migración idempotente en `migrations/init.sql`.
**Prioridad:** P2 — hace el asistente "usable de verdad" para gestión diaria.
**Implementación (2026-09-10):** dominio `src/domain/todos/` (models+service),
`src/repositories/todos.py` (SQL parametrizado, user-scoped), 12 tools en
`src/agent/tools/todos.py` (listas con propose/execute + items directos),
registro en `_init_domain_tools()`, skill `prompts/skills/todos.md`,
`tablas ancora.todo_lists/todo_items` en `migrations/init.sql`,
29 unit tests + 7 integration tests nuevos (168 unit passing, Ruff limpio,
mypy limpio en archivos nuevos). El wiring FastAPI del worker se corrigió
posteriormente en BL-22/specs/012. E2E Telegram pendiente (bloqueado por BL-18).

---

### ~~BL-28 · Comandos de Telegram: manejo nativo de `/new` y namespace `/` reservado~~ ✅ implementado
`5625bbb` + `ed864fb` (2026-09-20). `domain/interactions/commands.py` resuelve
`/new` (nueva generación de conversación) y `/help`/`/start`; cualquier otro
comando válido recibe un reply constante ("no disponible") y **nunca llega al
LLM**, ni arrastra historial al proveedor. La respuesta viaja por el mismo
outbox durable que una respuesta del Agent (chunks, delivery state, ambigüedad)
mediante `claim_command_reply` (gated en `accepted` ⇒ un replay no responde dos
veces; nada externo ocurre antes del commit). La generación se guarda en la
fila del propio `/new` (`agno_session_id`) y los runs siguientes la resuelven
con `current_session_id(chat_id)`; texto que empieza por `/` pero no es comando
Telegram válido (`/home/user/x`) sigue siendo conversación. Telemetría nueva
bounded (`ancora.command` ∈ {new, help, start, unsupported}) añadida a la
allowlist con test de privacidad. Cobertura: 6 unit (parse/replies/generaciones)
+ 5 unit de processor + 4 de integración PostgreSQL (`/new` sin run, sesión
heredada por el mensaje siguiente, claim único, `current_session_id`).

**Decisión:** sin `propose/execute` — los comandos no escriben datos canónicos
ni llaman a proveedores; `/new` sólo abre una generación conversacional.

**Paso de operador (BLOQUEADO — requiere tu aprobación):** publicar el menú de
autocompletado en Telegram con
`python scripts/telegram_webhook.py commands` (usa `setMyCommands` con el mismo
mapa del dominio; sin esto `/new` funciona igual pero no aparece al escribir
`/`). No lo he ejecutado: cambia estado del bot de producción.

### ~~BL-29 · Renderizado real de Markdown en las respuestas de Telegram~~ ✅ implementado
`5625bbb` + `ed864fb` (2026-09-20). Se eligió **HTML** (no MarkdownV2) por ser
mucho más tolerante: `notifications/markup.py` escapa `&`, `<`, `>` de todo el
texto literal y emite etiquetas sólo desde una whitelist propia (`b`, `i`, `s`,
`code`, `pre`, `a` con URL `http(s)` sin comillas, headings y bullets `•`). Un
span sin cierre queda como texto literal (nunca tag roto) y un bloque de código
sin cerrar no deja `<pre>` colgando, así que un corte de chunk puede perder
formato pero jamás significado. Si el render excede 4096 chars, la entrega manda
el chunk en texto plano; y si Telegram rechaza el markup (`TelegramSendError`
ahora lleva `description`), el notifier reintenta una vez en texto plano en
lugar de perder el mensaje. El contenido persistido sigue siendo el Markdown
original del modelo (presentación ≠ auditoría). `format_reminder_message` sigue
en texto plano a propósito (ADR-003/§2.8). Cobertura: 19 unit de render + 4 unit
de notifier.

**Límite conocido:** el path AgentOS legado (admission deshabilitada) entrega con
el cliente Telegram interno de Agno y no pasa por este notifier.

### BL-30 · Tool de búsqueda web gobernada (respuestas "¿qué es X?")
Añadir una capability de consulta a Internet para términos desconocidos
("que me digas qué es X"), sin investigación profunda ni browsing largo.
Debe seguir la disciplina de capabilities: nueva tool en `src/agent/tools/`
con servicio de dominio detrás, `EXTERNAL_ACTION` por riesgo (salida del
perímetro hacia terceros → gobernanza; decidir en spec si requiere
propose/execute o se trata como READ sujeto a rate/budget), ruta de red en la
capa de infraestructura, datos devueltos = DATA no confiable, sin contenido
personal en logs/OTel, coste/uso auditables y presupuesto del run aplicado
(hooks de budget ya existentes la cortan igual que cualquier tool).

**Opciones a evaluar en el spec:** API de búsqueda (Brave/Serper/Tavily…) con
clave por secretos + síntesis por el propio modelo, o un modelo con búsqueda
nativa vía OpenRouter si existe y permite el Gateway. El resultado debe incluir
fuentes/URLs y fecha de consulta suficientes para distinguir conocimiento del
modelo de información recuperada; no presentar snippets como hechos verificados.
Aplicar allow/deny de destinos, protección SSRF si se recuperan páginas, timeout,
máximo de resultados/páginas/bytes, cache con TTL, rate limit y budget por run.
No enviar memoria personal ni contexto conversacional completo al buscador: sólo
la consulta mínima necesaria, advertir/confirmar antes de incluir datos sensibles
y registrar metadata de proveedor/coste sin query ni contenido. **Prioridad P2**
(valor alto de UX, no bloquea MVP). Al añadir capability: seguir
`docs/adding-tools.md` + skill prompt + tests/evals de prompt injection web.

### BL-31 · Deduplicación de documentos por hash de contenido
Comprobado que no existe: `storage_key` es UUID aleatorio (local y Supabase) y
`ancora.documents` no guarda hash — el mismo fichero enviado dos veces se
almacena, procesa y cobra dos veces. Propuesta: columnas `content_sha256
CHAR(64)` + índice `(user_id, content_sha256)` en `documents` (migración
Alembic aditiva + `init.sql`); calcular SHA-256 en `DocumentService.ingest`
antes de almacenar; si existe fila vigente del mismo usuario, reutilizar el
registro existente (no re-almacenar bytes) y decidir política de extracción:
re-usar la extracción previa y devolver su resumen (recomendado — evita coste
duplicado) con opción de re-extraer explícita. Mantener el original_filename
de la última subida si se desea, sin borrar documentos previos (provenance).
El hash es derivado del contenido, no dato sensible; auditar en
`ai_extractions` el `document_id` real usado. **Prioridad P2** (ahorro directo
de coste y ruido canónico; encaja antes del E2E de visión/PDF).

### BL-32 · Acuse de recibo temprano para procesos pesados (fast-ack UX)
Cuando la respuesta previsible tarde (documento/imagen/PDF), enviar en el
mismo run un mensaje inmediato tipo "📄 Documento recibido, analizando…" antes
de la inferencia, sin romper las garantías de specs/013. Restricciones: no
reenvíos ambiguos (el acuse es un mensaje más de la outbox con su delivery
state; si falla se marca y no se reintenta a ciegas), no duplicar acuses si el
update se reprocesa (idempotente por `interaction_id`), y el mensaje final
sigue siendo único. Alternativas a evaluar: (a) acuse como chunk previo de la
misma `logical_response`; (b) mensaje efímero borrado al responder (ensucia y
necesita `deleteMessage`); (c) solo `typing` continuo (ya existe como BL-17,
no basta para 15–30 s de visión). Propongo (a) con heuristic gate: media/flags
por tipo de interacción (media ⇒ acuse; texto ⇒ no).

Generalizar el mecanismo como **eventos internos tipados de progreso**
metadata-only (`operation_started`, `stage_changed`, `operation_succeeded`,
`operation_failed`), vinculados a `interaction_id`/`correlation_id`. Productores
como documentos, STT, búsqueda web o consolidación de memoria publican estados
semánticos, no texto de canal; un proyector Telegram decide qué eventos merecen
mensaje y los persiste primero en la outbox. Los hooks son puntos de extensión
internos, explícitos y acotados del lifecycle —no plugins dinámicos—, con timeout,
aislamiento de errores y allowlist de payload. No pueden alterar identidad,
autorización, argumentos/resultados de tools ni convertir un fallo de delivery en
repetición del Agent. **Prioridad P3** (pulir después del E2E de visión, donde la
latencia real será medible).

### BL-35 · Ingesta gobernada de documentos ofimáticos (DOCX/XLSX/PPTX)
Ampliar Document Memory para recibir formatos ofimáticos habituales sin ejecutar
macros, relaciones externas, objetos embebidos ni contenido activo. Implementar
extractores deterministas detrás de un puerto de infraestructura: texto y tablas
de DOCX, hojas/celdas relevantes de XLSX y texto/notas de PPTX; después reutilizar
el pipeline de almacenamiento, extracción gobernada, provenance y propuestas
existente. El contenido extraído sigue siendo DATA, nunca instrucciones.

**Dependencia obligatoria:** BL-31 debe estar cerrado antes de activar esta
capability para evitar almacenamiento y coste duplicados. Aplicar allowlist real
por firma/MIME además de extensión, límites de bytes, entradas ZIP, ratio de
compresión, profundidad, nº de hojas/diapositivas/filas/celdas, texto total y
tiempo; rechazar cifrado/contraseña, macros y formatos legacy binarios inicialmente.
No renderizar fórmulas ni seguir hyperlinks/conexiones externas. Conservar original
y provenance, y declarar extracción parcial/truncada al usuario. **Prioridad P2.**
**Criterio de cierre:** fixtures benignas y maliciosas (ZIP bomb, path traversal,
macro, archivo renombrado y workbook desmesurado), deduplicación, aislamiento por
usuario y E2E Telegram por cada formato soportado.

### BL-13 · Memoria personal y consolidación gobernada «Dream»
Convertir la "Soft Personal memory" de `docs/architecture.md` §7 en una capacidad
propia de AncoraMind para aprender preferencias estables, hábitos útiles y estilo
de interacción (idioma, longitud/tono, formatos, nombres/apodos frecuentes), sin
confundirlos con datos canónicos ni con el resumen de contexto de BL-34.

Un proceso incremental «Dream» revisa únicamente interacciones ya finalizadas
desde un cursor durable, en lotes acotados, y produce **candidatos estructurados**
con categoría, valor, confianza, evidencia/provenance, vigencia y posible conflicto.
La inferencia pasa por `LLMAccess`, ruta lógica versionada, snapshot, budget, ledger
de uso y telemetría metadata-only. El prompt vive en `prompts/`; historial,
documentos y resultados de tools son DATA no confiable. Dream no puede editar
prompts, `SOUL`, skills, archivos, permisos ni memoria canónica, ni crear nuevas
capabilities. Un hook tipado post-interacción puede marcar trabajo pendiente, pero
la consolidación se ejecuta fuera del request y nunca retrasa ni reejecuta la
respuesta Telegram.

**Política de promoción:** preferencias explícitas del usuario pueden activarse
con alta confianza y auditoría; inferencias implícitas requieren repetición/evidencia
suficiente o confirmación humana según sensibilidad. Correcciones explícitas
reemplazan la versión anterior sin borrar provenance. Hechos sensibles, secretos,
credenciales, instrucciones operativas, datos de terceros y estados pasajeros no
se aprenden automáticamente. La memoria canónica siempre prevalece ante conflicto.
El usuario debe poder consultar «qué sabes/prefieres sobre mí», corregir, olvidar,
desactivar el aprendizaje y solicitar purga; estas mutaciones siguen gobernanza y
quedan auditadas.

Decidir en spec/ADR el almacenamiento: se recomienda modelo de dominio/repository
propio en schema `ancora` para no atar el producto a Agno, con cifrado/retención y
aislamiento por usuario, enmendando `docs/architecture.md` §7 si se aprueba. Evitar
un blob opaco único: usar registros versionados y estados
`candidate/active/rejected/superseded/deleted`. **Prioridad P2**, después del cierre
operativo de BL-23; puede desarrollarse en paralelo a BL-34 una vez fijados sus
contratos. **Criterio de cierre:** evals de preferencia explícita, repetición,
contradicción/corrección, prompt injection, dato sensible, borrado y precedencia de
memoria canónica; E2E que demuestre personalización posterior sin filtrar contenido.

### BL-36 · API de aplicación multicanal para clientes web/backend
Exponer las capacidades conversacionales y operativas de AncoraMind mediante una
API HTTP versionada, para que una página web, aplicación móvil o pequeño backend
(BFF) pueda ofrecer los mismos casos de uso disponibles desde Telegram sin
duplicar lógica de negocio. No es un endpoint directo al modelo, a las tools o a
los repositorios, ni una API compatible con OpenAI: es la API del producto y debe
atravesar la misma admisión, identidad confiable, `GovernedInteractionRunner`,
`LLMAccess`, budgets, propuestas/confirmaciones, auditoría y aislamiento por
usuario que cualquier otro canal.

**Contrato inicial recomendado:**

- `POST /api/v1/interactions` acepta texto, `session_id` opcional y referencias a
  adjuntos ya subidos; requiere `Idempotency-Key` y devuelve `202` con
  `interaction_id`, `correlation_id` y estado, sin mantener una petición HTTP
  abierta durante toda la inferencia.
- `GET /api/v1/interactions/{id}` devuelve estado, progreso metadata-safe y la
  respuesta final sólo al propietario; polling es suficiente para v1. WebSocket o
  SSE queda como optimización posterior basada en eventos/outbox de BL-32, nunca
  como streaming directo de tokens sin persistencia.
- Endpoints autenticados para subir/consultar documentos y para consultar,
  confirmar o rechazar `ActionProposal` reutilizan servicios existentes; no crean
  rutas mutantes paralelas que eviten `propose_* → execute_*`.
- Las sesiones son identificadores opacos scoped por usuario/canal. Una cuenta web
  puede vincularse a la misma identidad AncoraMind que Telegram sólo mediante un
  proceso explícito y auditable; nunca por nombre, email o heurística del LLM.

Crear una admisión **agnóstica de canal** y un modelo de interacción común en el
Core (`channel`, `external_interaction_id`, principal/user, payload cifrado,
idempotency key, estado y deliveries), conservando un adaptador Telegram y un
adaptador HTTP. La migración debe preservar la semántica actual
`same source + external interaction/idempotency key => at most one Agent execution`
y los estados `accepted → agent_started → terminal`; después de `agent_started`
no hay replay automático. El runner debe recibir metadata neutral de canal en vez
de exigir IDs Telegram, sin perder trazabilidad de los flujos existentes.

**Seguridad/API:** autenticación real (OIDC/session para BFF o tokens API
revocables y hasheados para integraciones), scopes/roles, rate/concurrency limits,
límites de body/adjuntos, CORS deny-by-default, CSRF cuando haya cookies, rotación
de credenciales y errores sin contenido personal. El `user_id` se deriva siempre
del principal autenticado. Definir OpenAPI, schemas cerrados, versionado y
compatibilidad; no exponer prompts, rutas físicas/modelos, secrets, argumentos
internos de tools ni trazas. Aplicar la misma retención/cifrado y política
metadata-only de specs/013.

**Despliegue recomendado:** el navegador habla con un BFF pequeño, y el BFF con
AncoraMind mediante la API; así las credenciales de servicio no llegan al cliente.
Para un frontend first-party puede usarse cookie segura/OIDC contra el mismo host,
pero la UI no forma parte de esta historia. **Prioridad P2**, después del cierre
operativo de BL-23 y coordinada con BL-24 para identidades. **Criterio de cierre:**
un cliente de referencia sin Telegram completa conversación, documento,
consulta READ y propuesta/confirmación WRITE; duplicados ejecutan el Agent como
máximo una vez; otro usuario no puede leer estado, respuesta, adjuntos ni
propuestas; tests contract/unit/integration y E2E sobre Railway.

## P3 — Calidad del agente

### BL-34 · Política de contexto por tokens y compactación gobernada
La mitigación actual (`num_history_runs=10`, `add_history_to_context=True`) acota
turnos, pero no el tamaño real: diez respuestas largas pueden agotar modelos
pequeños y desperdiciar ventana en modelos grandes. Sustituir el número fijo como
protección principal por una política calculada desde la ventana efectiva de la
ruta/modelo y el budget del run, reservando espacio explícito para instrucciones,
mensaje actual, schemas/tools, respuesta y margen de seguridad.

Cuando el historial no quepa, conservar mensajes recientes y generar un checkpoint
compactado de lo anterior mediante una ruta lógica gobernada. El checkpoint debe
ser reemplazable, versionado, acotado y enlazado al rango de mensajes que resume;
no es memoria personal ni canónica y no puede introducir permisos, hechos no
presentes o instrucciones provenientes de contenido no confiable. Si la
compactación falla o excede budget, degradar de forma determinista a truncado
seguro sin reintentos genéricos. Separar esta **memoria de trabajo** de BL-13:
BL-34 mantiene continuidad de la conversación; BL-13 aprende preferencias
duraderas con provenance y reglas distintas.

Configurar umbrales por revisión de runtime, medir tokens estimados/reales y emitir
eventos tipados metadata-only compatibles con BL-32. Definir además retención y
purga de sesiones en `agno_runtime`. **Criterio de cierre:** tests con historiales
largos, mensajes/tool calls grandes, cambio de modelo/ruta, compactación fallida y
ausencia de contenido personal en logs/OTel.

### BL-8 · Evals agentic 🔶 en curso — specs/014
Base determinista implementada: contrato JSON v1, runner local sin llamadas a
LLM/tools/servicios y 15 casos sintéticos iniciales para `confirmation`,
`documents`, `security`, `tool_selection` y `vehicle`. El runner valida schema,
cobertura, expectativas contradictorias y ausencia de secretos obvios; ejecutar
`python scripts/run_evals.py` tras cambios de prompts/models/tools.

**Pendiente:** adaptar el catálogo para ejecutar un Agent gobernado y evaluar
metadata permitida (tool/decisión/resultado), acordar scoring semántico y baseline
por ruta lógica, y añadir la modalidad LLM al flujo CI/E2E con budget explícito.
No almacenar contenido personal en datasets, outputs ni telemetría.

**Candidatos para la fase LLM (registrados 2026-09-23, análisis de
observabilidad; aún sin decisión):**

- **Agno evals nativo** (`agno.eval`: accuracy, agent-as-judge, reliability
  de tool calls/arguments, scorer, performance; suites con exit code para CI).
  Requisito de gobernanza: el evaluator model debe pasar por
  `LLMAccess`/Gateway, nunca por un provider directo. Encaja naturalmente con
  las categorías actuales (`tool_selection` ≈ reliability, `security`).
- **Langfuse self-hosted local** (6 contenedores: web + worker + Postgres +
  Redis + ClickHouse + MinIO; ~4–8 GB RAM): datasets, anotación manual y evals
  sobre trazas. En modo metadata-only aporta poco sobre Grafana; con contenido
  exigiría enmendar ADR-006 (decisión explícita del propietario). En Railway
  inviable por coste. **Registrado como candidato a evals en local.**
- **promptfoo** (CLI, YAML, asserts deterministas + LLM-as-judge,
  red-teaming orientado a la categoría `security`): sin vendor lock, apto
  para CI.
- **DeepEval** (pytest-native): encaja con la suite existente; opción si se
  quiere scoring semántico dentro de pytest.

Descartados de partida: LangSmith/Braintrust/OpenAI Evals (envían contenido a
terceros — incompatible con la policy de specs/013) y Ragas (RAG/vector search
fuera de alcance).

### BL-15 · Botones de confirmación en Telegram (HITL UX)
La interfaz Telegram de AgentOS ignora los `callback_query`: no soporta
inline keyboards nativamente (Discord sí — ver hallazgo en
`specs/006-vehicle-creation/verification.md`). Opciones: (a) extender el
webhook de AgentOS para procesar callback_query y enviar reply_markup vía
pyTelegramBotAPI (toca internals de Agno — seguir proceso ADR-001:
documentar → demostrar límite → proponer → decidir), (b) mantener
confirmación textual (estado actual, suficiente para POC), (c) reconsiderar
canal. Hallazgo proveniente del E2E de specs/006.
**Previsto para:** post-MVP, junto a la decisión de BL-14 (Supabase) si hay
migración de runtime.

### BL-16 · Retirar workaround SafeOpenRouter cuando Agno valide tool calls
El E2E de specs/006 descubrió que `minimax/minimax-m3:free` vía OpenRouter
(backend GMICloud) emitió un tool call vacío junto al válido. Agno 2.9.0 le
añadió UUID, lo persistió y OpenRouter rechazó el siguiente turno. Workaround
actual: `SafeOpenRouter` filtra calls incompletos en las rutas streaming y
no-streaming antes de ejecutar/persistir. Es acoplamiento a métodos privados
de Agno.
**Criterio de cierre:** al actualizar Agno o cambiar de modelo/proveedor,
reproducir el caso; si Agno ya filtra llamadas incompletas, eliminar subclase
y sus tests. Mientras exista, test unitario obligatorio sobre la forma exacta.

### BL-17 · Mantener indicador «escribiendo…» durante procesos largos
Agno 2.9 Telegram envía `send_chat_action("typing")` una sola vez antes de
procesar. Telegram lo expira a los pocos segundos; búsquedas/tools lentas
parecen bloqueadas. Implementar un refresco periódico mientras dure el run,
cancelándolo siempre en `finally`. Preferible a enviar/borrar un mensaje
«Procesando…», que ensucia el chat y requiere más llamadas API.
**Restricción:** Agno no expone configuración/hook para refrescarlo; aislar la
extensión en la capa `agent/` y seguir ADR-001 (no tocar domain). Añadir tests
de cancelación en éxito y error. Post-MVP salvo que la latencia empeore.

### BL-12 · Introducir Alembic como sistema de migraciones ✅ implementado — 2026-09-13
Alembic es la historia canónica del schema `ancora`: revisión
`0001_ancora_baseline` idempotente para adoptar bases preexistentes y
`0002_llm_governance` para los cambios aditivos de specs/013.
`migrations/init.sql` se mantiene equivalente a `head` para bootstrap fresh.
Verificado contra PostgreSQL Docker: instalación vacía, adopción de schema sin
versionar conservando datos, ejecución doble de `init.sql`, upgrade a head y
downgrade `-1` que retira solo specs/013. Tres integration tests nuevos; Alembic
y las revisiones se incluyen en la imagen Docker y Ruff/CI cubren `migrations/`.

### BL-14 · Migrar infraestructura a Supabase 🔶 en curso — specs/007 + ADR-002
**Decisión del propietario (2026-09-05):** trabajar con Supabase desde ya en
vez de PostgreSQL en contenedor. **Hecho (2026-09-06):** migración baseline
`ancora_baseline` aplicada (8 tablas), bucket privado `ancora-documents`
creado, `SupabaseDocumentStorage` + factory (`DOCUMENT_STORAGE_BACKEND`),
ADR-002, Storage real verificado y 26 tests nuevos (123 total). Seguridad:
`rls_auto_enable()` ya no es ejecutable por roles API y Security Advisor está
limpio. Session pooler sync/async e integración directa de repositorios ya
verificados. E2E nota y alta de vehículo PASS; fixes de foto, búsqueda de
matrícula formateada y OpenRouter streaming listos. **Pendiente/pausado:**
re-test Telegram de documento y búsqueda para cerrar T7, bloqueado hasta
resolver BL-18 (alternativa autorizada a ngrok). pgvector: disponible (0.8.2),
NO instalado — diseño solo hasta BL-6.

---

## Hecho (registro)

| Item | Spec | Fecha |
|---|---|---|
| M1 Agent Runtime | specs/001 | — |
| M2 Canonical Memory (notes) | specs/002 | — |
| M3 Document Memory | (sin spec — BL-9) | — |
| M4 Vehicle vertical slice | specs/004 | — |
| M5 Calendar & Reminders | specs/005 | — |
| Docs multi-shell (PowerShell/Git Bash) | — | 2026-09-05 |
| BL-9 · Spec-003 retroactiva (+ fix aislamiento test_config) | specs/003 | 2026-09-05 |
| BL-11 · docs/development.md actualizado (env vars, migraciones, multi-shell) | — | 2026-09-05 |
| BL-3 · Higiene de repo (commits pendientes, push, .env no commiteado) | — | 2026-09-05 |
| BL-4 · Tool para crear vehículos (propose/execute + normalización + E2E) | specs/006 | 2026-09-06 |
| BL-10 · Unificar factory de modelo en tools de documentos (`create_model_from_settings`, respetando `LLM_PROVIDER`/`LLM_MODEL`) | — | 2026-09-09 |
| BL-19 · Baseline Ruff limpio en `src/ tests/ scripts/` (155 avisos → 0; gate global en CI) | — | 2026-09-09 |
| BL-2 · Integration tests con PostgreSQL real (16 tests, BD dedicada `ancoramind_test`, fix jsonb asyncpg en documents.py, job CI integration) | specs/009 | 2026-09-09 |
| BL-5 · Background worker de recordatorios (asyncio in-process + TelegramNotifier outbound; worker arranca con la app — ADR-003, documentado para BL-18/Railway) | specs/010 | 2026-09-09 |
| BL-21 · Listas TODO (múltiples listas por usuario: dominio + repo + 12 tools + skill + tablas; spec redactada retroactivamente — ver specs/011/verification.md) | specs/011 | 2026-09-10 |
| BL-22 · Migrar reminder worker a FastAPI lifespan (preserva lifecycle AgentOS; auto-gates + cancelación limpia) | specs/012 | 2026-09-10 |
| BL-12 · Alembic canónico + baseline/adopción + migración specs/013 + lifecycle tests | specs/013 T2 | 2026-09-13 |
| BL-23 · Interaction ledger durable (cipher/Fernet, deliveries, claim y retención) | specs/013 T3 | 2026-09-13 |
| BL-23 · Telegram admission feature-flagged (secret, private chat, allowlist, rate/queue durable) | specs/013 T4 | 2026-09-13 |
| BL-23 · Processor/outbox Telegram (claim, recovery, chunks, delivery states y typing) | specs/013 T5 | 2026-09-13 |
| BL-25 · Script E2E nativo para PowerShell | specs/015 | 2026-09-19 |
| BL-28 · Comandos de bot deterministas (`/new`, `/help`; sin IA, outbox durable, generaciones de sesión en el ledger, `ancora.command` en la allowlist) | — (BL-28) | 2026-09-20 |
| BL-29 · Renderizado Markdown → HTML de Telegram (whitelist de tags, escaping total, fallback texto plano, retry ante rechazo de markup) | — (BL-29) | 2026-09-20 |

---

## Opciones diferidas (no comprometidas; reevaluar sólo con caso de uso y spec)

- **Control visible del run:** `/stop` con cancelación cooperativa y gobernada, y
  `/status` limitado a metadata no sensible. Requieren semántica durable ante
  `agent_started`, tools/efectos externos y deliveries ambiguas; no son un simple
  `task.cancel()` ni deben prometer rollback.
- **Interfaces/canales adicionales:** una WebUI/TUI first-party completa y
  Discord/Slack/Email/WhatsApp continúan diferidos. BL-36 sí compromete la API que
  permite construir una página web o BFF pequeño; cada UI/canal adicional deberá
  consumir esa frontera o implementar un adaptador con garantías equivalentes de
  admisión, identidad y delivery. No compartir una identidad por heurística.
- **Integraciones extensibles:** MCP, plugins dinámicos y skills instalables. Antes
  exigen catálogo firmado/allowlisted, permisos por capability, sandboxing,
  provenance y supply-chain policy. Los hooks internos tipados de BL-32/BL-13 no
  implican abrir esta superficie.
- **Automatizaciones agentic generales/cron, generación de imágenes y API
  compatible con OpenAI:** valorar como capabilities separadas sólo cuando exista
  una necesidad concreta, modelo de autorización, budget y auditoría. La API de
  producto de BL-36 no implica compatibilidad con `/v1/chat/completions` ni expone
  selección libre de modelo/tools.
- GraphRAG, vector search, microservices y event sourcing continúan «not yet».

## Decisiones explícitamente no adoptadas

- Shell o filesystem generalistas accesibles al Agent/Dream; la infraestructura
  usa puertos y operaciones específicas con allowlist.
- Streaming directo de tokens a Telegram: la entrega continúa pasando por
  respuesta lógica durable, render seguro y outbox.
- Selección/cambio de modelo por usuario: las rutas son configuración operativa
  versionada y gobernada (ADR-005), no una preferencia conversacional.
- Reintentos genéricos de Agent/tools/acciones externas: sólo políticas específicas
  que preserven idempotencia y distingan fallos seguros de efectos ambiguos.
- Subagentes o delegación general mientras una capability/tool del agente principal
  resuelva el caso; cualquier excepción requiere necesidad demostrada y ADR.
