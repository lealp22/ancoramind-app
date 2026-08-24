# Verification: 002 — Canonical Memory

## Automated Tests

### Unit Tests (30 passing)

| Test file | Tests |
|---|---|
| `test_config.py` | Settings defaults, env override, db_url property, allowed_user_ids |
| `test_instructions.py` | Load 4 prompt files, assemble, no empty blocks |
| `test_system_tools.py` | Current datetime, ISO 8601, docstring |
| `test_user_context.py` | Creation, RunContext parsing, session_id fallback, frozen |
| `test_notes_models.py` | NoteCreate validation (empty, too long), Note from attributes |
| `test_notes_service.py` | remember(), search(), trusted user context enforcement |

### Key Security Tests

```
test_remember_uses_trusted_user_context:
    → Service MUST use UserContext.user_id (from channel),
      never from LLM input
```

## Manual E2E Tests (requires real credentials + PostgreSQL)

### E2E-002-001: Remember and Retrieve
```
User: Recuerda que la plaza del garaje es la 42.
Agent calls: remember_note(run_context, content="La plaza del garaje es la 42")
Agent: Nota guardada (id: ...)

User: ¿Qué plaza de garaje tengo?
Agent calls: search_notes(run_context, query="plaza")
Agent: Encontré 1 nota sobre "plaza": - [2026-08-24 22:00] La plaza del garaje es la 42
```

### E2E-002-002: No Domain DB — Graceful Degradation
```
# Without ANCORA_DATABASE_URL
Log: ANCORA_DATABASE_URL not set — domain tools skipped
Tools: ['get_current_datetime']  (notes tools not loaded)
```

## Acceptance Criteria

- [x] 30 unit tests pass
- [x] Config robusto (extra="ignore", validación de IDs)
- [x] User context desde RunContext (session_id parsing)
- [x] NotesRepository con queries parametrizadas (ILIKE, LIMIT)
- [x] NotesService usa UserContext, no input del LLM
- [x] Agent registra 3 tools con ANCORA_DATABASE_URL
- [x] Agent funciona con 1 tool sin ANCORA_DATABASE_URL
- [x] Modelos Pydantic validan input
- [ ] E2E Telegram con PostgreSQL real pendiente