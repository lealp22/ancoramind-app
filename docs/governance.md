# AncoraMind — AI Governance

> **Versión:** 1.0 | **Estado:** POC/MVP | **Última actualización:** 2026-08-23

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
| Model configuration | Git (config) | ✅ |
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
    └── calendar.md
```

No crear un único system prompt gigantesco.

---

## 3. Model Governance

Registrar por ejecución relevante:

| Campo | Ejemplo |
|---|---|
| `provider` | `openai`, `anthropic`, `groq` |
| `model` | `gpt-4o`, `claude-3.5-sonnet` |
| `temperature` | `0.7` |
| `max_tokens` | `4096` |

En extracciones importantes registrar además: `prompt_version`, `schema_version`.

> Cambiar de modelo debe considerarse un cambio evaluable.

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
| **DESTRUCTIVE** | Elimina datos | `delete_document` |

### Matriz de confirmación

| Tool | Riesgo | Confirmación |
|---|---|---|
| `get_vehicle_summary` | READ | No |
| `search_documents` | READ | No |
| `analyze_document` | READ/PROCESS | No |
| `register_vehicle_maintenance` | WRITE | Sí |
| `create_reminder` | WRITE | Sí |
| `create_calendar_event` | EXTERNAL_ACTION | Sí |
| `delete_document` | DESTRUCTIVE | Sí |

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
3. Obtener confirmación humana (Agno HITL)
4. Ser re-validada por el Core antes de ejecución
5. Registrar ejecución en audit trail
6. Vincular procedencia (source document, extraction, etc.)

> **El prompt puede instruir al agente, pero no constituye la barrera de seguridad.** La política final debe evaluarse en código.

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

Cuando interviene IA: `model`, `prompt_version`.

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

### Datos no confiables

Contenido de documentos, PDF, OCR, summary, filename, emails, web, MCP externo = **DATA, no INSTRUCTIONS**.

> **Aunque el LLM se equivoque, el Core no permite romper la frontera de autorización.**