# Spec: 002 — Canonical Memory

> **Milestone:** M2 — Canonical Memory mínima
> **Status:** implemented
> **Target:** PostgreSQL domain schema + `remember_note` / `search_notes`

---

## Requirement

Crear persistencia canónica propia en PostgreSQL separada del runtime de Agno.

Capacidad inicial: `remember_note` / `search_notes`.

### Must Have

- Schema `ancora` en PostgreSQL con tabla `notes`
- Tool `remember_note` — guarda nota personal en PostgreSQL
- Tool `search_notes` — busca notas por query o lista recientes
- User context desde Agno `RunContext` (nunca del LLM)
- Parameterized SQL queries (sin string interpolation)
- Cada nota scoped al usuario autenticado

### Should Have

- Pydantic models para validación
- Separación Repository → Service → Tool
- Domain DB opcional (sin ANCORA_DATABASE_URL → sin domain tools)

### Won't Have (this milestone)

- Vehículos, documentos, recordatorios, calendario
- Action proposals / confirmaciones
- Multi-user con tabla `users`

---

## Success Criteria

1. `remember_note("La plaza del garaje es la 42")` → nota guardada en PostgreSQL
2. `search_notes("plaza")` → devuelve la nota desde PostgreSQL, no desde memoria Agno
3. `search_notes()` sin query → lista notas recientes
4. User B no puede ver notas de User A
5. Sin ANCORA_DATABASE_URL → app funciona sin domain tools