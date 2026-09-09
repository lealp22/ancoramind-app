# Spec: 009 — Integration Tests with Real PostgreSQL

> **Backlog:** BL-2
> **Status:** specified (pendiente de implementación)
> **Target:** Validar los repositorios reales de AncoraMind Core contra el
> PostgreSQL dockerizado del propio repo, sin depender de Telegram (BL-18) ni
> de Supabase. Es la vía de validación de M3–M5 mientras el canal está pausado.

---

## Requirement

Los 126 unit tests mockean todos los repositorios. Nunca se ha ejecutado el
SQL real contra un PostgreSQL: schemas (`ancora`), JSONB (`payload`,
`extraction`, `work_performed`), FKs (`ON DELETE CASCADE` / `SET NULL`),
`TIMESTAMPTZ` y el scoping por `user_id` solo se han validado parcialmente en
E2E manuales. Cualquier drift entre `migrations/init.sql` y las queries de
los repos se detectaría hoy solo en producción.

### Must Have

- `tests/integration/conftest.py` con fixture **session-scoped** que:
  - Resuelve el servidor: `ANCORA_TEST_DATABASE_URL` si está definida; si no,
    el PostgreSQL de docker-compose (`ancora:ancora@localhost:5432`).
  - Arranca el contenedor con `docker compose up -d postgres` (idempotente) y
    espera readiness con reintentos (timeout ~30 s).
  - **No toca la BD de dev** (`ancoramind`): crea la BD dedicada
    `ancoramind_test`, aplica `migrations/init.sql` y la deja limpia al inicio.
- Si PostgreSQL no está disponible, los tests se **saltan** con mensaje
  accionable (`pytest.skip`) — nunca rompen `pytest` bare ni el flujo de quien
  no tenga Docker activo.
- Aislamiento **function-scoped**: `TRUNCATE ... RESTART IDENTITY CASCADE` de
  las 8 tablas de `ancora` tras cada test (rápido, sin recrear la BD).
- Tests de los **7 repositorios reales**:
  - `NotesRepository`: create + search (ILIKE) + orden por `created_at DESC`.
  - `DocumentsRepository`: create/get_by_id/search/delete, extracciones IA
    (create_extraction/get_latest/get_with_extraction) y **cascade**
    document→extractions (`ON DELETE CASCADE`).
  - `VehiclesRepository`: create/get_by_id/list_by_user/find_by_reference
    (ILIKE multi-campo).
  - `MaintenanceRepository`: create/get_history/get_last, FK vehicle
    (cascade) y round-trip JSONB de `work_performed`.
  - `ActionProposalsRepository`: ciclo de gobernanza completo
    create→get_pending→confirm→mark_executed con transiciones de status y
    timestamps; FK `source_document_id` (`SET NULL`).
  - `RemindersRepository`: create/list_by_user (con y sin filtro `status`),
    FK `source_action_id`.
  - `CalendarRepository`: create/list_range (límites inclusivos).
- **Transversales**: scoping por `user_id` en TODOS los repos (los datos de
  un usuario son invisibles/inalterables para otro), datetimes devueltos
  timezone-aware, JSONB devuelto como dict nativo.

### Should Have

- Job de CI `integration` en GitHub Actions con service container
  `postgres:16` aplicando `init.sql` — los integration tests pasan en cada PR.
- Marker `integration` registrado en `pyproject.toml` para filtrar
  (`pytest -m integration` / `-m "not integration"`).
- Un test del flujo de gobernanza de nivel service (propose/confirm/execute)
  combinando `ActionProposalsRepository` con un service de dominio real.

### Won't Have (esta spec)

- Testear el schema `agno_runtime` o el runtime de Agno — infraestructura
  reemplazable (ADR-001); su DB es la de Agno, no la del dominio (§2.7).
- Testear los backends de Storage (local/Supabase) contra servicios reales:
  cubierto por unit tests (mocks) y por el E2E de specs/007 (BL-14 T7).
- Añadir `testcontainers-python`: se reutiliza el `docker-compose.yml`
  existente (mismo Docker que ya exige el repo); cero dependencias nuevas.
- Alembic (BL-12): la fixture aplica `init.sql` directamente (idempotente).
- Cargar datos semilla: cada test crea lo que necesita; el estado parte
  vacío tras el TRUNCATE.

---

## Design

### Resolución de BD

```text
ANCORA_TEST_DATABASE_URL definida → usar tal cual (CI, setup custom)
si no → docker compose up -d postgres
        → DSN admin  postgresql://ancora:ancora@localhost:5432/ancoramind
        → CREATE DATABASE ancoramind_test (drop previo si existe)
        → aplicar migrations/init.sql sobre ancoramind_test (psycopg,
          multi-statement)
        → engine async: postgresql+asyncpg://ancora:ancora@localhost:5432/ancoramind_test
```

El usuario `ancora` de docker-compose es superusuario de la instancia, por lo
que puede `CREATE DATABASE`. La BD de dev `ancoramind` queda intocada.

### Fixtures (conftest.py)

| Fixture | Scope | Responsabilidad |
|---|---|---|
| `_postgres_ready` | session | arrancar contenedor, esperar readiness, skip si no hay Docker |
| `_test_database` | session | drop/create `ancoramind_test` + aplicar `init.sql` |
| `db` | session | `init_database(url)` → yield → `close_database()` |
| `session` | function | `AsyncSession` fresca por test + `TRUNCATE` de las 8 tablas al final |

### Aislamiento

`TRUNCATE ancora.notes, ancora.documents, ancora.ai_extractions,
ancora.vehicles, ancora.vehicle_maintenance, ancora.action_proposals,
ancora.reminders, ancora.calendar_events RESTART IDENTITY CASCADE` — el
`CASCADE` cubre las FKs entre ellas. Más rápido que recrear la BD por test y
suficiente porque cada test crea sus entidades.

### Compatibilidad

- `pytest tests/unit/` no cambia (126 tests, mocks).
- `pytest` bare (testpaths=`tests`): integration se **salta** sin Docker, no
  falla. Con Docker arrancado, corre unit + integration.
- Windows/Docker Desktop: `docker compose up -d postgres` funciona igual
  (PowerShell no interviene: sin redirecciones `<`).

---

## Success Criteria

1. Con `docker compose up postgres -d`: `pytest tests/integration/` verde
   cubriendo los 7 repositorios + transversales (scoping, JSONB, tz, FKs).
2. Sin Docker/PostgreSQL: la suite **se salta** con instrucciones, sin errores.
3. `pytest tests/unit/` sigue verde; el conteo documentado (126) no cambia.
4. La BD de dev `ancoramind` permanece intacta: todo ocurre en
   `ancoramind_test`.
5. (Should Have) CI verde con job `integration` sobre service container
   `postgres:16`.
6. BL-2 tachado en `BACKLOG.md` con enlace a esta spec; `verification.md`
   documenta la ejecución local (y CI si procede).
