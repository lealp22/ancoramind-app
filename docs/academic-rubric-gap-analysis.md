# Gap analysis contra el rúbrico de evaluación del programa

> Análisis puntual (2026-10-18) de cómo se posiciona AncoraMind frente al
> texto de evaluación del entregable final del programa (módulos 1-4:
> modelo/coste, flujo agentic, despliegue/evaluación/monitorización,
> seguridad/riesgos). No es un documento de arquitectura ni sustituye a
> `AGENTS.md`/`docs/architecture.md`; es una fotografía para priorizar qué
> cerrar antes de la entrega. Revisar y actualizar si cambia el alcance del
> proyecto o se cierran los huecos aquí descritos — este documento puede
> quedar obsoleto más rápido que el resto de `docs/`.

## Resumen por módulo

### Módulo 1 — Modelos, configuración, costes

**Cubierto:**
- Configuración/consumo/parametrización: `AGENTS.md` §4 (tabla de
  proveedores LLM, modo Gateway vs. directo, cambio de modelo sin redeploy).
- Prompts empleados: versionados en Git (`prompts/*.md`), con
  `prompt_version` como campo de auditoría trazable en cada extracción.
- Coste real medido por llamada/eval: `CostGovernanceConfig`,
  `pricing_snapshot`, ledger de uso (specs/013).

**Falta:**
- **Justificación comparativa de modelo** (por qué GPT-6 Luna y no otro) —
  hoy solo existe la mecánica de *cómo* cambiarlo (ADR-005), no el *por qué*
  de la elección actual frente a alternativas.
- **Proyección de coste por niveles de uso** (ej. "a N usuarios/día,
  ~$X/mes") — no existe; solo hay coste medido por llamada/campaña puntual
  ya ocurrida, nunca una proyección hacia delante.
- **Historial de prompts candidatos/alternativas explorados** — los
  prompts están versionados pero no hay documento que explique *por qué*
  cambió una versión frente a otra (es trazabilidad, no justificación).

### Módulo 2 — Flujo de agente, autonomía, framework

**Cubierto (el módulo mejor cubierto del proyecto):**
- Niveles de autonomía/intervención humana: `docs/governance.md` §5-7
  (tabla de riesgo READ/WRITE/WRITE_TRIVIAL/EXTERNAL_ACTION/DESTRUCTIVE +
  matriz de confirmación por tool).
- Por qué Agno/AgentOS y no otro framework: `docs/adr/ADR-001-agno-runtime.md`
  — contexto, decisión, alternativas consideradas (Pydantic AI, LangGraph,
  loop custom) con razones explícitas de rechazo y criterios de
  re-evaluación.

**Falta:**
- Documento único que muestre explícitamente la traducción de un proceso de
  negocio a patrón técnico (ej. "recordar mantenimiento del coche" →
  `propose_vehicle_maintenance`/`execute_vehicle_maintenance`). Hoy esa
  lógica está repartida entre `AGENTS.md` y los specs de cada dominio, sin
  una pieza narrativa que explique el razonamiento de diseño.

### Módulo 3 — Despliegue, evaluación, monitorización

**Cubierto:**
- Despliegue: `docs/deployment-railway.md`, `docs/deployment-e2e.md`, con
  evidencia real de producción (ver BL-18/BL-1 en BACKLOG.md).
- Evaluador no-subjetivo/determinista corriendo hoy: catálogo `evals/` +
  `scripts/run_evals.py` (no llama a ningún LLM, evalúa estructura) +
  `src/domain/security/injection_heuristics.py` (heurísticas deterministas,
  8/8 recall medido contra `evals/security/cases.json`).
- Monitorización: `/health/readiness` con señales reales (DB, Gateway,
  worker, cola) + dashboard Grafana con datos reales importado (BL-33,
  alcance acotado para demo).

**Falta:**
- **LLM como juez**: diseñado (`Jev`,
  `specs/014-agentic-evals/jev-pilot-proposal.md`) pero el propio documento
  dice explícitamente *"propuesta de siguiente incremento, no
  implementada"*. Ningún juez semántico corre hoy.
- BL-33 T7 (alertas, matriz de degradación) sigue pendiente — fuera del
  alcance acotado para demo visual ya decidido.
- No hay métrica de **calidad de negocio en producción** más allá de salud
  técnica (vivo/circuito cerrado), no "cómo de bien está respondiendo el
  agente".

El enunciado pide explícitamente *"LLMs como Juez, o al menos algún
evaluador no-subjetivo"*: el no-subjetivo está cubierto y corriendo; el
LLM-juez está diseñado pero no ejecutado.

### Módulo 4 — Seguridad y análisis de riesgos

**Cubierto:**
- Controles de seguridad: `docs/llm-security-hardening.md` (modelo de
  amenaza, 4 capas: autorización determinista, preparación de adjuntos,
  frontera de confianza, detección/respuesta) y
  `docs/production-security-privacy.md` (GDPR/RGPD, gates antes de abrir a
  terceros).
- Candidatos de red-teaming/framework evaluados: PyRIT y Garak documentados
  (2026-10-18) en `docs/llm-security-hardening.md` §"Herramientas
  consideradas", con comparación resumida.

**Falta:**
- El enunciado pide explícitamente apoyarse en *"algún agente o framework
  de red-teaming"* — hoy **ninguno está ejecutado**, solo documentado como
  candidato evaluado.
- No hay un **documento de análisis de riesgos independiente**
  (threat model / risk register). El modelo de amenaza vive como
  subsección dentro de `llm-security-hardening.md` (§"Alcance y modelo de
  amenaza"), no como artefacto propio.

## Resumen priorizado (esfuerzo vs. impacto en el rúbrico)

| Prioridad | Hueco | Esfuerzo estimado | Módulo |
|---|---|---|---|
| Alta | Documento de justificación de modelo + proyección de coste por niveles de uso | Bajo — los datos de coste real ya existen como base | 1 |
| Alta | Ejecutar un piloto mínimo de red-teaming (PyRIT o casos manuales inspirados) contra el harness de evals ya construido (BL-8) | Medio — reutiliza la misma pieza que ya se venía desbloqueando | 4 |
| Media | Ejecutar un piloto mínimo de Jev (LLM-juez) sobre los casos ya preparados | Medio — diseño ya existe, falta solo ejecutar | 3 |
| Media | Extraer el "modelo de amenaza" a un documento de riesgos independiente | Bajo — es reorganizar contenido ya escrito | 4 |
| Baja | Documento de mapeo proceso de negocio → patrón técnico | Bajo — es narrativa, no implementación | 2 |

## Lectura global

Según el baremo descrito (5-7 por reflejar los conceptos; 7-9 por tenerlo
implementado aunque no desplegado del todo; 9-10 por completo y sin carga
de mantenimiento para terceros), AncoraMind está sólidamente en la banda
7-9: casi todo lo exigido está implementado con evidencia real de
producción. Los huecos reales son concretos y acotados (coste proyectado,
LLM-juez ejecutado, red-teaming ejecutado, análisis de riesgos como
documento propio) — el riesgo no es falta de trabajo de fondo, sino que el
documento final no nombre estos huecos explícitamente y dé la impresión de
que faltan por desconocimiento en vez de por decisión consciente de
priorización.

## Vigencia

Este análisis se hizo el 2026-10-18 contra el estado del repo en ese
momento. Antes de usarlo para decidir qué entra en la entrega final,
confirmar que ningún ítem de la tabla ya se cerró en el BACKLOG (buscar
"BL-55" en `BACKLOG.md` para el ítem que referencia este documento, y
revisar si los huecos de la tabla siguen abiertos).
