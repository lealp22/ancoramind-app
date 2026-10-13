# Tasks: 035 — Subclasificación WRITE_TRIVIAL / WRITE_REVIEWABLE

> Todas las tareas son código puro + migración + tests unitarios/integración.
> Ninguna requiere infraestructura real para implementarse; los tests de
> integración (T3, T8) solo se **verifican** contra PostgreSQL/Docker cuando
> esté disponible — mientras tanto quedan preparados y se omiten, igual que
> el resto de la suite (`AGENTS.md` §1).

## T1: Migración Alembic — `consent_mode`

- [ ] `migrations/versions/0014_write_trivial_consent_mode.py`
      (`down_revision="0013_session_token_index"`): añade
      `ancora.action_proposals.consent_mode VARCHAR(32) NOT NULL
      DEFAULT 'explicit_confirmation'` + `CHECK` nuevo
      (`ck_action_proposals_consent_mode IN ('explicit_confirmation',
      'self_authorized')`), siguiendo el mismo patrón idempotente
      (`ADD COLUMN IF NOT EXISTS` + `DO $$ ... IF NOT EXISTS` para el
      constraint) que `0006_proposal_consent.py`. Sin índice nuevo: no hay
      consulta que filtre por `consent_mode` todavía.
- [ ] `downgrade()`: `DROP CONSTRAINT IF EXISTS` + `DROP COLUMN IF EXISTS`,
      simétrico.
- [ ] `migrations/init.sql` actualizado para quedar equivalente a `head`
      (columna + constraint en la definición de `action_proposals`).
- [ ] Aplicar y verificar contra PostgreSQL real cuando haya Docker
      disponible (fresh install + upgrade sobre datos existentes +
      downgrade), como exige `AGENTS.md` §10.5. Mientras tanto: validar que
      `alembic upgrade head`/`downgrade -1` no lanzan error de sintaxis
      (revisión aislada, sin aplicar).

## T2: Dominio — `ConsentMode`

- [ ] `src/domain/actions/models.py`: nuevo
      `class ConsentMode(StrEnum): EXPLICIT_CONFIRMATION = "explicit_confirmation"`
      `SELF_AUTHORIZED = "self_authorized"`, junto a `ProposalStatus`. Sin
      cambios en `ClaimedProposal`/`ConsentClaimResult` — `consent_mode` no
      participa en el pipeline de confirmación (`claim_confirmation`,
      `ProposalExecutor`), es exclusivo de la fila de auditoría.
- [ ] Tests: extender `tests/unit/test_proposal_consent_model.py` con el
      round-trip del enum (valores, `StrEnum` comparación con string plano).

## T3: Repositorio — `ActionProposalsRepository.create_self_authorized`

- [ ] `src/repositories/actions.py`: nuevo método, mismo estilo que
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
- [ ] Tests de integración: nuevo caso en `tests/integration/test_actions_repo.py`
      — inserta una fila `self_authorized`, verifica `confirming_interaction_id
      IS NULL` sin violar `uq_action_proposals_confirming_interaction`
      (dos filas `self_authorized` seguidas, ambas con `NULL`, no
      colisionan), verifica que el método **no comitea** por sí solo
      (la fila no es visible desde otra sesión hasta que el llamador
      comitea). Preparado, se omite sin Docker; estructura y aserciones
      completas desde esta iteración.

## T4: Orquestador — `TrivialExecutor`

- [ ] `src/domain/actions/trivial_executor.py` (nuevo), mismo patrón que
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
- [ ] Tests unitarios: `tests/unit/test_trivial_executor.py` (nuevo) —
      mock de `apply_mutation` y de `ActionProposalsRepository` (o sesión
      en memoria si el patrón ya usado en `test_governed_interaction_runner.py`
      lo permite): éxito (mutación + auditoría + 1 solo commit), fallo
      `target_missing_or_not_owned` (rollback, sin fila de auditoría, sin
      excepción propagada), fallo inesperado (rollback, mensaje genérico).

## T5: Tools — rama trivial en `todos.py` y `notes.py`

- [ ] `src/agent/tools/todos.py::propose_todo_item` (L324-387): si
      `description is None and priority is None and due_date is None` →
      delega en `TrivialExecutor.execute("create_todo_item", {"list_id":
      str(list_id), "title": title.strip()}, user_ctx.user_id)` y devuelve
      su resultado directamente (sin crear `ActionProposal` pending). Si
      **cualquier** campo opcional viene informado, sigue el camino actual
      sin cambios (crea proposal `pending_confirmation`). Docstring
      actualizado explicando ambas ramas al LLM.
- [ ] `propose_todo_item_complete` (L452-464) / `propose_todo_item_reopen`
      (L467-479): ya no delegan en `_propose_todo_item_status` (crea
      proposal); delegan siempre en
      `TrivialExecutor.execute("set_todo_item_status", {"item_id": str(item_id),
      "status": "done"|"pending"}, user_ctx.user_id)`. Si
      `_propose_todo_item_status` queda sin otros llamadores, se elimina.
- [ ] `src/agent/tools/notes.py::propose_note` (L41-69): delega siempre en
      `TrivialExecutor.execute("remember_note", {"content": content.strip()},
      user_ctx.user_id)` en vez de crear `ActionProposal` pending. Docstring
      y texto de respuesta actualizados (ya no "¿Confirmas?").
- [ ] Sin cambios en `propose_todo_list`, `propose_todo_item_update`,
      `propose_todo_item_move`, `propose_todo_item_delete` — quedan
      `WRITE_REVIEWABLE` exactamente como hoy.
- [ ] Tests: extender `tests/unit/test_todos_tools.py` (rama trivial vs
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

- [ ] `AGENTS.md` §2.4: añade la subclasificación `WRITE_TRIVIAL` /
      `WRITE_REVIEWABLE` dentro del punto 4, con el criterio ("reversible en
      un paso, sin datos ambiguos que revisar, target ya existente y
      propiedad verificada") y los 3 ejemplos concretos de esta iteración
      (`create_todo_item` sin campos opcionales, `set_todo_item_status`,
      `remember_note`). Mantiene intacta la excepción ya aprobada de
      `analyze_document` (T4.7/specs/023) y aclara que `WRITE_TRIVIAL` es
      gobernanza equivalente (auditoría atómica obligatoria), no una
      segunda excepción ad hoc.
- [ ] `docs/governance.md`: tabla de riesgo actualizada con la subfila
      `WRITE_TRIVIAL` y sus 3 tools.
- [ ] `prompts/skills/todos.md` / `prompts/skills/notes.md` (si existe este
      último; si no, valorar si hace falta crearlo): nota breve sobre qué
      respuesta esperar en la rama trivial (confirmación inmediata, no
      botones Sí/No).
- [ ] `AGENTS.md` §1 (contador de tests) y `BACKLOG.md` BL-46: marcar
      "implementado localmente" con fecha, enlazando `specs/035` y
      resumiendo el alcance real entregado (no el propuesto originalmente,
      si difiere).

## T8: Verificación

- [ ] `pytest tests/unit/` completo en verde, incluidos los tests nuevos de
      T2/T4/T5 y de regresión (los casos existentes de `propose_todo_item`
      con `description`/`priority`/`due_date` informados siguen creando
      `ActionProposal` pending sin tocar `TrivialExecutor`).
- [ ] `ruff check src/ tests/ scripts/ migrations/` y `mypy src/` limpios.
- [ ] `tests/integration/` (T3) ejecutado y verificado contra PostgreSQL
      real cuando haya Docker disponible; documentar en `verification.md`
      si esta iteración se cierra sin esa verificación (como ya ocurrió en
      specs/024, T3 marcado "aplicada y verificada" solo tras disponer de
      Postgres).
- [ ] `verification.md` nuevo, con el resumen de qué se probó y qué quedó
      pendiente de infraestructura real.
