# Tasks: 007 — Supabase Infrastructure

## Task Breakdown

### T1: Infraestructura (vía MCP — hecho)
- [x] Migración baseline `ancora_baseline` aplicada (8 tablas + índices)
- [x] Bucket `ancora-documents` creado (privado, 20 MB limit)
- [x] Verificado: pgvector 0.8.2 disponible, NO instalado (diseño solo)

### T2: Config
- [x] `src/config.py`: `document_storage_backend` (default "local"),
      `supabase_url`, `supabase_service_role_key`, `supabase_storage_bucket`
- [x] `.env.example`: sección Supabase (2 URLs pooler + storage)

### T3: SupabaseDocumentStorage
- [x] `src/storage/supabase_storage.py`: store/get/delete/exists
- [x] Layout de keys idéntico al local (`{YY}/{MM}/{hex12}.{ext}`)
- [x] `asyncio.to_thread` para las llamadas bloqueantes del cliente
- [x] Mapeo de errores: no existe → `FileNotFoundError`; traversal → `ValueError`

### T4: Factory + wiring
- [x] `src/storage/factory.py`: `create_storage(settings) -> DocumentStorage`
- [x] `src/agent/tools/documents.py`: usar la factory en vez del singleton local
- [x] `pyproject.toml`: +`supabase>=2.5.0` (instalada)

### T5: Tests
- [x] `tests/unit/test_supabase_storage.py` (cliente mockeado): 17 tests —
      happy paths, FileNotFoundError, key traversal, layout de keys, factory
- [x] `pytest tests/unit/` verde completo → **99 tests**
- [x] ruff limpio en ficheros tocados (+ fix preexistente SIM115 en documents.py)

### T6: Documentación + cierre
- [x] ADR-002 commiteado
- [x] BACKLOG.md: BL-14 🔶 en curso — código listo, falta E2E (T7)
- [ ] `docs/development.md` / `docs/quick-start.md`: instrucciones Supabase

### T7: E2E contra Supabase (requiere credenciales del usuario en .env)
- [ ] Nota: remember/search contra Supabase
- [ ] Documento: subir attachment → bucket `ancora-documents`
- [ ] Vehículo: propose → Sí → execute (regresión de specs/006)
