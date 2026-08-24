# Spec: 001 — Agent Runtime Functional

> **Milestone:** M1 — Agent Runtime funcional
> **Status:** draft
> **Target:** Telegram private chat + Agno + AgentOS + LLM + session + 1 Tool

---

## Requirement

El usuario debe poder mantener una conversación real con AncoraMind desde Telegram.

### Must Have

- Telegram private chat → AncoraMind Agent → respuesta
- Sesiones de conversación persistentes
- LLM configurable (provider, model, API key)
- Al menos 1 Tool real funcionando (`get_current_datetime`)
- Respuesta en streaming en Telegram

### Should Have

- Rechazo de chats no privados (grupos, canales)
- Allowlist de usuarios autorizados
- Logging básico de request/response

### Won't Have (this milestone)

- Persistencia canónica propia (PostgreSQL domain schema)
- Documentos, vehículos, recordatorios, calendario
- Cualquier operación WRITE

---

## Success Criteria

1. Enviar mensaje desde Telegram → recibir respuesta del agente
2. Preguntar "¿Qué hora es?" → el agente usa `get_current_datetime` Tool → responde la hora
3. Preguntar "¿Cómo te llamas?" → el agente responde sin Tool
4. Mantener contexto entre mensajes en una sesión
5. El agente responde en español por defecto

---

## Constraints

- Usar Agno + AgentOS (ADR-001)
- No crear lógica de dominio todavía
- No crear tablas en schema `ancora` todavía
- No acoplar código a un proveedor LLM específico