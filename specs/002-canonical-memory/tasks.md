# Tasks: 002 — Canonical Memory

## Task Breakdown

### T1: Database layer
- [x] `src/repositories/database.py` — AsyncEngine + session factory
- [x] `migrations/init.sql` — `ancora.notes` table with indexes
- [x] Parameterized queries only (SQLAlchemy `text()` with bind params)

### T2: Domain models
- [x] `src/domain/notes/models.py` — NoteCreate + Note (Pydantic)
- [x] Validation: min_length=1, max_length=5000

### T3: Repository
- [x] `src/repositories/notes.py` — NotesRepository
- [x] `create(user_id, data)` — INSERT with RETURNING
- [x] `search(user_id, query)` — ILIKE + LIMIT 20
- [x] All queries scoped to user_id

### T4: Domain service
- [x] `src/domain/notes/service.py` — NotesService
- [x] `remember(user_context, content)` 
- [x] `search(user_context, query)`
- [x] Framework-independent (no Agno imports)

### T5: Security layer
- [x] `src/security/user_context.py` — UserContext dataclass
- [x] `from_run_context(run_context)` — parse from Agno RunContext
- [x] Session ID parsing: `tg:entity:chat_id` → user_id
- [x] Frozen dataclass (immutable)

### T6: Tool adapters
- [x] `src/agent/tools/notes.py` — remember_note + search_notes
- [x] Async tools with `run_context: RunContext` injection
- [x] Formatted responses (dates, counts)

### T7: App wiring
- [x] `src/main.py` — optional domain DB init
- [x] Domain tools loaded only when ANCORA_DATABASE_URL is set
- [x] Graceful degradation without domain DB

### T8: Tests
- [x] 30 unit tests (13 new: user_context, notes_models, notes_service)
- [x] Security test: service uses trusted UserContext, not LLM input
- [ ] Integration test with real PostgreSQL