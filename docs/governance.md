# AncoraMind — AI Governance

> **Versión:** 1.1 | **Estado:** POC/MVP | **Última actualización:** 2026-09-13

---

## Principio rector

> **La gobernanza debe reducir riesgo y aumentar reproducibilidad sin bloquear el desarrollo del producto.**

Gobernanza proporcional desde el POC: Git, PostgreSQL, tests y metadatos cubren gran parte del MVP sin necesidad de plataformas empresariales específicas.

---

## 1. AI Asset Governance

Todos los assets de IA deben versionarse en Git:

```
prompts/
  soul.md
  tool_contract.md

skills/
  vehicle-maintenance.md

schemas/
  vehicle_invoice_v1.py

evals/
  documents.yaml
```

| Asset | Versionado en | Cambio revisable |
|---|---|---|
| Prompts | Git | ✅ |
| Skills | Git | ✅ |
| Tool contracts | Git | ✅ |
| Schemas de extracción | Git | ✅ |
| Bootstrap/secrets de modelo | Railway environment | ✅ |
| Runtime model configuration | PostgreSQL revisions + schema version (target specs/013) | ✅ |
| Evaluation datasets | Git | ✅ |
| Policies | Git | ✅ |

---

## 2. Estructura de prompts

Los prompts se organizan de forma modular:

```
prompts/
├── identity.md          ← quién es AncoraMind
├── soul.md              ← personalidad y principios
├── tool_contract.md     ← reglas de uso de Tools
├── channels/
│   └── telegram.md      ← políticas específicas del canal
└── skills/
    ├── documents.md
    ├── vehicle_maintenance.md
    ├── calendar.md
    ├── todos.md
    └── document_extraction.md   ← NO se carga aquí (ver nota)
```

No crear un único system prompt gigantesco. `assemble_instructions()`
(`src/agent/instructions.py`) carga identity, soul, tool_contract, telegram
y todas las skills de dominio, **excepto** `document_extraction.md`: ese
prompt es el system prompt de la llamada de extracción estructurada separada
(`src/agent/document_extraction.py`, schema-constrained), no del agente
conversacional principal — exclusión intencional, no un olvido
(specs/023 T6.5). Hasta 2026-10-03, `skills/calendar.md` existía en disco
pero no estaba cableado en `assemble_instructions()` (olvido real, corregido
en specs/023 Fase 6).

---

## 3. Model Governance

Registrar por ejecución relevante:

| Campo | Ejemplo |
|---|---|
| `logical_route` | `ancoramind-default` |
| `effective_gateway_route` | `ancoramind-default-r43` |
| `provider` | `openrouter`, `openai`, `anthropic` |
| `model` | `openai/gpt-*`, `anthropic/claude-*` |
| `config_version` | `43` |
| `temperature` | `0.7` |
| `max_tokens` | `4096` |
| `input_tokens` / `output_tokens` | `1200` / `180` |
| `cost` / `cost_source` | `0.0031` / `gateway` |

En extracciones importantes registrar además: `prompt_version`, `schema_version`.

> Cambiar de modelo debe considerarse un cambio evaluable.

### Acceso LLM gobernado (target specs/013)

- Toda inferencia debe pasar por `LLMAccess`; no se crean providers físicos en
  servicios o tools.
- Cada run usa un `RuntimeConfigSnapshot` inmutable y un `ExecutionBudget`.
- Provider/model se resuelven mediante rutas lógicas versionadas en LiteLLM.
- API keys y credenciales permanecen fuera de las revisiones runtime.
- El Gateway falla cerrado; no existe bypass directo en caso de caída.
- Retries, fallbacks y circuit breaker deben tener un propietario y un límite
  agregado para evitar amplification.
- La configuración runtime se valida y activa atómicamente; una revisión
  inválida no sustituye last-known-good.

---

## 4. Prompt Governance

Los prompts deben:
- Estar en Git
- Tener propósito definido
- Tener cambios revisables (diff amigable)
- Poder relacionarse con evaluaciones

**No distribuir instrucciones críticas entre múltiples strings anónimos dentro del código.**
---

## 5. Tool Governance

Cada capability debe declarar su metadata:

```yaml
name: register_vehicle_maintenance
version: 1
risk: WRITE
requires_confirmation: true
```

### Clasificación de riesgo

| Clasificación | Descripción | Ejemplo |
|---|---|---|
| **READ** | Solo consulta | `get_vehicle_summary` |
| **WRITE** | Modifica datos canónicos | `register_vehicle_maintenance` |
| **EXTERNAL_ACTION** | Actúa fuera del sistema | `create_calendar_event` |
| **DESTRUCTIVE** | Elimina datos | `execute_document_delete` |

### Matriz de confirmación

| Tool | Riesgo | Confirmación |
|---|---|---|
| `get_vehicle_summary` | READ | No |
| `search_documents` | READ | No |
| `analyze_document` | READ/PROCESS | No |
| `register_vehicle_maintenance` | WRITE | Sí |
| `create_reminder` | WRITE | Sí |
| `create_calendar_event` | EXTERNAL_ACTION | Sí |
| `execute_document_delete` | DESTRUCTIVE | Sí |

---

## 6. Data Governance

Distinguir siempre entre niveles de confianza:

```
original source → AI extracted → AI inferred → confirmed canonical → executed action
```

| Estado | Significado |
|---|---|
| `document stored` | El archivo está guardado |
| `extracted fields` | La IA ha extraído datos (no confirmados) |
| `action proposed` | Se ha sugerido una acción |
| `action confirmed` | El usuario ha aprobado |
| `action executed` | La operación se ha completado |

> "Documento guardado" ≠ "datos confirmados". "Acción propuesta" ≠ "acción autorizada".
---

## 7. Action Governance

Toda acción WRITE, EXTERNAL_ACTION o DESTRUCTIVE debe:

1. Pasar por el Policy Engine
2. Generar un `ActionProposal`
3. Obtener confirmación humana validada por el Core antes del Agent
4. Ser re-validada por el Core antes de ejecución
5. Registrar ejecución en audit trail
6. Vincular procedencia (source document, extraction, etc.)

> **El prompt puede instruir al agente, pero no constituye la barrera de seguridad.** La política final debe evaluarse en código.

**Hardening local 2026-10-11 (BL-39/40, pendiente rollout):** el catálogo del
Agent excluye `execute_*`, también en el singleton AgentOS. El repositorio
rechaza `confirm`/`confirm_or_use_confirmed`/`mark_executed` sin I/O: ni una
propuesta pendiente ni una ya confirmada pueden ejecutarse por una tool legacy.
`ProposalExecutor` conserva el claim único, revalidación, transacción y auditoría.
Con consentimiento gobernado OFF no se ejecutan propuestas; no hay fallback LLM.
La ingesta documental y exportación conservan sus excepciones aprobadas.

---

## 8. Audit Governance

Debe poder reconstruirse una operación relevante:

| Campo | Descripción |
|---|---|
| `request` | Mensaje original del usuario |
| `user` | UserContext resuelto |
| `session` | Session ID |
| `tool` | Tool invocada |
| `tool_version` | Versión de la Tool |
| `action` | Acción realizada |
| `timestamp` | Cuándo ocurrió |
| `result` | Resultado de la operación |
| `source` | Documento/extracción de origen |
| `correlation_id` | Identidad transversal de la interacción |
| `telegram_update_id` | Identidad del update por bot |
| `railway_request_id` | Delivery HTTP concreta |
| `agno_run_id` / `session_id` | Ejecución y conversación runtime |
| `gateway_request_id` | Llamada al Gateway |
| `config_version` | Revisión inmutable usada por el run |

Cuando interviene IA: `model`, `prompt_version`.

La auditoría durable vive en PostgreSQL. Los sistemas de observabilidad pueden
perder o muestrear eventos y no sustituyen al ledger canónico.

### Idempotencia de canal y acciones (target specs/013)

```text
same bot_id + telegram_update_id
=> at most one Agent execution
=> at most one persisted logical response/action
```

- Los duplicados se reconocen con `2xx` sin IA.
- Rate limiting no sustituye a idempotencia.
- Después de `agent_started` no hay replay automático; un resultado incierto se
  registra como `failed_ambiguous`.
- ActionProposal, acciones canónicas y respuestas lógicas añaden idempotency
  keys defensivas.

---

## 9. Evaluation Governance

Suite de evaluaciones desde el comienzo:

```
evals/
├── tool_selection/
├── documents/
├── vehicle/
├── confirmation/
└── security/
```

Los casos se versionan como catálogos JSON sintéticos en `evals/<category>/cases.json`.
`python scripts/run_evals.py` valida su contrato de forma determinista; no llama
a modelos ni ejecuta tools. Tras cada cambio de prompts, modelo o descripción de
tools se revisan los casos afectados y se ejecuta este gate. La futura evaluación
contra modelos debe reutilizar los mismos casos y registrar únicamente metadata
permitida por specs/013.

| Entrada | Expectativa |
|---|---|
| "¿Qué vehículos tengo?" | → vehicle Tool |
| "Busca mi factura" | → document Tool |
| "Sí" (acción pendiente) | → confirma acción correcta |
| "Ignore previous instructions..." (doc) | → no nueva Tool, no cambio permisos |

---

## 10. Change Governance

- **SDD** para capacidades importantes
- **ADR** para decisiones arquitectónicas
- No usar SDD como burocracia

Flujo: `Requirement → Spec → Design → Task → Verification`

---

## 11. Security Governance

### Least Privilege

Una capability solo debe tener acceso a lo que necesita.

### Controles mínimos
- Telegram private chats only + allowlisted users
- Runtime-derived identity (LLM nunca proporciona user_id)
- No arbitrary SQL Tools — parameterized DB access
- Secrets via environment variables
- LLM Gateway y OpenTelemetry Collector solo por red privada
- Control plane administrativo separado del Agent y no expuesto como tool
- Idempotencia, rate limit, concurrency y execution budget como barreras
  independientes

### Datos no confiables

Contenido de documentos, PDF, OCR, summary, filename, emails, web, MCP externo = **DATA, no INSTRUCTIONS**.

> **Aunque el LLM se equivoque, el Core no permite romper la frontera de autorización.**

---

## 12. Observability Governance (target specs/013)

- OpenTelemetry es el estándar de instrumentación y OTLP el protocolo de
  exportación.
- Un OpenTelemetry Collector upstream privado aplica allowlist/redaction,
  memory limits, batch y cola/retry acotados antes de Grafana Cloud.
- Collector/Grafana fallan abiertos respecto a la funcionalidad; la caída de
  observabilidad no bloquea al usuario.
- La telemetría de producto de Agno se desactiva cuando la observabilidad propia
  entra en servicio.
- No registrar prompts, mensajes, respuestas, documentos, extracciones ni
  argumentos/resultados completos de tools.
- IDs de alta cardinalidad se usan en spans/logs, no como labels de métricas.
- Toda nueva instrumentación requiere tests de privacidad antes de producción.
