# Tasks: 035 — Subclasificación WRITE_TRIVIAL / WRITE_REVIEWABLE

> Implementación y verificación PostgreSQL completadas. El E2E Telegram se
> mantiene separado en `verification.md`.

## T1: Migración Alembic — `consent_mode`

- [x] `migrations/versions/0014_write_trivial_consent_mode.py`
      (`down_revision="0013_session_token_index"`): añade
      `ancora.action_proposals.consent_mode VARCHAR(32) NOT NULL
      DEFAULT 'explicit_confirmation'` + `CHECK` nuevo
      (`ck_action_proposals_consent_mode IN ('explicit_confirmation',
      'self_authorized')`), siguiendo el mismo patrón idempotente
      (`ADD COLUMN IF NOT EXISTS` + `DO $$ ... IF NOT EXISTS` para el
      constraint) que `0006_proposal_consent.py`. Sin índice nuevo: no hay
      consulta que filtre por `consent_mode` todavía.
- [x] `downgrade()`: `DROP CONSTRAINT IF EXISTS` + `DROP COLUMN IF EXISTS`,
      simétrico.
- [x] `migrations/init.sql` actualizado para quedar equivalente a `head`
      (columna + constraint en la definición de `action_proposals`).
- [x] Aplicar y verificar contra PostgreSQL real: fresh install, upgrade sobre
      datos existentes, downgrade e equivalencia de `migrations/init.sql`
      cubiertos por `tests/integration/test_migrations.py` (4 passed).

## T2: Dominio — `ConsentMode`

- [x] `src/domain/actions/models.py`: nuevo
      `class ConsentMode(StrEnum): EXPLICIT_CONFIRMATION = "explicit_confirmation"`
      `SELF_AUTHORIZED = "self_authorized"`, junto a `ProposalStatus`. Sin
      cambios en `ClaimedProposal`/`ConsentClaimResult` — `consent_mode` no
      participa en el pipeline de confirmación (`claim_confirmation`,
      `ProposalExecutor`), es exclusivo de la fila de auditoría.
- [x] Tests: extender `tests/unit/test_proposal_consent_model.py` con el
      round-trip del enum (valores, `StrEnum` comparación con string plano).

## T3: Repositorio — `ActionProposalsRepository.create_self_authorized`

- [x] `src/repositories/actions.py`: nuevo método, mismo estilo que
      `create()` (L53-106) pero:
      - **no comitea** (disciplina de la "Consent API" ya documentada en
        el docstring del módulo — el llamador controla la transacción
        junto con la mutación real);
      - `INSERT` con `status='executed'`, `consent_mode='self_authorized'`,
        `completed_at=now`, `confirming_interaction_id=NULL`,
        `payload_hash` calculado igual que hoy;
      - resuelve `source_interaction_id`/`bot_id`/`chat_id` igual que
        `create()` (parámetros explícitos, o `current_provenance()` si no
        se pasan) — **reusa la columna existente**, no crea ninguna nueva
        de interacción;
      - devuelve el `ProposalRecord` insertado (mismo shape que `create()`)
        para que el llamador pueda usar su `id` en logs/auditoría si hace
        falta.
      Firma propuesta:
      `async def create_self_authorized(self, user_id: str, tool_name: str, payload: ProposalPayload, *, source_interaction_id: UUID | None = None, bot_id: int | None = None, chat_id: int | None = None) -> ProposalRecord`.
- [x] Tests de integración: casos en `tests/integration/test_actions_repo.py`
      — inserta una fila `self_authorized`, verifica `confirming_interaction_id
      IS NULL` sin violar `uq_action_proposals_confirming_interaction`
      (dos filas `self_authorized` seguidas, ambas con `NULL`, no
      colisionan), y verifica que el método **no comitea** por sí solo.
      Verificado contra PostgreSQL real dentro de los 9 tests de
      `test_actions_repo.py` superados el 2026-10-15.

## T4: Orquestador — `TrivialExecutor`

- [x] `src/domain/actions/trivial_executor.py` (nuevo), mismo patrón que
      `src/domain/actions/executor.py::ProposalExecutor` pero sin estado
      previo que reclamar:
      ```python
      class TrivialExecutor:
          def __init__(self, sessions: Callable[[], Awaitable[AsyncSession]]): ...

          async def execute(self, tool_name: str, payload: dict, user_id: str) -> str:
              # abre sesión; construye un ClaimedProposal sintético
              # (id=uuid4(), tool_name, payload, source_document_id=None,
              #  confirming_interaction_id=uuid4()) — campo requerido por el
              # dataclass pero no usado por apply_mutation(), que no lo lee
              # ni lo persiste; nunca llega a action_proposals por esta vía.
              # intenta: reply = await apply_mutation(session, claimed, user_id)
              #   (reutiliza TODO el dispatch existente de mutations.py —
              #   create_todo_item/set_todo_item_status/remember_note ya
              #   están en SUPPORTED_MUTATIONS, no hace falta tocarlo)
              # si éxito: ActionProposalsRepository(session).create_self_authorized(
              #   user_id, tool_name, payload) sin commit propio
              # await session.commit()  # mutación + auditoría atómicas
              # salvo ValueError("target_missing_or_not_owned"): rollback,
              #   devuelve mensaje "no encontrado", SIN crear fila de
              #   auditoría (nada ocurrió, nada que auditar)
              # salvo cualquier otra excepción: rollback, mensaje genérico
              #   fijo, sin reintento (mismo criterio que ProposalExecutor)
      ```
      Deliberadamente **no** extiende `ProposalExecutor` ni comparte su
      `SUPPORTED`: no hay reclamo de confirmación que validar, y mezclar
      ambas máquinas de estado en una clase complicaría el camino auditado
      del flujo reviewable existente.
- [x] Tests unitarios: `tests/unit/test_trivial_executor.py` (nuevo) —
      mock de `apply_mutation` y de `ActionProposalsRepository` (o sesión
      en memoria si el patrón ya usado en `test_governed_interaction_runner.py`
      lo permite): éxito (mutación + auditoría + 1 solo commit), fallo
      `target_missing_or_not_owned` (rollback, sin fila de auditoría, sin
      excepción propagada), fallo inesperado (rollback, mensaje genérico).

## T5: Tools — rama trivial en `todos.py` y `notes.py`

- [x] `src/agent/tools/todos.py::propose_todo_item` (L324-387): si
      `description is None and priority is None and due_date is None` →
      delega en `TrivialExecutor.execute("create_todo_item", {"list_id":
      str(list_id), "title": title.strip()}, user_ctx.user_id)` y devuelve
      su resultado directamente (sin crear `ActionProposal` pending). Si
      **cualquier** campo opcional viene informado, sigue el camino actual
      sin cambios (crea proposal `pending_confirmation`). Docstring
      actualizado explicando ambas ramas al LLM.
- [x] `propose_todo_item_complete` (L452-464) / `propose_todo_item_reopen`
      (L467-479): ya no delegan en `_propose_todo_item_status` (crea
      proposal); delegan siempre en
      `TrivialExecutor.execute("set_todo_item_status", {"item_id": str(item_id),
      "status": "done"|"pending"}, user_ctx.user_id)`. Si
      `_propose_todo_item_status` queda sin otros llamadores, se elimina.
- [x] `src/agent/tools/notes.py::propose_note` (L41-69): delega siempre en
      `TrivialExecutor.execute("remember_note", {"content": content.strip()},
      user_ctx.user_id)` en vez de crear `ActionProposal` pending. Docstring
      y texto de respuesta actualizados (ya no "¿Confirmas?").
- [x] Sin cambios en `propose_todo_list`, `propose_todo_item_update`,
      `propose_todo_item_move`, `propose_todo_item_delete` — quedan
      `WRITE_REVIEWABLE` exactamente como hoy.
- [x] Tests: extender `tests/unit/test_todos_tools.py` (rama trivial vs
      reviewable de `propose_todo_item` según campos opcionales;
      `propose_todo_item_complete`/`reopen` siempre trivial) y
      `tests/unit/test_note_tools.py` (`propose_note` siempre trivial),
      mockeando `TrivialExecutor`.

## T6: Wiring — `main.py`

- [x] **Resuelto sin cambios en `main.py` (2026-10-13).** T5 ya instancia
      `TrivialExecutor` como singleton perezoso **dentro de cada módulo**
      (`todos.py::_get_trivial_executor()`, `notes.py::_get_trivial_executor()`),
      usando `src.repositories.database.get_session` directamente — el mismo
      patrón que ya usan `_get_todos_service()`/`_get_actions_repo()`/
      `_get_notes_service()` en esos mismos módulos. `main.py` nunca
      construye esos repositorios/servicios por inyección; solo llama
      `init_database()` en `_init_domain_tools()` para que `get_session`
      funcione, y eso ya cubre `TrivialExecutor` sin tocar nada más.
      Centralizar la construcción en `main.py` habría sido inconsistente con
      el resto del fichero y no aportaba nada (no hay estado que compartir
      entre tools).
- [x] `python -c "from src.main import app"` — import limpio, sin errores.
- [x] `tests/unit/test_legacy_consent_boundary.py` (incluye
      `test_production_registration_only_exposes_reads_proposals_and_approved_exceptions`)
      — 33 passed, confirma que `propose_note`/`propose_todo_item` siguen
      registrados y que ningún `execute_*` lo está.

## T7: Documentación y gobernanza

- [x] `AGENTS.md` §2.4: añadida la subclasificación `WRITE_TRIVIAL` /
      `WRITE_REVIEWABLE` dentro del punto 4, con el criterio y los 3
      ejemplos concretos de esta iteración. Mantiene intacta la excepción
      ya aprobada de `analyze_document` (T4.7/specs/023) y aclara que
      `WRITE_TRIVIAL` es gobernanza equivalente (auditoría atómica
      obligatoria), no una segunda excepción ad hoc.
- [x] `docs/governance.md`: tabla de riesgo + matriz de confirmación
      actualizadas con la subfila `WRITE_TRIVIAL` y sus 3 tools; nota en §7
      aclarando que es independiente de `GOVERNED_CONSENT_ENABLED`.
- [x] `prompts/skills/todos.md`: separado en "Trivial Mutations" (ejecuta
      directo, nunca inventar "¿Confirmas?") y "Reviewable Mutations"
      (gobernado, sin cambios). `prompts/skills/notes.md` no existe y no se
      crea — el docstring de `propose_note` ya es la única fuente que el
      Agent necesita para una tool suelta sin skill dedicada.
- [x] `AGENTS.md` §1 (1329 unit + 158 integration) y `BACKLOG.md` BL-46
      (snapshot + entrada completa) actualizados con el alcance real
      entregado.

## T8: Verificación

- [x] `pytest tests/unit/` → 1329 passed, incluidos los tests nuevos de
      T2/T4/T5 y de regresión (los casos existentes de `propose_todo_item`
      con `description`/`priority`/`due_date` informados siguen creando
      `ActionProposal` pending sin tocar `TrivialExecutor`).
- [x] `ruff check src/ tests/ scripts/ migrations/` y `mypy src/` (167
      archivos) limpios.
- [x] `tests/integration/` (T3): suite global verificada contra PostgreSQL real
      (**159 passed, 1 STT live skipped**) y suite focal
      `test_actions_repo.py` (**9 passed**) el 2026-10-15.
- [x] `verification.md` actualizado con migración e integración PostgreSQL
      verificadas; solo queda E2E Telegram.
