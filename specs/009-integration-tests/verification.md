# Verification: 009 — Integration Tests with Real PostgreSQL

> **Fecha:** 2026-09-09 · **Entorno:** Windows 11 + Docker Desktop 29.2.1
> (pgvector/pgvector:pg16) · **Estado:** ✅ verificado localmente

---

## Resultado

| Check | Resultado |
|---|---|
| `pytest tests/integration/` | ✅ **16 passed** (contenedor arrancado por la fixture) |
| `pytest tests/unit/` | ✅ 126 passed (sin cambios) |
| `pytest` bare (unit + integration) | ✅ 142 passed |
| `pytest -m "not integration"` | ✅ 126 passed, 16 deselected |
| Sin PostgreSQL (URL inalcanzable simulada) | ✅ 16 skipped con mensaje accionable |
| `ruff check src/ tests/ scripts/` | ✅ limpio |
| BD dev `ancoramind` intacta | ✅ 1 nota preexistente conservada; toda la actividad en `ancoramind_test` (0 filas tras el TRUNCATE final) |

## Hallazgo principal: bug real en `documents.py`

`DocumentsRepository.create_extraction` pasaba el dict `extraction` directamente
al bind de `CAST(:extraction AS jsonb)`. Con asyncpg —el driver de
`ANCORA_DATABASE_URL` en producción (Supabase)— el bind falla con
`AttributeError: 'dict' object has no attribute 'encode'`. `actions.py` y
`maintenance.py` ya serializaban con `json.dumps()`; era el único punto sin
hacerlo. La escritura de extracciones IA (flujo M3) nunca se había probado por
la vía asyncpg: el E2E temprano fue anterior y el re-test de documentos quedó
bloqueado (BL-14 T7 / BL-18).

**Fix:** `"extraction": json.dumps(data.extraction)` en
`src/repositories/documents.py` (mismo patrón que los otros repos). El test
`test_extractions_latest_wins_and_cascade` lo detectó (falló → fix → verde).
Esto valida el objetivo de BL-2: detectar drift repos/SQL sin Telegram.

## Desviaciones del spec (documentadas)

1. **Engine async por test**, no session-scoped como sugería la tabla de
   fixtures del spec: las conexiones pooled de asyncpg quedan ligadas al event
   loop que las creó y pytest-asyncio 1.4 usa un loop nuevo por test. Crear y
   disponer el engine en la fixture `session` elimina errores cross-loop con
   coste despreciable (la BD se crea/migra una sola vez por sesión).
2. **Skip vs fail configurable**: `ANCORA_TEST_REQUIRE_DB=1` convierte el skip
   en fail (lo usa el job de CI para no enmascarar problemas de infra).

## CI

Job `integration` añadido a `.github/workflows/ci.yml`. El runner ubuntu trae
Docker + compose v2: la fixture arranca `docker compose up -d postgres` por sí
misma — misma ruta de código que local, cero configuración extra. Primera
validación en GitHub Actions: en el push de cierre de esta spec.

## Cobertura (16 tests)

| Módulo | Tests | Qué cubre |
|---|---|---|
| `test_notes_repo.py` | 3 | create, ILIKE search, orden DESC, scoping |
| `test_documents_repo.py` | 3 | lifecycle completo, extracciones (latest gana), cascade, scoping |
| `test_vehicles_repo.py` | 1 | create/get/list/find_by_reference multi-campo, scoping |
| `test_maintenance_repo.py` | 3 | history/last, JSONB round-trip, FK, cascade, scoping |
| `test_actions_repo.py` | 3 | ciclo de gobernanza + timestamps, idempotencia confirm, SET NULL, scoping |
| `test_reminders_repo.py` | 2 | create con default BD, filtro status, FK source_action |
| `test_calendar_repo.py` | 1 | list_range inclusivo y ordenado, scoping |

Transversales: `user_id` scoping en todos, JSONB → dict, `TIMESTAMPTZ`
timezone-aware, FKs `ON DELETE CASCADE` / `SET NULL`, defaults de BD.
