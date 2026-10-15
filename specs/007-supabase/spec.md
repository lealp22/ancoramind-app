# Spec: 007 — Supabase Infrastructure (BL-14)

> **Backlog:** BL-14
> **Status:** in_progress
> **Decision doc:** [ADR-002](../../docs/adr/ADR-002-supabase-infrastructure.md)

---

## Requirement

Migrar la infraestructura de AncoraMind de Docker local a Supabase:
PostgreSQL gestionado (runtime Agno + dominio `ancora`) y Storage de
documentos, manteniendo intactas las fronteras arquitectónicas (§2.5, §2.7,
`DocumentStorage` Protocol).

### Must Have

- Schema `ancora` aplicado en Supabase como migración baseline
  (`ancora_baseline`, sin los GRANT al rol `ancora` inexistente)
- Bucket privado `ancora-documents` (20 MB limit) en Supabase Storage
- Conexión vía **session pooler** (IPv4, puerto 5432) para ambos URLs
- Runtime Agno fijado explícitamente en schema `agno_runtime`
- `SupabaseDocumentStorage` — implementación del `DocumentStorage` Protocol
  (`store`/`get`/`delete`/`exists`) con `supabase-py`, I/O bloqueante envuelto
  en `asyncio.to_thread`
- Factory de storage (`src/storage/factory.py`) seleccionada por env var
  `DOCUMENT_STORAGE_BACKEND=local|supabase` (default `local` — no rompe dev)
- Nuevas env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_STORAGE_BUCKET`
- Service Role Key solo en servidor, nunca en Git ni en el cliente

### Should Have

- Layout de storage keys idéntico al local (`{YY}/{MM}/{uuid}.{ext}`) para
  que el resto del sistema no cambie
- Tests unitarios con cliente Supabase mockeado (mismos behaviors que los
  tests de storage local)

### Won't Have (esta spec)

- Instalar/activar pgvector (solo diseño — depende de BL-6)
- Migración de documentos ya guardados en filesystem local (keys antiguas
  solo válidas con backend local — aceptado en ADR-002)
- Branches dev/prod de Supabase (requiere plan Pro)
- Background migration de notas/vehículos existentes (POC: se re-valida
  creando datos nuevos contra Supabase)

---

## Design

### Cambios en código

1. `src/config.py` — +`document_storage_backend`, +`supabase_url`,
   +`supabase_service_role_key`, +`supabase_storage_bucket`
2. `src/storage/supabase_storage.py` — nuevo. Mismo layout de keys que
   `LocalFileSystemStorage` (`{YY}/{MM}/{hex12}.{ext}`). Errores mapeados:
   no existe → `FileNotFoundError`; key inválida → `ValueError`
3. `src/storage/factory.py` — `create_storage(settings) -> DocumentStorage`
4. `src/agent/tools/documents.py` — sustituir el singleton
   `LocalFileSystemStorage` por la factory
5. `pyproject.toml` — +`supabase>=2.5.0`
6. `.env.example` — sección Supabase con los 2 URLs de pooler y las 3 vars
   de storage
7. `src/agent/ancora_agent.py` — `PostgresDb(..., db_schema="agno_runtime")`
   para impedir que las tablas de Agno terminen en `public`

### Infra (fuera del código — hecho vía MCP/dashboard)

- [x] Migración `ancora_baseline` aplicada (8 tablas + índices)
- [x] Bucket `ancora-documents` creado (privado, 20 MB)
- [x] Head `0015_ancora_rls_hardening` aplicado: 24/24 tablas `ancora` con
  RLS, cero policies y cero grants de tabla para roles Data API

### Usuario (manual — credenciales)

- `ANCORA_DATABASE_URL`/`AGNO_DATABASE_URL` apuntando al session pooler
  (copiar de Supabase Dashboard → Connect → Session pooler)
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (Dashboard → Settings → API)

---

## Success Criteria

1. `ancora.notes`, `ancora.vehicles` etc. existen en Supabase (8 tablas)
2. `DOCUMENT_STORAGE_BACKEND=supabase` → los documentos se guardan en el
   bucket; `local` → comportamiento previo intacto
3. Tests unitarios verdes (existentes + nuevos de Supabase storage)
4. Sin credenciales Supabase y backend=local → la app funciona como siempre
   (retro-compatibilidad)
5. E2E real contra Supabase (nota + documento + vehículo) documentado en
   `verification.md` — o anotado en BACKLOG (alimenta BL-1)
