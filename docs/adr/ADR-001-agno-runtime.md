# ADR-001: Agno + AgentOS as Initial Agent Runtime

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-23 |
| **Deciders** | AncoraMind engineering |

---

## Context

AncoraMind needs an agentic runtime for the POC/MVP. The primary goal is to minimize the time to a working personal assistant that can:

1. Receive messages via Telegram
2. Maintain persistent conversation sessions
3. Select and invoke Tools
4. Stream responses
5. Handle human-in-the-loop confirmations
6. Persist runtime state

Building these capabilities manually (agent loop, session engine, streaming, Telegram adapter, approval runtime, agent API, runtime observability) would delay the first working assistant significantly.

---

## Decision

**Use Agno + AgentOS as the initial agentic runtime.**

AgentOS will act as the execution and API layer around the agent.

Agno will initially manage:

- Agent execution
- Tool calling
- Sessions
- Conversation history
- Runtime persistence
- Streaming
- Human-in-the-loop runtime
- Runtime API
- Telegram interface
- Tracing
- Evaluations
- MCP integration
- Runtime lifecycle

---

## Consequences

### Positive

- **Fastest path to working assistant** — Telegram + conversation + session out of the box
- **Battle-tested tool calling** — Agno handles the complexity of tool selection and argument passing
- **Built-in HITL** — confirmation flow for sensitive operations without custom implementation
- **Runtime observability** — tracing and evals from day one
- **MCP-ready** — future ecosystem integration without architectural changes

### Negative

- **Dependency risk** — if Agno changes its API or is discontinued, migration cost exists
- **Abstraction overhead** — Agno's internal model may influence design decisions if not careful
- **Version coupling** — must track Agno releases and compatibility

### Mitigation

The architecture enforces a strict separation:

```
Agno Agent → Agno Tool adapter → Domain Service → Repository → PostgreSQL
```

- Domain logic **never inherits** from Agno classes
- Same logic must be invocable from: Agno Tool, REST API, MCP Server, CLI, background worker, LangGraph workflow, or another Agent Runtime
- If Agno needs replacement, only the `agent/` module changes — `domain/` remains untouched

---

## Alternatives Considered

### Pydantic AI

**Excellent software engineering fit:** typing, dependency injection, structured outputs, Pydantic ecosystem, evals, clean Python architecture.

**Rejected for initial POC** because it would require building more application infrastructure (agent loop, session engine, Telegram adapter, HITL runtime) before obtaining a working assistant. Remains a strong candidate for future evolution if stronger typing and lower runtime abstraction are needed.

### LangGraph

**Excellent for:** durable workflows, explicit state machines, complex pause/resume, deterministic orchestration, long-running processes.

**Rejected as general runtime** because AncoraMind's primary interaction pattern is conversational (request → tool → response), not multi-step state machine workflows. LangGraph remains permitted for specific capabilities that genuinely require durable workflows.

### Custom Agent Loop

**Rejected for MVP.** While Nanobot demonstrates that a simple loop can evolve into a complex runtime, AncoraMind should not invest initial resources in rebuilding that infrastructure.

---

## Re-evaluation Criteria

Agno will be reconsidered if:

1. A concrete requirement is blocked by an Agno limitation
2. The limitation is documented and demonstrated
3. Alternatives are proposed with trade-off analysis
4. A decision is explicitly requested before replacing the runtime

**Do not** initiate an "Agno vs LangGraph vs Pydantic AI" investigation without authorization. The decision is made for the POC.

---

## References

- [AncoraMind Architecture](../architecture.md)
- [AncoraMind Governance](../governance.md)
- [Engineering Brief — Section 4: Agent Runtime Decision](../../README.md)