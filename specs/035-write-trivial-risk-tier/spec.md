# Spec: 035 — Subclasificación WRITE_TRIVIAL / WRITE_REVIEWABLE

> **Backlog:** BL-46
> **Status:** proposed (2026-10-13) — pendiente de implementación, sin tasks.md
> ejecutable todavía.
> **Decisiones del propietario (2026-10-13):**
> 1. Se aprueba subclasificar `WRITE` dentro de AGENTS.md §2.4 en
>    `WRITE_TRIVIAL` (ejecuta directo, con auditoría) y `WRITE_REVIEWABLE`
>    (mantiene `propose_*`/confirmación explícita, sin cambios).
> 2. Alcance de la primera iteración: **toda nota** (`propose_note`/
>    `remember_note`) y, dentro de TODO items, **solo** añadir un item con
>    título (sin `description`/`priority`/`due_date`) y marcar
>    completado/reabierto, siempre sobre una lista ya existente.
> 3. Esta spec documenta la decisión y el diseño antes de tocar código
>    (ADR no aplica — no hay cambio de runtime/infraestructura; se sigue el
>    mismo precedente que T4.7/specs/023, documentado en AGENTS.md + spec).
> **Target:** reducir la fricción de confirmación para el subconjunto de
> mutaciones de menor riesgo, sin debilitar la gobernanza de ninguna otra
> mutación WRITE/EXTERNAL_ACTION/DESTRUCTIVE existente.

---

## Requirement

Hallazgo real (BL-46, E2E Telegram 2026-10-13): pedir "Añade leche y pan a la
lista Compras" (lista ya existente, orden sin ambigüedad) exige igualmente un
par de botones Sí/No por item. AGENTS.md §2.4 hoy no distingue riesgo dentro
de `WRITE` — toda mutación, trivial o no, pasa por `ActionProposal`
(`pending_confirmation → confirmado → ejecutado`), salvo la única excepción ya
aprobada (`analyze_document`/`DocumentService.ingest`, T4.7/specs/023: "enviar
un adjunto ya es la señal de intención").

Investigación previa a esta spec (`specs/035`, exploración de código,
2026-10-13) encontró dos hechos que condicionan el diseño:

1. **El camino `execute_*` de las tools del Agent ya no ejecuta nada.**
   `src/repositories/actions.py::confirm_or_use_confirmed` está retirado y
   siempre devuelve `None` (hardening BL-39/40, 2026-10-11); `execute_todo_item`,
   `execute_todo_list` y `execute_note` (`src/agent/tools/todos.py`,
   `src/agent/tools/notes.py`) responden siempre "No se encontró la propuesta
   ... o ya no está pendiente." El pipeline real de confirmación/ejecución es
   `InteractionProcessor` (`src/domain/interactions/processor.py`) →
   `ActionProposalsRepository.claim_confirmation` →
   `ProposalExecutor.execute()` (`src/domain/actions/executor.py`) →
   `apply_mutation()` (`src/domain/actions/mutations.py`), disparado por el
   "Sí" del usuario **antes** de que el Agent corra, nunca por una tool call
   del LLM. Esta spec no puede "acelerar" ese pipeline — necesita una vía
   nueva y distinta.
2. **`Note` no tiene campos estructurados de riesgo.** `NoteCreate`/`Note`
   (`src/domain/notes/models.py`) solo tienen `content: str` (1–5000 chars)
   libre; no hay fecha, importe ni identificador dedicado. No existe hoy
   ninguna forma de distinguir "nota simple" de "nota sensible" a nivel de
   esquema sin introducir un heurístico de contenido nuevo (descartado para
   esta iteración, ver "Won't Have"). Por eso el propietario decidió tratar
   **toda** nota como `WRITE_TRIVIAL`.

### Must Have

- **AGENTS.md §2.4** documenta `WRITE_TRIVIAL` y `WRITE_REVIEWABLE` como
  subniveles de `WRITE`, con el criterio: *reversible en un paso, sin
  ambigüedad de datos a revisar, target ya identificado y existente* →
  `WRITE_TRIVIAL`; cualquier dato que convenga revisar antes de persistir
  (fecha/hora, importe, identificador, creación de un recurso nuevo con
  nombre libre) → `WRITE_REVIEWABLE` (sin cambios respecto a hoy).
  `EXTERNAL_ACTION`/`DESTRUCTIVE` no se tocan.
- **Vía de ejecución nueva** (tool → servicio de dominio directo, mismo
  patrón que `analyze_document`): la tool valida input + propiedad del
  recurso objetivo (lista/item ya existente y del usuario) y llama al
  servicio de dominio directamente, **sin** crear un `ActionProposal`
  `pending_confirmation` y sin pasar por `claim_confirmation`/
  `ProposalExecutor`/`apply_mutation` (esa vía sigue siendo exclusiva de
  `WRITE_REVIEWABLE`).
- **Auditoría atómica obligatoria** para toda mutación `WRITE_TRIVIAL`,
  igual que exige el patrón `ActionProposal` para `WRITE_REVIEWABLE`:
  mutación + fila de auditoría se escriben en la misma transacción. Diseño
  **resuelto** (2026-10-13, tras inspeccionar `src/repositories/actions.py`):
  - Nueva columna `action_proposals.consent_mode` (`'explicit_confirmation'`
    por defecto | `'self_authorized'`) — única columna nueva necesaria.
  - **No hace falta columna de interacción nueva**: `source_interaction_id`
    (ya existe desde `migrations/versions/0002_llm_governance.py`, sin
    índice único) ya registra "qué interacción pidió la propuesta" y es
    justo lo que necesita una fila `self_authorized`. El campo con índice
    único (`uq_action_proposals_confirming_interaction`) es
    `confirming_interaction_id` — una fila `self_authorized` simplemente lo
    deja en `NULL` (el índice es parcial, `WHERE confirming_interaction_id
    IS NOT NULL`, así que varios `NULL` no colisionan).
  - **Nuevo método en `ActionProposalsRepository`** (no reusar `create()`):
    `create()` comitea por su cuenta y tiene `'pending_confirmation'`
    hardcodeado en el SQL de inserción — no sirve para escribir directo en
    `'executed'` ni para compartir transacción con la mutación. El método
    nuevo sigue la disciplina de la "Consent API" ya documentada en el
    repositorio (`mark_presented`/`claim_confirmation`/etc.: **nunca
    comitea**, el llamador controla la transacción junto con la mutación
    real), inserta con `status='executed'`, `consent_mode='self_authorized'`,
    `completed_at=now`, `confirming_interaction_id=NULL`, y resuelve
    `source_interaction_id`/`bot_id`/`chat_id` igual que `create()` hoy
    (`current_provenance()` cuando no se pasan explícitos).
- **Alcance exacto de esta iteración:**
  - `propose_note` → ejecuta directo (ver "Should Have" sobre renombrar).
  - `propose_todo_item(..., description=None, priority=None, due_date=None)`
    sobre un `list_id` existente del usuario → ejecuta directo. Si **cualquier**
    campo opcional viene informado, sigue siendo `WRITE_REVIEWABLE` (dato a
    revisar) — mismo nombre de tool, rama interna distinta.
  - `propose_todo_item_complete` / `propose_todo_item_reopen` → ejecutan
    directo siempre (no tienen campos opcionales).
  - **Quedan en `WRITE_REVIEWABLE` sin cambios:** `propose_todo_list` (crea
    recurso nuevo con nombre libre), `propose_todo_item_move`,
    `propose_todo_item_delete`, y absolutamente todo lo demás (vehículos,
    mantenimiento, recordatorios, calendario, borrado documental).
- Respuesta de la tool para el caso trivial: confirma la acción ya realizada
  (p.ej. "✅ Añadido «leche» a Compras.") en vez del texto actual de
  "¿Confirmas? Sí/No" — nunca debe sugerir que algo sigue pendiente cuando ya
  se ejecutó.
- Migración Alembic para `consent_mode` (+ columna de interacción de origen
  sin índice único, para trazabilidad) y actualización de
  `migrations/init.sql`.
- `docs/governance.md` (tabla de riesgo) sincronizado con la nueva
  subclasificación.
- Tests unitarios: rama trivial vs reviewable en `propose_todo_item`
  (con/sin campos opcionales), `propose_note`, nueva auditoría
  `self_authorized`, y que ningún camino `WRITE_REVIEWABLE` existente cambia
  de comportamiento (regresión).

### Should Have

- **Decidido (2026-10-13): no renombrar.** `propose_note`,
  `propose_todo_item_complete`, `propose_todo_item_reopen` y
  `propose_todo_item` conservan su nombre — sin cambio de contrato con el
  LLM. Se actualiza únicamente el docstring de cada tool para que quede claro
  que la rama trivial ejecuta inmediatamente, y la respuesta devuelta a ese
  camino nunca dice "¿Confirmas? Sí/No" (ver Must Have).
- `prompts/skills/todos.md` y `prompts/skills/notes.md` (si existe) con una
  nota explícita de qué espera el usuario ver en cada rama.

### Won't Have (esta spec)

- **Heurístico de contenido sensible para notas** (longitud, patrones de
  fecha/importe/IBAN): descartado explícitamente por el propietario — toda
  nota es `WRITE_TRIVIAL` en esta iteración, sin excepción basada en texto.
- **`propose_todo_item_move`/`propose_todo_item_delete` como trivial**: mover
  cambia estructura entre listas y borrar pierde historial del item — quedan
  `WRITE_REVIEWABLE` sin reabrir esta decisión aquí (podría proponerse en una
  iteración posterior con su propio hallazgo).
- **`propose_todo_list` como trivial**: crear una lista nueva con nombre
  libre no cumple "target ya identificado y existente".
- **Extender `WRITE_TRIVIAL` a otros dominios** (vehículos, mantenimiento,
  recordatorios, calendario): fuera de alcance; requeriría su propio
  hallazgo/decisión por dominio.
- **Limpiar los tools `execute_todo_item`/`execute_todo_list`/`execute_note`
  vestigiales** (código muerto desde el hardening BL-39/40 del 2026-10-11,
  hallazgo de esta misma investigación): no es parte de esta spec. Se deja
  anotado como deuda a resolver en un incremento de limpieza aparte — no
  bloquea esta spec porque la vía nueva no los usa ni depende de ellos.
- **Reactivar `confirm_or_use_confirmed`** o cualquier variante del pipeline
  retirado: la vía trivial es nueva e independiente, no una reactivación del
  camino legacy.
- **Undo/deshacer** para la rama trivial: el propietario eligió "ejecuta
  directo con auditoría" frente a la alternativa de "deshacer rápido" — no se
  diseña un mecanismo de deshacer en esta spec.

---

## Design

```text
Tool (propose_todo_item, con list_id existente del usuario):
  1. Valida list_id (UUID, pertenece al usuario) — igual que hoy.
  2. ¿description/priority/due_date informados?
     SÍ -> rama WRITE_REVIEWABLE (sin cambios): crea ActionProposal
           pending_confirmation, como hoy.
     NO -> rama WRITE_TRIVIAL (nueva):
           dentro de una transacción (ninguno de los dos pasos comitea por
           su cuenta — comitea el llamador, igual que `ProposalExecutor`):
             a. TodosService.add_item(user_context, list_id, title) — mutación real
             b. ActionProposalsRepository.create_self_authorized(
                  user_id, tool_name="create_todo_item", payload,
                ) — inserta status='executed', consent_mode='self_authorized',
                completed_at=now, confirming_interaction_id=NULL,
                source_interaction_id resuelto de current_provenance()
                (igual que create() hoy)
           commit único; la tool devuelve el resultado ya ejecutado.

propose_todo_item_complete / propose_todo_item_reopen:
  siempre rama WRITE_TRIVIAL (sin campos opcionales que la hagan reviewable).

propose_note:
  siempre rama WRITE_TRIVIAL (Note no tiene campos de riesgo estructurados).
```

- **Por qué `confirming_interaction_id` queda `NULL` en vez de reusarla:**
  ese campo tiene un índice único (`uq_action_proposals_confirming_interaction`)
  porque una interacción de confirmación ("Sí") solo puede autorizar una
  propuesta. Una fila `self_authorized` no es una confirmación — es la
  propia interacción que *pidió* la acción, ya capturada por
  `source_interaction_id` (columna existente, sin índice único). Dejar
  `confirming_interaction_id` en `NULL` evita cualquier riesgo de colisión
  si el mismo mensaje contuviera además un "Sí" a otra propuesta pendiente.
- **Por qué sigue existiendo una fila en `action_proposals`:** mantiene un
  único lugar de auditoría para toda mutación WRITE del sistema (actor,
  payload, timestamp), coherente con el principio de AGENTS.md §7 de que
  toda mutación es auditable — no se crea una tabla de auditoría paralela.
- **Transacción única mutación+auditoría:** mismo patrón ya usado en
  BL-26 (ejecutor determinista de voz) y en `ProposalExecutor.execute()`
  (mutación + transición de estado en el mismo commit) — ninguna mutación
  `WRITE_TRIVIAL` puede quedar sin su fila de auditoría ni viceversa.
- **Gobernanza:** `WRITE_REVIEWABLE` no cambia en absoluto — mismo
  `ActionProposal`/`claim_confirmation`/`ProposalExecutor` de hoy. Esta spec
  solo añade una vía paralela para el subconjunto `WRITE_TRIVIAL` aprobado;
  no reemplaza ni toca el pipeline existente.

---

## Decisiones ya resueltas (2026-10-13, antes de escribir tasks.md)

Las tres preguntas abiertas de la primera versión de esta spec quedaron
cerradas tras inspeccionar `src/repositories/actions.py`:

1. **Método nuevo vs reusar `create()`** → método nuevo
   (`create_self_authorized` o nombre equivalente), sin auto-commit, porque
   `create()` comitea por su cuenta y fuerza `status='pending_confirmation'`
   en el SQL.
2. **Columna de interacción nueva** → innecesaria. Se reusa
   `source_interaction_id` (ya existe, sin índice único); solo se añade
   `consent_mode`.
3. **Renombrar `propose_note`/`propose_todo_item_complete`/`reopen`** →
   no, se mantienen los nombres actuales (decisión del propietario,
   2026-10-13); solo cambian docstrings y el texto de respuesta.

No quedan preguntas abiertas que bloqueen escribir `tasks.md`. El único
detalle que `tasks.md` debe fijar es el nombre exacto del método nuevo del
repositorio (p.ej. `create_self_authorized` vs `create_executed_trivial`) —
una elección de naming sin impacto de diseño.
