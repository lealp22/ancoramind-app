# Tasks: 009 — Integration Tests with Real PostgreSQL

## T1: Infraestructura de test (conftest.py)

- [x] Resolver servidor: `ANCORA_TEST_DATABASE_URL` o default docker-compose.
- [x] Arrancar `docker compose up -d postgres` y esperar readiness
      (reintentos, timeout ~30 s); `pytest.skip` accionable si no hay Docker
      (`ANCORA_TEST_REQUIRE_DB=1` convierte el skip en fail — usado en CI).
- [x] Crear BD dedicada `ancoramind_test` (drop + create vía psycopg sobre
      DSN admin; jamás tocar `ancoramind`).
- [x] Aplicar `migrations/init.sql` sobre `ancoramind_test` (psycopg,
      multi-statement).
- [x] Fixtures: `db` (init/close de engine por test con
      `postgresql+asyncpg://...ancoramind_test` — ver desviación 1 en
      verification.md) y `session` (function: AsyncSession fresca + TRUNCATE
      de las 8 tablas `RESTART IDENTITY CASCADE` al terminar).
- [x] Registrar marker `integration` en `pyproject.toml`; verificado:
      `pytest` bare sin Docker salta sin fallos (16 skipped), con Docker corre
      todo (142 passed), `-m "not integration"` = 126 passed/16 deselected.

## T2: Notes + Documents

- [x] `NotesRepository.create` + `search` con y sin query (ILIKE, orden
      `created_at DESC`, límite 20).
- [x] `DocumentsRepository`: create → get_by_id → search → delete (True);
      get/delete de otro usuario → None/False.
- [x] `create_extraction` → `get_latest_extraction` (la más reciente gana) →
      `get_document_with_extraction`. **Halló bug real**: el repo pasaba el
      dict sin `json.dumps()` al bind jsonb de asyncpg → fix en
      `documents.py` (detallado en verification.md).
- [x] Cascade: borrar documento elimina sus `ai_extractions`
      (`ON DELETE CASCADE`).

## T3: Vehicles + Maintenance

- [x] `VehiclesRepository`: create (UUID/created_at generados por BD) →
      get_by_id → list_by_user (orden) → find_by_reference (ILIKE sobre
      make/model/nickname/registration).
- [x] `MaintenanceRepository`: create → get_history (orden date DESC) →
      get_last; round-trip JSONB de `work_performed`.
- [x] FK vehicle: borrar vehículo elimina su mantenimiento (cascade);
      registro con vehicle_id inexistente → `IntegrityError`.

## T4: Actions (gobernanza) + Reminders + Calendar

- [x] `ActionProposalsRepository`: ciclo completo create (status
      `pending_confirmation`) → get_pending → confirm (status `confirmed` +
      `confirmed_at`) → mark_executed (status `executed` + `executed_at`).
- [x] Gobernanza de scoping: usuario B no puede confirmar ni obtener la
      propuesta de A (get_pending → None, confirm → None, mark_executed no-op).
- [x] Confirm doble sobre la misma propuesta → None (idempotencia de estado).
- [x] `RemindersRepository`: create (status `pending` default de BD) →
      list_by_user con y sin filtro status; FK `source_action_id` válida.
- [x] `CalendarRepository`: create → list_range con límites inclusivos y
      eventos fuera de rango excluidos.

## T5: Transversales + CI + docs

- [x] Scoping por `user_id` verificado en todos los repos (fixtures
      `user_a`/`user_b` en conftest).
- [x] Datetimes devueltos timezone-aware (TIMESTAMPTZ) y JSONB como dict
      (asyncpg/SQLAlchemy decodifica a dict).
- [x] (Should) Job CI `integration`: la fixture arranca el postgres de
      docker-compose en el runner (misma ruta de código que local) con
      `ANCORA_TEST_REQUIRE_DB=1`. Primera validación: push de cierre.
- [ ] (Should, no bloquea el cierre) Test de gobernanza de nivel service
      (propose/confirm/execute combinando repo + service real) — los repos y
      el ciclo ya están cubiertos; el flujo service se valida en BL-1.
- [x] `docs/development.md`: sección "Integration tests" + variables
      `ANCORA_TEST_*` en la tabla de env vars.
- [x] Actualizar AGENTS.md (comandos) y BACKLOG.md al cerrar.

## T6: Verificación

- [x] `pytest tests/unit/` sigue verde (126).
- [x] `docker compose up postgres -d` + `pytest tests/integration/ -v` verde
      en local (Windows 11 + Docker Desktop 29.2.1) → **16 passed**.
- [x] Sin PostgreSQL (URL inalcanzable simulada): suite se salta (16 skipped)
      con mensaje accionable.
- [x] Verificado que `ancoramind` (dev) queda intacta (1 nota preexistente
      conservada; toda la actividad en `ancoramind_test`, truncada a 0 filas).
- [x] `verification.md` con salida de ejecución y conteo de tests.
