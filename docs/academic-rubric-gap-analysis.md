# Gap analysis contra el rúbrico de evaluación del programa

> Fotografía del **2026-10-23** (actualiza la del 2026-10-18) de cómo se posiciona
> AncoraMind frente al texto de evaluación del entregable final (módulos 1-4:
> modelo/coste, flujo agentic, despliegue/evaluación/monitorización,
> seguridad/riesgos). No sustituye a `AGENTS.md`/`docs/architecture.md`.
>
> **Origen:** exploración módulo a módulo del repo, volcada en
> [`docs/academic/`](academic/). Cada fichero contiene el detalle, la evidencia con
> rutas y su propia tabla de huecos (H1…Hn). Este documento los **consolida y
> prioriza**; no repite el detalle.
>
> | Módulo | Material de recopilación |
> |---|---|
> | 1 · Modelos, configuración, costes | [`academic/modulo-1-modelos-config-costes.md`](academic/modulo-1-modelos-config-costes.md) |
> | 2 · Flujo agentic y autonomía | [`academic/modulo-2-flujo-agentic-autonomia.md`](academic/modulo-2-flujo-agentic-autonomia.md) |
> | 3 · Despliegue, evaluación, monitorización | [`academic/modulo-3-despliegue-evaluacion-monitorizacion.md`](academic/modulo-3-despliegue-evaluacion-monitorizacion.md) |
> | 4 · Seguridad y riesgos | [`academic/modulo-4-seguridad-riesgos.md`](academic/modulo-4-seguridad-riesgos.md) |
>
> **Contexto de esta fotografía:** la plataforma Railway no está disponible, así
> que no se ha consultado ningún servicio remoto. Todo lo remoto se cita como
> afirmación documental con su fecha. La última validación en producción
> registrada en el repo es del **2026-10-17** (SHA `778c5a3`, readiness 200); los
> incrementos del 2026-10-22 (dashboard con pestañas, catálogo de prompts…) sólo
> están validados en local. Las propuestas de los ficheros `academic/` son
> **propuestas**, no decisiones.

## 1. Lectura global

Según el baremo (5-7 por reflejar los conceptos; 7-9 por estar implementado aunque
no completamente desplegado; 9-10 por estar completo y sin carga de mantenimiento
para terceros), AncoraMind está en la banda **7-9**: casi todo lo exigido está
implementado, con evidencia real de producción hasta el 2026-10-17.

Lo que separa de la banda 9-10 no es trabajo de fondo sino **cuatro carencias de
evidencia**, que además son las que el enunciado nombra explícitamente:

1. **Ningún LLM-juez ha corrido** (módulo 3) y **ningún framework de red-teaming**
   (módulo 4). Ambos están diseñados/documentados y no ejecutados.
2. **No hay medición de calidad con un modelo real.** De 5 casos autorizados en la
   campaña de evals se evaluó 1; no hay baseline ni pass-rate (módulos 2, 3 y 4).
3. **Los pases a producción son manuales** y no hay lockfile, escaneo de
   dependencias ni protección de rama (módulo 3, criterio 9-10).
4. **Varias piezas están diseñadas pero no activas o no verificadas** (alertas,
   parada de emergencia durable, Phoenix, RGPD).

Lo defendible en el PDF es «controles diseñados y verificados con limitaciones
conocidas», no «agente seguro/completo». Los huecos deben aparecer **nombrados y
justificados como decisión de priorización**, no omitidos.

## 2. Estado por módulo

### Módulo 1 — Modelos, configuración, costes

**Cubierto:** modelo vigente y razón de coste/capacidades; Gateway LiteLLM +
`LLMAccess` + runtime config versionada; prompts en Git con historial (16 ficheros,
64 versiones en `src/agent/prompt_history.json`); coste medido por interacción
(media ≈ 0,0034 USD) y proyección por niveles (`docs/model-selection-and-cost-projection.md`),
con topes de presupuesto que fallan cerrado.

**Huecos (consolidados de `academic/modulo-1…` H1-H13):**

| # | Hueco | Esfuerzo | Gasto | Deploy |
|---|---|---|---|---|
| M1-1 | **Motivo de GLM 5.3 Flash → GPT-6 Luna** y comparación de calidad: no documentado y no se reconstruye. Sólo hay evidencias de *rechazo* (minimax free, MiMo `r5` que incumplió `present_reply`, GLM razonador). El doc de apoyo omite el experimento `r5` | Bajo (matriz de decisión con hechos y «no medido») / Alto (benchmark real) | No / Sí | No / Sí |
| M1-2 | **Coste real = `NULL`**: todo es estimación; posible fallo propio de lectura de `input_tokens` en no-streaming (hipótesis sin demostrar, comprobable sin red) | Medio | No | Sólo si se corrige código |
| M1-3 | **Ventana de contexto `null`** en la ruta default ⇒ el código usa 8 192 tokens y el historial queda en 3 turnos sin que se haya decidido | Bajo (doc) / Medio (nueva revisión) | No | Revisión |
| M1-4 | **Parametrización**: `temperature`/`top_p`/`max_tokens` no se envían; `max_output_tokens=1024` sólo estima coste; el timeout de 45 s no se aplica al chat | Bajo (declararlo) / Medio (código, cambio evaluable) | No | Sí si hay código |
| M1-5 | **Costes fuera de contabilidad/proyección**: visión (sin precio en rev. 8, BL-51), embeddings, voz, Tavily, Dream, compactación | Bajo (tabla) | No | No |
| M1-6 | **Prompts candidatos/alternativas**: no existen variantes A/B. Sólo evolución lineal y el rediseño del contrato de salida (`AgentReply` JSON → `present_reply`) | Bajo (variantes documentales) / Medio (medirlas) | No / Sí | No |
| M1-7 | **Latencia/TTFT** por modelo y benchmark Gateway vs directo: pendiente | Bajo (extraer del panel) | No | Acceso al panel |
| M1-8 | **Palancas de coste** (caché de prefijo; el prompt de ≈ 7 k tokens se reenvía en 2-4 llamadas) no documentadas | Bajo | No | No |
| M1-9 | **Supuesto de 10 interacciones/usuario/día** no medido; **costes fijos** (Railway, Supabase, Grafana, Tavily) sin cuantificar; precio de Luna sin ficha archivada | Bajo (pedir datos al propietario) | No | No |
| M1-10 | **Inconsistencias a reconciliar** (ver §4) | Bajo | No | No |

### Módulo 2 — Flujo de agente, autonomía, framework

**Cubierto (el módulo mejor cubierto):** niveles de autonomía READ / WRITE_TRIVIAL /
WRITE_REVIEWABLE / EXTERNAL_ACTION / DESTRUCTIVE, confirmación en el Core y no en el
LLM, `present_reply` como salida terminal, ADR-001 con alternativas, SDD con
`spec/tasks/verification`. Cifras medidas el 2026-10-23: 2 262 tests unitarios
recolectados, 219 de integración recolectados, ruff y mypy limpios (187 ficheros).

**Huecos (consolidados de `academic/modulo-2…` H1-H12):**

| # | Hueco | Esfuerzo | Gasto | Deploy |
|---|---|---|---|---|
| M2-1 | **Narrativa proceso de negocio → técnico**: ya redactada en borrador (§5 del fichero del módulo 2, 4 casos). Falta convertirla en capítulo con un diagrama por caso | Bajo | No | No |
| M2-2 | **El nivel de riesgo no está codificado**: sin enum ni registro, `src/governance/` vacío; la política vive en la ruta de código de cada tool. Propuesta: test que exija clasificar toda tool nueva | Bajo-medio | No | No |
| M2-3 | **`analyze_document` es inconsistente**: `prompts/skills/documents.md:13` y `prompts/tool_contract.md:95` ordenan llamarla, y el texto sintético de `processor.py:408` también; está definida en `src/agent/tools/documents.py:450` pero **no se registra** en `_init_domain_tools` (`src/main.py:116-134`). Pendiente de confirmar si la ingesta tiene otro camino determinista previo al Agent. Corregir es un cambio de prompt (**evaluable**) | Bajo | No | No |
| M2-4 | **ADR-001 desfasado**: eligió Agno por su HITL, pero el consentimiento lo implementa el Core. Falta addendum; `architecture.md` §13 y otras secciones «target» contradicen el estado actual | Bajo | No | No |
| M2-5 | **Trazabilidad del uso de copilotos**: 0 trailers `Co-Authored-By` en 268 commits (verificado), sin registro de revisión por PR, `.claude/` no versionado. Redactar «Método de trabajo humano-agente» con ejemplos reales (spec 023, congelación de gobernanza del 2026-10-17, BL-47/BL-48) y mantener el trailer desde ahora | Bajo | No | No |
| M2-6 | **Evaluación real del comportamiento del Agent**: ver §3, hueco transversal T-1 | Medio-alto | **Sí** | Sí o Gateway local |
| M2-7 | **Capacidades implementadas pero no cableadas o con flag OFF**: Dream, compactación, fast-ack; parada de emergencia en memoria. Presentarlas como diseño/implementación local, no como funcionalidad operativa. Su estado en producción no es verificable desde el repo | Bajo | No | No |
| M2-8 | **`EXTERNAL_ACTION` sin acción externa real** en el executor (`NoopCalendarProvider`); el calendario es canónico-only por esa vía. Declarar el matiz (BL-7) | Bajo (matiz) / Alto (real) | No / Sí | No / Sí |
| M2-9 | **Código residual `execute_*`** inerte en los módulos de tools; límites conscientes: BL-45 (sin confirmación por lote) y worker de recordatorios en una réplica sin dead-letter | Bajo | No | No |

### Módulo 3 — Despliegue, evaluación, monitorización

**Cubierto:** despliegue Railway + Gateway + Supabase + Collector/Grafana Cloud;
CI con ruff, mypy, pytest y `export_prompt_history --check`; migraciones Alembic;
evaluador determinista corriendo (`scripts/run_evals.py` valida **59 casos en 6
categorías**; no llama a ningún LLM); harness aislado del Agent y del Core de
consentimiento; `/health/readiness`, OpenTelemetry, ledger de uso en PostgreSQL,
dashboard propio `/admin/dashboard` (FinOps y calidad); 2 260 tests unitarios
pasan (cobertura 81,75 %).

**Huecos (consolidados de `academic/modulo-3…` H-1…H-11):**

| # | Hueco | Esfuerzo | Gasto | Railway |
|---|---|---|---|---|
| M3-1 | **LLM-juez (Jev) no ejecutado.** Hay diseño (`specs/014-agentic-evals/jev-pilot-proposal.md`) y contrato de código (`SemanticJudge`, calibración, baseline), pero no hay adaptador, modelo juez, golden set revisado ni ejecución. El repo no fija modelo juez ni coste: cualquier cifra es propuesta. Piloto sobre `response_style` (26 criterios) | Medio-alto | Sí (céntimos) | No (Gateway Docker local) |
| M3-2 | **Resultados de evals con LLM real**: 1/5 casos. `db0c59b` se interrumpió; `7ea0cf06` pasó el caso 1, el caso 2 abortó con `InvalidPresentationOutputError` y 3 no se iniciaron. Sin baseline ni pass-rate | Medio | Sí (≈ 0,02 USD/caso; tope 0,10) | Sí o local |
| M3-3 | **Alertas**: 6 reglas versionadas, 0 provisionadas en Grafana; `GatewayCircuitOpen` es inalcanzable (`set_circuit_state` sólo se llama con «unknown»); matriz de degradación (BL-33 T7) sin evidencia | Bajo-medio | No | Para probar sí |
| M3-4 | **Calidad de negocio en producción**: sólo proxies (propuestas ejecutadas/descartadas). Sin feedback de usuario ni muestreo | Medio | Sólo si hay juez | Sí para observar |
| M3-5 | **Automatización de pases a producción (criterio 9-10)**: despliegue manual con «Wait for CI» desactivado; **migraciones Alembic manuales** (causaron el incidente del 2026-10-07, servicio CRASHED hasta el 2026-10-10); sin lockfile, protección de `main`, staging, IaC ni smoke post-despliegue. El único CD automatizado es `deploy-evals.yml`, reutilizable como patrón | Medio-alto | No | Para validar sí; escribirlo no |
| M3-6 | **Despliegue por un tercero**: guía extensa pero ~35 variables manuales y estado documental mixto (contradicciones Auto Deploy/Wait for CI) | Bajo | No | No |
| M3-7 | **Benchmark de latencia/TTFT con clave real** y SLO reales (SLO candidatos propuestos en §5 del fichero del módulo) | Bajo-medio | Sí (céntimos-USD) | Preferible |
| M3-8 | **Phoenix (ADR-007)** desplegado pero sin conexión con la app; ADR *Proposed* | Alto | No | Sí |
| M3-9 | **Parada de emergencia no durable** (sólo memoria; un reinicio la desactiva, BL-44) | Bajo-medio | No | No |
| M3-10 | **Evidencia del estado actual de producción**: usar capturas/exports ya existentes con fecha, sin inventar métricas | Bajo | No | No |

### Módulo 4 — Seguridad y análisis de riesgos

**Cubierto:** 45 controles inventariados con ruta y pruebas (C1-C45), en cuatro capas
(autorización determinista, adjuntos, frontera de confianza, detección/respuesta);
`docs/llm-security-hardening.md`, `docs/production-security-privacy.md`; **borrador
de registro de 16 riesgos (R1-R16)** como síntesis nueva, **a revisar por el
propietario**; PyRIT y Garak evaluados en papel.

**Huecos (consolidados de `academic/modulo-4…` H1-H16):**

| # | Hueco | Esfuerzo | Gasto | Deploy |
|---|---|---|---|---|
| M4-1 | **Red-teaming no ejecutado** (lo pide el enunciado). PyRIT/Garak no están instalados ni hay resultados. Piloto propuesto sobre el harness aislado, mapeado a OWASP LLM Top 10; alternativa manual si no es viable. Estimación 0,5-5 USD (cálculo del agente, no del repo) | Medio | **Sí, requiere aprobación** | No |
| M4-2 | **Seguridad sin medir con modelo real**: los 31 casos de `evals/security` (17 originales + 14 semillas de red-teaming) son estáticos. Es el riesgo dominante (R1/R10). Ejecutar con `GovernedPhysicalEvalExecutor` y medir ASR/falsos positivos | Medio | Sí (≈ 0,1-0,5 USD) | No |
| M4-3 | **Documento de riesgos propio**: promover el borrador de registro a `docs/` tras revisión | Bajo | No | No |
| M4-4 | **Heurística de inyección débil**: el «8/8 recall» es recall **en muestra**, medido sobre los casos con los que se calibró, con 3 negativos benignos (no 2: el test exige 3 y los docs están desfasados). En web da 4/5. **No está cableada en ninguna tool** (verificado: `src/` no la importa), por lo que no protege producción. Ampliar corpus (≥ 100 negativos ES) y decidir cablear o descartar | Medio | No | Si se cablea |
| M4-5 | **Aislamiento entre dos cuentas**: guion preparado (`specs/017…/data-isolation-e2e.md`), sin evidencia de ejecución real | Bajo-medio | Sí (≈ 13 interacciones, ≈ 0,05 USD) | No |
| M4-6 | **Cadena de suministro**: sin lockfile, `pip-audit`, Dependabot, escáner de secretos ni de imagen en CI (verificado); Dockerfile corre como root. La imagen LiteLLM sí va fijada por digest | Bajo | No | Dockerfile sí |
| M4-7 | **`propose_note` y TODO con sólo título no piden confirmación** (WRITE_TRIVIAL, decisión BL-46). Una inyección indirecta podría escribir notas triviales sin «Sí». Es una decisión documentada; el riesgo residual debe constar en el registro | Bajo (documentar) | No | No |
| M4-8 | **RGPD/AI Act**: checklist casi todo «Pendiente». Presentarlo como *decisión consciente de alcance* (piloto con datos ficticios) más hoja de ruta | Alto (ejecutar) / Bajo (presentar) | No | No |
| M4-9 | **Rotación de secretos** no ensayada; **sin sandbox ni timeout propio** al parsear PDF/Office; **sin límite específico de canjes de pairing fallidos** (sólo rate limit global); chequeo de path traversal por `startswith` (usar `Path.is_relative_to`) | Bajo-medio | No | Algunos |
| M4-10 | **Verificación remota autenticada** de controles (métodos HTTP, credencial válida) | Bajo-medio | No | Staging |

## 3. Huecos transversales

| # | Hueco | Módulos | Nota |
|---|---|---|---|
| T-1 | **Un único hilo de evidencia semántica falta**: juez + red-teaming + evals reales se apoyan en el mismo harness (BL-8 T7/T8) y en la misma aprobación de gasto. Ejecutar una campaña bien acotada cierra M2-6, M3-1, M3-2, M4-1 y M4-2 a la vez | 2, 3, 4 | Decisión del propietario |
| T-2 | **El fallo `InvalidPresentationOutputError` del caso 2** sigue sin causa histórica exacta. Cualquier cifra de calidad debe presentarlo tal cual, sin reconstruir la salida | 2, 3 | No relanzar la campaña interrumpida |
| T-3 | **Documentación contradictoria entre sí** (ver §4): riesgo de que el PDF copie cifras o descripciones obsoletas | 1-4 | Pasada de docs, sin gasto |

## 4. Contradicciones a corregir antes de copiar nada al PDF

Verificadas por los agentes salvo indicación. En caso de conflicto manda
`AGENTS.md`/`docs/architecture.md`, contrastado con código y `BACKLOG.md`.

| Dónde | Dice | Realidad detectada |
|---|---|---|
| `AGENTS.md` §3/§5 | 1 421 unitarios, 160 de integración | §1 del mismo fichero: 2 260 y 207; medido hoy: 2 262 / 219 recolectados |
| `AGENTS.md`, `BACKLOG.md` | 36 casos de evals | `scripts/run_evals.py` valida 59 en 6 categorías |
| `docs/development.md` | 506 tests | Obsoleto |
| `docs/architecture.md` §2.4, §3, §13 | Admisión, ledger y LiteLLM «no implementados»; HITL de Agno | Implementados (ADR-004, specs/013); el consentimiento lo implementa el Core |
| `docs/governance.md` §5 | Metadatos YAML `risk`/`requires_confirmation`; nombres previos al refactor; `temperature=0.7`, `r43` | No existen en `src/`; son ejemplos |
| `llm-security-hardening.md`, BL-39 y gap analysis anterior | «0/2 falsos positivos» | El test exige 3 negativos |
| `llm-security-hardening.md` | `confirm_or_use_confirmed` y flag apagado | El bypass ya se retiró |
| `specs/023…/verification.md` | Fases 5 y 6 «Pendiente» | A contrastar con el código |
| `specs/013…/configs/ancoramind-default-r4.json` | 0,43 / 0,87 USD/M | Snapshot rev. 8: 0,10 / 0,50 (sin origen documentado) |
| Snapshot rev. 8 (2026-10-17) | Es el vigente | Obsoleto: STT confirmada en producción el 2026-10-20, hay una revisión posterior que no está en el repo |
| Límite externo | 20 USD asumido | `BACKLOG.md:1549-1552` reporta 5 USD en la clave OpenRouter |
| `docs/model-selection-and-cost-projection.md` | «Corte duro al 90 %» en ruta y diario | El código sólo aplica el 90 % al límite externo; los demás cortan al 100 % |
| YAML del Gateway | `r1`, `fast`, `vision` → `gpt-5.6-luna` | `r4` → `gpt-6-luna` según reporte del propietario |
| Docs de despliegue | Auto Deploy vs. «Wait for CI» | Manda `AGENTS.md` §10: Wait for CI desactivado, despliegue manual |

## 5. Qué se puede cerrar con Railway caído y sin gasto

Todo lo de esta lista es documentación o código local y no necesita inferencia ni
plataforma:

- **Documental:** M1-1 (matriz de decisión), M1-3, M1-4 (declarar valores por
  defecto), M1-5, M1-6 (variantes como «candidatas»), M1-8, M1-10, M2-1, M2-4,
  M2-5, M2-7, M2-8, M3-6, M3-10, M4-3, M4-7, M4-8 (como decisión de alcance).
- **Código local con tests:** M2-2 (test de clasificación de tools), M2-3 (tras
  confirmar el camino de ingesta), M1-2 (comprobar lectura de tokens), M3-3
  (corregir o retirar `GatewayCircuitOpen`), M3-9, M4-6 (lockfile, `pip-audit`,
  Dependabot, no-root), M4-9, escribir el workflow `deploy-app` y la migración
  automática de M3-5 (sin validarlos).
- **Contrastar antes de redactar:** M2-3, M4-4.

## 6. Qué necesita decisión o aprobación del propietario

1. **Gasto de inferencia** para cerrar T-1: ejecutar el plan de 5 casos (nominal
   0,10 USD), un piloto de juez y un piloto de red-teaming (0,5-5 USD estimados).
   Ningún agente lo ha ejecutado ni lo hará sin aprobación expresa. Condiciones
   actuales: sesión acotada de specs/042, sin relanzar la campaña interrumpida.
2. **Dónde ejecutarlo**: Gateway Docker local (`gateway/docker-compose.litellm.yml`,
   no depende de Railway) o esperar a que Railway vuelva.
3. **Formulación del PDF**: «agente seguro» o «controles diseñados y verificados con
   limitaciones X». La evidencia sólo sostiene lo segundo.
4. **Importes de costes fijos** de Railway, Supabase, Grafana Cloud y Tavily (M1-9).
5. **Revisión del registro de riesgos** (síntesis nueva, M4-3).
6. **Activar o no el trailer `Co-Authored-By`** en commits asistidos (M2-5).

## 7. Resumen priorizado

| Prioridad | Hueco | Esfuerzo | Gasto | Módulos |
|---|---|---|---|---|
| Alta | Pasada de reconciliación de docs y cifras (§4) | Bajo | No | 1-4 |
| Alta | Matriz de decisión del modelo con «no medido» explícito (M1-1) + tabla de costes no medidos (M1-5) | Bajo | No | 1 |
| Alta | Capítulo proceso→técnico (M2-1) + método humano-agente (M2-5) + addendum ADR-001 (M2-4) | Bajo | No | 2 |
| Alta | Documento de riesgos propio (M4-3) | Bajo | No | 4 |
| Alta | Campaña acotada: evals reales + juez + red-teaming (T-1) | Medio-alto | **Sí** | 2, 3, 4 |
| Media | Seguridad de la cadena de suministro en CI (M4-6) y automatización de migraciones/despliegue (M3-5) | Medio | No | 3, 4 |
| Media | Test de clasificación de riesgo por tool (M2-2); resolver `analyze_document` (M2-3) | Bajo-medio | No | 2 |
| Media | Alertas provisionadas y circuito corregido (M3-3); parada de emergencia durable (M3-9) | Medio | No | 3, 4 |
| Baja | Heurística de inyección: ampliar corpus y decidir (M4-4) | Medio | No | 4 |
| Baja | Phoenix, RGPD completo, sandbox de parseo | Alto | No | 3, 4 |

## Vigencia

Este análisis refleja el repo el 2026-10-23. Antes de usarlo, confirmar en
`BACKLOG.md` (BL-55, BL-8, BL-33, BL-44) y en los ficheros de `docs/academic/` que
ningún ítem se ha cerrado. Los ficheros de `docs/academic/` conservan el detalle y
las rutas; si hay discrepancia con este resumen, manda el fichero de módulo.
