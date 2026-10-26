# BACKLOG — AncoraMind

> Lista viva y priorizada de trabajo pendiente. Fuente única de verdad para
> "qué queda por hacer". Los `specs/*/tasks.md` son el registro histórico de
> "qué se hizo" (no editarlos una vez completados).
>
> Convención: cuando un item pasa a "en curso", se le asigna un número de spec
> (`specs/00X-...`) y se trabaja con SDD (spec.md → tasks.md → implementación).
> Al completarse, se tacha aquí con fecha y se enlaza su spec.

Última actualización: 2026-10-20 (BL-56)

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
| BL-8 Evals agentic | 🔶 36 casos sintéticos, runner estático, harness aislado del Agent y harness Core de consentimiento implementados; pendiente ejecución LLM real (T7) y scoring semántico (T8) — specs/014 + 018 |
| BL-18 Hardening del despliegue Railway (CI/branch protection) | 🔶 gate manual por SHA (Wait for CI OFF por decisión del propietario); servicio/readiness recuperados; E2E de M3–M5 completo en Telegram/Railway (2026-10-17); litellm-postgres/Redis decidido no reactivar; único pendiente real: protección de `main` (decisión de plan/visibilidad diferida) — specs/008 |
| BL-23 Governed LLM Access, Telegram admission y OTel | 🔶 T2–T14 implementados; default GPT-6 Luna `r4` activo en runtime rev. 8, embeddings preservados; queda verificar matriz A–Y completa — specs/013 |
| BL-25 Script E2E nativo PowerShell | ✅ Validación/configuración y flujo local/remoto implementados — specs/015 |
| BL-33 Health signals + dashboard de salud | 🔶 Collector/Grafana base desplegados y 429 resuelto; faltan import/provisioning de dashboard/alertas y matriz T7 — specs/016 |
| BL-38 Conversión de documentos (texto PDF/DOCX + export Markdown→PDF) | 🔶 Fase 1 (PDF texto determinista) validada E2E por Telegram/Railway el 2026-10-13; Fases 2-3 bloqueadas por BL-35/BL-29 — specs/021 |
| BL-39 Seguridad LLM ante prompt injection | 🔶 consentimiento Core desplegado con evidencia E2E parcial; frontera `untrusted_results` extendida y bypass legacy retirado; pendientes evals adversariales reales y matriz completa de consentimiento — specs/022–023 |
| BL-40 Remediación de auditoría técnica (2026-10-02) | 🔶 remediaciones implementadas; GET anónimos de AgentOS protegidos (401) y health/readiness 200 revalidados el 2026-10-16; cierres por evidencia y matriz operativa restante pendientes — specs/023 |
| BL-41 Recurrencia en calendario/recordatorios + snooze | 🔶 implementado localmente (684 unit + 94 integration verdes); pendiente validación E2E Telegram con el propietario — specs/024 |
| BL-34 Política de contexto por tokens y compactación gobernada | 🔶 implementado localmente (política + wiring en `GovernedAgentFactory`); compactación real diferida — specs/030 |
| BL-31 Deduplicación de documentos por hash de contenido | ✅ implementado localmente (909 unit + 141 integration verdes); desbloquea BL-35 y BL-38 Fase 2 |
| BL-42 Recuperación semántica documental | ✅ ruta Gateway, reindexación explícita y E2E productivo ingesta preservada→índice→búsqueda validados; aislamiento por usuario PASS, 1536d, sin contenido en logs — specs/026 |
| BL-43 Pantalla de administración centralizada | 🔶 implementado localmente (invitaciones, runtime-config, salud, enlaces); pendiente validación manual en Railway — specs/027 |
| BL-44 Parada de emergencia manual para Agent/LLM | 🔶 implementado localmente (backend + API admin + CLI); persistencia durable diferida — specs/031 |
| BL-46 Subclasificación WRITE_TRIVIAL/WRITE_REVIEWABLE | ✅ completado: PostgreSQL, trivial y reviewable (prioridad, descripción-sola, fecha-sola); ausencia de escritura previa, descartes y hashes acreditados; versión/CI comprobados — specs/035 |
| BL-47 Tool de lectura `list_pending_proposals` | ✅ validado E2E Telegram con revisión 8/GPT-6 Luna: lectura real + `present_reply` (`tool_call_count=2`), excluye propuesta histórica no presentada |
| BL-48 Presentación única de propuestas y respuestas acotadas tras descarte | 🔶 AC1–AC7 E2E y AC8–AC9 aislados superados; harness real exigido: lanzador one-shot, SDK sin retry y revisión humana implementados/probados sin coste; commit/SHA, acceso privado, aprobación y resultados pendientes — specs/036 y 018 T7 |
| BL-55 Gap analysis contra rúbrico de evaluación académica | 🆕 registrado; huecos priorizados en justificación de modelo/coste proyectado, LLM-juez (Jev) ejecutado, red-teaming (PyRIT/Garak) ejecutado y documento de riesgos propio — ver `docs/academic-rubric-gap-analysis.md` |
| BL-56 Trazas con contenido enmascarado en Phoenix | 🔶 exporter/spike local sólo sintético; auth/OTLP/borrado probados sin Railway; ADR-007 Accepted (2026-10-23) con captura manual; implementar con flag OFF, activación sujeta al gate (procedencia documentos/voz, coste/UI, privacidad) — specs/046 |
| BL-58 Evals de adjuntos desfasados (tool `analyze_document` simulada, `files=`, caso `attachment_is_analyzed_once`) | 🆕 documentado, sin tocar para no alterar lo cerrado; prioridad 1b (no P0, lo siguiente tras el orden 1) |
| BL-57 Ataques adaptativos con PyRIT (red-teaming iterativo) | 🆕 diseño documentado, sin implementar; piloto determinista hecho (90 variantes, 12 pasadas, 0 `fail`); falta adaptador de inyección indirecta, scorer determinista y canal entre venvs; opcional — specs/051 |
| MVP usable | 🔶 E2E funcional de M1–M5 completo en Railway (2026-10-17 — BL-1); pendientes hallazgos de presentación BL-49/50/51, onboarding family&friends BL-24/43 y ejecución del harness de evals — ver orden de cierre P0 |

Tests locales (2026-10-17): 1503 unitarias (80,42 % cobertura) y 173 integraciones PostgreSQL
superadas; una prueba STT live omitida por diseño. Las 4 pruebas de migración
superan fresh install, upgrade/downgrade e idempotencia. Ruff y `mypy src/`
limpios en `src/ tests/ scripts/ migrations/`.

---

## P0 — Hardening transversal de ejecución e inferencia

### Decisión del propietario — 2026-10-17: priorizar cierre de MVP por plazo de presentación

**Contexto:** queda poco tiempo para presentar el MVP. El patrón de las últimas
rondas (BL-45→46→47→48, todas sobre el mismo flujo TODO) ha sido: cada E2E de
BL-1 destapa un hallazgo de gobernanza nuevo, y el trabajo se reinvierte en
profundizar gobernanza en vez de avanzar a los flujos de BL-1 todavía sin
probar (vehículo+mantenimiento, recordatorio, calendario, imagen/PDF
escaneado). Es una elección de calidad legítima, pero alarga el camino al MVP
más de lo que el plazo permite.

**Decisión:** congelar la apertura de nueva gobernanza más allá de lo ya
comprometido, y mover **BL-1 (validación E2E de M4/M5)** al primer puesto del
orden de cierre, junto con **invitaciones + administración (BL-24/43)** para
preparar las pruebas family&friends. BL-48 no se abandona ni se cierra
artificialmente — sigue abierto con su alcance actual (harness real +
evaluación de instrucciones) —
pero no se amplía con nuevos hallazgos derivados de BL-1 mientras dure esta
ventana: un hallazgo de gobernanza encontrado durante BL-1 en este periodo se
**registra como entrada nueva de backlog, no se investiga ni implementa en el
momento**, salvo que sea un fallo de seguridad que bloquee ejecutar una
mutación no autorizada (ese tipo de fallo nunca se aplaza).

**Qué sigue igual:** ningún control existente se desactiva, relaja ni se
expone el Gateway para acelerar esto (AGENTS.md §2 sigue mandando). Esto es
una decisión de **orden de trabajo**, no de alcance de seguridad.

**Vigencia:** esta prioridad aplica a cualquier sesión de trabajo —incluida
una nueva conversación con un agente que no haya visto esta decisión— hasta
que el propietario la revierta explícitamente aquí o el MVP quede presentado.

**Excepción acotada (2026-10-17): dashboard de Grafana visual para la demo.**
El propietario quiere mostrar en la presentación un dashboard real como
evidencia visual de lo que se audita/observa detrás — mover esto al orden 1
también. Alcance exacto de la excepción, para no colarse hacia todo BL-33/T7:
desplegar el Collector privado en Railway, crear los secretos
`GRAFANA_OTLP_ENDPOINT`/`GRAFANA_OTLP_AUTHORIZATION` e importar el dashboard
ya versionado (`observability/dashboards/ancoramind-health.json`) para que
Grafana muestre tráfico/salud real. **No incluye** alertas, la matriz de
degradación (Postgres/Gateway/worker caídos) ni rotación — eso sigue en BL-33
orden 3 tal cual, no se adelanta. Si surge un hallazgo de gobernanza al
desplegar esto, aplica la misma regla: se documenta como entrada nueva de
backlog, no se investiga en el momento, salvo fallo de seguridad real.

**Ampliación acordada (2026-10-17): invitaciones + administración para
family&friends (BL-24/43), dentro del primer grupo.** Es un requisito para
que otras personas puedan probar la aplicación, no una mejora posterior.
Se conserva el orden funcional acordado: recordatorios → vehículos y
mantenimiento → calendario, recurrencia y snooze → imagen/PDF escaneado.
BL-24/43 se prepara en paralelo y debe validarse antes de incorporar al
primer participante; el dashboard de Grafana mantiene su alcance acotado.

**Criterios de salida BL-24/43:** invitación temporal con TTL/cupo, canje
en chat privado y validación de los dos modos existentes por invitación:
**manual** (`auto_approve=false`, predeterminado), con solicitud pendiente
hasta aprobación/rechazo desde administración; y **automático**
(`auto_approve=true`, opt-in explícito al emitir), cuyo canje válido aprueba
la solicitud y crea la autorización activa atómicamente, sin revisión
manual posterior. La autoaprobación conserva TTL/cupo, auditoría y revocación;
el código se comparte sólo por canal privado con las personas previstas.
Verificar en ambos modos la revocación efectiva en el siguiente update,
sin reinicio, y el rechazo de códigos inválidos/expirados/agotados/revocados.
Con cuentas distintas, verificar que una solicitud pendiente/rechazada o
una autorización revocada no permite llegar al Agent y que los datos y
propuestas están aislados por usuario. Validar
en Railway el panel protegido y el rechazo de acceso administrativo sin
credenciales, sin exponer secretos/códigos en logs y con auditoría de las
operaciones. Los participantes no reciben acceso administrativo.

Esta prioridad **no autoriza** por sí sola despliegues, activación de flags
ni nuevas inferencias. Antes de invitar a terceros, concretar el alcance
del piloto y revisar los gates aplicables de seguridad/privacidad de
`docs/production-security-privacy.md`: family&friends no es una exención.
No se considera una apertura pública ni se dan por cerrados BL-23/39/40/48.

**Primer incremento ejecutado (2026-10-17):** recordatorios con tool real,
consentimiento/ejecutor/worker y PostgreSQL local aislado: 3 integraciones nuevas
superadas (confirmar/entregar, 503→entrega y descarte; no duplica en ciclos
posteriores ni con segunda pulsación). Telegram y selección LLM simulados:
recepción humana E2E sigue pendiente. Grafana demo importado, UID
`ancoramind-health` v1, 11 paneles; salud/revisión/heartbeats reales confirmados.
Corregidos dos nombres de contadores; 17 queries válidas no equivalen a 17
series con muestras. Sin alertas, cortes, rotaciones ni cambios Railway.
Pairing/admin: pruebas locales verdes, variables de habilitación aún no
configuradas en Railway; aprobación/rechazo/revocación son CLI/API, el panel
emite/lista y permite autoaprobar al emitir. Gates: 1504 unit + 176 integration
PostgreSQL (1 STT live skipped), Ruff/mypy limpios. Evidencia y siguiente campaña:
`specs/008-railway-deployment/mvp-release-campaign.md`.

**E2E recordatorio real autorizado (2026-10-17): PASS.** Una única petición
automatizada por Playwright y confirmación explícitamente autorizada: propuesta
`executed`, un recordatorio no recurrente `fired` y un aviso recibido en Telegram.
Programado `00:18:50Z`, entregado/marcado `00:18:51.955389Z` (+1,955389 s);
sin segundo aviso observado durante más de dos ciclos. Origen rev. 8/r4 con
3 model calls / 3 Gateway requests / 3 tool calls; confirmación 0/0/0,
sin retry/fallback. Estimación total 0,00378450 USD; coste real no informado.
SELECT final de auditoría, sin nueva inferencia ni escrituras directas. No
cierra recurrencia/snooze, toda M5 ni garantiza exactly-once ante crash/timeout.
Evidencia correlacionada en el registro de campaña; siguiente flujo: vehículos
y mantenimiento (requiere su propio alcance autorizado).

**E2E vehículo + mantenimiento autorizado (2026-10-17): PASS manual.**
Playwright: un vehículo ficticio sin matrícula/VIN, un mantenimiento sin
importe/documento y consulta posterior del historial. Cada escritura mostró
propuesta pendiente sin fila canónica antes del Sí; al final un vehículo,
un mantenimiento y dos propuestas `executed`, sin nueva propuesta en la lectura.
Los datos ficticios quedan identificados y persistidos, sin limpieza implícita.
Cinco interacciones `completed`; ambas confirmaciones 0 inferencia. Rev. 8/r4,
8 model calls / 8 Gateway requests / 8 tool calls entre las tres peticiones;
sin retry/fallback. Coste estimado 0,00998640 USD, real no informado.
41 unitarias focales superadas. No valida factura/OCR, importes ni toda M4.
Hallazgo UX no bloqueante registrado: el bloque de mantenimiento omite el
nombre del target; FK verificada por SELECT, sin cambio de gobernanza ahora.
Evidencia en `specs/008-railway-deployment/mvp-release-campaign.md`, entrega 2.
Siguiente flujo acordado: calendario, recurrencia y snooze.

**E2E calendario/recurrencia/snooze (2026-10-17): PASS funcional asistido.**
Serie diaria limitada a 16–17/10 con aviso vinculado y un snooze de 5 minutos:
una fila de evento, dos ocurrencias virtuales, tres avisos recibidos y tres
recordatorios `fired`, sin ocurrencia del 18 ni avisos futuros. Ambas propuestas
`executed`; confirmaciones sin LLM, cinco interacciones `completed`, rev. 8/r4
sin retry/fallback. Estimación 0,01018000 USD; real no informado. 69 unitarias
focales y 18 integraciones PostgreSQL local superadas. Presentación incompleta
registrada en BL-49: payload comprobado por SELECT antes del Sí autorizado;
no equivale a confirmar UX lista para family&friends ni cerrar toda BL-41.
Evidencia: registro de campaña, entrega 3. Siguiente flujo: imagen/PDF escaneado.

**E2E imagen/PDF escaneado autorizado (2026-10-17): PDF PASS; imagen parcial.**
PNG y PDF raster sintéticos, una página, un envío cada uno y una consulta
posterior: dos originales verificados por hash, dos extracciones visuales
correctas con r1 ya activo, índices completados, cero propuestas. La fecha de
la imagen se extrae bien pero desaparece antes del Agent: BL-50. Tres
interacciones `completed`, sin retry/fallback registrado, rev. 8. Subtotal
conversacional estimado 0,00946220 USD, **no coste total**: visión sin precio
informado y embeddings fuera del ledger/budget actuales (BL-51). 1504 unitarias
y 7 integraciones documentales locales superadas. Sin cambios operativos ni
de producto; registros sintéticos conservados. Evidencia: campaña, entrega 4.
No cerrar BL-6 ni readiness family&friends; próximos trabajos requieren alcance
propio (hallazgos y/o invitaciones/admin), no otra prueba inferencial implícita.

**Ampliación 2026-10-17 (tarde): la evaluación de modelos entra en el orden 1,
en paralelo — no es solo seguridad semántica de fondo.** El propietario aclara
que el MVP no es únicamente demostrar funcionalidad: lo que se quiere poner en
valor es el ciclo completo de ingeniería al trabajar con un LLM, y la
evaluación de modelos/respuestas es uno de esos pasos explícitos a mostrar.
Por eso la ejecución real del harness T7/T7a (BL-8/BL-48) ya preparado —
preflight validado, plan de 5 casos contra rev. 8/r4, reserva estimada de
~0,10 USD, sin tocar producción ni mutar datos reales— sube al mismo nivel que
BL-1/24/43/33: no bloquea ni es bloqueada por ellas, se ejecuta tan pronto el
propietario apruebe el gasto y el acceso privado que ya están pendientes.
Esto NO reabre el alcance congelado de BL-48 (presentación de propuestas,
armonía con hallazgos de BL-1): sigue sin ampliarse con nuevos hallazgos
salvo fallo de seguridad real. Es específicamente la ejecución del harness ya
construido, no trabajo de desarrollo nuevo.

| Orden | Bloque de trabajo | Qué falta para cerrar |
|---|---|---|
| 1 | **Validación MVP (BL-1/41) + invitaciones y administración family&friends (BL-24/43) + dashboard visual Grafana (BL-33, alcance acotado arriba) + ejecución del harness de evals (BL-8/BL-48 T7/T7a)** | Recordatorios → vehículos+mantenimiento → calendario, zona horaria, recurrencia/snooze → imagen/PDF escaneado (BL-6); en paralelo, validar onboarding/revocación, panel protegido y aislamiento antes del primer participante; Collector desplegado + dashboard importado como evidencia visual de demo; y ejecutar el plan de 5 casos del harness T7a contra rev. 8/r4 en cuanto se apruebe gasto/acceso — reutilizar las garantías de consentimiento ya implementadas, sin ampliar gobernanza nueva |
| 1b | **Evals de adjuntos alineados con el flujo actual (BL-58)** | Decisión del propietario (2026-10-26): no es P0, pero es lo siguiente tras cerrar el orden 1 y el trabajo final. Quitar la tool simulada `analyze_document` y `files=`, inyectar el bloque «Adjuntos archivados», reformular 2 casos de `documents`; cambio aparte, con su commit, anotando la pérdida de comparabilidad |
| 2 | Seguridad/consentimiento (BL-39/40 + BL-46/48) | BL-46 completado; BL-48 congelado en su alcance de presentación (no en la ejecución del harness, que ya subió al orden 1) hasta cerrar el orden 1 — no se amplía con hallazgos nuevos de BL-1 salvo fallo de seguridad real |
| 3 | Operación gobernada (BL-23/33/44, resto no cubierto por la excepción) | Degradación/circuit del Gateway sin bypass, alertas, matriz de degradación T7, parada/recuperación y rotación con runbook; requieren campaña operativa autorizada, no cortes improvisados |
| 4 | Seguridad semántica adicional (BL-8/39) | Ampliar catálogos/corpus más allá del plan de 5 casos ya ejecutado en orden 1, scoring semántico más profundo si procede |

GPT-6 Luna sigue como default `ancoramind-default-r4`, runtime rev. 8;
embeddings `ancoramind-embeddings-r1` sin cambios. No abrir otro experimento
de modelo mientras se valida este baseline. Las anotaciones fechadas debajo
son historia de un orden anterior (2026-10-16): no implican que hoy el
servicio esté pausado o el flag esté OFF, y el orden 1↔2 de esa tabla queda
sustituido por la decisión de arriba.

OCR, nuevas salidas y expansión de capabilities no preceden estos cierres.
Protección de `main` sigue pendiente de decisión de plan/visibilidad, no de
activar Wait for CI: se mantiene el gate manual acordado.

**Avance local de la prioridad 1:** 12 pruebas nuevas sobre PostgreSQL aislado
(`test_proposal_presentation.py`, `test_trivial_executor.py`) prueban respuesta
READ + dos propuestas, «Sí» ambiguo sin ejecución, selección individual,
doble pulsación, descarte/repropuesta, OFF, entrega parcial/fallida y cierre
terminal inválido antes/después de una mutación trivial. Escritura y auditoría
trivial se revierten juntas ante fallo de auditoría/commit; target ajeno no
escribe ni audita. No se encontró fallo funcional en estas fronteras. Corregida
una prueba STT flaky: el timeout real de asyncio se arma al entrar al proveedor
simulado, no durante los accesos DB previos. Sin cambios de código productivo,
prompts, configuración, migraciones, inferencia ni despliegue.

**Revisión remota GET, sin credenciales (2026-10-16):** health/readiness 200;
config/sessions/memories/agents/runs/docs/openapi 401; rutas reales de status
runtime-config y emergency-stop 401. Pairing/requests 404: no acredita flag ni
autenticación de un endpoint habilitado. Detalle y límites en
`specs/023-audit-remediation/verification.md`.

**Acuse botones 2026-10-11 — BL-39/40 (local, sin rollout):** `answerCallbackQuery`
implementado; `callback_query_id` solo en payload cifrado, sin migración. Acuse
antes del Core, best-effort/2 s/sin retry, no autoriza ni anuncia éxito. Callbacks
inválidos/OFF no alcanzan Agent/comandos; adjuntos del botón no se reingestan.
1300 unit (79.46% cobertura) + 155 integration passed (1 live STT skipped).
E2E pendiente y límites de acuse/concurrencia documentados en
`specs/023-audit-remediation/callback-acknowledgement.md`. Redis sigue disponible
y apagado por decisión del propietario; no es dependencia de este incremento.

**Incremento 2026-10-11 — BL-23/39/40 (local, sin deploy):** cerrado el bypass
legacy de consentimiento: Agent gobernado/singleton/eval Agent sin `execute_*`;
`confirm`/`confirm_or_use_confirmed`/`mark_executed` rechazan sin I/O. Core
`ProposalExecutor` conserva claims únicos, transacción y auditoría. Con
consentimiento OFF no hay mutación ni fallback LLM. Prompts/catálogo cambiados
(cambio evaluable), pendiente rollout explícito y E2E Telegram.

Diagnóstico remoto de solo lectura: app en `e25bfc4` (local base `9166f55`),
health/readiness 200 y REST/admin consultadas 401; Supabase revisión runtime 2.
En la revisión del 2026-10-11 el Collector recibía 429 de Grafana; Gateway
referencia Redis apagado (uso efectivo
pendiente). Valores efectivos de secrets/flags ocultos. Wait for CI permanece
OFF por decisión del propietario, con gate manual sobre el SHA desplegado.
Evidencia completa: `specs/023-audit-remediation/operational-review-2026-10-11.md`.
**Revalidación 2026-10-15:** el deployment actual del Collector está online y
no registra nuevos `429` ni fallos de exportación; los `429` del historial
terminan el 2026-10-11. Dashboard, alertas y matriz T7 siguen pendientes.
Validación final: 1263 unit + 144 integration passed (1 live STT skipped),
Ruff/mypy limpios, 27 casos de catálogo estático válidos. BL-23/39/40 abiertos.
El harness físico rechaza casos legacy de confirmación antes de inferencia;
BL-8 requiere trasladarlos a un harness Core, no considerarlos ya cubiertos.

### BL-40 · Remediación de auditoría técnica (2026-10-02) 🔶 en curso — specs/023

Auditoría de coherencia especificación/implementación (2026-10-02) detectó 8
hallazgos accionables, organizados en 6 fases con orden de ejecución explícito
en `specs/023-audit-remediation/tasks.md`:

1. **🔴 Crítico — API REST de AgentOS expuesta sin autenticación.** `/config`,
   `/memories`, `/agents/*/runs`, `/sessions`, `/docs`, `/openapi.json`
   accesibles sin credencial en la configuración actual (confirmado por
   inspección local de `app.openapi()`; pendiente confirmar contra Railway
   real antes de cerrar). Posible bypass completo de admission/gobernanza.
2. **🟠 Alto — `UserContext` con fallback silencioso + `APP_ENV` insegura por
   defecto.** Identidad puede degradar a `"unknown"`; `APP_ENV=development`
   (default actual) desactiva la validación del secret de webhook en Agno.
3. **🟠 Alto — Fuga de sesiones DB + UUID sin validar en tools.** Ninguna
   tool cierra `get_session()`; varios `UUID(...)` sin capturar y mensajes
   de error que exponen detalle interno (`str(e)[:200]`).
4. **🔴 Crítico — Consentimiento de mutaciones mediado por el LLM.**
   `execute_*`/`remember_note` no verifican una confirmación nueva atribuible
   al usuario tras una entrega verificada; `mark_executed` no exige
   `status='confirmed'`. **Resuelto (2026-10-02):** T6b/T7 de
   `specs/022-llm-input-trust/consent-design.md` implementados en Fase 4
   (T4.1–T4.8) detrás de `GOVERNED_CONSENT_ENABLED` (apagado por defecto).
5. **🟠 Alto — Zona horaria naive en recordatorios/calendario.** Fechas sin
   tz se persisten asumiendo UTC; un recordatorio a "las 17:00" puede
   disparar 1-2h tarde/pronto según DST. **Resuelto (2026-10-03):** Fase 5
   completa — `resolve_user_timezone()`/`to_utc()`/`to_local_display()` en
   `src/domain/preferences/timezone.py`, normalización en los servicios de
   reminders/calendar, display convertido de vuelta en las tools,
   `get_current_datetime` devuelve también hora local.
6. **🟡 Medio — Sincronización documental.** Recuentos de tests desfasados,
   specs marcados "pendiente" ya implementados, tablas de capabilities
   obsoletas en `docs/architecture.md`, prompts con contrato JSON que
   ninguna tool implementa, código muerto (`src/agent/context.py`,
   `src/services/`, `src/governance/` vacíos). **Resuelto (2026-10-03):**
   Fase 6 completa — recuentos y `> **Status:**` actualizados, tabla de
   capabilities sincronizada con README, contrato de tools reescrito al
   formato real, `src/agent/context.py` y `src/services/` eliminados
   (`src/governance/` se mantiene — está documentado como reservado),
   hallazgo adicional corregido: `skills/calendar.md` existía pero nunca se
   cargaba en `assemble_instructions()`.

**Orden de ejecución:** fase 1 → 2 → 3 → 4 → 5 → 6 (fase 4 depende de fase 3;
el resto son independientes y priorizadas por riesgo).

**Decisiones aprobadas (2026-10-02):**
- **T1.2:** intentar primero quitar las rutas REST de AgentOS que no usamos
  (preferida); si no es viable técnicamente, caer a `OS_SECURITY_KEY` como
  fallback — documentar cuál se aplicó.
- **T4.7:** `analyze_document` sigue siendo automático (enviar un documento
  ya es la señal de intención de guardarlo — mejor UX, excepción aprobada a
  la regla WRITE). A cambio se añade `propose_document_delete`/
  `execute_document_delete`, que hoy no existe, para el caso "no quiero
  esto guardado".
- **T5.1:** zona horaria fija (`Europe/Madrid`) para toda la app por ahora,
  pero el código accede a ella solo a través de una función
  `resolve_user_timezone()`, lista para pasar a configuración por usuario en
  el futuro sin tocar tools/servicios. Se descarta guardar un offset
  numérico (se rompe con el cambio de hora estacional).

**Fase 1 implementada localmente (2026-10-02):** `AgentOS` no permite omitir
routers selectivamente ni `OS_SECURITY_KEY` nativo es reusable sin romper
`/admin/*`/`/health/readiness` (su exclusión por defecto no cubre rutas
propias) — se implementó un middleware propio
(`src/agent/agent_os_rest_guard.py`) que exige bearer solo en las rutas REST
de Agno, dejando intactas `/telegram/*`, `/admin/*`, `/health*`. Fail-closed:
`APP_ENV != "development"` sin `AGENT_OS_SECURITY_KEY` impide arrancar.
`/docs`/`/redoc`/`/openapi.json` cerrados fuera de development. 8 tests
nuevos, 560 unit passing, Ruff/mypy limpios. **Pendiente:** T1.1/T1.5
(verificación contra Railway) bloqueadas — el servicio está pausado;
retomar cuando se reanude.

**Fase 2 implementada localmente (2026-10-02):** `UserContext` ya no degrada a
`"unknown"` ni usa un `session_id` arbitrario como identidad (fail-closed con
`ValueError`). `APP_ENV` pasa a `production` por defecto; fuera de development
la app no arranca sin `AGENT_OS_SECURITY_KEY` ni
`TELEGRAM_WEBHOOK_SECRET_TOKEN`. `tests/conftest.py` declara
`APP_ENV=development` para las suites. 570 unit + 71 integration passing,
Ruff/mypy limpios. **Antes de reanudar Railway:** añadir
`AGENT_OS_SECURITY_KEY` a las variables del servicio.

**Fase 3 implementada localmente (2026-10-02):** las 32 tools cierran sus
sesiones de BD con `@closes_sessions`, también cuando fallan (antes cada
llamada dejaba una conexión del pool sin devolver). `source_document_id` se
valida antes de tocar la BD, y los errores inesperados devuelven un mensaje
fijo y solo registran la clase de la excepción. 585 unit + 71 integration
passing, Ruff/mypy limpios.

**Fase 4 — T4.1/T4.2 implementadas localmente (2026-10-02):** migración
`0006_proposal_consent` con el modelo de estados de `consent-design.md`
(`pending_confirmation → confirmed → executing → executed | failed_*`, más
`expired`/`discarded`), CHECK de estados e índice único que impide que un «Sí»
autorice dos propuestas. El repositorio añade el claim atómico (bloqueo de
fila, reloj de la BD, hash del payload, sin commits propios) y corrige
`mark_executed`, que antes sobrescribía cualquier estado. Las propuestas
antiguas sin procedencia no son ejecutables. 590 unit + 89 integration
passing (incluida una carrera real entre dos sesiones).

**Fase 4 — T4.3/T4.4 implementadas localmente (2026-10-02):** detrás de
`GOVERNED_CONSENT_ENABLED` (apagado por defecto), el procesador reconoce
botones Sí/No y el «Sí» escrito **antes** de llamar al Agent, y el Core añade
un bloque fijo con esos botones a cada propuesta que un run crea, generado
desde los datos guardados y no desde las palabras del modelo. La propuesta
solo queda confirmable tras verificar que Telegram entregó ese mensaje.
Probado de extremo a extremo con PostgreSQL real (propuesta → entrega con
botones → confirmación por botón). **Pendiente:** `answerCallbackQuery` (el
botón no deja de mostrar su reloj de carga todavía).
605 unit + 91 integration passing.

**Fase 4 — T4.5 implementada localmente (2026-10-02):** las 6 tools
`execute_*` ya no llaman a `confirm()` directamente. Nuevo
`confirm_or_use_confirmed()`: con el flag apagado se comporta igual que
antes (el LLM sigue "confirmando"); con el flag encendido, si la propuesta
ya quedó `confirmed` por el claim pre-Agent de T4.3, la tool la ejecuta sin
que el LLM la autorice. Se eligió esta vía "con reserva" en vez de quitar
`confirm()` del todo, porque sin ella el bot se habría roto mientras el
flag siga apagado (que es como está hoy en producción). 605 unit + 93
integration passing.

**Fase 4 — T4.6 implementada localmente (2026-10-02):** `remember_note`
escribía directamente desde la llamada del LLM, sin ActionProposal ni
confirmación — era la última excepción a la regla WRITE de AGENTS.md §2.4.
Sustituida por `propose_note`/`execute_note` con el mismo patrón que el
resto de tools: proponer no escribe, ejecutar exige confirmación (vía
`confirm_or_use_confirmed`, igual que T4.5). 32→33 tools registradas.
609 unit + 93 integration passing.

**Fase 4 — T4.7/T4.8 implementadas localmente (2026-10-02):** el hueco real
de T4.7 (no existía ninguna tool para borrar un documento) se cerró con
`propose_document_delete`/`execute_document_delete` (DESTRUCTIVE,
propose/confirm). 33→35 tools registradas; `prompts/skills/documents.md`,
`README.md`, `docs/architecture.md`, `docs/governance.md` y `AGENTS.md`
actualizados. T4.8 añadió 8 tests parametrizados que confirman que cada
`execute_*` (incluyendo las dos tools nuevas) se niega a mutar cuando
`confirm_or_use_confirmed` devuelve `None`; las ramas de carrera real ya
estaban cubiertas por T4.1/T4.2 contra PostgreSQL. Al revisar el inventario
de `consent-design.md` se encontró que **`/new` nunca invalidaba las
propuestas pendientes del chat**: `discard_pending_for_chat` existía desde
T4.1 pero `_handle_command` no lo llamaba, dejando una propuesta confirmable
con «Sí» tras resetear la conversación. Corregido (best-effort, no bloquea
la respuesta de `/new`) con un test de integración end-to-end nuevo.
622 unit + 94 integration passing.

**Fase 4 — T4.9 ejecutada (2026-10-02), Fase 4 completa (T4.1–T4.9):**
`ruff check`, `mypy src/`, `pytest tests/unit/`, `pytest tests/integration/`,
`python scripts/run_evals.py` y `git diff --check` en verde (622 unit + 94
integration; evals 27 casos/6 categorías tras corregir una referencia
obsoleta a `remember_note` en `evals/security/cases.json`). Actualizados
`specs/022-llm-input-trust/tasks.md`/`verification.md`/`spec.md`,
`docs/llm-security-hardening.md` y las entradas de BL-39 más arriba, que
describían el consentimiento como diseño sin implementar — ya está
implementado y probado contra PostgreSQL real, detrás de
`GOVERNED_CONSENT_ENABLED` (apagado por defecto en producción; activarlo no
es parte de esta fase).

**Prioridad P0** junto a BL-39 (fase 4 es su implementación pendiente).
Ver `specs/023-audit-remediation/`.



### BL-39 · Seguridad ante prompt injection y contenido de menor confianza 🔶 en curso — specs/022

Revisar la frontera adjuntos/notas/extracciones/resultados de tools → Agent,
priorizando autorización de mutaciones en Core y confirmación atribuible a un
evento nuevo del usuario y a la propuesta concreta (no al criterio del LLM).
**Hecho (2026-10-02, specs/023 Fase 4):** WRITE directos (antes `remember_note`,
hoy `propose_note`/`execute_note`) y los 8 `execute_*` ya exigen esa
confirmación, detrás de `GOVERNED_CONSENT_ENABLED` (apagado en producción).
Después, endurecer la preparación local de adjuntos y la representación de

contenido/filenames/`suggested_actions` no confiables, incluido el paso directo
de medios al Agent y las lecturas posteriores. El antiguo fence
`<document_data>` no era una frontera de seguridad; la serialización JSON
introducida en specs/022 tampoco autoriza operaciones. Coordinar con BL-38 /
specs/021 los ensayos pendientes antes de ampliar la extracción de texto PDF.

Ampliar evals sintéticas y probarlas contra el Agent gobernado (BL-8/specs/018)
con tools simuladas; comparar detectores locales offline y falsos positivos
antes de añadir dependencias. No hay RAG/vector search hoy: si se introduce,
aplicar controles tanto en ingesta como en recuperación. Mantener privacidad
metadata-only (ADR-006) y todo acceso inferencial a través de `LLMAccess`.
**Prioridad P0** para consentimiento/WRITE; **P1** para la frontera documental
y de tools; **P2** para pilotos de detectores. Detalle, hipótesis y criterios de
cierre: `docs/llm-security-hardening.md` y `specs/022-llm-input-trust/`.
**Primer incremento local (2026-09-29):** instrucciones de extracción en
`prompts/`, fuente documental serializada en JSON con filename/texto acotados,
prompt versionado 1.2 y `suggested_actions` ya no devuelto en respuestas de
tools documentales. **No resuelve el P0 de consentimiento**, ni protege aún
adjuntos entregados directamente al Agent o notas/resultados de otras tools.
**Diseño P0 (2026-09-30):** `specs/022-llm-input-trust/consent-design.md`
define UX de confirmación inequívoca, entrega previa, caducidad de 15 minutos,
consumo único, estados y fallos ambiguos; inventaría ejecutores, WRITE directos
y ruta AgentOS heredada.
**Implementado y validado con PostgreSQL real (2026-10-02):** T6b/T7 del
diseño P0 se completaron en `specs/023-audit-remediation` (T4.1–T4.8), detrás
de `GOVERNED_CONSENT_ENABLED` (apagado por defecto en producción). Detalle en
`specs/022-llm-input-trust/verification.md` §"P0 — implementado" y en BL-40.

**Punto 1 implementado localmente (2026-10-03, specs/022 T8 segundo
segmento):** el envoltorio `untrusted_results` (acotado/truncado/marcado
`trust: "untrusted_data"`) que ya cubría `search_documents`/`get_document`/
`search_notes` se extiende a las tools de lectura restantes: `find_vehicle`,
`get_vehicle_summary`, `get_vehicle_maintenance_history` (vehículos.py),
`list_reminders` (reminders.py), `check_calendar` (calendar.py) y
`list_todo_lists`/`list_todo_items` (todos.py) — ninguna existía con tests de
tool antes de este incremento, así que se crean `test_vehicle_tools.py`,
`test_reminder_tools.py`, `test_calendar_tools.py` y se ampliá
`test_todos_tools.py` (18 tests nuevos, 723 unit passing). `MAX_RESULT_RECORDS`
aplicado donde no había límite de registros (`get_vehicle_maintenance_history`
devolvía el historial completo sin cap). `prompts/tool_contract.md` corregido
— afirmaba "never JSON"/"don't parse the reply as JSON" cuando
`search_documents`/`get_document`/`search_notes` ya devolvían el envoltorio
desde specs/022; ahora documenta ambas formas de respuesta. **Alcance
explícitamente fuera de este incremento** (ver `docs/llm-security-hardening.md`
§3 y `specs/022/tasks.md` T8): las respuestas de confirmación
`propose_*`/`execute_*` (ecoan contenido en el mismo turno en que el usuario
lo escribió, riesgo distinto al de datos de terceros recuperados después).

**Punto 2 implementado localmente (2026-10-07):** los tres huecos que
quedaban fuera del Punto 1 — adjunto original entregado directamente al
Agent principal y ruta AgentOS legada — se cierran así:
(a) `prompts/tool_contract.md` (regla 8) y `prompts/channels/telegram.md`
(regla 4) ahora dicen explícitamente que una imagen/archivo adjuntado
directamente a la conversación es DATA, no instrucciones, igual que un
resultado de tool — necesario porque desde el fix de BL-1 (2026-09-27)
`GovernedInteractionRunner.run()` pasa `images=`/`files=` crudos a
`agent.arun()` y el único prompt equivalente (`document_extraction.md`) está
excluido a propósito de las instrucciones del agente principal; nuevo test
en `test_instructions.py`. (b) `analyze_document` (`src/agent/tools/
documents.py`) ya envuelve su resultado con `render_retrieved_records`, igual
que el resto de tools de lectura, en vez de devolver texto plano sin acotar;
nuevo record `attachment_error` para adjuntos ilegibles; añadida a la lista
enumerada de `tool_contract.md`. (c) `src/main.py` ya no registra el interfaz
nativo `agno.os.interfaces.telegram.Telegram` cuando
`TELEGRAM_ADMISSION_ENABLED=true` — antes se registraba incondicionalmente,
dejando compilada una superficie Telegram sin `TelegramMediaResolver`
(límites de tamaño/MIME/path-safety) ni el pipeline de admisión/consentimiento
de specs/013/023, aunque la app nunca apuntara su webhook ahí. Sin cambios de
comportamiento en producción (admisión ya activa) ni en dev local (admisión
apagada por defecto). 912 unit + 141 integration passing, Ruff y
`mypy src/` limpios.

**Piloto de detectores locales offline implementado (2026-10-11, P2):**
primer incremento del punto "comparar detectores locales offline y falsos
positivos antes de añadir dependencias". `src/domain/security/
injection_heuristics.py` (`scan_for_injection_patterns`) — puro, sin I/O,
sin dependencias nuevas, cinco heurísticas deterministas (frase imperativa
tipo "ignore...instructions"/filename "IGNORE_...EXECUTE", prefijo falso
`SYSTEM:`, caracteres de control bidi Unicode, blob base64 junto a un verbo
de decodificación, URL acoplada a un verbo de acción). Validado contra el
catálogo real `evals/security/cases.json` (BL-8, no se crearon casos
nuevos): **8/8 recall** en los 8 casos `prompt_injection`, **0/2 falsos
positivos** en los 2 `benign_control`/`false_positive`
(`tests/unit/test_injection_heuristics.py`, 12 tests). Detalle completo,
incluidas las heurísticas descartadas de terceros, en
`docs/llm-security-hardening.md` §"Herramientas consideradas". **No
cierra el punto:** es señal de observabilidad, no un gate — ninguna tool
de producción lo invoca, sin telemetría nueva; el catálogo solo tiene 2
negativos benignos, muestra demasiado pequeña para fijar un umbral de
adopción (el propio plan de arriba pide ampliar ese corpus antes). 1224
unit tests (suite completa), Ruff y `mypy src/` limpios.

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
**Hallazgo E2E 2026-10-16:** el presupuesto contaba tools en memoria, pero el
ledger nunca persistía `tool_call_count`; todas las interacciones quedaban a
cero. Corrección local metadata-only, idempotente y fail-open implementada y
validada (1427 unit + 160 integration, 1 STT live skipped). Pendiente CI/deploy
y repetir la lectura BL-47 para obtener evidencia durable del run.

**Incidente E2E posterior (SHA `00f0d0f`):** la lectura BL-47 ejecutó una tool,
pero el segundo turno no cerró con `present_reply`; el Core rechazó la salida,
marcó `failed_ambiguous` y no reintentó ni entregó prosa, pero Telegram quedó en
silencio. Implementado localmente un aviso fijo mediante outbox secundaria
idempotente `failure_notice`, sin alterar el estado terminal ni afirmar efectos.
1428 unit + 161 integration verdes (1 STT live skipped); pendiente CI/deploy/E2E.
**Revalidación SHA `a0ace40`:** el aviso fijo quedó entregado E2E, sin retry,
fallback, propuesta ni `agent_final`; `r5` volvió a incumplir `present_reply` en
sesión limpia. `r5` corresponde al experimento `xiaomi/mimo-v2.6-pro`; preparado
asset aditivo para volver default a `r4`/GPT-6 Luna conservando embeddings y
pricing canónico `0.10/0.50`. Pendiente CI y activación CAS como revisión 7.
**Cierre operativo de este hallazgo:** SHA `5f0132f` desplegado; por doble envío
accidental se crearon revisiones 7 y 8 idénticas (7 inactiva). Revisión 8 activa
por CAS `6→8`, embeddings preservados. E2E BL-47 PASS: interacción completed,
2 llamadas LLM, 2 tools, ruta r4, `agent_final` entregada, sin retries/fallback,
propuestas nuevas ni `failure_notice`. BL-47 cerrado; BL-48 continúa parcial.
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

### BL-24 · Onboarding de usuarios Telegram mediante invitaciones gobernadas 🔶 en curso — specs/017

**E2E autoaprobado remoto 2026-10-17: PASS acotado.** Segunda cuenta, invitación
opt-in de un uso/5 min: canje crea solicitud approved y autorización activa en
el mismo instante; Telegram responde «Acceso concedido. Ya puedes escribir con
normalidad.»; `/help` funciona sin aprobar manualmente. Revocación API bloquea
el siguiente update sin reinicio. Tres interacciones, cero Agent/model/Gateway/
tools/usage LLM. Cierre `13cf938f-595c-4509-be0d-463fceae1b95` SUCCESS, mismo
SHA `bee0062`, tres flags OFF, servicio sano/rev.8; sin secretos nuevos ni
cambio de allowlist/webhook/runtime. Falta resto de matriz/aislamiento real.
Mensaje libre del propietario tras revocar quedó rejected sin outbox: aviso
genérico de acceso no activo propuesto en BL-52, no implementado.

**E2E manual remoto 2026-10-17: PASS acotado, no cierre global.** Segunda cuenta
fuera de allowlist: pending bloquea; aprobar admite `/help` sin Agent/LLM;
revocar bloquea el siguiente update sin reinicio. Un uso/TTL 5 min, dos entregas
outbox, cinco interacciones con cero model/Gateway/tools y sin usage LLM.
Autorización revocada, invitación agotada y tres flags OFF al cierre; servicio
sano/rev.8. CI verde SHA `bee0062`; deployment cierre
`5b7c5d96-30e1-42d6-9503-5aaff8924157` SUCCESS. Se añadieron secretos panel/pepper
preparados localmente, sin rotar el CLI previo; conservados según runbook.
Pendientes autoaprobación/matriz remota e aislamiento real de datos. Incidencia:
filtro de lectura del agente devolvió código ya agotado por whitespace Unicode;
no copiado en documentos, acceso revocado. No afirmar evidencia íntegramente
metadata-only. Registro completo: campaña MVP, «E2E manual remoto autorizado».

**Preparación local 2026-10-17:** siete integraciones nuevas conectan panel →
emisión persistida → canje/outbox sin Agent → aprobación manual o autoaprobación
opt-in → admisión → revocación/rechazo, con servicios/repos reales en PostgreSQL
loopback `_test`. Incluyen código redactado/HMAC, replay y estados no admitidos.
32 unitarias nuevas del panel prueban todas sus rutas JSON contra token
ausente/erróneo/CLI y exigen actor/motivo en mutaciones. Resultado: 70 unitarias
focales, 1536 globales y 183 integraciones passed/1 STT live skipped; Ruff/mypy
limpios. Checklist operativo en `docs/preflight-onboarding-admin.md`. Sin
producto/flags/allowlist/secretos operativos nuevos ni inferencia/contacto externo.
No cierra BL-24/43: faltan HTTPS/navegador y segunda cuenta real autorizada,
retención/gates de privacidad y ventana remota. BL-49/50/51 siguen abiertos.

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

**Actualización 2026-09-27 (T1):** creado `specs/017-telegram-governed-pairing`
y la base auditable: migración Alembic `0005_telegram_pairing`, bootstrap
idempotente y API administrativa apagada por defecto (`TELEGRAM_PAIRING_ADMIN_ENABLED`)
que reutiliza bearer + actor obligatorio. Las invitaciones se generan con alta
entropía y se persisten sólo como HMAC con `TELEGRAM_PAIRING_CODE_PEPPER`; la
emisión devuelve el código una única vez. **Actualización T2:** el canje atómico
ya existe en Core (`FOR UPDATE` de invitación + advisory lock por usuario), aplica
TTL/cupo/estado/replay y crea como máximo una solicitud `pending` por usuario; la
cola administrativa permite listar/rechazar con actor/motivo. **Actualización T3:**
`TELEGRAM_PAIRING_ENABLED` activa `/pair <code>` sólo en chat privado; el código se
canjea antes del Agent, se redacta del payload durable y genera una respuesta fija
por outbox sin llamada LLM. Admission conserva `ALLOWED_TELEGRAM_USER_IDS` como
ruta técnica y además consulta la autorización durable activa en cada nuevo update,
por lo que una revocación bloquea el siguiente update sin reinicio. Validación local:
491 unitarias passing + 2 fallos ambientales conocidos de PowerShell/ruta con
espacios, y 71 integraciones passing; quedan T4 (runbook/flags de despliegue y
E2E Telegram/Railway controlado con cuenta no productiva). **Actualización T4
local:** `scripts/telegram_pairing.py` opera la API administrativa protegida
(emitir/listar/aprobar/rechazar/revocar) sin acceso SQL directo, y
`docs/runbooks-017-telegram-pairing.md` documenta flags, rotación, rollback y el
E2E controlado. Aún no se ha registrado/modificado un webhook ni contactado una
cuenta Telegram: esas acciones requieren aprobación explícita.

**Actualización 2026-10-05 (T5, incremento sobre BL-43):** con un solo
operador, exigir siempre una segunda aprobación manual tras el canje era un
punto único de disponibilidad (si el operador está incomunicado, nadie puede
empezar a usar AncoraMind aunque la invitación ya se haya compartido por un
canal de confianza). Se añade `auto_approve` como flag **opt-in** por
invitación (`false` por defecto, migración `0010_pairing_auto_approve`): si se
activa al emitir, el canje (`/pair <código>`) crea la autorización activa en
el mismo paso atómico que hoy crea la solicitud `pending`, sin segunda
intervención — el invariante "invitación ≠ autorización" sigue siendo la
regla por defecto, `auto_approve` es la única excepción, explícita y
auditable (queda registrado qué operador la activó y con qué motivo, igual
que una aprobación manual). Expuesto en los tres puntos de entrada: CLI
(`--auto-approve`), admin API (`CreateInvitationRequest.auto_approve`) y el
dashboard de BL-43 (checkbox con aviso del trade-off: el código pasa a ser el
único factor de confianza, combinarlo con un `max_uses` ajustado). Tests:
2 nuevos de integración (atomicidad de la autorización, E2E de admission con
la respuesta de outbox diferenciada) + unitarios de servicio/admin API/CLI.

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

**Actualización 2026-09-27 (bug de continuidad conversacional tras adjunto ✅):**
diagnosticado en producción vía Telegram: tras `analyze_document` procesar un
`.txt`, una pregunta de seguimiento en el mismo hilo ("¿qué vas a hacer con esta
información?") ignoraba por completo el documento — el LLM respondía sobre un
tema anterior no relacionado. Causa: `GovernedInteractionRunner.run()` invocaba
`analyze_document` directamente cuando había adjuntos, evitando `agent.arun()`;
solo `arun()` persiste el turno en la `AgentSession` que alimenta
`add_history_to_context`, así que el turno del documento nunca quedaba en el
historial. Corregido eliminando esa rama: ahora todo run (con o sin adjuntos)
pasa por `agent.arun(..., images=..., files=...)`, dejando que Agno invoque
`analyze_document` como tool call normal y registre el turno. Tests actualizados
en `test_governed_interaction_runner.py`; 506 unit tests, ruff y mypy en verde.
Pendiente de re-validar en Telegram/Railway como parte del E2E de M3.

**Actualización 2026-10-13 (sesión E2E en producción, flujo 5/TODO ✅
funcional):** con `GOVERNED_CONSENT_ENABLED=true` confirmado activo en
Railway (y `CALENDAR_PROVIDER` sin definir ⇒ `noop` por defecto), se probó el
flujo TODO completo contra el bot real: crear lista → confirmar por botón →
proponer 2 items en paralelo → confirmar cada uno por botón → marcar un item
como completado → listar la lista con estados reales. **Resultado funcional:
correcto end-to-end**, incluida la caducidad real de una propuesta a los 15
minutos (rechazada tal como diseña consent-design) y el rechazo de un "Sí"
mezclado con otra frase cuando había más de una propuesta pendiente. Tres
hallazgos de UX/fiabilidad derivados de esta prueba, documentados como nuevas
entradas (no implementados): **BL-45** (N propuestas simultáneas ⇒ N pares de
botones, no escala), **BL-46** (pedir confirmación para una orden explícita
sin ambigüedad sobre un recurso ya existente se siente redundante — propuesta
de subniveles de riesgo dentro de WRITE, toca AGENTS.md §2.4, requiere
decisión del propietario) y **BL-47** (el Agent narra qué propuestas están
"pendientes" desde memoria conversacional, no desde una tool de lectura real
— puede afirmar como pendiente algo ya ejecutado o ya caducado). Pendiente en
esta ronda de E2E: flujos 4 (calendario), 3 (recordatorio), 2 (vehículo +
mantenimiento) y 1 (documento imagen/PDF visión).

**Corrección 2026-10-13 (frontera de adjuntos Telegram):** el flujo anterior
de continuidad quedó retirado porque entregar `images=`/`files=` crudos al
Agent principal hacía que Agno/LiteLLM/OpenRouter intentara parsear el archivo
original antes de que pudiera ejecutarse `analyze_document`. Ahora
`GovernedInteractionRunner` llama primero a la entrada de ingesta de aplicación:
almacena el original, prepara localmente PDFs con capa de texto y Office, y
limita la ruta visual a PDFs escaneados/imágenes. El Agent principal recibe sólo
un resumen canónico `untrusted_data` dentro de su turno persistido, sin bytes,
URLs, `images=` ni `files=` de Telegram. `analyze_document` deja de estar en el
catálogo del Agent principal; permanece como adaptador legado/testeable de la
misma lógica. Validación local: 1307 unit tests passed, Ruff y `mypy src/`
limpios. Pendiente: E2E Telegram/Railway que confirme ausencia de solicitudes
de parser documental/rate limits de OpenRouter.

**Validación E2E 2026-10-13 (PDF textual + continuidad ✅):** en Telegram con
Railway se subió un PDF real con capa de texto. El bot confirmó que quedó
archivado, produjo un resumen documental correcto con confianza aproximada del
85 % y no presentó el error previo de parsing/rate limit de OpenRouter. Una
pregunta de seguimiento en el mismo chat obtuvo una respuesta correcta y
trazable a la guía archivada, incluyendo la advertencia de confianza; confirma
que el turno persistido conserva el resumen canónico `untrusted_data` sin
reenviar el PDF al Agent principal. Esta evidencia cierra el ensayo E2E de PDF
textual de BL-38/Fase 1 y avanza M3, pero **no** valida todavía imágenes ni PDFs
escaneados (ruta visual), ni los flujos M4–M5.

### BL-55 · Fechas legibles en mensajes y propuestas, sin ISO técnico 🔶 implementado local — specs/047

Preferencia explícita del propietario al revisar la propuesta natural BL-54:
`2026-11-01T10:00:00+01:00` añade ruido. Formato visible deseado:
**`YYYY-MM-DD`** si sólo corresponde una fecha y **`YYYY-MM-DD HH:MM`** si
también corresponde hora; ejemplos `2026-11-01` y `2026-11-01 10:00`.
Aplicar a mensajes de uso normal, empezando por bloques Core de calendario
(inicio/fin/límite inclusivo) y recordatorios; revisar después otras salidas
deterministas y respuestas del Agent para no tener formatos contradictorios.

**Evidencia:** propuesta sintética de BL-54 observada en Telegram, mensaje
visual `14448` / Bot API `510`, origen `c6e99224-8bdf-4a7d-994f-481958949610`.
El renderer `src/domain/actions/presentation.py` muestra start_at/end_at/
trigger_at y recurrence_until como valores almacenados; las fechas límite
TODO ya tienen otro formato legible. No es un fallo de parsing o ejecución.

**Contrato del incremento:** presentación consistente usando la
resolución de timezone existente, sin cambiar el instante ni ocultar una
zona relevante para confirmar. No basta sustituir `T` y cortar el offset:
cuando sea necesario, indicar la zona de forma legible aparte en vez de un
sufijo ISO por campo. No inferir fecha sola por tener hora 00:00 en eventos
o recordatorios ni convertir naive a UTC silenciosamente; preservar precisión
significativa (segundos/fracciones no cero) mediante una regla explícita,
sin redondear u ocultar diferencias entre lo mostrado y lo que se ejecuta.
Payload/hash, parser, consentimiento y ejecución deben quedar intactos.

Añadir regresiones de fecha sola, hora, medianoche, offset distinto de la
zona del usuario, UTC y cambio horario; conservar fallback seguro para valores
inválidos y procedencia. Si se cambian prompts/descripciones, tratar como
cambio evaluable. Revalidación Telegram sólo en ventana autorizada; no repetir
inferencias para registrar este hallazgo ni reabrir el cierre acotado BL-54.
**Implementado local (2026-10-22):** formateador compartido, timezone resuelta
desde identidad, zona/offset legibles y precisión conservada; renderer Core y
tools calendario/recordatorios alineados, fechas TODO normalizadas al formato
acordado. Hash/payload/parser/consentimiento intactos; integración local comprueba
conversión y no ejecución. Cambio evaluable de prompts; sin inferencia ni deploy.
Detalles/resultados y límites: `specs/047-readable-presentation/verification.md`.
Validación global junto con BL-53/56: 2211 unitarias/1 skip, 81,69 % cobertura;
218 integraciones locales/1 STT skip; Ruff/mypy186/catálogos/diff limpios.
Incluye regresiones de lectura DST y filtrado de tracestate/scope/links.
Pendientes SHA/CI, publicación y evaluación semántica/E2E autorizada; no afirmar
que la instrucción de formato del Agent esté ya validada contra un modelo real.

### BL-54 · Investigar rechazo de recurrencia en petición natural de calendario ✅ contrato corregido y regresión natural E2E acotada superada — 2026-10-17

Durante E2E de presentación BL-49, petición natural con inicio/fin y límite
inclusivo timezone-aware `+01:00`, frecuencia semanal cada 2 semanas y aviso
90 min antes: respuesta de rechazo de regla de recurrencia, sin propuesta ni
evento creado. Interacción `46021851-1eb1-49d3-bf61-d608a5086577`, completed,
2 model/2 Gateway/2 tools. Los valores de referencia son válidos al probar
`recurrence_rule_from_flat` localmente; no se inspeccionaron los argumentos
efectivos privados de la tool y no hay causa demostrada de parsing/modelo/DST.

Una petición nueva explícita con parámetros UTC equivalentes sí generó el
bloque correcto; no convierte la primera en PASS ni justifica exigir nombres
técnicos a usuarios. Pendiente diagnóstico mínimo sin nueva inferencia ni
captura de contenido personal indiscriminada; regresión cuando se localice
el mecanismo. No retries/fallbacks ni cambio de timezone/prompts implícitos.
Evidencia en specs/038 y campaña de liberación, E2E BL-49/52. Registro sólo,
sin ampliar el alcance implementado de BL-49 ni el congelado de BL-48.

**Diagnóstico/corrección local autorizados (specs/039):** schema real Agno y
prompt de calendario describían `recurrence_until` como fecha; el Core exige
datetime timezone-aware. Fecha sola/naive e intervalo inválido se rechazan
incluso con weekly válida, pero el error anterior apuntaba a frecuencia.
Offsets +01:00/UTC válidos pasan parser y FunctionCall reales sin inferencia.
Esto prueba la contradicción, **no** los argumentos ni causa exacta del run
histórico. Corregidas las dos descripciones y assets calendar/reminders,
incluido rango 1–365, preservación de hora/zona y aclaración natural si falta;
error fijo sin eco de entradas. Parser/semántica/permisos/ejecución intactos.
44 regresiones nuevas; 1626 unitarias, 207 integraciones locales passed y 1
STT live skipped; Ruff/mypy limpios. Sin inferencia ni acceso remoto, flags o
despliegue en aquella fase. **Pendiente al cerrar la fase local:** commit evaluable, CI/SHA y E2E natural
autorizado; no exigir parámetros técnicos ni declarar retrospectivamente
corregida la interacción fallida. T7 no se amplía ni se ejecuta en este cambio.

**Validación posterior autorizada:** SHA `778c5a3` desplegado por el propietario,
deployment `1193d431-a2f8-4536-ba73-0c1c7895e865` SUCCESS y CI del mismo SHA
verde. Una petición natural sin parámetros técnicos, con UTC+01:00 y límite
inclusivo explícitos, produjo weekly/2/until correctos y aviso de 90 min al
primer intento. Propuesta `07fb5ef6-ed21-4ef1-ad4e-4c5b321a670e` observada en
Telegram y descartada por No; hash intacto, cero eventos/avisos nuevos.
Origen `c6e99224-8bdf-4a7d-994f-481958949610`, 2/2/2 model/Gateway/tools,
0,00249900 USD estimados (real desconocido); descarte sin IA. 93 unitarias
focales superadas. Evidencia specs/039. Cierre de contrato/regresión acotado,
no causa histórica exacta, garantía general semántica ni toda M5. Sin cambiar
flags/desplegar desde esta ventana; navegador conservado. Evals T7 pendientes.

### BL-55 · Gap analysis contra el rúbrico de evaluación académica 🆕 registrado — 2026-10-18

El propietario compartió el texto de evaluación del entregable final del
programa (4 módulos: modelo/coste, flujo agentic, despliegue/evaluación/
monitorización, seguridad/riesgos). Se hizo un gap analysis puntual contra
el estado actual del repo, documentado en
`docs/academic-rubric-gap-analysis.md` — no se repite el detalle aquí, solo
el resumen para priorización.

**Huecos identificados (ninguno implementado en este registro):**
1. Módulo 1: falta justificación comparativa de por qué GPT-6 Luna frente a
   otros modelos (hoy solo existe el *cómo* cambiarlo, no el *por qué* de
   la elección actual), y falta una proyección de coste por niveles de uso
   (solo hay coste medido retrospectivo, nunca una proyección "$X/mes a N
   usuarios/día").
2. Módulo 2: falta un documento que traduzca explícitamente un proceso de
   negocio real a su patrón técnico (ej. "recordar mantenimiento del
   coche" → `propose_vehicle_maintenance`/`execute_vehicle_maintenance`);
   hoy esa lógica está repartida sin pieza narrativa propia. Es, de los
   cuatro módulos, el mejor cubierto ya (autonomía/gobernanza y elección de
   framework con ADR-001 ya documentados).
3. Módulo 3: el LLM-juez (`Jev`,
   `specs/014-agentic-evals/jev-pilot-proposal.md`) sigue en estado
   "propuesta, no implementada" — el enunciado pide explícitamente "LLMs
   como Juez, o al menos algún evaluador no-subjetivo"; el no-subjetivo ya
   corre (`evals/`, `injection_heuristics.py`), falta ejecutar el juez.
4. Módulo 4: PyRIT/Garak quedaron documentados como candidatos evaluados
   (2026-10-18, `docs/llm-security-hardening.md`) pero ninguno está
   ejecutado — el enunciado pide apoyarse en "algún agente o framework de
   red-teaming". Tampoco existe un documento de análisis de riesgos
   independiente (el modelo de amenaza vive como subsección de
   `llm-security-hardening.md`, no como artefacto propio).

**Lectura global:** según el baremo descrito por el propietario (5-7 por
reflejar conceptos; 7-9 por implementado aunque no desplegado del todo; 9-10
por completo sin carga de mantenimiento para terceros), el proyecto está
hoy sólidamente en banda 7-9. El riesgo no es falta de trabajo de fondo —es
que el documento final no nombre estos huecos explícitamente.

**Pendiente, no implementado:** decidir cuáles de estos huecos se cierran
antes de la entrega y cuáles se documentan como "trabajo futuro reconocido"
en el propio entregable. No amplía ni reabre ninguna gobernanza existente;
es puramente un registro de priorización. Revisar vigencia de
`docs/academic-rubric-gap-analysis.md` antes de usarlo — puede quedar
obsoleto si se cierran estos puntos.

### BL-53 · Ocultar IDs técnicos documentales en respuestas de uso normal 🔶 implementado local — specs/047

Preferencia explícita del propietario al revisar el E2E visual de BL-1/6:
los UUIDs internos de documentos añaden ruido y pueden confundir al usuario.
Mostrar por defecto el nombre del documento y una referencia legible suficiente
para atribuir los datos, sin volcar identificadores técnicos en el mensaje.
Conservar los IDs en tools, persistencia y auditoría para trazabilidad y scope;
no eliminarlos del contrato interno ni sustituirlos por nombres al autorizar.
Reservar su presentación para petición explícita del usuario o diagnóstico
solicitado, no como parte rutinaria de una respuesta documental.

**Evidencia histórica, no nueva prueba:** la consulta de los fixtures
`ancora-visual-e2e-20261017-image.png` y `ancora-visual-e2e-20261017-scan.pdf`
incluyó nombre e ID en la respuesta. El guion pedía expresamente ambos, por lo
que ese ensayo no demuestra incumplimiento del Agent: registra una mejora de
UX para el uso normal y para futuros guiones de validación. La procedencia
técnica puede comprobarse aparte sin exigir UUIDs en la respuesta visible.

**Implementado local (2026-10-22):** instrucciones Telegram/documentos para uso
normal sin UUID, excepción explícita de ID documental y homónimos con procedencia
o aclaración; IDs internos/autoridad intactos. Tres casos evaluables y fixtures
sintéticos, tests de instrucciones y del contrato de tools. No se filtra la salida
con regex ni se promete cumplimiento semántico por tests estáticos. Sin ingesta,
inferencia real, publicación o ampliación de campaña histórica. Separado de BL-50.
Evidencia y gates conjuntos con BL-55: `specs/047-readable-presentation/verification.md`.

### BL-52 · Aviso determinista y acotado para cuentas sin acceso ✅ desplegado; E2E acotado superado — 2026-10-17

**Incremento autorizado:** aviso fijo «🔒 Tu acceso no está activo. Contacta
con quien te invitó o con el administrador.» para nuevos mensajes privados
autenticados completos, sin contenido del usuario. Interacción permanece
rejected y sin Agent/LLM; outbox secundario cifrado, dedup/claim durable y cero
reenvío tras fallo ambiguo. Flag propio `TELEGRAM_ACCESS_NOTICE_ENABLED=false`
por defecto, independiente de pairing; requiere admission+processor existentes.
Cooldown 300 s por bot/usuario o chat, 20 reservas/min global, 20 pendientes y
TTL 300 s. Callback/grupo/edit/rate-limit/secret inválido no notifican.

Alembic local `0017_access_notice_index` (sólo índice parcial) e init.sql
equivalente; sin modificar datos. 17 unitarias y 20 integraciones nuevas:
global 1553 unitarias/203 integraciones passed, 1 live skipped, Ruff/mypy limpios.
Especificación/evidencia en `specs/037-access-denied-notice/`.
**Rollout autorizado posterior:** Alembic canónico 0016→0017 aplicado y
verificado; flag de aviso ON en deployment `a20e86e1-93b1-4949-82e1-663ae290e162`,
SHA `65295ac` y CI del mismo SHA verde. Telegram account=2 revocada: primer
aviso recibido, silencio a +75 s y nuevo aviso tras cooldown; tres rejected,
payload NULL y 0 Agent/model/Gateway/tools/usage. `/help` autorizado correcto
sin IA. Panel y pairing permanecen ON por decisión del propietario, sin
rollback automático; navegador abierto. PASS del guion acotado, no E2E de
presión global/crash ni toda la matriz de onboarding. Evidencia specs/037.
Los párrafos siguientes conservan hallazgo/propuesta de origen, no el estado
actual de implementación local.

Observación del propietario tras el E2E manual: escribir desde la segunda
cuenta no obtiene respuesta. Verificado en producción por metadata scoped:
interacción `8625d9b1-068f-4d0d-85ec-7844b2b68380` rejected por
`user_not_allowlisted`, cero LLM y sin logical_response. No es fallo de Telegram
ni del modelo: admission rechaza y el processor sólo consume accepted/
response_ready. Estado actual intencional de la implementación; UX insuficiente.

**Propuesta, no implementada ni desplegada:** aviso fijo del Core en chat
privado autenticado, por ejemplo «Tu acceso no está activo. Contacta con quien
te invitó o con el administrador.» No distinguir desconocido/pending/revocado
ni revelar validez/cupo/TTL de códigos, no prometer activación por invitación
cuando pairing está OFF. No responder a secretos webhook inválidos, grupos,
updates sin identidad o descartes de spam/rate limit con un nuevo bucle.

Requiere un camino de notificación de rechazo que conserve la denegación y
cero Agent/LLM, idempotencia durable y outbox sin replay. **No basta añadir el
texto al service ni cambiar rejected a accepted**: los límites actuales sólo
se evalúan para accepted; añadir límites durables por usuario/chat y globales
para esos avisos, sin amplificación ante flood. Definir cuota/cooldown y flags
antes de implementar; no nueva excepción de autorización. Tests de ráfaga,
duplicados, private-only, secretos, pending/revocado, flag OFF, fallos de entrega
y regresión de admisión/consentimiento. Trabajo separado de BL-48; evidencia
en campaña MVP, «E2E autoaprobado remoto».

### BL-50 · Conservar campos documentales estructurados al consultar 🆕 registrado — 2026-10-17

E2E visual de BL-1/6: fecha `2026-10-17` correctamente persistida en
`ai_extractions.extraction.document_date` del PNG, pero el bot dice que no
está disponible tanto tras adjuntar como tras consultar el archivo. Causa
reproducida: `_extraction_record` en tools/documentos sólo entrega
tipo/resumen/confianza; elimina fechas/importes/entidades estructuradas y
depende de que el resumen las repita. El PDF del mismo ensayo sí responde
todos los datos porque su resumen los incluye. No es un fallo probado de OCR.

Pendiente, sin implementación en esta ventana: exponer campos relevantes
acotados como datos no confiables, conservando procedencia y límites;
regresión de ingesta/`get_document` con fecha no repetida en summary y E2E
posterior. No recuperar la fecha del filename ni añadir instrucciones crudas
del documento. La consulta documental queda parcial hasta resolverlo.
Evidencia y IDs en campaña, entrega 4. No amplía gobernanza BL-48.

### BL-51 · Completar presupuesto/auditoría de visión y embeddings 🆕 registrado — 2026-10-17

El E2E visual usa r1 activo: dos llamadas `ancoramind-vision-r1` completadas,
sin estimated_cost/actual_cost y sin pricing para ese alias en la revisión 8.
El subtotal default-r4 no representa el coste total ni permite acreditar que
el techo monetario cubre lo no medido. Índices documentales con embeddings r1
completados; `GovernedDocumentEmbeddingAdapter` resuelve snapshot/Gateway y
emergency-stop, pero sus HTTP no reservan ExecutionBudget ni registran
LlmUsageRecorder. Los contadores model/Gateway del ledger no los incluyen.

Pendiente: acordar precio/ruta y cobertura de presupuesto de esas capabilities,
integrar contabilidad correlacionada (incluido coste desconocido), regresiones
y validación acotada. **No resuelto por este E2E ni autorizado implícitamente
un cambio de configuración o modelo.** Registrar separado, sin nuevo benchmark
inferencial hasta acordar alcance; no declarar garantía completa de coste con
el ledger parcial. No se desactivó ningún control desde esta sesión.
Evidencia en campaña, entrega 4; marco existente specs/013/026, no BL-48.

### BL-49 · Completar presentación de calendario y snooze antes del piloto ✅ desplegado; presentación/descarte E2E superados — 2026-10-17

Hallazgo del E2E de calendario/recurrencia/snooze (BL-1/41): el bloque Core
de `create_calendar_event` muestra título/inicio/fin, pero no frecuencia,
intervalo, límite `until`, creación de aviso ni antelación. El bloque de
`snooze_reminder` sólo muestra el identificador técnico, sin recordatorio
objetivo ni duración. No es un fallo de ejecución observado: los payloads
persistidos eran correctos y el flujo autorizado pasó tras revisión asistida
por SELECT; un participante normal no dispone de esa revisión.

**Incremento local autorizado e implementado (specs/038):** calendario muestra
frecuencia/intervalo, límite inclusivo o sin fecha límite, aviso sí/no y
antelación (cero = al inicio). Snooze muestra «Posponer recordatorio», título
canónico consultado por ID + usuario de la interacción y duración desde la
confirmación. Target ausente/no propio/ID inválido → «No disponible»; nunca un
título del modelo. Payload/hash, botones, consentimiento y ejecución intactos.
Sin migraciones ni cambios de tools/prompts. 29 unitarias y 4 integraciones
nuevas; gates globales: 1582 unitarias, 207 integraciones passed y 1 STT live
skipped, Ruff/mypy limpios. Evidencia: `specs/038-calendar-snooze-presentation/verification.md`.
**E2E autorizado posterior:** SHA `65295ac`/CI verde, deployment
`a20e86e1-93b1-4949-82e1-663ae290e162`. Bloques de calendario semanal cada
2 semanas con límite/aviso de 90 min y snooze de 90 min con título canónico
observados en Telegram. Ambos descartados por No, hash intacto y cero nuevas
filas canónicas; no ejecución nueva ni avisos programados. Primera petición
natural rechazó recurrencia sin propuesta: se registra BL-54, no se oculta
con el PASS posterior parametrizado. 6/6/6 model/Gateway/tools entre tres
peticiones, 0,00805790 USD estimados, coste real desconocido; descartes sin IA.
PASS de presentación/descarte acotado, no de toda UX family&friends ni BL-48.

Observaciones relacionadas a priorizar por separado si procede: doble prefijo
«Recordatorio:» en avisos vinculados, y texto de retraso que atribuye siempre
parada/reinicio aunque el trigger se creó deliberadamente en el pasado.
Evidencia en `specs/008-railway-deployment/mvp-release-campaign.md`, entrega 3.

### BL-45 · Confirmación por lote para múltiples propuestas pendientes simultáneas 🆕 propuesto — 2026-10-13

**Hallazgo (E2E Telegram, flujo TODO/BL-1):** al pedir "Añade leche y pan a la
lista Compras" se generan dos `ActionProposal` independientes y Telegram
muestra **dos pares de botones Sí/No** (uno por propuesta). Con N elementos en
una sola petición saldrían N pares de botones — no escala y es confuso para
el usuario, que ve una sola intención ("añadir estos dos items") partida en
N confirmaciones visualmente separadas.

**Causa:** por diseño (`src/domain/actions/presentation.py::consent_buttons`),
cada botón codifica el `proposal_id` exacto que autoriza, precisamente para
que la confirmación sea atribuible a una propuesta concreta (specs/022
consent-design) y no exista un "confirmar todo" genérico que ejecute algo no
revisado individualmente. No es un bug; es el trade-off seguridad/UX actual.

**Propuesta a evaluar (sin diseñar aún):** un mecanismo de confirmación por
lote cuando varias propuestas se crean en el mismo turno del Agent — por
ejemplo, un botón único "✅ Confirmar todas (N)" cuyo `callback_data` referencie
un lote (hash/lista de IDs, respetando el límite de 64 bytes de Telegram) y que
en el Core se traduzca en N claims atómicos individuales (reutilizando
`claim_confirmation` por cada proposal_id, nunca un claim "todo o nada" que
oculte cuáles se autorizaron). Debe seguir cumpliendo consent-design: la
atribución de qué se confirmó debe quedar auditada id por id. Alternativa más
simple: agrupar el texto en un solo bloque y dejar los botones individuales,
pero con una capa de resumen que no repita "Pulsa ✅ Sí..." por cada item.
**Prioridad P2** — mejora de usabilidad, no bloquea el MVP (los flujos
funcionan, solo son incómodos con múltiples items a la vez).

### BL-46 · Niveles de riesgo dentro de WRITE para reducir confirmaciones redundantes ✅ completado — 2026-10-16 — specs/035

**Hallazgo (E2E Telegram, flujo TODO/BL-1):** al pedir explícitamente "Añade
leche y pan a la lista Compras" (lista ya existente, orden inequívoca), el
bot pide confirmación igualmente. Desde la perspectiva de uso cotidiano, esto
es redundante y poco práctico: el usuario ya expresó la intención completa y
sin ambigüedad; no se parece al comportamiento esperado de un asistente
personal (comparado, por ejemplo, con pedir confirmación para crear un
recordatorio con detalles de fecha/hora que sí conviene revisar antes de
guardarlos).

**Tensión con AGENTS.md §2.4 (no negociable tal como está hoy):** "Toda
operación WRITE/EXTERNAL_ACTION/DESTRUCTIVE requiere gobernanza" sin
distinción de riesgo dentro de WRITE, salvo la única excepción aprobada hasta
ahora (`analyze_document`, T4.7 — "enviar un adjunto ya es la señal de
intención"). Este hallazgo plantea si esa misma lógica ("el usuario ya dio
una orden explícita y sin ambigüedad sobre un recurso que ya existe") debería
extenderse a un subconjunto de mutaciones WRITE de bajo riesgo.

**Propuesta formal a decidir por el propietario (no implementada):**
introducir una subclasificación dentro de `WRITE` — por ejemplo
`WRITE_TRIVIAL` (reversible con un solo paso, sin ambigüedad de datos, target
ya identificado — ej. añadir un item con solo título a una lista existente,
marcar un item como completado) vs `WRITE_REVIEWABLE` (implica datos que
conviene que el usuario revise antes de persistir — ej. fecha/hora de un
recordatorio, importe de un mantenimiento, matrícula de un vehículo). Solo
`WRITE_REVIEWABLE` seguiría exigiendo `propose_*`/`execute_*` con
confirmación explícita; `WRITE_TRIVIAL` podría ejecutar directo (igual que la
excepción ya aprobada de `analyze_document`) manteniendo auditoría pero sin
bloquear en espera de un "Sí". Alternativas a valorar en el spec si se
aprueba: mantener siempre un `execute_*` auditado aunque sin "pending"
intermedio, o un undo rápido ("deshacer") en vez de confirmación previa para
ese subconjunto. **Toca una regla no negociable de AGENTS.md §2.4 — requiere
decisión explícita del propietario antes de cualquier cambio de código**,
igual que T4.7.

**Decisión del propietario (2026-10-13):** aprobada la opción
`WRITE_TRIVIAL`/`WRITE_REVIEWABLE` ("ejecuta directo con auditoría", no el
undo ni el "siempre execute_* sin pending"). Alcance de esta primera
iteración: toda nota (`propose_note` — `Note` no tiene ningún campo
estructurado de riesgo) y, en TODO items, solo añadir con título (sin
`description`/`priority`/`due_date`) y completar/reabrir sobre una lista ya
existente. Mover/eliminar item y crear/renombrar/borrar lista quedan
`WRITE_REVIEWABLE` sin cambios. Nombres de tool sin cambios (`propose_note`,
`propose_todo_item*`) — solo cambian docstrings y el texto de respuesta.

**Implementado localmente (2026-10-13, specs/035):** nueva columna
`action_proposals.consent_mode` (migración `0014_write_trivial_consent_mode`)
y `ActionProposalsRepository.create_self_authorized()` (disciplina de la
Consent API: nunca comitea) insertan la auditoría de una mutación trivial ya
en estado terminal `executed`, con `confirming_interaction_id=NULL` (el
índice único de esa columna es parcial sobre `NOT NULL`, así que nunca
colisiona). Nuevo `TrivialExecutor`
(`src/domain/actions/trivial_executor.py`) reutiliza `apply_mutation()` tal
cual existe — mutación y auditoría comitean en una sola transacción, sin
crear nunca un `ActionProposal` `pending_confirmation`. `propose_todo_item`
ramifica según si vienen informados los campos opcionales;
`propose_todo_item_complete`/`reopen` y `propose_note` ejecutan siempre
directo. `AGENTS.md` §2.4 y `docs/governance.md` documentan la
subclasificación. Revalidación 2026-10-15: suite global **159 integration
passed, 1 STT live skipped**; `test_actions_repo.py` **9 passed** (incluye los
dos casos `create_self_authorized`) y migraciones **4 passed**. Ruff y
`mypy src/` limpios. Pendiente: validación E2E Telegram.

**E2E asistido autorizado (2026-10-16, specs/036 paso 10):** alta título-solo,
completar/reabrir y guardar/buscar nota superados con revisión 8/r4, sin botones
ni preguntas de confirmación. Cuatro auditorías `self_authorized`/`executed`
correlacionadas, hashes válidos y ninguna duplicación observada; póliza AC3
intacta. Se conservan tarea y nota sintéticas, cero propuestas confirmables.
Regresión reviewable con prioridad y prioridad+fecha acreditada en pasos 2/8/9;
variantes E2E description/fecha-sola y revisión de cierre/versiones pendientes en specs/035.
Sin cambios de código, despliegue ni configuración; BL-46 no se cierra aún.

**Revisión local posterior (2026-10-16):** regresiones independientes de descripción,
prioridad y fecha-sola, sin vía trivial ni mutación previa. **1433 unitarias, 80 %
cobertura; 173 integraciones, 1 STT live omitida**; Ruff/mypy, catálogo estático y
build/validate Collector verdes. Solo tests/documentación, sin campaña Telegram,
commit ni cambios productivos. No sustituye las dos variantes E2E pendientes.

**Cierre funcional posterior (2026-10-16):** descripción-sola y fecha-sola
superadas por Telegram con autorización, runtime 8/r4. Propuestas `195dce39…` y
`d6c4052f…`, hashes 2/2 válidos, sin tareas antes del consentimiento; No individual
en cada una, ambas descartadas, callbacks sin LLM. Consulta final: solo las dos
tareas anteriores, nota intacta, cero propuestas confirmables ni nuevas auditorías
ejecutadas. SHA sirviendo `5f0132f…`, deployment `838ab705…`, CI del mismo SHA
quality/integration/collector-config success comprobado. **BL-46 completado**;
no se despliega ni modifica configuración. Evidencia specs/035 final y specs/036 §13.

### BL-47 · El Agent narra el estado de propuestas pendientes desde memoria conversacional, sin fuente de verdad ✅ implementado localmente — 2026-10-13

**Hallazgo (E2E Telegram, flujo TODO/BL-1):** tras confirmar una propuesta ya
ejecutada (`a93acfbf`, "Leche completada") y dejar caducar otra (`bbe31cd8`,
"Gel de ducha", >15 min sin confirmar), al intentar confirmar una propuesta
expirada el bot respondió correctamente "Esa propuesta ya caducó" (el Core
rechazó bien — sin fallo de seguridad), pero en el mismo mensaje añadió "Y
siguen pendientes de confirmar: Leche completada (a93acfbf) y Gel de ducha
(bbe31cd8)" — **ambas afirmaciones son falsas**: la primera ya estaba
`executed` desde varios turnos antes, la segunda ya estaba expirada.

**Causa probable:** no existe ninguna tool de lectura `list_pending_proposals`
(o equivalente) que el Agent pueda invocar para consultar el estado real de
`action_proposals` del chat/usuario — el inventario de tools confirma que
las únicas operaciones sobre propuestas son los `execute_*` por tool de
dominio (`src/agent/tools/*.py`, grep de `proposal_id`), ninguna de lectura
agregada. El modelo reconstruye "qué está pendiente" únicamente desde su
propio historial conversacional, que puede quedar desincronizado del estado
real en Postgres (confirmaciones/expiraciones ya ocurridas no se reflejan en
lo que el modelo "recuerda" haber dicho antes).

**Impacto:** no es un fallo de autorización (`ProposalExecutor`/
`claim_confirmation` siguen siendo la única fuente que importa para
ejecutar), pero sí de confianza/UX — el usuario recibe información
incorrecta sobre qué sigue abierto, lo que puede llevar a reintentos
innecesarios o confusión sobre si algo se guardó o no.

**Propuesta a evaluar:** nueva tool de lectura (`list_pending_proposals` o
similar, READ, envuelta en `untrusted_results` igual que el resto de tools de
lectura) que consulte `ActionProposalsRepository` por `user_id`/chat y
devuelva las propuestas realmente en `pending_confirmation` (no caducadas),
para que el modelo la invoque en vez de narrar desde memoria cuando el
usuario pregunta "qué tengo pendiente" o tras un intento de confirmación
fallido. **Prioridad P1** — afecta la fiabilidad percibida de un patrón
(`propose_*`/`execute_*`) que es central en toda la gobernanza WRITE del MVP.

**Implementado localmente (2026-10-13):** nuevo
`ActionProposalsRepository.list_pending(user_id)` (mismo criterio que
`list_confirmable` — `pending_confirmation`, presentada, no caducada, reloj
de la BD — pero devuelve registros completos en vez de solo IDs, y sin
`bot_id`/`chat_id` porque `UserContext` no los expone a las tools). Nueva
tool `list_pending_proposals` (`src/agent/tools/proposals.py`), READ,
envuelta en `untrusted_results` igual que el resto de tools de lectura;
registrada en `_init_domain_tools()`. `prompts/tool_contract.md` instruye
explícitamente al Agent a llamarla en vez de narrar desde memoria, tanto
cuando el usuario pregunta "qué tengo pendiente" como tras un intento de
confirmación fallido. Revalidación 2026-10-15: los dos tests PostgreSQL de
`list_pending` están incluidos en `test_actions_repo.py` (**9 passed**) y la
suite global queda en **159 passed, 1 STT live skipped**. Ruff y `mypy src/`
limpios. Pendiente: validación E2E Telegram (reproducir el caso real del
hallazgo: confirmar una propuesta, dejar caducar otra, y comprobar que la
respuesta ya no narra ninguna de las dos como pendiente).

### BL-48 · Presentación única de propuestas y respuestas acotadas tras descarte 🔶 desplegado, E2E parcial — 2026-10-14 — specs/036

**Hallazgo (E2E Telegram comunicado por el propietario):** al proponer la
tarea «Renovar el seguro» con prioridad alta y vencimiento el 20 de octubre
de 2026, el Agent enumera los campos y pide confirmación; a continuación el
Core añade otro resumen con esos mismos campos, la petición Sí/No y los
botones. El segundo bloque muestra `high` y `2026-10-20T00:00:00`, formatos
internos innecesarios para este caso. La duplicación está confirmada en la
composición actual: `_append_proposal_blocks` concatena la respuesta del
modelo con `render_proposal_block` generado desde el payload guardado.

**El descarte funciona:** pulsar No devuelve «Propuesta descartada» y la
consulta posterior solo muestra «Comprar café» completada. Sin embargo,
esa respuesta añade el estado de propuestas pendientes y ofrece volver a
proponer la tarea rechazada sin que se haya pedido. No hay evidencia de la
tool consultada en ese turno: no se afirma que BL-47 haya fallado.

**Cambio a implementar:** una sola presentación autoritativa por propuesta,
propiedad del Core, con prioridad/fecha legibles; el Agent no duplica los
campos ni el pedido de confirmación. Las consultas de tareas se limitan a
las tareas solicitadas, sin ofertas automáticas de reproponer lo rechazado
ni afirmaciones de pendientes desde memoria. Mantener respuestas útiles
en mensajes mixtos y el circuito determinista de consentimiento, TTL,
presentación verificada, auditoría y aislamiento por usuario.

**Registro de documentación previa (2026-10-14):** autorización inicial
limitada a documentar, antes de implementar.
`specs/036-telegram-proposal-presentation/spec.md` fija alcance y criterios;
`tasks.md` deja toda implementación pendiente; `verification.md` separa la
evidencia funcional previa de la validación futura de esta mejora. Sin
código, cambios de prompts, migraciones, despliegue ni nueva policy de
consentimiento. Relacionado con BL-46/specs/035, BL-47 y BL-39/40/specs/023;
no incluye confirmación por lotes (BL-45).

**Implementación local posterior autorizada (2026-10-14):** contrato Pydantic
`AgentReply(answer, proposal_text)` en la factory/runner gobernados (JSON mode,
sin parser/modelo extra). El Core sustituye solo la narración de propuestas
si existen filas de esa interacción/usuario; mantiene respuestas READ,
errores y advertencias relevantes, sin regex de prosa ni descarte total.
Renderer con prioridades españolas/fecha TODO legible conservando offsets
y horas. Prompts alineados; cinco evals sintéticos nuevos (32 casos totales).
Prueba con Agno real y modelo simulado confirma parsing y una sola llamada,
no obediencia semántica. Ruff/mypy y suite unitaria global verdes. En esa
sesión Docker no estaba disponible; la revalidación del 2026-10-15 ejecutó la
integración PostgreSQL: **159 passed, 1 STT live skipped**, más **4 pruebas de
migración**. **32 casos de catálogo válidos** (sin scoring semántico real).
Sin fixtures productivos. Pendientes evaluación LLM real y E2E del SHA
autorizado; no se cierra BL-48.

**Corrección de regresión local (2026-10-15):** rechazar los dos campos vacíos
no restauró la selección de herramientas: las pruebas manuales posteriores
mostraron preámbulos finales y propuestas narradas sin controles. Se retira JSON
mode/output_schema del Agent principal y del harness físico; `present_reply`
con `tool_choice=required` conserva la partición como herramienta terminal sin
I/O canónico, parser ni otro modelo. El Core descarta narración sin propuestas
persistidas. Pruebas SDK con HTTP simulado cubren el protocolo, no obediencia
semántica real. Sin despliegue; validación de Gateway/Telegram sigue pendiente.

**E2E asistido autorizado (2026-10-16, specs/036 pasos 8/9):** baseline rev. 8 /
`ancoramind-default-r4`. Dos bloques Core, «Sí» ambiguo sin ejecución, confirmar
solo póliza y descartar solo recibo mediante sus botones: IDs y efectos
verificados en PostgreSQL. Consentimiento sin llamadas LLM; queda una tarea
sintética autorizada y cero propuestas confirmables. AC3 superado en esta
ejecución delegada; no equivale a pulsación personal ni prueba de concurrencia.
AC5 positivo/detallado/vacío coherente, pero no se deducen tools de contadores.
AC7 y resto de matriz pendientes; sin código, despliegue ni cambios de configuración.

**AC7 asistido posterior (2026-10-16, paso 10):** autorización exclusiva para
crear/completar/reabrir «Validar reapertura AC7», consultar y guardar/buscar nota
sintética. Camino trivial superado con cuatro auditorías terminales, hashes
válidos, sin botones ni propuestas revisables. Cierre de esta fase: dos tareas
pendientes de campaña (póliza y reapertura), una nota sintética y cero propuestas
confirmables. AC5/trazabilidad, AC8–AC9 y cierre global siguen abiertos.

**Revisión posterior de AC5/AC8–AC9 (2026-10-16, specs/036 §§11–12):** recuperadas
las cuatro trazas Tempo de los pasos 5/6/7/9; cada una muestra
`list_pending_proposals` → `present_reply`, con run/correlación/revisión 8
coincidentes con el ledger. Junto con respuestas y estados canónicos previos,
**AC5 queda superado**, sin inferir tools de contadores ni repetir mensajes.
AC8–AC9 superados en aislamiento (temporalidad/escapado/hash, OFF, entrega fallida,
no replay); gates locales verdes: 1433 unitarias, 173 integraciones, 1 STT live
omitida. Pendientes evaluación real de instrucciones y cierre/versiones;
**BL-48 sigue abierto**. No hay despliegue, cambio de controles ni nueva campaña.

**Continuación autorizada (2026-10-16, specs/036 §§13–14):** variantes BL-46
completadas y evidencia de tools nominadas ampliada. El propietario exige
**harness real aislado**, no acepta sustituir ese gate por revisión manual E2E.
Preparados snapshot exportado secret-free, plan de cinco casos default/r4 rev. 8,
reserva candidata 0,02 USD estimados/caso (0,10 total), límites no ampliables,
LLMAccess Gateway-only, recorder sin DB y preflight sin inferencia. 1465 unitarias,
173 integraciones, 1 STT live omitida; Ruff/mypy verdes. Sin credenciales nuevas,
aprobación de gasto ni acceso de red creado: **BL-48 continúa abierto** hasta
aprobación concreta/acceso privado/ejecución y evaluación; semántica not_evaluated.

**Hallazgo de trazabilidad para BL-23/specs/013:** el checksum histórico rev. 8
no se reprodujo en la investigación inicial; la serialización de capacidades
frozenset varía entre procesos. **Actualización 2026-10-17:** una de las 72
combinaciones de orden sobre la representación canónica del snapshot local
reproduce exactamente `e2663c6a…db25` con igual configuración tipada. El orden
explica la discrepancia local; no se ha contrastado vigencia con producción ni
identificado el proceso histórico. Remediación compatible pendiente, sin alterar
revisiones ni aliases activos. Eval mantiene su fingerprint separado; detalle y
límites en specs/018 `t7-preparation.md`.

**Lanzador T7 completado localmente (2026-10-17):** `execute_eval_campaign.py`
es preflight puro por defecto; ejecución explícita exige commit limpio, SHA y
huellas de plan/fuentes/casos aprobados, reserva estimada completa, clave privada
restringida y revisor humano en terminal. Marca local exclusiva retenida ante
fallo, serie sin retries SDK/Agent, stop ante fallo/check/no evaluado y reporte
metadata-only. Respuestas particionadas solo en memoria/consola humana, sin logs
de bibliotecas. **1503 unitarias, cobertura 80,42 %; 173 integraciones y 1 STT live
omitida**, Ruff/mypy limpios. No se llama al Gateway ni se genera credencial/acceso,
ni commit/push/deploy; reserva candidata 0,10 USD estimados aún pendiente de
aprobación y protección externa. BL-48 abierto hasta ejecución/revisión reales.
Runbook actualizado specs/018 `t7-preparation.md`; el bloqueo de replay es local,
no distribuido ni garantía de facturación máxima.

**Decisión incremental del propietario (2026-10-17):** primero conservar motor
compartido y preparar uso puntual por shell en servicio temporal privado Railway,
separado del bot; después campaña humana existente de cinco casos. Sin túneles,
ngrok ni inferencia al arrancar/reiniciar. Reserva estimada 0,10 USD aceptada,
propietario como revisor; no autoriza recursos, claves, despliegue o ejecución.
Preparación de imagen/TTY/estado anti-replay, procedencia del snapshot y aprobación
concreta SHA/plan/huellas pendientes. Web opcional, golden set humano, Jev calibrado,
segunda opinión y automatización quedan diferidos, sin bloquear T7. Registro
completo: specs/018 `incremental-roadmap.md`. **BL-48 sigue abierto**.

**Incrementos 1–2 solicitados posteriormente:** preparación local del servicio
temporal implementada: `evals/Dockerfile`/config propia, arranque idle sin red ni
Agent, fuentes selladas sin copiar Git/secretos y huella contrastable externamente,
mount obligatorio para estado, revisor p/f/x con repregunta y prueba TTY sin modelo.
No cambia bot/Gateway/prompts ni cinco casos. Runbook specs/018
`railway-console-runbook.md`. Incremento 2 pendiente de CI/SHA y aprobación
concreta, recursos/clave exclusiva/acceso y etiquetas del propietario. Sin
despliegue ni inferencia; Jev sigue en propuesta existente, no duplicada.
Verificación: **1647 unitarias (80,58 % cobertura), 207 integraciones y 1 STT
live omitida**, Ruff/mypy limpios. Docker sin red: preflight, arranque idle,
SIGTERM, PTY real y protección de reserva entre contenedores con mismo volumen
superados. Imagen de desarrollo, no SHA aprobado; evidencia/límites en el runbook.

**Aprovisionamiento inicial autorizado (2026-10-17):** propietario acepta coste
Railway. CI `db0c59b` verde; creados `ancoramind-evals` y volumen exclusivo 100 MB
en `/eval-state`, sin dominio/secretos/clave Gateway. Config directo porque API
rechaza nuevo Config as Code; no se migra el bot. **Bloqueado:** build selecciona
Dockerfile raíz pese a path evals en metadata; variable documentada y ruta absoluta
no lo corrigen. Último deployment `a308909d-760b-436e-80c6-3ee58cc5365f` CRASHED,
`eval_service_blocked`/sin inferencia, restart NEVER. Servicio existe pero no listo;
no seguir relanzando sin causa demostrada. Bot/Gateway intactos, sin staged changes
al control. Evidencia specs/018 `railway-provisioning.md`; T7 y BL-48 abiertos.

**Recuperación del evaluador (2026-10-17):** ruta GitHub sigue sin respetarse;
no era JSON legacy activo. Build directo y V2 reprodujeron fallo. Contexto privado
explícito, mismos fuentes/huella de db0c59b CI-verde y Dockerfile eval en raíz,
desplegado `54892e8d-84be-422a-b5a4-e4a2f4dfc7b9`: COPY evals + sello completados,
idle_manual_only/sin inferencia, **1 running/0 crashed**. Subida autenticada, no
GitHub deploy ni registry público; sin CLI/túneles/keys, bot/Gateway intactos.
Utilidad local reproducible `scripts/prepare_eval_build.py` sin upload; no está en
imagen db0c59b. Servicio queda encendido idle; no reconstruir por GitHub a ciegas.
Mount/preflight/TTY remotos confirmados después por propietario: mount válido y
escribible, preflight_valid con SHA db0c59b/huella/plan esperados y console_ready,
sin inferencia ni aprobación concedida. Pendientes clave exclusiva/expirable,
scope/presupuesto externo, Gateway not_checked y aprobación/campaña humana;
T7c-remoto/T7b/BL-48 abiertos y semántica not_evaluated. Evidencia y hashes
diferenciados de paquete manual/utilidad en specs/018.
Autorizada después clave temporal/acceso sin inferencia: preparación local de
helpers de operador y runbook Gateway; **no clave creada ni acceso comprobado**
por el agente (sin shell remota disponible). Requiere ejecutar en shells existentes,
sin extraer master ni clave bot, sólo clave nueva r4/lectura/2 h/0,10 USD sin reset.
Sin flags de campaña/deploy; pricing y presupuesto externo live aún pendientes.
Preparación de acceso: 21 pruebas específicas, suite global **1681 unitarias,
80,58 % cobertura**, Ruff/mypy limpios; helpers sin TTY/red fallan cerrados.
Reporte posterior del propietario: clave creada/verificada en Gateway, alias
`ancoramind-evals-access-1eacd663da85`, caduca 2026-10-18T01:37:40.773Z; sólo r4 y
lectura, 0,10 USD nominal sin reset/gasto cero, sin inferencia. Acceso desde evals,
pricing y campaña pendientes. No gestor de secretos configurado ni clave en docs;
transferencia temporal a prompt oculto, sin persistencia/redeploy ni regeneración.
Intento real desde evals: eval_gateway_check_blocked/sin inferencia, causa sin
confirmar (helper original genérico). Diagnóstico local por etapa/clase fija/HTTP
status/URL-presente preparado y probado, sin secretos ni ampliar permisos; sólo
repetición GET manual con clave vigente, pendiente reporte operador. Servicios
Online sin cambios; no regeneración ni campaña.
Diagnóstico validado: 34 pruebas focales, **1694 unitarias/80,58 %**, Ruff/mypy
limpios; imagen db0c59b sin TTY/red informa etapa sin traceback. Sin commit/push.
Clave temporal perdida posteriormente; propietario aporta eval_key_absent_verified
del alias antiguo tras retirada dirigida. Sustitución única sólo lectura con mismos
límites prevista, nueva clave/reporte pendientes; no acceso/campaña verificados.
Recibido después reporte sustituta `ancoramind-evals-access-238d37ae3e0e`,
read-only r4/mismos límites, caduca 2026-10-18T02:08:48.318Z; sin inferencia.
Pendiente acceso/diagnóstico desde evals, pricing y aprobación de campaña.
Reporte posterior: **eval_gateway_read_only_verified/restricted_alias_verified**
desde evals, sustituta238d37ae3e0e/SHA db0c59b/huella/plan correctos, presupuesto
nominal 0,10 USD sin reset/gasto cero. Acceso privado y scope comprobados;
inferencia deshabilitada/no iniciada, pricing y aceptación snapshot/presupuesto
y aprobación/campaña pendientes. T7c/T7b/BL-48 abiertos; no se atribuye causa exacta
al primer bloqueo ni se habilitan rutas/deploys por recibir este reporte.
Reporte precio: Gateway r4 physical openrouter/gpt-6-luna con metadata0/0; catálogo
oficial OpenRouter consultado 2026-10-18 base openai/gpt-6-luna0,10/0,50 USD/M,
coincide snapshot pero con variantes endpoint/contexto. No gratuito ni spend roto
demostrados: LiteLLM soporta coste upstream. Enforcement externo aún no validado;
próximo GET presupuesto proveedor, sin mutar claves/bot/r4 ni habilitar inferencia.
Reporte posterior upstream: límite5 USD/restante4,44046623 USD/sin reset y BYOK no
incluido, sin inferencia. Control compartido, no límite exclusivo0,10 ni permiso
para consumir saldo. Difiere de snapshot histórico rev8 external_limit20; inmutable,
requiere aceptación de esa diferencia. Contabilidad efectiva/riesgo/campaña aún
pendientes; no flags/rutas ni cambios de clave upstream del bot por el reporte.
Investigación offline autorizada: 10 pruebas en imagen LiteLLM fijada, sin red/
credenciales/inferencia, coste0.03→callback/cola KEY/contador/budget funciona;
umbral acumulado no garantiza techo0.10, coste ausente/lecturas no verificables
requieren atención. No spend productivo certificado ni fallo deducido de metadata0.
Probe local reproducible y `accounting-offline-review.md`; sin cambio remoto ni
permisos/claves, T7c/T7b/BL-48 abiertos, falta decisión/evidencia runtime de gasto.
Validación de investigación: 10 pruebas Docker offline separadas y 7 unitarias nuevas;
suite global **1701 passed/80,58 %**, Ruff/mypy limpios, sin integración DB nueva.
Revisión adicional autorizada de evidencia existente cerrada (2026-10-18):
Gateway/evals sanos sin cambios; filtros logs metadata coste/tracking sin filas,
control logs peticiones visible/truncado, sin contenido ni secretos. No certifica
spend real ni flags efectivos. Recomendación concreta: un smoke sintético pagado
único por LLMAccess/Gateway, max64 salida/30s/sin retry, nominal0,01 USD y lectura
spend propio antes/después; requiere aprobación específica, aún no ejecutado.
Si contabiliza cierra investigación; si ambiguo/falla se para sin repetir, no
otra ronda abierta. No modificar r4/clave proveedor/bot/candidato para ello.
Autorización explícita recibida: UNA prueba pagada nominal0,01 USD/max64/30s/1POST,
sin tools/retry/fallback/replay, por LLMAccess; campaña sigue sin aprobar. Clave
eval anterior caducada (control05:56Z); preparar sustituta dedicada sólo al estar
operador listo. Helper dos roles admin/smoke, TTY secreto y cleanup Enter/revocación;
marca persistente separada de campaña, reporte sin contenido. 13 pruebas nuevas,
**1714 unitarias/80,58 %**, Ruff/mypy limpios; imagen sellada offline mock1POST y
replay bloqueado. Ninguna inferencia/clave real/deploy ejecutados por agente;
pendiente operación humana y JSON smoke+revocación. Runbook accounting-smoke.
**Smoke real aportado después:** 1POST/1call, gasto0→0,0000353 USD=header Gateway,
smoke_accounting_verified; clave87a125a812bd revocada/ausente confirmada por operador.
Investigación contable cerrada acotadamente, sin más rondas/smokes. No garantía
absoluta de factura ni campaña aprobada; siguiente decisión cinco casos por plan
existente y revisión humana. No borrar reserva ni reutilizar la clave revocada.
**Campaña autorizada después expresamente:** UNA ejecución cinco casos exactos
SHA db0c59b/fuente108c410d…/plan8f3e4a51…/snapshot rev8 histórico, nominal0,10 USD
adicional y riesgo residual/límite upstream5vs20 aceptados, revisor humano presente.
Clave campaña exclusiva r4/2h/0,10 nominal, revocación final; bot/DB/upstream/r4
intactos. Wrapper local reutiliza harness sellado sin cambiar candidato ni plan,
7 tests nuevos/1721 unitarias/80,58 % y Ruff/mypy limpios; cinco casos simulados
offline en imagen sellada/replay bloqueado. Procedimiento campaign-approved listo,
falta ejecución humana/reporte+cleanup real: T7b/BL-48 abiertos, sin nueva inferencia.
**Incidencia posterior reportada por propietario:** primer caso ejecutado llegó a
review pero evidencia insuficiente (no payload/Core) y Unicode difícil de leer;
desconexión por inactividad impidió etiquetar y confirmar revocación. No declarar
pass/fail ni cleanup por inferencia. No relanzar/borrar reserva/recuperar texto no
persistido. Propietario acepta incremento usabilidad+guardado de revisiones como
candidatos golden y trazabilidad. **specs/040 implementada localmente:** comando
único `eval_console.py run`, worker desacoplado/review reabrible sin modelo,
evidencia sintética cifrada en volumen y autosave por criterio/historial, TODOs con
payload real simulado/renderer Core/validación reviewable, Unicode seguro legible,
promoción manual a Agent/juez con provenance y separación development/validation.
No web/auto-juez ni claves creadas: setup reutilizable7d propuesta/presupuesto por
acordar y aprobación exacta de nuevo SHA siguen remotos pendientes. Retención bruta
7d/purga manual conserva markers; golden curado sólo decisión explícita. 1753
unitarias/1 skip (symlink Windows; Linux validado),80,85 %;207 integration/1 STT skip,
Ruff/mypy177fuentes limpios; Docker offline hijo/revisión reconectada superado.
Sin nuevas inferencias/deploy/commit/push; T7b/BL-48 reales abiertos, no más smokes.
**Actualización candidato sin CLI local (specs/041):** propietario restringe equipo
gestionado: no instalar/ejecutar Railway CLI local. Implementado botón GitHub
**Actualizar evaluador** manual/main/SHAcompleto/confirm_idle/CI exacta; runner
GitHub instala CLI fijada, empaqueta con helper existente y publica sólo evaluador,
verifica SUCCESS/running/idle SHA/huella y volumen/otros deployments. No evaluación
ni permisos/gasto modelo. Token initial proyecto/entorno en environment secret
GitHub; alcance no exclusivo de servicio, riesgo/documentación explícitos.
Setup secreto hecho por propietario; SHA da351546/CI verde, run39157815349 prepara
pero bloquea antes de mutaciones. Error confirmado: schema staged NON_NULL, no
significa cambios reales. Enmienda autorizada: patch sólo en memoria, permitir
STAGED/`{}` exacto + única fila pendingWork del mismo id/entorno sin hijos; bloquear
contenido/inconsistencias/en curso, no imprimir/persistir ni aplicar/descartar.
SHA b0b6beb9/run39160757789 pasa staged pero bloquea réplica legacy=null; API/
manifiesto demuestra una región/réplica, RUNNING y volumen correcto. Fix local
contrasta réplica explícita del manifiesto con CLI5.70.0, sin default null→1;
reasons específicos y check_only opcional sólo lectura. Fixture API saneada/
adaptador integral y arranque offline del paquete b0b6 (deps cacheadas, no build
fresh) superados. **Primer rollout cerrado2026-10-18:** SHA
7ea0cf06002d76692f230d189c43e8f9f5e742b1/CI39163986626 verde;
check_only39164426466 y publicación39165134464 success/deployed_idle_verified.
Deploymentb4305cc0-3ddd-404e-8dbc-a3b002103b1f Online/SUCCESS,1RUNNING/0crashed,
sin pendingWork; volumen/otros servicios conservados según workflow. No campaña
ni recuperación histórica/revisión real certificadas. Después, propietario reporta
clave eval r4 nominal0,10USD/7d creada sin inferencia; cuatro variables confirmadas
con Alt+Deploy (sin reinicio/valores consultados). Run39171845184 bloquea antes de
up: API devuelve sentinel `<empty>`/STAGED/entorno/patch`{}` y pendingWork`[]`,
no UUID+fila. Fix local sólo acepta ambas combinaciones exactas, sin omitir guard
ni crear borradores; fixture saneada, regresión roja antes del fix y158 focales.
1898 unitarias/1 skip,80,85 %,Ruff global/mypy177/diff limpios; warning conocido
Collector local no disponible, sin fallos. Falta commit/push/CI del helper y nuevo
Run workflow desde main (no Re-run); puede conservarse candidato7ea0cf06/huella.
No tocar claves otra vez ni añadir staged; aplicación al nuevo contenedor y
approval.json/campaña siguen pendientes. Histórico de validación primer rollout:
1867 unitarias/1 skip,127 focales,80,85 %,Ruff/mypy177 limpios.
Sin CLI local/inferencia/deploy por agente. Evals efectivo7ea0cf06; mantener
pin GitHub histórico sin connect/rebuild; versión upload por sello/log. Detalle
`specs/041-manual-eval-deploy/runbook.md`; no borrar reservas ni relanzar campaña.
**Actualización posterior real:** helper1c700339/Run39173039736 success,
deployed_idle_verified del candidato7ea0cf06/deployment085cb777-6e58-489b-93ef-c4596d68e0c7;
variables aplicadas/sin pendingWork/volumen conservado. Propietario autorizó UNA
campaña5casos/nominal0,10USD/humano/cifrado7d y ejecutó run52759a15ad454050aef8b5c1a9b3f122:
caso1passed técnico+2pass/3calls/estimado0,003563USD/actual desconocido;
caso2stopped InvalidPresentationOutputError tras2calls/sin observación;3not_started.
No tecla p, no fallo setup acreditado; guard terminal impidió observación y no hay
causa fina recuperable. Incremento local diagnóstico allowlist/counters/estado +
status por caso, sin texto rechazado/args/proveedor ni cambio guard/prompt/retries.
Caso mixto guionizado offline válido, pruebas cifrado/noleaks/replay;158focales/1skip.
1925unitarias/1skip,80,98 %,14integraciones focales PostgreSQL local;
Ruff/mypy178/catálogos/diff limpios. No toda integración repetida.
BL-48/T7 no superados; nueva fuente requiere aprobación independiente, no repetir
ni borrar reserva/labels históricos. No commit/push/deploy/inferencia por agente.
**Enmienda operativa specs/042 local autorizada:** límite0,10USD acumulados de sesión,
incluye histórico; no consentimiento repetido por cada SHA operativo. Ledger Fernet
persistente/binding misma key/scope estable, reservas por caso, import conservador
coste desconocido, checks pre/postGateway y bloqueo antes de transporte; claim
source/lease exclusivo/manualidad/replay incierto intactos. Base3f2e8b89 CIverde sólo
diagnóstico; falta publicar incremento sesión. No más claves/configuración; nueva
decisión sólo fuera scope o sin saldo. No factura exacta, ni sumar pasados como
evaluación completa del candidato nuevo. Detalle specs/042; gates por registrar.
Validado1969unitarias/1skip,81,22 %,44pruebas sesión, Ruff/mypy180/catálogos/diff;
paquete sellado/help local sin commit ni inferencia.14integraciones focales
bloqueadas en setup: Docker daemon/PG local ausentes, no usar productiva. Pendiente
SHA/CI/publicación; import separa db0c59b/claves2h previas de7ea0cf06, sin borrar
históricos ni gastar como si empezase desde cero.
**Publicación y bloqueo posterior2026-10-19:**32474d5b/CI39237715770,
workflow39239239445/deploymente30e1e80 idle verificado; propietario ejecuta init
y reporta session_prior_execution_not_terminal sin inferencia. Repro local prueba
orden erróneo: estado terminal exigido antes de excluir candidato db0c59b antiguo.
Fix mínimo local prioriza exclusión conocida, sin relajar bloqueo de actual/
desconocido ni tocar reportes/markers/budget.80focales,1991unitarias/1skip,81,22 %,
Ruff/mypy180/diff limpios. Metadata posterior del propietario confirma histórico
db0c59b/running junto a actual/otro stopped; bug de orden acreditado, no evidencia
de worker activo.21focales recheck pasan; publicación/aceptación remota fix pendientes,
sin borrar reportes/editar estado ni reset saldo. Sin commit/push/deploy/inferencia por agente.
Fix import subido68ae6654/CI39246649825 verde; publicación39248955747 bloqueada
legítimamente por pendingWork botfce3f7ac/collector5de0748a NEEDS_APPROVAL (mismo
push11:43Z). No staged config, sí deployments ajenos; guard no se modifica.
Skip por propietario de los dos intentos no deseados conserva activos; no Remove
SUCCESS ni Deploy ciego. Verificar entorno vacío antes de nuevo workflow mismoSHA.
42regresiones pending pasan, sin mutaciones remotas ni inferencia; fix aún no live.
Validación continuación: **1660 unitarias, 80,58 % cobertura**, Ruff/mypy limpios,
catálogo estático válido; paquete reproducible build/preflight local sin red
superado. No nuevas integraciones PostgreSQL (últimas 207/1 skip); sin commit/push.

### BL-18 · Hardening del despliegue Railway (CI/branch protection) 🔶 bloqueado por decisión diferida del propietario — specs/008
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

**Verificación real (2026-10-10):**
- ✅ **Wait for CI activado**: `railway__get-service-config` confirma
  `source.checkSuites: true` en el servicio. Las últimas 10 ejecuciones de CI
  en `main` (`gh run list --repo lealp22/ancoramind-app`) están en verde.
- 🔶 **Protección de rama `main`: bloqueada por plan, no por omisión.** El repo
  es privado en el plan gratuito de GitHub — `gh api .../branches/main/protection`
  → 404 y `.../rulesets` → 403 "Upgrade to GitHub Pro or make this repository
  public". Pendiente de decisión del propietario (upgrade o hacer público).
- 🔴 **Incidente encontrado y resuelto en el momento de esta verificación:**
  el servicio `ancoramind-app` estaba `CRASHED` en producción desde
  2026-10-07T19:52Z (commit `70ba659`). Causa:
  `relation "ancora.voice_preparations" does not exist` —
  `ancora.alembic_version` seguía en `0010_pairing_auto_approve` mientras el
  código ya requería `0011_voice_preparation`/`0012_document_content_hash`
  (nunca aplicadas a producción). Aplicadas ambas migraciones directamente
  contra Supabase (`asnsqdbsogpxqpweyxui`) y redeploy disparado
  (`ec46433e`): servicio `SUCCESS`/`Online`, `/health` → `200 ok`,
  `/health/readiness` → `status: ok` (`database: healthy`,
  `interaction_processor`/`reminder_worker`/`runtime_config`: `healthy`).
  Cinco intentos de deploy previos ese mismo día (16:48–19:52) habían fallado
  por la misma causa.
- 🔶 **Gateway degradado (hallazgo aparte, no corregido aquí):**
  `/health/readiness` reporta `gateway: degraded` — los servicios `LiteLLM`,
  `litellm-postgres`, `Postgres` (Railway) y `Redis` están `Offline` desde
  2026-10-05T23:06Z, parada deliberada previa al incidente anterior, sin
  relación con el crash de migraciones. Con `LITELLM_PROXY_ENABLED=true` toda
  inferencia real falla en modo fail-closed (comportamiento correcto, pero
  sin servicio) hasta que el propietario decida reactivar ese stack.
- ✅ **Gateway reactivado por el propietario (2026-10-09T22:57Z):** `LiteLLM`
  y `Postgres` (Railway) vueltos a `Online`/`SUCCESS`; LiteLLM relistó sus
  tres alias base (`ancoramind-default-r1`, `ancoramind-fast-r1`,
  `ancoramind-vision-r1`) sin TCP proxy/dominio público (sigue privado).
  `/health/readiness` confirma `gateway: healthy`, `database: healthy`.
  **`litellm-postgres` y `Redis` siguen `Offline`** — no bloquean el estado
  `healthy` observado, pero no se ha confirmado si el panel de
  administración de LiteLLM o algún rate-limiting opcional dependen de
  ellos; decisión del propietario si también los reactiva.

**Actualización 2026-10-18 (cierre de 2 de los 3 criterios pendientes):**
1. ✅ **E2E Telegram de M3–M5 satisfecho.** El 2026-10-17 los 4 flujos
   restantes (recordatorio, vehículo+mantenimiento, calendario/recurrencia/
   snooze, imagen/PDF escaneado) corrieron contra Telegram+Railway en
   producción y pasaron PASS — ver BL-1 más arriba y
   `specs/008-railway-deployment/mvp-release-campaign.md` (entregas 1-4).
   Este criterio queda cerrado; el ítem no se había actualizado para
   reflejarlo hasta ahora.
2. ✅ **`litellm-postgres`/`Redis`: decisión del propietario — no
   reactivar.** El Gateway lleva operando `healthy` sin ellos desde su
   reactivación del 2026-10-09; no son dependencia bloqueante de
   producción. Si en el futuro hiciera falta el panel de administración
   de LiteLLM o rate-limiting opcional que dependa de ellos, se reabre
   como entrada propia, no como parte de BL-18.
3. 🔶 **Protección de rama `main`: decisión explícitamente diferida.**
   El propietario decide no resolver ahora si hacer el repo público o
   contratar GitHub Pro; sigue bloqueado por esa elección pendiente, sin
   fecha. Este es el **único criterio que mantiene BL-18 abierto**.

**Pendiente para cerrar BL-18:** únicamente decidir y aplicar la
protección de rama `main` (upgrade de plan GitHub o hacer el repo
público). Los otros dos criterios históricos quedan resueltos (arriba).
**Nota (2026-09-09):** al desplegar se activará también el worker de
recordatorios (BL-5 / ADR-003 / specs/010): variables `REMINDER_WORKER_*`
opcionales (defaults válidos); su entrega es **outbound** y funciona desde el
primer deployment saludable, sin esperar al registro del webhook. Ver
`docs/deployment-railway.md` §8.
**Criterio de cierre:** protección de rama `main` aplicada (upgrade de plan
GitHub o repo público, decisión del propietario). Dominio HTTPS Railway
estable, CI/CD operativo y E2E Telegram ya cumplidos desde 2026-10-17/18.


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

### BL-33 · Health signals + Dashboard de salud 🔶 T1–T6 implementados localmente, solo T7 pendiente — specs/016

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

**Actualización (2026-10-09, sincronización de doc):** esta entrada seguía
descrita como "en curso" sin más detalle aunque `specs/016-health-dashboard/
tasks.md` ya tenía T1–T6 marcados hechos: `HealthRegistry` in-process,
`GET /health/readiness` metadata-only, health metrics por la fachada OTel,
`observability/dashboards/ancoramind-health.json` y
`observability/alerts/` versionados (con tests estructurales), y la
documentación de despliegue/runbook actualizada. Todo cubierto por la suite
unit actual (970 tests, Ruff y `mypy src/` limpios). **Solo queda T7**, que
es enteramente de infraestructura real y no se puede avanzar sin ella:
desplegar el Collector privado en Railway, crear los secretos
`GRAFANA_OTLP_ENDPOINT`/`GRAFANA_OTLP_AUTHORIZATION`, importar el dashboard y
las alertas a Grafana Cloud, normalizar los nombres de métricas contra las
series reales que Grafana termine persistiendo (no se puede asumir que
conserva los nombres del JSON local) y ejecutar la matriz de degradación
(Postgres/Gateway/worker caídos) en staging con evidencia. Procedimiento
completo en `specs/016-health-dashboard/verification.md` §"Procedimiento de
cierre T7".

---

## P2 — Funcionalidad para "usable de verdad"

### BL-6 · OCR/vision real para extracción de documentos 🔶 E2E sintético parcial — 2026-10-17

**Actualización vigente:** la ruta ya activa `ancoramind-vision-r1` funcionó
en Telegram para PNG y PDF raster de una página: originales/extracciones
verificados y consulta posterior sin nuevo OCR. PDF PASS; imagen parcial por
pérdida de fecha al proyectar la extracción al Agent (BL-50), no error visual.
Coste visual desconocido y embeddings sin contabilidad completa (BL-51).
No se publicó r2 ni se cambió runtime. No exigir ese cambio para acreditar
lo probado con r1, ni declarar benchmark/cierre global de BL-6. Pendientes
BL-50/51 y benchmark representativo autorizado. Evidencia en campaña entrega 4
y `specs/003-document-memory/verification.md`.

**Antecedente de implementación/plan, no estado de la ruta activa actual:**
La extracción visual está implementada localmente: imagen directa o PDF renderizado
con PyMuPDF (máximo 3 páginas) → ruta lógica `ancoramind-vision` → salida
estructurada. Los contenidos siguen siendo DATA, no INSTRUCTIONS. Pendiente:
publicar/autorizar `ancoramind-vision-r2` con Qwen en Railway, activar la revisión
runtime, benchmark de precisión/coste/latencia y E2E Telegram con PDF e imagen.
**Nota triage TODO (2026-09-20):** los PDFs escaneados ya fluyen por la ruta
visual (PyMuPDF rasteriza páginas con o sin capa de texto — el "fallback OCR"
propuesto ya está cubierto por diseño). **Resuelto (2026-10-03, specs/021 Fase
1/BL-38):** `analyze_document` ya detecta la capa de texto (`has_extractable_text`)
y, cuando existe, usa `extract_pdf_text_markdown` (determinista, PyMuPDF/
pymupdf4llm) en vez de la ruta visual — PDFs digitales ya no pagan una llamada
de visión. **Resuelto (2026-10-10):** política explícita de páginas para PDFs
largos — `document_text_max_pdf_pages` (20, sin coste de inferencia) ya es
independiente de `document_vision_max_pdf_pages` (3, con coste de inferencia
por página); antes compartían el mismo límite conservador pensado solo para la
ruta visual. Sigue pendiente, y requiere infraestructura real (no código):
publicar/autorizar `ancoramind-vision-r2`, el benchmark de precisión/coste/
latencia y el E2E Telegram con PDF/imagen — OCR dedicado solo si la ruta
visual no alcanza precisión en escaneados.


### BL-7 · Proveedor de calendario real 🔶 CalDAV implementado localmente — 2026-10-10

**Implementado localmente:** `CaldavCalendarProvider`
(`src/agent/calendar_caldav.py`) tras el `Protocol` ya existente — CalDAV en
vez de Google Calendar/Outlook porque estos exigen un flujo OAuth2 completo
con refresh tokens, fuera de alcance sin infraestructura para probarlo.
Vía deliberadamente simple: `httpx` (ya dependencia) + `icalendar` (nueva,
BSD-2-Clause, puro Python) con un `PUT` directo del VEVENT a la URL de
colección de calendario que configure el operador — sin descubrimiento
WebDAV (principal/calendar-home-set) como haría la librería `caldav`
completa. `list_events` también implementado de verdad vía `REPORT`
CalDAV (`calendar-query` + `time-range`), aunque **hoy nadie lo invoca**
(`check_calendar` solo lee de Postgres, nunca del proveedor externo) — se
implementó igual para dejar el Protocol completo. La respuesta XML del
servidor se trata como no confiable: se rechaza si declara
`<!ENTITY`/`<!DOCTYPE` antes de parsearla, mismo criterio ya usado para
OOXML en `document_office.py`, sin añadir `defusedxml`.

**Hallazgo y decisión de fiabilidad:** `CalendarService.create_event`
llamaba al proveedor **antes** de persistir en Postgres; con Noop eso nunca
podía fallar, pero un proveedor real sí puede (red, auth, caída) — así que
se hizo la llamada al proveedor **best-effort**: un fallo se loguea y
`provider_event_id` queda `None`, pero el evento siempre se persiste
canónicamente (mismo criterio ya usado en BL-32/BL-38/Dream). Esto permitió
conectar el proveedor real en `tools/calendar.py` sin riesgo.

**Limitación conocida, aceptada:** una sola cuenta/calendario compartido
por despliegue, sin OAuth ni cuentas por usuario — coherente con que este
es un asistente personal de un propietario (más un grupo acotado de
evaluadores vía BL-24), no un SaaS multi-tenant. `user_external_id` se
ignora en la implementación CalDAV. El dispatch de mutación **gobernado**
(`src/domain/actions/mutations.py`, usado bajo `GOVERNED_CONSENT_ENABLED`)
sigue deliberadamente en `NoopCalendarProvider` — conectarlo ahí violaría
la separación dominio/infra (AGENTS.md §2.1: el dominio nunca importa
`src/agent/`) sin antes inyectar el proveedor vía
`InteractionProcessor`→`ProposalExecutor`→`apply_mutation`, un cambio de
plomería mayor fuera de alcance de este incremento. Config nueva:
`CALENDAR_PROVIDER` (`noop`/`caldav`), `CALENDAR_CALDAV_BASE_URL/USERNAME/
PASSWORD`, fail-closed si `caldav` sin las tres variables. 20 tests nuevos
(`test_calendar_caldav.py` + 1 en `test_reminder_calendar_service.py`),
1145 unit tests (suite completa), Ruff y `mypy src/` (161 ficheros)
limpios. Validación E2E contra un servidor CalDAV real pendiente — sin
infraestructura disponible en esta sesión.

### BL-26 · Notas de voz entrantes y transcripción gobernada (STT) 🔶 implementación parcial — specs/028
**Autorización ampliada (2026-10-07, prevalece):** propietario acepta las
limitaciones OpenRouter también para audio personal, Telegram y producción MVP.
Activación supeditada a validación técnica; voz sigue OFF. Fallo STT ambiguo
debe informar que no se entiende el audio sin reintentos ni Agent. Revisiones
de privacidad antes de apertura pública conservadas en `preflight-smoke.md`.
**Decisión MVP y autorización (2026-10-07):** mantener OpenRouter; propietario
acepta proveedor no fijo/retención cero no garantizada para UNA prueba con voz
artificial y sin datos personales. No habilita audio personal, Telegram ni
producción. Tarifa/Gateway/credenciales pendientes; sin inferencia ejecutada.
Gates de privacidad y alternativas antes de apertura pública documentados en
`specs/028-telegram-voice-stt/preflight-smoke.md`.
**Preflight/smoke (2026-10-07):** catálogo público revisado sin inferencia;
smoke opt-in preparado, probado con HTTP simulado y PostgreSQL real. 910 unit
passed (12 físicos omitidos), 139 integration passed (1 live smoke omitido).
Privacidad STT, mínimo/redondeo, upstream y coste real siguen pendientes; ver
`specs/028-telegram-voice-stt/preflight-smoke.md`. Voz OFF; sin cambios remotos.
**Incremento inspector/T5/T6:** decoder real validado en Docker (12 tests),
consentimiento vocal con ejecutor transaccional solo para notas y adaptador STT
privado probado con HTTP simulado. Restan executors demás capabilities,
compatibilidad Gateway/upstream, concurrencia adversarial completa y E2E.
Voz sigue OFF; no publicación de alias ni inferencia real.

**Actualización 2026-10-06 — ejecutores y compatibilidad offline:** ejecutor
determinista compartido por voz/texto/botones para notas, vehículos/mantenimiento,
TODOs, recordatorios/snooze, calendario canónico con recordatorio y borrado
documental. Mutaciones locales y auditoría comparten transacción; borrado externo
persiste intención antes del efecto y nunca se reintenta automáticamente.
Pruebas adversariales incluyen concurrencia, aislamiento, hash/procedencia,
caducidad, generación y rollback. Imagen LiteLLM fijada validada con endpoint
HTTP real y upstream local simulado, sin red externa ni credenciales. OpenRouter
documenta STT multipart; la ruta compatible se configura con `openai/` y api_base
OpenRouter, no se presume soporte del adaptador nativo `openrouter/` para STT.
Pendientes alias/tarifa reales, prueba autorizada upstream, benchmark y piloto.
**Actualización 2026-10-06:** alcance acordado: notas de voz originales de hasta
**5 minutos**, respuesta textual y «Sí»/«No» por voz como alternativa de
consentimiento determinista, sin exigir teclear ni botones. El coste por nota
se deriva de duración y tarifa versionada (incluido redondeo/mínimo); no se pide
un presupuesto USD STT manual adicional, pero se conservan límites de gasto
agregado y presupuesto de interacción. `specs/028-telegram-voice-stt/` define
contratos, fases y matriz V01–V36; **runtime y aceptación voz pendientes**.
T2 implementado localmente en `src/domain/speech/`: límites puros, facturación
Decimal exacta, puertos STT/inspector y parser vocal Sí/No independiente; sin
conectar Telegram, proveedor ni claims. Inspección FFmpeg/ffprobe candidata,
sin binarios instalados ni validación de audio físico aún.
T3 implementado y validado localmente en PostgreSQL (2026-10-06): tabla de preparación
exclusiva sin audio, intención/reserva STT durable, transcripción cifrada,
recuperación sin replay y limpieza terminal/expiración; migración 0011 e init.sql.
T4 integrado con inspector/STT simulados: normalización voice, descarga streaming
acotada, preparación exclusiva con bloqueo PostgreSQL, snapshot/budget compartido
y recovery/purge en lifecycle incluso voz OFF. Validación 2026-10-06: 887 unit y
117 integration verdes; Ruff/mypy limpios. Pendientes inspector físico/temporales
reales, T5 consentimiento y T6 proveedor. Bootstrap no permite activar voz sin
adaptadores físicos; no hay STT fake en producción.
Dependencia para E2E de confirmación/ejecución: conectar `_execute_claimed()`
(BL-40/specs/023) y habilitar consentimiento gobernado sin bypass legacy.

**V27/V29/V30 implementados localmente (2026-10-11):** 15 tests unitarios
nuevos (`tests/unit/test_voice_consent_handling.py`) sobre
`InteractionProcessor._handle_voice_consent` — propuesta reenviada/editada/
mezclada con texto nunca es consentimiento fresco (V27), consentimiento
gobernado apagado o sin ejecutor determinista responde sin ejecutar nada
(V29), y la verificación de evidencia (transcripción re-descifrada contra
el payload original, nunca el argumento de texto suelto) impide que un
documento/foto/historial con un "Sí" cree evidencia de consentimiento
vocal (V30). **V25/V26/V28 (carreras reales en PostgreSQL — dos "Sí"
concurrentes, generación/caducidad cambiando mientras STT procesa) siguen
pendientes**, no se pueden cubrir con mocks sin fingir el resultado;
requieren el locking real de `resolve_voice_consent` contra PostgreSQL.
1209 unit tests (suite completa), Ruff y `mypy src/` limpios.

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

### BL-27 · Respuestas de voz opcionales en Telegram (TTS) 🔶 mini-ADR documentado — specs/033

**Mini-ADR documentado (2026-10-11, specs/033, sin código):** investigado
el pipeline de voz entrante (BL-26/specs/028) como plantilla a invertir, no
reutilizar literalmente. Decisiones clave:

- **El texto nunca deja de enviarse** — TTS es un enriquecimiento
  best-effort *posterior* a que la respuesta de texto ya esté `completed`,
  nunca un sustituto ni algo que compita con la máquina de estados
  principal. Esto resuelve de raíz el "fallback a texto": nunca hay que
  activarlo, porque el texto nunca espera a la voz.
- **Outbox independiente** — `response_kind='voice'` como fila hermana de
  `'ack'` (BL-32: `ON CONFLICT (interaction_id, response_kind) DO NOTHING`,
  nunca toca `telegram_interactions.status`, `chunk_count=1` siempre; una
  respuesta hablada es un fichero, nunca se fragmenta como el texto).
- **Ruta gobernada hermana, no reutilización** — `RuntimeConfiguration.speech`
  es un único campo para la ruta de STT, no un diccionario de capacidades
  de voz; TTS necesita un campo `speech_output` aditivo propio y un nuevo
  valor `"speech_synthesis"` en el `Literal` de capacidades, con la misma
  exigencia de `cost_governance` que ya aplica a `speech` si hay tarifa.
- **Entrega confirmada con el propietario:** `sendVoice` (Ogg/Opus, nota de
  voz nativa) en vez de `sendAudio`, transcodificando con `ffmpeg` — mismo
  binario ya aprobado para STT (`voice_inspector.py`), usado en sentido
  inverso (codificar, no decodificar).
- **Nunca se persisten bytes de audio** sintetizado, igual que la voz
  entrante; el texto que origina el audio ya es la fuente de verdad
  persistida.
- **Gap real señalado, no ocultado:** no existe ningún almacén de
  preferencias por usuario en el repo hoy (`src/domain/preferences/` solo
  tiene zona horaria, y su propio código documenta que la tabla todavía no
  existe) — v1 queda gobernada por un flag global
  (`TELEGRAM_TTS_ENABLED`), igual que BL-26; la preferencia por usuario
  que pedía el ítem original queda como su propio pendiente (T6 de
  `specs/033/tasks.md`), no como algo resuelto implícitamente.

`specs/033/tasks.md` define T1–T7 (campo de runtime config → spike de
proveedor contra Gateway real → `GovernedSpeechSynthesisAccess` →
transcodificación/entrega → outbox independiente → preferencia por
usuario → E2E), ninguna implementada. Bloqueado por el mismo Gateway real
que BL-30 Fase 2 para fijar el proveedor concreto.

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

**Fase 1 implementada localmente (2026-10-04, specs/025):** Tavily directo tras
un puerto de dominio, habilitación explícita (`WEB_SEARCH_ENABLED=false` por
defecto), consulta pública minimizada, `basic`, máximo 5 resultados, sin
`include_answer` ni contenido bruto, caché sólo en memoria y envoltorio
`untrusted_data`. No persiste consultas/resultados y rechaza patrones básicos de
datos personales/sensibles. La Fase 2 (spike OpenRouter/LiteLLM) queda diferida
y documentada en `specs/025-web-search/spec.md`.

**Revisión documental de Fase 2 (2026-10-09, sin Gateway real — ver
`specs/025-web-search/spec.md` §"Revisión documental"):** confirmado que
OpenRouter activa búsqueda nativa vía sufijo `:online`, plugin `web` o el
server tool `openrouter:web_search`, con filtros de dominio y hasta 10
resultados por búsqueda. **Hallazgo que bloquea adoptarlo tal cual:** no
existe ningún parámetro documentado para fijar un número máximo de
*búsquedas* por petición (solo de resultados por búsqueda) — el modelo
decide 0..N búsquedas y cada una se factura por separado ($0.007 con Exa,
variable por motor), coste que solo se conoce **después** de la llamada.
Esto rompe la invariante de presupuesto pre-reservado que ya cumplen el
resto de capacidades gobernadas (`ExecutionBudget.reserve_model_call()`
exige conocer el coste antes de llamar). **Recomendación no vinculante:**
mantener Tavily como única vía mientras ese límite no exista documentado;
no se ha tocado código, solo la spec. El spike real contra el Gateway
desplegado (criterios 1/4/5/6 de la lista original) sigue sin ejecutarse.

**Validación Telegram en producción (2026-10-24, specs/025/verification.md):**
tres mensajes (1 texto, 2 voz) con `search_web` + `present_reply`, fuentes
citadas y sin consulta/snippets en las trazas de Tempo. Pendientes: consulta
con dato personal vía Agent, prompt injection web real y revisión de logs/Phoenix.

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

### ~~BL-31 · Deduplicación de documentos por hash de contenido~~ ✅ implementado localmente — 2026-10-07
Columna `ancora.documents.content_hash VARCHAR(64)` (nullable, sin backfill)
+ índice único parcial `(user_id, content_hash) WHERE content_hash IS NOT NULL`
(migración `0012_document_content_hash`, `init.sql` sincronizado).
`DocumentService.ingest()` calcula SHA-256 de los bytes crudos antes de
`storage.store()`; si ya existe un documento con ese hash para el mismo
usuario, se devuelve el documento y su extracción existentes vía
`get_document_with_extraction()` sin volver a almacenar ni a invocar
`DocumentExtractionPort` (política "reutilizar extracción" recomendada en el
diseño original). Sin manejo de carrera explícito: la admisión de Telegram
(specs/013 T5) ya serializa por chat/usuario antes de llegar al Agent, así
que dos subidas idénticas del mismo usuario no pueden ejecutar `ingest()` en
paralelo. Nuevo `DocumentsRepository.get_by_content_hash()`. Tests: 2 unit
nuevos de servicio (`test_document_service.py`), 3 integration nuevos de
repositorio (incluida la colisión `IntegrityError` entre dos usuarios con el
mismo contenido) y `test_migrations.py` actualizado para que la aserción de
`downgrade -1` desde head apunte a esta migración en vez de a la anterior
(`voice_preparations`, movida al downgrade más profundo). 909 unit + 141
integration passing (1 fallo de timing preexistente y no relacionado,
confirmado en aislamiento), Ruff y `mypy src/` limpios. Desbloquea BL-35 y la
Fase 2 de BL-38.

### BL-32 · Acuse de recibo temprano para procesos pesados (fast-ack UX) 🔶 acuse Telegram implementado localmente — 2026-10-10

**Implementado localmente (2026-10-10):** opción (a) del diseño original
— acuse como respuesta propia de la outbox, no un chunk de la respuesta
final ni un mensaje efímero. Hallazgo clave de diseño: no se pudo
reutilizar `persist_response_ready`/`claim_delivery_start`/
`finalize_response_delivery` (`src/repositories/interactions.py`) porque
los tres mutan `telegram_interactions.status`
(`accepted→response_ready→delivery_started→completed`) — exactamente el
estado que el acuse no puede tocar, ya que convive con `agent_started`
mientras el run principal sigue en curso. Solución: dos métodos nuevos y
deliberadamente simples, `create_ack_response`/`mark_ack_delivery_outcome`,
que escriben en `ancora.logical_responses`/`ancora.telegram_response_deliveries`
con `response_kind='ack'` (la tabla ya soporta esto nativamente —
`UNIQUE (interaction_id, response_kind)` y `claim_delivery_start` ya filtra
por `response_kind='agent_final'`, así que una fila `'ack'` es invisible
para toda la máquina de estados del flujo principal) **sin ninguna
migración nueva**. `InteractionProcessor._run_agent` envía el acuse justo
tras `_claim_agent` (heurística: `attachments` no vacío tras descartar
voces ⇒ acuse; texto ⇒ no), con `ON CONFLICT (interaction_id, response_kind)
DO NOTHING` garantizando que un update reprocesado nunca duplica el acuse.
Todo el envío va envuelto en un único `try/except` que solo loguea: un
fallo de persistencia o de `sender.send_text` nunca bloquea, retrasa ni
falla el run principal, y no hay scan de recuperación para `response_kind='ack'`
(a diferencia de `agent_final`) — limitación aceptada explícitamente, mismo
criterio "best-effort" ya usado para `export_document` (BL-38) y la captura
de Dream (BL-13). Flag nuevo `TELEGRAM_FAST_ACK_ENABLED` (default `false`,
mismo patrón que `TELEGRAM_VOICE_ENABLED`/`GOVERNED_CONSENT_ENABLED`). 6
tests nuevos en `test_interaction_processor.py` (envío único con flag
activo, nunca para texto puro, nunca con flag apagado, no duplica si ya
existía, un fallo de envío o de persistencia del acuse no bloquea el run
principal). 1125 unit tests (suite completa), Ruff y `mypy src/` limpios.
Los dos métodos de repositorio nuevos no tienen test de integración propio
todavía (solo SQL, requiere Postgres real) — queda pendiente para cuando
haya infraestructura, igual que el resto de la suite de integración.

**Diferido explícitamente, sin cambios respecto al diseño original:** la
generalización a **eventos internos tipados de progreso** metadata-only
(`operation_started`, `stage_changed`, `operation_succeeded`,
`operation_failed`) para otros productores (documentos, STT, búsqueda web,
consolidación de memoria) sigue fuera de alcance — este incremento resuelve
solo el acuse de Telegram para adjuntos, no la plataforma de eventos
genérica que el ítem original esbozaba como visión a futuro.

### BL-35 · Ingesta gobernada de documentos ofimáticos (DOCX/XLSX/PPTX) 🔶 extractores + fixtures adversariales implementados, falta E2E — 2026-10-10
Ampliar Document Memory para recibir formatos ofimáticos habituales sin ejecutar
macros, relaciones externas, objetos embebidos ni contenido activo. Implementar
extractores deterministas detrás de un puerto de infraestructura: texto y tablas
de DOCX, hojas/celdas relevantes de XLSX y texto/notas de PPTX; después reutilizar
el pipeline de almacenamiento, extracción gobernada, provenance y propuestas
existente. El contenido extraído sigue siendo DATA, nunca instrucciones.

**Dependencia (resuelta 2026-10-07):** BL-31 (deduplicación por hash) ya está
implementado localmente — desbloqueada. Aplicar allowlist real
por firma/MIME además de extensión, límites de bytes, entradas ZIP, ratio de
compresión, profundidad, nº de hojas/diapositivas/filas/celdas, texto total y
tiempo; rechazar cifrado/contraseña, macros y formatos legacy binarios inicialmente.
No renderizar fórmulas ni seguir hyperlinks/conexiones externas. Conservar original
y provenance, y declarar extracción parcial/truncada al usuario. **Prioridad P2.**
**Criterio de cierre:** fixtures benignas y maliciosas (ZIP bomb, path traversal,
macro, archivo renombrado y workbook desmesurado), deduplicación, aislamiento por
usuario y E2E Telegram por cada formato soportado.

**DOCX implementado localmente (2026-10-09):** para no mezclar tres formatos
y tres superficies de seguridad en un solo cambio, este incremento cubre
**solo DOCX** (`application/vnd.openxmlformats-officedocument.
wordprocessingml.document`); XLSX y PPTX quedan como siguientes incrementos
del mismo item, reutilizando el mismo patrón. `src/agent/document_office.py`
inspecciona el contenedor ZIP antes de confiar en `python-docx` (nº de
entradas, nombre de entrada sin `../`/ruta absoluta, suma de tamaños sin
comprimir contra un tope — defensa de zip-bomb por metadato declarado, nunca
inflando la entrada —, exige `word/document.xml` y rechaza si aparece
`word/vbaProject.bin`); `.docm` (macro-habilitado) y el `.doc` legado binario
quedan excluidos por construcción (no están en el MIME allowlist, caen al
camino visual existente sin cambio de comportamiento). El Markdown se
renderiza recorriendo `document.element.body` en orden real (párrafos +
tablas intercaladas, no las listas planas `.paragraphs`/`.tables` de
python-docx, que pierden el orden), con un presupuesto compartido de bloques
que trunca sin lanzar excepción. Reutiliza el mismo mecanismo que el PDF con
capa de texto (specs/021 Fase 1): `extracted_text` pasa a
`DocumentService.ingest()` sin tocar `DocumentExtractionPort`,
`DocumentCreate` ni la persistencia de `ai_extractions`. Nueva dependencia
`python-docx` (MIT, puro Python, sin binarios nativos) — se descartó
`mammoth` porque su soporte Markdown está marcado experimental/deprecado en
su propia documentación. `ALLOWED_MIME_TYPES` (`.env`/`.env.example` y el
default en `src/config.py`) amplía su allowlist con este MIME; sin ese
cambio el adjunto se habría rechazado antes de llegar a `analyze_document`.
12 tests nuevos (`test_document_office.py`: ZIP malformado, exceso de
entradas, zip-bomb por metadato, path traversal, macro, truncamiento por
bloques, extracción feliz con heading/tabla; más 2 de integración en
`test_document_tools.py` — DOCX válido usa la ruta determinista, DOCX roto
no bloquea el ingest). 982 unit tests (suite completa), Ruff y `mypy src/`
limpios.

**XLSX implementado localmente (2026-10-09, mismo incremento):**
`extract_xlsx_text_markdown` en el mismo `src/agent/document_office.py`,
reutilizando el inspector de ZIP generalizado (`_inspect_office_zip`, ya
compartido con DOCX) con sus propios códigos de error (`xlsx_malformed`,
`xlsx_too_many_entries`, `xlsx_zip_bomb_suspected`,
`xlsx_unsafe_entry_name`, `xlsx_macro_rejected`). Usa `openpyxl`
(`data_only=True` para leer el valor cacheado de cada fórmula, nunca la
fórmula en sí; `read_only=True` para transmitir filas en vez de cargar la
hoja entera, acotando memoria aunque el workbook declare dimensiones
falsas). Un cifrado/con contraseña no es siquiera un ZIP válido para
`openpyxl` y cae en `xlsx_malformed` sin trato especial. `.xlsm`
(macro-habilitado) y el `.xls` legado binario quedan excluidos por
construcción, igual que `.docm`/`.doc`. Toda fila escaneada —en blanco o
no— consume el presupuesto compartido de bloques, para que una hoja
adversarial de filas vacías no itere sin límite; `max_sheets` y
`max_cols_per_sheet` acotan hojas y columnas. **Hallazgo de seguridad
propio de XLSX, sin precedente en DOCX:** `openpyxl` advierte en su propia
documentación que no protege por defecto contra ataques XML de expansión
de entidades ("billion laughs") y recomienda instalar `defusedxml` — pero
su integración automática no está confirmada. En vez de añadir una segunda
dependencia nueva con una integración incierta, `_inspect_office_zip`
incorpora una guardia propia sin dependencias: rechaza cualquier entrada
XML del ZIP que declare `<!ENTITY`/`<!DOCTYPE` (el formato OOXML legítimo
nunca los usa), aplicada también retroactivamente a DOCX. Nueva dependencia
`openpyxl` (MIT, puro Python). 13 tests nuevos (11 en `test_document_office.py`
incluida la guardia de entidades XML para ambos formatos; 2 de integración
en `test_document_tools.py`). 995 unit tests (suite completa), Ruff y
`mypy src/` limpios.

**PPTX implementado localmente (2026-10-09, mismo incremento):**
`extract_pptx_text_markdown`, mismo `document_office.py`, reutilizando
`_inspect_office_zip` con sus propios códigos (`pptx_malformed`,
`pptx_too_many_entries`, `pptx_zip_bomb_suspected`, `pptx_unsafe_entry_name`,
`pptx_macro_rejected`, `pptx_xml_entity_rejected`). Alcance deliberadamente
acotado a **texto y notas del orador** (criterio textual de BL-35 para
PPTX): solo se leen `shapes` con `text_frame` (títulos, cuerpos, cuadros de
texto) y `notes_slide`; tablas, gráficos, imágenes y objetos embebidos en
diapositivas nunca se leen, ni siquiera su texto. Cada `shape` escaneado
—tenga texto o no— consume el presupuesto compartido de bloques, igual que
los párrafos de DOCX y las filas de XLSX, para que una diapositiva repleta
de formas sin texto no itere sin límite. `.pptm` (macro-habilitado) y el
`.ppt` legado binario quedan excluidos por construcción. Nueva dependencia
`python-pptx` (MIT, puro Python; arrastra `Pillow` como transitiva, ya
asumible por ser estándar de facto). Nuevos settings
`document_office_max_slides` (100 por defecto). 10 tests nuevos (8 en
`test_document_office.py` + 2 de integración en `test_document_tools.py`).
1020 unit tests (suite completa), Ruff y `mypy src/` limpios.

**Fixtures adversariales "archivo renombrado"/"workbook desmesurado"
implementadas localmente (2026-10-10):** "archivo renombrado" — un DOCX,
XLSX o PPTX real declarado/renombrado como otro de los tres — se cubre con
6 tests (las 6 combinaciones cruzadas: cada extractor rechaza el contenido
real de los otros dos formatos). Ya estaba defendido por el chequeo
`required_entry` existente (p. ej. un DOCX real no tiene `xl/workbook.xml`
→ `xlsx_malformed`), pero no había un test dedicado que lo demostrara con
contenido *realmente válido* de otro formato en vez de un ZIP arbitrario.
"Workbook desmesurado" — un XLSX cuyo XML de hoja declara un `<dimension
ref="A1:XFD1048576"/>` (el máximo absoluto de Excel) muy por encima de sus
filas reales — se cubre con 2 tests que reescriben esa declaración en un
workbook real por lo demás válido: la extracción solo lee lo que de verdad
hay (streaming `read_only=True`, ya existente) y el truncado por
`max_blocks` sigue basándose en filas escaneadas de verdad, nunca en la
dimensión declarada (que aquí es una mentira deliberada). 8 tests nuevos en
`test_document_office.py`, 1119 unit tests (suite completa), Ruff y
`mypy src/` limpios.

Con DOCX+XLSX+PPTX implementados y estas fixtures cubiertas, de BL-35 solo
queda lo que ya era explícitamente de infraestructura en su criterio de
cierre original: E2E Telegram real por formato (bloqueado por BL-18, igual
que el resto del pipeline documental).

### BL-38 · Conversión de documentos texto↔Markdown/PDF reutilizando lógica de `mcp_doc_to_markdown` 🔶 Fases 1–3 implementadas localmente, falta E2E — specs/021
Existe un servidor MCP externo (`C:\Users\0020572\OneDrive - ViewNext\IA\Research\tools\mcp_doc_to_markdown.py`,
fuera de este repositorio) con conversores ya probados: PDF con capa de texto y
DOCX → Markdown (`pymupdf4llm`, `mammoth`/`markdownify` vía `docx_to_md_app.py`),
PDF escaneado → Markdown por visión página a página (`pdf_img_to_md.py`,
reutilizable como adaptador `DocumentExtractionPort` — mismo patrón que T9/BL-6),
detección de PDF escaneado vs. texto (`get_pdf_info`, basado en
`page.get_text("text")` con PyMuPDF), VTT → Markdown y **Markdown → DOCX**
(`markdown_docx_converter.py`).

**No se conecta ese servidor MCP como infraestructura del runtime** (viola
AGENTS.md §2.1/§2.9: no es un provider gobernado, no pasa por `LLMAccess`, no
tiene `RuntimeConfigSnapshot`/budget/auditoría y vive fuera del repo). Lo que se
incorpora es la **lógica determinista de conversión** portada a
`src/domain/documents/` detrás de un puerto de infraestructura, siguiendo el
mismo patrón que `DocumentExtractionPort`:

1. **Selección de ruta de extracción por capa de texto.** Antes de invocar la
   ruta visual (`ancoramind-vision`, BL-6), comprobar con PyMuPDF si el PDF tiene
   texto extraíble (equivalente a `get_pdf_info`/`likely_scanned`). Si lo tiene,
   extraer con `pymupdf4llm` (determinista, sin coste de inferencia ni budget);
   si no, seguir la ruta visual ya implementada. Esto es exactamente el
   refinamiento ya anotado en BL-6 ("detectar capa de texto para preferir
   extracción textual… reservar visión para escaneados") y cierra ese pendiente.
2. **Extracción DOCX determinista** como parte de BL-35 (ingesta ofimática):
   reutilizar el enfoque de `docx_to_md_app.py` (texto + tablas a Markdown, modo
   `remove`/`save` para imágenes) detrás del mismo puerto, con los límites de
   seguridad ya exigidos en BL-35 (sin macros, sin relaciones externas, límites
   de tamaño/profundidad).
3. **Markdown → PDF para compartir salidas del asistente.** Hoy AncoraMind sólo
   entrega texto/HTML por Telegram (BL-29). Añadir una capability
   `propose_export_document` / `execute_export_document` (o, si se decide READ
   por ser generación efímera sin escritura canónica, justificarlo explícitamente
   en el spec) que convierta un Markdown (nota, resumen, lista TODO exportada,
   etc.) a PDF y lo entregue como documento adjunto de Telegram
   (`sendDocument`). El repo de origen no incluye un conversor Markdown→PDF
   (sólo Markdown→DOCX); evaluar en el spec una librería determinista sin
   dependencias de sistema pesadas (p. ej. generar DOCX con
   `markdown_docx_converter.py` y convertir a PDF, o un renderer HTML→PDF
   embebible) y documentar la decisión con sus límites de tamaño/tiempo.
4. **VTT → Markdown** como adaptador adicional de `DocumentExtractionPort` si
   aparece un caso de uso real (transcripciones de reuniones); no implementar
   especulativamente sin ese caso.

**Restricciones de gobernanza a preservar:** el contenido de cualquier documento
convertido sigue siendo DATA, nunca instrucciones (AGENTS.md §2.8); la
inferencia de la ruta visual sigue pasando por `LLMAccess`/Gateway con
`RuntimeConfigSnapshot`, budget y auditoría (no se copia `create_vision_llm_client`
tal cual — ese cliente físico directo del script de origen debe sustituirse por
el adaptador `DocumentExtractionPort` ya existente); ninguna conversión ejecuta
macros ni sigue referencias externas; los límites de tamaño/páginas/tiempo ya
vigentes para documentos (BL-6/BL-35) aplican igual aquí. Dependencias de Python
nuevas (`pymupdf4llm`, `mammoth`, `markdownify`, `python-docx`) se añaden a
`pyproject.toml` sólo tras confirmar licencia y huella de instalación.

**Prioridad P2.** El punto 1 (detección de capa de texto) es de bajo esfuerzo y
ahorro directo de coste — candidato a adelantarse dentro del benchmark de BL-6.
Los puntos 2 y 3 dependen de BL-35 y BL-29 respectivamente y deben spec-earse
junto a ellos, no de forma aislada. **Criterio de cierre:** PDF de texto usa la
ruta determinista (cero coste de inferencia) y PDF escaneado sigue usando
visión; export Markdown→PDF probado con al menos una nota/lista real y entregado
por Telegram con evidencia en `verification.md`; ningún adaptador nuevo crea un
provider físico ni bypassa `LLMAccess`.

**Actualización 2026-09-29 (specs/021 creado):** SDD redactado con tres fases.
Fase 1 (detección de capa de texto + extracción determinista de PDF con
`pymupdf4llm`) es autocontenida y lista para implementar — resuelve el
refinamiento pendiente de BL-6. Fase 2 (DOCX determinista) queda bloqueada por
el cierre de BL-35. Fase 3 (export Markdown→PDF) queda bloqueada por una
decisión de diseño propia (DOCX→PDF vs. HTML→PDF) y por BL-29. Ver
`specs/021-document-conversion-toolkit/`.

**Fase 1 implementada localmente (2026-10-03):** `extract_pdf_text_markdown`
(`src/agent/document_vision.py`, PyMuPDF + `pymupdf4llm.to_markdown`, mismo
límite `document_vision_max_pdf_pages` que la ruta visual — sin introducir un
tope independiente) se cablea en `analyze_document`
(`src/agent/tools/documents.py`): un PDF con `has_extractable_text` ya usa la
ruta determinista y nunca llama a la ruta visual; `DocumentService.ingest`
acepta `extracted_text` y lo trata como el `text_preview` ya existente para
`text/*` (mismo acotado `MAX_TEXT_PREVIEW_BYTES`, mismo tratamiento como DATA
no confiable). Señal metadata-only (`ancora.document.extraction_route` ∈
{`deterministic`, `visual`, `none`}) añadida al allowlist de
`src/observability/telemetry.py` y emitida en `DocumentService._extract`
(T7). `pymupdf4llm>=1.24.0,<2.0.0` añadido a `pyproject.toml` (mismo régimen
de licencia que `PyMuPDF`, ya aceptado). 9 tests nuevos (693 unit passing),
Ruff/mypy limpios. **Pendiente:** T8/T9 de `specs/021/tasks.md` marcados
hechos; falta validar con un PDF real de usuario vía Telegram (bloqueado por
las restricciones de infraestructura actuales) antes de cerrar el criterio de
cierre completo de la fase.

**Límite de páginas desacoplado (2026-10-10, cierra el pendiente de BL-6
"política explícita para PDFs de más de 3 páginas"):** la ruta determinista
y la visual compartían `document_vision_max_pdf_pages` (3 por defecto) desde
la Fase 1. Como `extract_pdf_text_markdown` no tiene coste de inferencia, se
introduce `document_text_max_pdf_pages` (default 20, independiente) en
`src/config.py`; `analyze_document` pasa ahora el límite correcto a cada
ruta. La ruta visual sigue acotada a 3 páginas (coste de inferencia por
página); un PDF con capa de texto puede leer hasta 20. 4 tests nuevos
(`test_config.py`, `test_document_tools.py`), Ruff/mypy limpios.

**Fase 2 (DOCX/XLSX/PPTX) implementada localmente — ver BL-35**, que
terminó cubriendo este punto para los tres formatos ofimáticos, no solo
DOCX como anotaba el plan original de aquí.

**Fase 3 implementada localmente (2026-10-09):** export Markdown→PDF, única
pieza que quedaba de BL-38. Decisión de diseño (punto 3 de arriba):
**ni DOCX como intermedio ni una librería de PDF nueva** — PyMuPDF (ya
aprobado, usado en Fase 1/BL-6) renderiza HTML real (headings, listas,
tablas) a PDF vía su API `Story`/`DocumentWriter`, confirmado empíricamente
antes de implementar, no solo por documentación. Solo se añade `markdown`
(BSD-3-Clause, puro Python) para Markdown→HTML — una dependencia nueva en
vez de las dos que implicaba cualquiera de las dos vías originalmente
propuestas, y cero dependencias de sistema (nunca wkhtmltopdf/LibreOffice).
Gobernanza (punto 3, pregunta abierta): **automático, un único tool
`export_document`, sin `propose_*`/`execute_*`** — misma excepción ya
aprobada para `analyze_document`: no hay mutación canónica y el fichero
solo llega al usuario que lo pidió, por el mismo canal donde ya habla.
Alcance deliberadamente genérico: recibe Markdown ya compuesto por el
modelo (de una nota/lista que el modelo ya leyó con sus tools de lectura),
sin lógica de exportación por dominio. Nuevo `TelegramNotifier.
send_document()` (multipart a `sendDocument`, misma clasificación de
fallos que `send_text`). **Riesgo de gobernanza documentado, no resuelto:**
el envío ocurre a mitad del run, fuera del outbox gobernado de specs/013;
un fallo justo después de un envío correcto podría duplicar el PDF en un
reintento (nunca una mutación, solo un fichero) — aceptado explícitamente
con el mismo criterio "best-effort" ya usado para la captura de
transcripts de Dream (BL-13); integrarlo en el outbox real (BL-32) queda
como seguimiento. 20 tests nuevos, 1066 unit tests (suite completa), Ruff
y `mypy src/` limpios. **Pendiente:** E2E real por Telegram, bloqueado por
BL-18 igual que el resto del pipeline documental.

**Seguimiento de idempotencia cerrado (2026-10-11):** el párrafo anterior
especulaba con que "un reintento del run" podría duplicar el PDF y proponía
integrarlo en el outbox de BL-32. Investigado antes de tocar código: ese
reintento **no existe** en este repo — `retries=0` en el Agent gobernado
(`governed_agent_factory.py`), admisión de Telegram at-most-once antes de
llegar al Agent, y `mark_inflight_as_ambiguous` marca `failed_ambiguous`
(nunca reejecuta) cualquier interacción que quedara `agent_started` tras un
crash. El riesgo real es intra-run: el modelo invocando `export_document`
dos veces para la misma petición dentro de un único `agent.arun()`. Se
cierra con deduplicación en memoria, con alcance de un solo run — no con el
outbox (ese patrón resuelve "como mucho una fila por interacción"; aquí un
run puede generar legítimamente N exports distintos, así que la clave debe
ser el contenido, no la interacción). `GovernedInteractionRunner.run()`
(`src/agent/governed_interaction_runner.py`) construye `RunContext(...,
session_state={})` — un dict vacío, nuevo en cada run, no ligado a la
persistencia de sesión de Agno (`add_session_state_to_context` nunca se
activa). `export_document` (`src/agent/tools/export.py`) guarda en
`run_context.session_state["sent_exports"]` la respuesta ya devuelta,
indexada por `sha256(title + markdown_text)`: una segunda llamada idéntica
dentro del mismo run devuelve la misma respuesta sin reenviar; dos llamadas
con contenido distinto (dos PDFs pedidos a la vez) se envían ambas. Si
`session_state` es `None` (p. ej. un `RunContext` construido a mano en un
test sin pasar el kwarg) se degrada a no deduplicar — el comportamiento
previo, nunca un error. Nunca se persiste el PDF, solo el texto de
respuesta. 3 tests nuevos en `test_export_tools.py` + 1 ampliado en
`test_governed_interaction_runner.py`, 1212 unit tests (suite completa),
Ruff y `mypy src/` limpios.

Con esto, de BL-38 solo queda el E2E real (BL-18) — las tres fases de
diseño/implementación y el seguimiento de idempotencia están completos.

### BL-13 · Memoria personal y consolidación gobernada «Dream» 🔶 T3/T4/T5 implementados localmente, T1/T2 pendientes de Postgres — specs/029
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

**Diseño completo (2026-10-09, specs/029):** antes de diseñar el modelo de
datos se encontró un bloqueo real para la premisa "revisar interacciones ya
finalizadas desde un cursor": `payload_ciphertext` se limpia de forma
**síncrona** en el mismo commit que marca la interacción `completed`
(`TelegramInteractionsRepository.finalize_response_delivery`), así que el
texto de la conversación no sobrevive más que unos segundos en el schema
`ancora`. El único sitio con el texto en claro es la sesión interna de Agno
(`agno_runtime`), vedada por AGENTS.md §2.1/§2.7. Decisión aprobada por el
propietario: AncoraMind captura su propia copia acotada y cifrada del turno
(`ancora.dream_transcripts`, nuevo punto de escritura en
`processor.py::_run_agent`, no solo un lector nuevo). `specs/029-dream-
personal-memory/spec.md` desarrolla el modelo completo (`dream_transcripts`/
`dream_candidates`/`dream_cursor`/`dream_runs`), el enum cerrado de
categorías permitidas, la política de promoción explícito/implícito, el
worker (mismo patrón que el reminder worker) y las tools
`list_my_preferences`/`propose_preference_forget`/`execute_preference_forget`.
Limitación conocida y aceptada: el gasto de Dream se audita en
`dream_runs`, no en `llm_usage_events` (esa tabla exige una
`telegram_interactions` real), así que no entra en el agregado global de
`evaluate_cost_governance` por ahora. `docs/architecture.md` §7 actualizado
para reflejar que la memoria personal es propiedad de AncoraMind Core, no de
Agno. **Sin implementación todavía** — `tasks.md` desglosa T1–T6 para el
siguiente incremento.

**T4 implementado localmente (2026-10-09):** `DreamPromotionService`
(`src/domain/dream/service.py`), lógica de dominio pura sin I/O que aplica
la política de promoción de spec.md §4.1 y además fija 4 escenarios que la
política dejaba implícitos: un signal implícito nunca sobrescribe un valor
`active` (se rechaza, auditado); reforzar un valor `active` ya idéntico no
genera escritura; una contradicción implícita antes de alcanzar el umbral
reinicia el conteo; un signal explícito siempre gana aunque exista un
`candidate` pendiente. 11 tests nuevos.

**T3 (núcleo) implementado localmente (2026-10-09):** `DreamWorker`
(`src/domain/dream/worker.py`) y `GovernedDreamConsolidationAdapter`
(`src/agent/dream_access.py`), ambos contra puertos de dominio
(`src/domain/dream/ports.py`) — el worker nunca depende de SQL concreto, se
testea con los puertos mockeados. Ruta lógica `ancoramind-dream` añadida a
`bootstrap_runtime_configuration()`. **Desviación deliberada del patrón de
`document_extraction.py`/`document_embeddings.py`:** esos adaptadores caen a
un contexto standalone con config hardcodeada solo como *fallback*
transicional cuando no hay run gobernado; Dream nunca tiene un run
gobernado — es su único camino siempre —, así que el adaptador usa
`RuntimeConfigManager.snapshot()` (la config realmente activada), no el
bootstrap, para no ignorar en silencio un alias de Gateway publicado.
10 tests nuevos. **Diferido explícitamente:** la lifecycle wiring en
`src/agent/lifecycle.py` necesita un `DreamRepositoryPort` concreto sobre
SQL real (T1/T2) — cablearla contra un stub dejaría `DREAM_ENABLED` sin
efecto real.

**T5 implementado localmente (2026-10-09):** tools `list_my_preferences`
(READ) y `propose_preference_forget`/`execute_preference_forget`
(DESTRUCTIVE, patrón estándar) en `src/agent/tools/dream.py`, con
`DreamPreferenceService` (`src/domain/dream/preferences.py`) y
`DreamCandidatesRepository` (`src/repositories/dream_candidates.py`,
"olvidar" es un *soft delete* a `status='deleted'`, nunca borra la fila).
Añadido `"forget_dream_preference"` a `SUPPORTED_MUTATIONS`
(`src/domain/actions/mutations.py`) para que el camino Core
(`_execute_claimed`, voz/botón/«Sí» a secas) también pueda ejecutarlo.
`prompts/skills/dream.md` nuevo. 22 tests nuevos. **Diferido
deliberadamente, igual que T3:** el registro en `_init_domain_tools()`
(`src/main.py`) — la tabla `ancora.dream_candidates` no existe todavía
(T1 sin migrar); registrar las tools ahora las dejaría activas y fallando
contra una tabla inexistente en cuanto el LLM las invocara. También queda
sin implementar el flag de opt-out durable por usuario (spec.md §8).

De BL-13 solo quedan T1 (migración) y T2 (cablear la captura en
`processor.py::_run_agent`), ambos genuinamente bloqueados por necesitar
PostgreSQL real para validar; y la wiring de T3/T5 en `main.py`/
`lifecycle.py`, que depende de T1/T2.

### BL-36 · API de aplicación multicanal para clientes web/backend 🔶 diseño documentado — specs/032

**Diseño documentado (2026-10-10, specs/032, sin código):** investigado el
acoplamiento real a Telegram antes de diseñar — dos correcciones sobre el
texto original de este ítem: (1) `GovernedInteractionRunner`/
`ExecutionContext.telegram_update_id` es **obligatorio**, no solo
Telegram-shaped de nombre: ningún canal nuevo puede invocar el runner hoy
sin ese entero; (2) la ruta de **consentimiento gobernada** (`ConsentPrincipal`,
`action_proposals.bot_id`/`chat_id`, `claim_confirmation`) **no es
agnóstica de canal como se asumía** — necesita su propia generalización,
no solo el ledger. Decisiones propuestas (a confirmar antes de implementar,
ver specs/032/spec.md §5–§7): un `AncoraPrincipal` + tabla
`channel_identities` independiente de canal para resolver la coordinación
con BL-24 (hoy la autorización durable de BL-24 está keyed directamente por
`telegram_user_id`, sin ningún concepto de principal); migraciones aditivas
(nunca reemplazo) para ledger/`ExecutionContext`/consentimiento; tokens de
API hasheados y revocables por principal para v1 (no OIDC — eso es
responsabilidad del BFF recomendado delante de AncoraMind). `specs/032/tasks.md`
define T1–T8 (identidad → ledger → runner → consentimiento → admisión HTTP
→ polling/documentos/propuestas → OpenAPI/CORS/rate-limit → E2E Railway),
ninguna implementada. Sigue bloqueado por el cierre operativo de BL-23 y
la coordinación con BL-24, exactamente como ya marcaba este ítem.

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

### BL-41 · Recurrencia en calendario/recordatorios + snooze 🔶 E2E diario acotado superado; presentación pendiente — specs/024

Hoy `calendar_events` y `reminders` solo soportan ocurrencias únicas: no existe
"cada año", "cada semana" ni "cada mes", y un evento de calendario nunca
dispara un aviso de Telegram (solo lo hacen los recordatorios, totalmente
desacoplados hoy). Añadir recurrencia simple (frecuencia + intervalo + fin
opcional, sin RRULE) a ambos dominios: en calendario mediante **expansión
virtual** en lectura (`check_calendar`), sin materializar ocurrencias futuras
ni worker nuevo; en recordatorios insertando una fila `pending` nueva tras
cada disparo exitoso (manteniendo la fila `fired` como auditoría permanente),
con purga automática de `fired` con más de 90 días como housekeeping del
propio worker. `propose_calendar_event`/`execute_calendar_event` ganan
parámetros opcionales para vincular, en la misma propuesta, un recordatorio
recurrente al evento (resuelve el caso "cumpleaños que avisa cada año" en un
solo paso). Nuevo par gobernado `propose_reminder_snooze`/
  `execute_reminder_snooze` para posponer un recordatorio ya disparado (5 min–7 días),
independiente de su recurrencia. **Prioridad P2.**

**Estado:** implementado localmente — 684 unit + 94 integration tests verdes,
Ruff y `mypy src/` limpios; migración `0007_recurrence_snooze` aplicada.
**Actualización 2026-10-17:** E2E Telegram autorizado diario con fin explícito,
avance de ocurrencia y snooze entregados: PASS funcional asistido. 69 unitarias
focales y 18 integraciones locales verdes. Presentación incompleta pendiente
BL-49; yearly/monthly/DST/retención no revalidados E2E (ver
`specs/024-recurring-events-reminders/verification.md`). **Criterio de
cierre:** ver `specs/024-recurring-events-reminders/spec.md` §Success Criteria.

## P3 — Calidad del agente

### Deuda técnica · Hardening incremental de `mypy src/` ✅ completada — specs/019

Baseline local del 2026-09-27: 93 errores en 14 archivos bajo el modo estricto
actual. El trabajo se hace por grupos cohesivos sin relajar configuración ni
silenciar errores. Resultado: `mypy src/` limpio en 105 módulos; se corrigieron
`GovernedInteractionRunner`, repositorios SQLAlchemy y helpers de tools. Ver
`specs/019-mypy-hardening/`.

### Calidad estática · `mypy src/` como gate CI ✅ completada — specs/020

Con aprobación explícita, el job `quality` ejecuta `mypy src/` después de Ruff y
antes de los tests unitarios. El alcance mantiene 105 módulos de `src/` con modo
estricto; no incluye tests, scripts ni migraciones. La primera ejecución verde de
GitHub Actions fue confirmada el 2026-09-27.

### BL-34 · Política de contexto por tokens y compactación gobernada 🔶 compactación real implementada localmente (gate barato + resumen vía LLM) — specs/030
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

**Implementado localmente (2026-10-09, specs/030, T1–T6):** política pura de
estimación de tokens (heurística `len//4`, igual que `governed_model.py`),
nueva `context_window_tokens` opcional por ruta y `context_budget` opcional
en `RuntimeConfiguration` (aditivos, no rompen checksums de revisiones ya
persistidas), `select_history_window`/`resolve_num_history_runs`/
`resolve_history_ceiling` sin leer la sesión real de Agno (ceiling aproximado
por tamaño medio de turno, `[1, 10]`) y contrato `CompactionPort` diferido
(solo interfaz; sin generación real todavía — `needs_compaction` degrada
siempre a `truncated` sin compactor configurado). **Cableado:**
`GovernedAgentFactory.create_for_run()` ya sustituye el `num_history_runs=10`
fijo por el techo calculado a partir de la ruta/modelo resuelto en el
snapshot del run; emite `ancora.context.outcome` (metadata-only,
`fits_entirely`/`truncated`) desde la propia factory. 1084 unit tests, Ruff y
`mypy src/` (154 ficheros) limpios — todo dominio puro + wiring testeado con
mocks, sin necesidad de PostgreSQL/Docker.

**Limitaciones conocidas, aceptadas para este incremento (spec.md §8):**
estimación por heurística de caracteres, no tokenizer real por proveedor; el
techo no lee el historial real de Agno (aproximación por tamaño medio de
turno — si el E2E revela desbordes en modelos pequeños, leer la sesión real
queda como extensión futura); compactación real no implementada (el contrato
existe, `needs_compaction` nunca se activa de verdad todavía).

**Pendiente separado, fuera de alcance de este spec:** retención/purga de
sesiones en `agno_runtime` — housekeeping operativo de la tabla de Agno, no
parte de la política de contexto en sí.

**Compactación real activada localmente (2026-10-12), vía el ledger propio
en vez de la sesión de Agno:** el propietario propuso un contador barato
(tokens reales acumulados de la sesión, ya devueltos por el LLM) para no
pagar en cada mensaje el I/O que §6 evitó (leer la sesión completa de Agno),
reservando la lectura cara al momento puntual de cruzar un umbral.
Confirmado antes de implementar: `ancora.llm_usage_events.total_tokens` ya
existe por llamada; solo faltaba un índice en
`telegram_interactions.agno_session_id` (migración `0013_session_token_index`,
`init.sql` sincronizado) para que `LlmUsageRepository.sum_session_tokens()`
(nuevo, `SUM` + `JOIN` indexado) sea barato. Con el flag activo y el umbral
cruzado, `InteractionProcessor._maybe_compact_context()` lee
`TelegramInteractionsRepository.list_session_exchanges()` — **el propio
ledger gobernado de AncoraMind (mensaje del usuario + respuesta final del
Agent, ambos ya cifrados), nunca la tabla interna de Agno** — descifra con
el mismo `TelegramPayloadCipher`, toma el ~40% más antiguo
(`context_policy.service.oldest_fraction_count`, ratio configurable) y pide
un resumen real vía LLM a `GovernedContextCompactionAdapter`
(`src/agent/context_compaction_access.py`, ruta lógica dedicada
`ancoramind-context-compaction`, mismo patrón standalone-context que Dream).
El resumen se añade como bloque extra de `instructions` para ese run
(`GovernedAgentFactory.create_for_run(..., compaction_summary=...,
reduced_history_runs=...)`) — nunca se persiste, ni en Postgres ni en la
sesión de Agno. Flag `CONTEXT_COMPACTION_ENABLED` apagado por defecto; un
fallo del compactor nunca aborta el run, solo pierde la mejora para ese
turno. 15 tests nuevos, 1310 unit tests (suite completa), Ruff y
`mypy src/` limpios. Migración del índice escrita pero no validada contra
PostgreSQL real en esta sesión (sin Docker disponible).

**Decisión de diseño que diverge del contrato original:** `CompactionPort`/
`CompactionOutcome` (`compaction.py`) seguían pensados para turnos reales de
Agno (`ConversationTurn`, opacos) — exactamente el I/O que §6 evitó. Este
incremento no los activa; usa un contrato nuevo y más simple,
`SessionSummarizationPort`/`SessionExchange` (`session_summary.py`), sobre
el ledger propio. `CompactionPort` queda sin usar, documentado como tal —
no se ha borrado por si una futura necesidad de resumir la sesión real de
Agno (no solo el ledger) lo retoma.

**Hallazgo colateral corregido (2026-10-12):** al replicar el patrón de
Dream (`src/agent/dream_access.py`, specs/029 T3) para
`context_compaction_access.py` se encontró que `dream_access.py` nunca
abría `execution_context_scope(context)` antes de `agent.arun()` — con un
modelo real envuelto por `build_governed_model` (no el `Model` directo que
usan sus propios tests), eso lanzaba `GovernanceViolationError`
(`current_execution_context()` sin contexto activo). Corregido con el mismo
patrón ya usado en `src/agent/document_extraction.py`: `model_for`+
`agent.arun()` ahora corren dentro de `with execution_context_scope(context):`.
Nuevo test de regresión en `test_dream_access.py`
(`test_consolidate_opens_its_own_execution_context_scope`) que construye un
modelo gobernado real vía `build_governed_model` (no el `Model` plano que
usan los demás tests de este fichero, que nunca habría detectado el gap) y
confirma `outcome.status == "completed"` con `budget.model_calls == 1`;
verificado manualmente que ese mismo test falla con
`GovernanceViolationError` si se revierte el fix. 1311 unit tests (suite
completa), Ruff y `mypy src/` limpios.

### ~~BL-37~~ · Cerrar gates de calidad detectados en auditoría técnica (2026-09-27) ✅ implementado — 2026-10-07
Auditoría de arquitectura/consistencia sobre `main.py`, `ancora_agent.py`,
`governed_model.py`, `governed_agent_factory.py`,
`governed_interaction_runner.py`, tools de `todos`/`notes`/`maintenance`/
`calendar`/`reminders`/`vehicles`, `repositories/actions.py`,
`domain/llm_access/`, `storage/`, `domain/interactions/commands.py` y
`notifications/markup.py`: no se detectó drift arquitectónico respecto a
AGENTS.md §2 ni a los ADRs vigentes. Dos gaps de configuración de gates quedan
pendientes de decisión de prioridad (no aplicados directamente por ser cambios
de policy transversal, no fixes puntuales de código):

- **Ruff sin reglas de docstrings** (`D`) ni de seguridad (`S`) en
  `pyproject.toml` `[tool.ruff.lint]`, pese a que el docstring de cada tool en
  `src/agent/tools/` es el contrato/schema que ve el LLM (AGENTS.md §4).
  Evaluar activar `D` al menos sobre `src/agent/tools/` vía `per-file-ignores`
  inverso, y `S` sobre todo `src/` si el ruido de falsos positivos es
  manejable.
- **`pytest-cov` instalado sin `--cov-fail-under`** en
  `[tool.pytest.ini_options]`: la cobertura se mide pero no es un gate real de
  CI. Fijar un umbral y añadirlo al pipeline una vez medida la cobertura base
  actual.

Los hallazgos de menor severidad (mensajes de error genéricos sin distinguir
payload inválido de fallo de infraestructura en `calendar.py`, `reminders.py`
y `maintenance.py`) se corrigieron directamente en la misma fecha: se añadió
`except (KeyError, TypeError, ValueError)` antes del `except Exception`
genérico, siguiendo el patrón ya existente en `vehicles.py`/`todos.py`.

**Resuelto (2026-10-07):**
- **`D` activado solo sobre `src/agent/tools/`** vía un `ruff.toml` anidado
  en ese directorio (`extend = "../../../pyproject.toml"`,
  `extend-select = ["D"]`) — el `per-file-ignores` "inverso" sugerido no es
  viable en Ruff (los ignores de varios patrones que matchean el mismo
  fichero se unen, nunca se restan; verificado empíricamente). Único hallazgo:
  38 `D413` (falta línea en blanco tras `Args:`), autocorregido con `--fix`;
  cero `D1xx` — todas las tools ya tenían docstring.
- **`S` activado en todo el proyecto** (`select` en `pyproject.toml`).
  `S101` (`assert`) se ignora globalmente: dispara igual sobre asserts de
  *type narrowing* bajo `mypy strict` que sobre asserts reales, sin señal
  útil fuera de contexto. `tests/**` ignora todo `S` (asserts son el propio
  idioma de pytest; "contraseñas hardcodeadas" son literales de fixture).
  `scripts/*.py` ignora `S310`/`S603`/`S607`/`S104` (CLIs de operador con
  HTTP/subprocess deliberado contra URLs/rutas que el propio operador
  proporciona). `migrations/versions/*.py` ignora `S608` (las migraciones DDL
  interpolan listas/constantes del propio código, nunca entrada de usuario).
  4 hallazgos reales corregidos con justificación inline en vez de
  silenciarlos: `src/agent/server.py` (`S104`, bind `0.0.0.0` fuera de
  development — lo exige el contenedor de Railway), `src/repositories/
  todos.py` (`S608` × 2 — los fragmentos de la cláusula dinámica son
  literales fijos, los valores van siempre por `params`),
  `src/observability/telemetry.py` (`S110` — el `except: pass` pasa a
  `logger.debug(...)` sin contenido, igual que el patrón ya usado en la
  función vecina).
- **`--cov-fail-under` real en CI.** Cobertura base medida con
  `pytest tests/unit/ --cov=src` (reproduciendo el entorno de CI): 76%. Los
  tests de integración cubren una porción distinta (repositorios/DB, ~46%
  en solitario) así que el umbral no puede ser global vía
  `pytest.ini_options addopts` sin romper ese job. Se fija
  `[tool.coverage.report] fail_under = 70` (leído automáticamente por
  `pytest-cov` vía `coverage.py`) y se añade `--cov=src --cov-report=term-missing`
  solo al step "Unit tests" de `.github/workflows/ci.yml`; el job
  `integration` queda sin tocar.

Verificado: `ruff check src/ tests/ scripts/ migrations/` y `mypy src/`
limpios, 912 unit (76% cobertura, gate en 70% superado) + 141 integration
passing.
**Criterio de cierre:** cumplido — `D`/`S` aplicados con `ruff check` limpio,
`--cov-fail-under` real en el pipeline con `pytest tests/unit/` en verde.

### BL-8 · Evals agentic 🔶 en curso — specs/014 + 018
Base determinista implementada: contrato JSON v1, runner local sin llamadas a
LLM/tools/servicios y 36 casos sintéticos actuales para `confirmation`,
`documents`, `response_style`, `security`, `tool_selection` y `vehicle` (15 en la
entrega inicial). El runner valida schema, cobertura, expectativas
contradictorias y ausencia de secretos obvios; ejecutar
`python scripts/run_evals.py` tras cambios de prompts/models/tools.

**Actualización 2026-09-27 (specs/018):** `src.agent.evals` materializa los
catálogos ya validados en casos tipados, inyecta un executor aislado y compara
determinísticamente outcome, tool requerida/vetada y confirmación. El reporte
proyecta sólo metadata; input, contexto y respuesta permanecen en memoria. No
crea Agent, provider, `LLMAccess`, sesión de DB ni tools de producción.

**Actualización 2026-10-03 (specs/018 T6):** adaptador físico implementado
localmente — `GovernedPhysicalEvalExecutor`
(`src/agent/eval_physical_executor.py`) ejecuta un Agent real por caso,
modelo resuelto vía `LLMAccess` inyectado (nunca un provider directo),
`RuntimeConfigSnapshot`/budget propios de evaluación (bootstrap, sin
PostgreSQL) y un catálogo de 15 tools simuladas sin I/O
(`src/agent/eval_tools.py`, sin importar `src.repositories`/`src.storage`/
tools de producción). Probado solo con un `Model` scripted en memoria — sin
credenciales, sin red, sin coste (`tests/unit/test_eval_tools.py` +
`tests/unit/test_eval_physical_executor.py`, 705 unit tests en total).
`outcome` se deriva únicamente de las tools realmente invocadas; un sentinel
`no_tool_call` sustituye a `clarify`/`safe_response` cuando no se invoca
ninguna (distinguirlos exige juzgar el texto de respuesta — eso es T8, no
T6). Detalle en `specs/018-agentic-evals-execution-harness/verification.md`.

**Actualización 2026-10-14 (specs/018 T6b):** los casos de confirmación ya no
fingen que el Agent llama `execute_*`. `CoreConsentEvalExecutor` modela en
memoria el camino Core de propuesta presentada → claim válido → mutación
canónica, y los negativos de cero/múltiples propuestas, propuesta no presentada,
expirada, principal distinto y descarte. Incluye `WRITE_TRIVIAL` fuera del
pipeline de confirmación. No importa repositorios/SQLAlchemy/Telegram ni
ejecutores productivos; los 7 casos de `confirmation` se ejecutan contra este
harness y el catálogo suma 36. No sustituye integración PostgreSQL ni una
evaluación semántica/LLM real.

**Preparación T8 local (2026-10-14, sin inferencia):** contrato puro
`eval_semantic_scoring` para juez opcional por criterio, estado explícito
`not_evaluated`, calibración y baseline compatible por ruta/revisión/rúbrica/juez.
Nueve ejemplos sintéticos buenos/malos/ambiguos se validan como
`provisional_synthetic`; no pueden calibrar un juez hasta que haya etiquetas
`human_reviewed`. El runner estático sigue sin llamar modelos ni red.

**Pendiente:** T7 — ejecutar la modalidad LLM real contra el adaptador físico
ya construido, con credenciales, acceso y campaña explícitamente aprobados,
fuera de CI por defecto. Reserva estimada 0,10 USD aceptada, no autorización de
inferencia ni recursos Railway; preparación remota y gates concretos pendientes.
T8 — acordar scoring semántico y baseline por ruta lógica con
etiquetas humanas (bloqueado por etiquetado manual del propietario). No
almacenar contenido personal en datasets, outputs ni telemetría.

**Secuencia acordada (2026-10-17):** incrementos inmediatos 1–2: motor único
reutilizable por consola/futura web y campaña humana puntual en servicio privado
temporal separado. Después: golden set revisado (casos del Agent y ejemplos para
validar al juez separados), piloto Jev con Decisions API compatible con Gateway,
calibración/validación independiente, segunda opinión y solo entonces automatización
acotada/gates si se aprueban. Nueve ejemplos provisionales no son golden set; web
no implementada ni requisito de T7, sin CI pagada ni ampliación de cinco casos.
Ver specs/018 `incremental-roadmap.md` y `tasks.md` T7c–T7d. BL-8 continúa abierto.
**Legibilidad de la revisión humana (2026-10-20; specs/045, propuesta):** la
consola de revisión vuelca el caso completo una vez por criterio, en JSON
compacto, con errores genéricos y estado solo en JSON. Spec 045: caso impreso una
vez, secciones legibles con escapado intacto, `reason` de error de lista cerrada
y `--human` en `status`/`session-status`. Seguir revisando tras un fail **no
cambia** (decisión del propietario). Sin módulos nuevos fuera de la allowlist
`_HARNESS` de specs/042; cambia la huella del harness (commit/CI/publicación
manual) pero no amplía gasto. No desbloquea la publicación pendiente. Evidently
valorado el mismo día: aparcado mientras haya 5 casos y un solo run (retomar con
golden set de decenas de casos, 3+ ejecuciones comparables y un juez calibrado).
Phoenix **no** está aparcado: sigue su propio camino en ADR-007 (trazas de
producción con contenido enmascarado) y es independiente de este incremento.



**Propuesta para el siguiente incremento (2026-09-26; no implementada):** probar
Jev como juez semántico *opcional* de los casos sintéticos de `response_style`,
después de ejecutar el Agent gobernado y comprobar por código tools, resultados
observables y confirmaciones. Comparar puntuaciones con etiquetas humanas y un
baseline versionado antes de adoptar umbrales o CI; Jev no autoriza acciones ni
sustituye los gates deterministas de seguridad. Ver
`specs/014-agentic-evals/jev-pilot-proposal.md` para alcance, compatibilidad
pendiente con `LLMAccess`/Gateway, presupuestos y criterios de decisión.

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

### ~~BL-15~~ · Botones de confirmación en Telegram (HITL UX) ✅ resuelto por BL-40/specs/023 T4.3 — 2026-10-10

El hallazgo original seguía vigente para la interfaz Telegram **nativa de
AgentOS** (que efectivamente ignora `callback_query` y no soporta inline
keyboards) — pero esa ruta ya no es la que gobierna producción: la admisión
durable propia (specs/013) la sustituye por completo cuando
`TELEGRAM_ADMISSION_ENABLED`. Sobre esa ruta propia, BL-40 (specs/023 T4.3)
implementó botones de confirmación inline **reales**, sin tocar internals
de Agno — ninguna de las tres vías (a)/(b)/(c) que este ítem planteaba
originalmente, sino un cuarto camino que resultó más simple al no depender
del runtime de AgentOS en absoluto:
`normalize_telegram_update` (`src/domain/interactions/models.py`) ya
reconoce `callback_query` como tipo de update válido;
`TelegramNotifier.send_text` (`src/notifications/telegram.py`) envía
`reply_markup` con los botones ✅ Sí/❌ No reales
(`consent_buttons`/`ConsentButton`, `src/domain/actions/presentation.py`);
`InteractionProcessor._handle_consent_input`/`_handle_consent_callback`
(`src/domain/interactions/processor.py`) resuelven el callback **antes**
de cualquier ejecución del Agent, re-validando principal/bot/chat/ventana/
hash del payload en `ActionProposalsRepository.claim_confirmation` — el
`callback_data` nunca es prueba de consentimiento por sí mismo. Activo
detrás de `GOVERNED_CONSENT_ENABLED` (default `false`, mismo patrón de
rollout que el resto de flags opt-in). Se cierra como resuelto en vez de
dejarlo abierto con texto obsoleto; el E2E real contra Telegram/Railway
sigue pendiente igual que el resto del pipeline (bloqueado por BL-18).

### BL-16 · Retirar workaround SafeOpenRouter cuando Agno valide tool calls 🔶 protección compartida — specs/034
El E2E de specs/006 descubrió que `minimax/minimax-m3:free` vía OpenRouter
(backend GMICloud) emitió un tool call vacío junto al válido. Agno 2.9.0 le
añadió UUID, lo persistió y OpenRouter rechazó el siguiente turno. Workaround
actual: `SafeOpenRouter` filtra calls incompletos en las rutas streaming y
no-streaming antes de ejecutar/persistir. Es acoplamiento a métodos privados
de Agno.
**Criterio de cierre:** al actualizar Agno o cambiar de modelo/proveedor,
reproducir el caso; si Agno ya filtra llamadas incompletas, eliminar subclase
y sus tests. Mientras exista, test unitario obligatorio sobre la forma exacta.

**Revisión e incremento local (2026-10-11, specs/034):** el repro sintético
con Agno **2.9.0** confirma que `OpenRouter` y `OpenAILike` nativos aún
conservan llamadas vacías; el segundo era el adaptador elegido por LiteLLM
y por tanto no recibía el filtro de `SafeOpenRouter`. Corregido mediante
`ToolCallSafetyMixin` compartido + `SafeOpenAILike` seleccionado por la
factory `openai-like`, también bajo `AgnoLLMAccess`. Se mantienen retries
cero, Gateway privado/fail-closed, snapshots, budget y auditoría; el modo
gobernado sigue rechazando sync/streaming. Los deltas streaming solo se
filtran **después** de consolidarlos; llamadas válidas conservan orden y
argumentos, y Agno sigue generando IDs ausentes. El filtro admite ausencia
de llamadas (`[]`/`None`) y rechaza nombres no-string o solo espacios, sin
convertirse en un validador de argumentos/autorización.

La revisión del código upstream **v3.1.2** encontró las mismas
implementaciones de los tres métodos relevantes que en 2.9.0; no se instaló
ni ejecutó 3.x, fuera del rango del proyecto. **BL-16 sigue abierta:** el
criterio de retirada no se cumple. Pruebas offline del modelo compuesto
por `AgnoLLMAccess` cubren solo vacías → un turno y ninguna tool; vacías +
válida → una ejecución y siguiente turno con historial limpio; también
budget, usage y caminos prohibidos. Sin inferencia, E2E ni cambios remotos.
Evidencia y procedimiento de retirada: `specs/034-tool-call-safety/`.

**Validación:** 1199 unit pasando (78,58 % cobertura, gate 70 % superado),
143 integration pasando + 1 smoke live omitido; Ruff y `mypy src/` limpios
(161 módulos), catálogo de 27 evals válido y diff-check limpio. 49 casos
adicionales: 44 nuevos + parametrización de las 5 regresiones originales
para ambos adaptadores. El SDK OpenAI/parser/loop se prueban con
`httpx.MockTransport`, sin sockets externos. La suite integration tuvo dos
fallos de timing en STT (timeout de 50 ms antes de entrar al mock), pasó en
aislamiento y en la repetición final completa; no se modificó voz.

### ~~BL-17~~ · Mantener indicador «escribiendo…» durante procesos largos ✅ resuelto por specs/013 — 2026-10-11

El hallazgo original seguía vigente para la interfaz Telegram **nativa de
AgentOS** (`send_chat_action` una sola vez, sin refresco) — pero, igual que
BL-15, esa ruta ya no gobierna producción: la admisión durable propia
(specs/013) la sustituye por completo cuando `TELEGRAM_ADMISSION_ENABLED`.
Sobre esa ruta propia, `InteractionProcessor._run_agent` ya lanza
`_refresh_typing` como tarea en paralelo al arrancar el run
(`asyncio.create_task`, `src/domain/interactions/processor.py`), que llama
a `sender.send_typing(chat_id)` cada `typing_refresh_seconds` mientras el
run está en curso, y la cancela siempre en el `finally` del bloque
principal (`typing_task.cancel()` + `await` con `CancelledError`
suprimida) — tanto en éxito como en error, exactamente lo que este ítem
pedía. Cubierto por
`test_processor_refreshes_typing_while_agent_run_is_pending`
(`tests/unit/test_interaction_processor.py`). Se cierra como resuelto en
vez de dejarlo abierto con texto obsoleto sobre una ruta que ya no
gobierna producción.

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
matrícula formateada y OpenRouter streaming listos. **Actualización
2026-10-18:** el re-test Telegram de documento/búsqueda que cerraba T7 ya se
cubrió con el E2E completo de M1-M5 en Railway (2026-10-17, ver BL-1/BL-18).
pgvector: disponible (0.8.2), NO instalado — diseño solo hasta BL-6.


**Hardening RLS desplegado (2026-10-15, incremento 1):** revisión Alembic
`0015_ancora_rls_hardening` habilita RLS sin policies (default deny) en todas
las tablas `ancora` y revoca acceso actual/futuro de `PUBLIC`, `anon` y
`authenticated`. `service_role` no se revoca: ya carece de grants SQL en
`ancora` y la credencial server-side se usa para el bucket privado Storage.
El runtime PostgreSQL continúa como `postgres`/`BYPASSRLS`; aislamiento backend
real con roles dedicados queda separado. Confirmado en producción: head 0015,
24/24 tablas con RLS, cero policies y cero grants para roles Data API. Security
Advisor refleja los 24 avisos informativos esperados por default-deny y dos
warnings independientes que requieren triage separado. Integración local:
159 superadas, una STT live omitida; las 4 pruebas de migración están verdes.

**Hardening local adicional (2026-10-15):** revisión
`0016_voice_guard_search_path` fija `search_path=''` en
`ancora.voice_preparation_parent_guard`, cuya única relación ya está cualificada.
Fresh install, downgrade/upgrade, equivalencia de `init.sql` y `pg_proc.proconfig`
validados contra PostgreSQL real (**4 migration tests passed**), más unit guards,
Ruff y mypy limpios. La suite global reprodujo el fallo de timing STT preexistente
de 50 ms documentado en specs/034 (el mock no llega a invocarse bajo carga); el
módulo focal pasa 4/4 y la suite sin ese único nodo pasa. Pendiente aplicar el
mismo SHA a Supabase y confirmar que desaparece `function_search_path_mutable`;
`vector` en `public` se triagea aparte.

---

### BL-43 · Pantalla de administración centralizada 🔶 implementado localmente — specs/027

**Incrementos locales 2026-10-22 (sin nuevo despliegue):** organización en pestañas
y salud compacta (`82d924e`); gráficos FinOps/calidad (`64bd683`, specs/043):
columnas diarias compactas, anillos coste/estados y barras ejecutadas/descartadas/
caducadas sin umbrales. Catálogo de prompts specs/048 preparado localmente:
cuarta pestaña con contenido, referencias estáticas, SHA-256 e histórico real
exportado para el paquete sin `.git`. No editor/aprobaciones/activación ni evidencia
prompt efectivo por run. 2260 unitarias/2 skips, Ruff/mypy 187 y navegador aislado
superados en ese incremento; no cierre remoto de BL-43. Documentación funcional
en `docs/runbooks-027-admin-dashboard.md`; evidencia en specs/027, 043 y 048.
Los cuatro paneles descritos más abajo corresponden al incremento original.

**E2E remoto parcial 2026-10-17:** panel HTTPS, auth/separación token CLI,
login, emisión/listado de invitación manual, sessionStorage sin localStorage y
logout validados. Cuenta evaluadora completó circuito manual sin inferencia.
Flags temporales cerrados y acceso revocado, sin cambio runtime-config. Falta
timeout real por inactividad y resto de matriz; no cierre global de BL-43.
Incidencia acotada de redacción de código agotado en salida diagnóstica del
agente documentada en campaña. Evidencia en specs/027 y campaña MVP.

**Preparación onboarding 2026-10-17:** reforzada autenticación de las ocho rutas
JSON, separación token panel/CLI y actor/motivo con 32 unitarias; 7 integraciones
reales nuevas prueban emisión del panel más decisiones CLI sobre la misma DB
aislada. Validación global: 1536 unitarias, 183 integraciones/1 live omitida,
Ruff/mypy limpios. Evidencia en specs/027 y guion en
`docs/preflight-onboarding-admin.md`. Sin arranque operativo ni activación remota;
no se añaden botones de aprobación/revocación ni se declara cierre de BL-43.

AncoraMind depende hoy de varias piezas externas (Railway, Supabase,
OpenRouter, LiteLLM Gateway, Grafana) además de dos superficies HTTP de
administración propias — `/admin/runtime-config/*` (BL-23/specs/013) y
`/admin/telegram-pairing/*` (BL-24/specs/017) — operadas sólo desde dos
scripts CLI. Se añade `GET /admin/dashboard`: una página HTML autocontenida
(sin build, sin dependencias nuevas) con cuatro paneles — invitaciones de
pairing, runtime-config (status/validar/crear revisión/activar/rollback, con
paridad completa frente al CLI), salud (`GET /health/readiness` tal cual) y
enlaces centralizados a las plataformas externas (estáticos salvo Supabase y
LiteLLM Gateway, que reutilizan el estado ya calculado por `HealthRegistry`).
Gateada por `ADMIN_DASHBOARD_TOKEN`, un secreto nuevo y propio — distinto de
`RUNTIME_CONFIG_ADMIN_TOKEN` — porque el dashboard vive en un navegador (más
expuesto que una terminal); su backend llama directamente a
`TelegramPairingService` y al `RuntimeConfigManager` ya existente, sin
reenviar peticiones HTTP a los admin API existentes. Los CLIs
(`scripts/runtime_config.py`, `scripts/telegram_pairing.py`) siguen
funcionando sin cambios; conviven con el dashboard como dos fachadas sobre el
mismo dominio.
**Criterio de cierre:** validado a mano en Railway con las variables
`ADMIN_DASHBOARD_*` configuradas (ver specs/027/verification.md y
`docs/runbooks-027-admin-dashboard.md`).

### BL-44 · Parada de emergencia manual para Agent/LLM 🔶 implementado localmente, persistencia diferida — specs/031

Hasta ahora sólo existía un hard-stop **automático** al 90% del gasto
(`CostGovernanceConfig.hard_stop_threshold_pct`) — nada que el propietario
pudiera accionar a mano si la aplicación falla de forma general o el gasto se
dispara de otra manera no cubierta por ese umbral. Surgió al definir BL-43,
que deliberadamente lo dejó fuera de alcance por tocar la ruta crítica de
`LLMAccess`/`GovernedModel`.

**Implementado localmente (2026-10-10, specs/031):** `EmergencyStopManager`
(`src/domain/emergency_stop/`) cachea el estado en memoria del proceso
(mismo patrón que `RuntimeConfigManager`, cero I/O en el camino de
inferencia) y se comprueba en **dos puntos**: antes de construir el
`ExecutionContext` en `GovernedInteractionRunner.prepare_execution_context`
(barato, evita arrancar el Agent) y, sobre todo, dentro de
`GovernedModelMixin.ainvoke` — el único punto que intercepta **cada**
llamada física al Gateway, así que puede interrumpir un run ya en marcha
atrapado en un bucle de tool calls caro, que el chequeo de nivel-run no
cubre. `InteractionProcessor` trata `EmergencyStopActiveError` igual que
`CostGovernanceError` (`FAILED_CONTROLLED`, nunca se reintenta). API admin
HTTP (`GET/POST /admin/emergency-stop/*`) reutilizando el mismo gate que
`runtime_config_admin.py` (`RUNTIME_CONFIG_ADMIN_ENABLED`/
`RUNTIME_CONFIG_ADMIN_TOKEN`, sin secreto nuevo) + CLI
(`scripts/emergency_stop.py`, mismo esqueleto que `scripts/runtime_config.py`).
`get_emergency_stop_manager()` (`src/agent/emergency_stop_runtime.py`, mismo
patrón que `get_telemetry()`/`get_session()`) expone un único manager para
todo el proceso: `_get_document_service()` (extracción de documentos) y
`GovernedDocumentEmbeddingAdapter.embed()` (recuperación semántica,
BL-42/specs/026 — llama a su endpoint OpenAI-compatible directo, sin pasar
por `AgnoLLMAccess`, así que tenía su propio chequeo) también respetan el
interruptor. 31 tests nuevos, 1111 unit tests (suite completa), Ruff y
`mypy src/` (160 ficheros) limpios.

**Limitaciones conocidas, aceptadas para este incremento (specs/031 §8):**

- **Sin persistencia durable** — sin Postgres/Docker disponibles en esta
  sesión, el estado vive solo en memoria del proceso: un restart lo borra y
  vuelve a `active=False`. La tabla Postgres + repositorio real detrás del
  mismo `EmergencyStopReader` quedan como siguiente incremento explícito
  (mismo patrón que BL-13/Dream T1).
- **Panel visual en `/admin/dashboard` diferido** — decisión explícita de
  este incremento; la API HTTP y el CLI ya permiten operar manualmente.
- **Sin broadcast multi-instancia** — cada réplica tendría su propio estado
  en memoria (no es un escenario de despliegue actual conocido).

### BL-56 · Trazas con contenido enmascarado en Phoenix 🔶 implementado local con flag OFF (T1–T9); falta runbook, SHA/CI y activación — specs/046 + ADR-007

Hoy no se puede saber qué vio el modelo ni por qué falló una petición concreta
(p. ej. `InvalidPresentationOutputError` solo deja un contador). ADR-007
(*Proposed*) propone Arize Phoenix autoalojado con contenido enmascarado.

**Estado (2026-10-20):** Phoenix 15.1.0 + Postgres propio (`Postgres-lM2q`)
desplegados por el propietario en Railway (`ancoramind-app`), auth activa,
retención 30 días, `PHOENIX_TELEMETRY_ENABLED=false`, contraseña inicial cambiada
y API key generada. Sin conexión con la app: no hay código, variables ni
dependencias `openinference`; no recibe ni guarda datos personales. Dominio
público aún presente; retirarlo (acceso solo por red privada) queda pendiente.

**Incremento local autorizado (2026-10-22):** masking existente conservado;
`scripts/phoenix_spike/` implementa exporter experimental fail-closed por span,
allowlist/esquema/patrones y reconstrucción de superficies SDK, sin imports desde
la app. Agent gobernado real + HTTP simulado, terminal/correlación/aislamiento,
fallo de sink y benchmark 50+50; backend Phoenix15.1 local desechable con auth,
OTLP enmascarado y borrado por seudónimo probado. Sin LLM real, Railway ni flag.
Informe Q1–Q9: `specs/046-phoenix-masked-traces/spike-result.md`.

**Pendiente, no implementado en producción:**
- Cierre sin reservas del spike: coste recibido como atributo no demuestra
  cálculo/UI, overhead sin SLO aceptado, no prueba fresh install ni backend PG.
- Seam de captura confiable: mensajes genéricos/historial pueden arrastrar
  documentos/voz; no basta allowlist de nombres. No auto-instrumentar globalmente.
- Aceptación del ADR-007 y de la enmienda acotada del principio 11 por el
  propietario. Decidido (2026-10-20): entran las trazas de todos los usuarios
  autorizados, sin lista adicional; exige actualizar los términos del piloto y el
  inventario de privacidad antes de activar el flag.
- Integración del exporter productivo y configuración (sin activar por defecto),
  tests de privacidad y actualización de `docs/production-security-privacy.md`.

**Gobernanza:** propietario autoriza este trabajo aislado; no equivale a aceptar
ADR-007 ni habilitar captura. No bloquea ni reabre incrementos existentes;
Grafana (ADR-006) sigue sin contenido.

**Implementación local (2026-10-25, T1–T9, flag OFF, sin desplegar):**
`phoenix_export.py`, `phoenix_capture.py` y `field_policy.py` en
`src/observability/`; captura manual en `GovernedInteractionRunner.run`; el
processor pasa `capture_user_text` (falso para voz y texto sintetizado). Spans por
tool con metadatos y mensaje de error acotado y enmascarado. Test de extremo a
extremo de privacidad y fail-open (`test_phoenix_pipeline_privacy.py`). Detalle y
decisiones del propietario en `specs/046-phoenix-masked-traces/{spec,tasks}.md`;
inventario y límites en `docs/production-security-privacy.md`. Sin variables
`PHOENIX_*` en Railway (comprobado por nombre el 2026-10-25).

**Hallazgos de T7/T9 que no son de Phoenix (decisión del propietario pendiente):**

- *Corregido:* los spans de Grafana copiaban el mensaje y la traza de una excepción
  de tool (`telemetry.py`). El contenido manejado hasta hoy es ficticio.
- *Abierto:* `purge_expired_payloads` (payloads de `failed_ambiguous` a 7 días) está
  implementada y probada, pero **ningún código de producción la invoca**. Los
  términos del piloto prometían ese borrado; el texto ya dice que hoy no es
  automático. Cablear la purga en un worker o cambiar la promesa.
- *Abierto (ya anotado por el propietario):* `agno_runtime.agno_sessions` guarda
  sin enmascarar los resultados de las tools, sin retención (BL-34).

---

### BL-57 · Ataques adaptativos con PyRIT (red-teaming iterativo) 🆕 diseño documentado, sin implementar — specs/051

El piloto de PyRIT (2026-10-26) usó la librería como **generador de texto fijo**:
90 variantes (68 deterministas + 22 paráfrasis con LLM), 12 pasadas con el evaluador
ligero, 0 `fail`, ninguna tool de escritura llamada, unos 0,41 USD de 2 USD
(`docs/academic/modulo-4-seguridad-riesgos.md` §5.3). No mide a un atacante que
**ve la respuesta y reintenta**, que es lo que más se parece a un adversario real. El
propietario quiere abordarlo "en lo que sea posible" cuando haya tiempo.

**Hallazgo clave:** los ataques multi-turno de PyRIT (`RedTeamingAttack`, Crescendo,
PAIR, TAP) asumen un atacante que escribe en el turno del usuario, y el riesgo de
AncoraMind es la **inyección indirecta** (datos devueltos por una tool). PyRIT v1.1.0
trae `XPIAWorkflow` (cross-domain prompt injection), que encaja mejor, pero hace un
solo intento: la adaptación habría que construirla.

**Qué falta (nada de ello probado, ver la spec):**
- Un adaptador que coloque el texto del atacante en el `context` del caso (la pieza que
  no existe en PyRIT ni en el evaluador) y un target que envuelva el Agent.
- Un scorer **determinista** (¿se llamó a una tool prohibida?), en lugar de un LLM
  scorer: el éxito del ataque ya es observable por código y evita el ruido del juez.
- Un canal entre el venv de PyRIT (aislado, sin `src/`) y el del repo.
- Tope de gasto por ataque y global, con `RETRY_MAX_NUM_ATTEMPTS=1` y SDK sin
  reintentos (PyRIT reintenta 10 veces por defecto).

**Plan por fases, cada una con su presupuesto y su decisión:** 0) bucle sin LLM
(0 USD); 1) atacante simple sin PyRIT (~0,05 USD); 2) `RedTeamingAttack` de PyRIT
(~0,10–0,30 USD); 3) Crescendo/PAIR/TAP solo si las anteriores muestran algo. Las cifras
son estimaciones del agente, no medidas.

**Restricciones heredadas:** no sustituye ni modifica el evaluador ligero (specs/049);
no promueve `security_pyrit` a categoría viva (decisión del 2026-10-26); sin Gateway
(decisión de capstone, OpenRouter directo con la clave de evals); cero escritura real
(tools simuladas, sin DB ni Telegram). Prioridad: **opcional**, no bloquea ningún
orden de la tabla de prioridades.

### BL-58 · Evals de adjuntos desfasados respecto al flujo actual 🆕 documentado, sin tocar

**Hallazgo (2026-10-26):** el Core archiva el adjunto antes del turno e inyecta al Agent
un bloque «Adjuntos archivados antes de este turno» (`governed_interaction_runner.py`).
El Agent ya no tiene `analyze_document` y `prompts/skills/documents.md` se lo prohíbe.
Los evals siguen modelando el flujo antiguo:

- `src/agent/eval_tools.py`: registra una tool simulada `analyze_document` que producción
  no ofrece (el defecto más relevante: el Agent evaluado dispone de una tool inexistente).
- `src/agent/eval_physical_executor.py`: pasa el adjunto como `files=`; producción nunca
  da bytes al Agent.
- `evals/documents/cases.json`: `attachment_is_analyzed_once` exige
  `required_tool: analyze_document` y fallaría con el prompt actual;
  `no_invented_archive_confirmation` describe el flujo antiguo.
- `tests/unit/test_eval_tools.py:227` prueba esa tool simulada.
  (`forbidden_tools` de `evals/security/cases.json` la nombra: inofensivo, sirve de centinela.)

**Propuesta:** quitar `files=` y la tool simulada; con `attachment` (y sin
`analysis_completed: false`) inyectar en `run_input` el mismo bloque que construye
producción, reutilizando `render_retrieved_records`; reformular el caso 2 como
`safe_response` con `forbidden_tools: ["analyze_document"]`; el caso 3 sin bloque
(coherente con la regla del prompt). Los recuentos de casos no cambian.

**Por qué no se hizo:** cerrar el documento del trabajo final. Cambiar el catálogo hace no
comparables las pasadas históricas de `documents`, y tocar los ejecutores afecta a
specs/040-042 y 049. Hacerlo como cambio aparte, con su propio commit, y anotar la
ruptura de comparabilidad. Sin inferencia hasta decidirlo. Prioridad (decisión del propietario, 2026-10-26):
**1b** en la tabla de órdenes: no es P0, pero es lo siguiente tras cerrar el orden 1.

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
| Preparación del cambio de modelo por defecto GPT-5.6 Luna → GPT-6 Luna (fallback directo + candidato gobernado `ancoramind-default-r3` + pricing y runbook; rollout remoto registrado en BL-23) | specs/013 + ADR-005 | 2026-09-28 |

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
