# Revisión legible de evals — qué cambia y cómo usarlo

Incremento local de specs/045. Sin commit de publicación, push, despliegue ni
inferencia por el agente. No cambia semántica de etiquetas ni el presupuesto de la
sesión de specs/042 (0,10 USD acumulados).

## Qué verá el propietario

- `review --run ID`: el bloque del caso (Input, Contexto, answer, proposal_text,
  Propuestas, Presentación Core, Hechos de tools, Tools) sale **una sola vez**, y
  después los criterios pendientes, uno a uno. Cada línea de datos lleva el prefijo
  fijo `  | `; los saltos de línea y caracteres de control dentro de un valor salen
  escapados (`\u000a`), no como líneas reales. Cada criterio sigue guardándose en el
  momento. Un fail o `x` sigue deteniendo el caso y los siguientes (decisión E).
- `status --run ID --human` y `session-status --human`: resumen en texto con estado,
  una línea por caso (`criterios=revisados/total`), saldo de sesión y **Siguiente
  paso**. Ninguna sugerencia dice «ejecuta `run`». Sin `--human` la salida es el
  mismo JSON de antes.
- Un fallo de consola imprime `eval_console_blocked_or_disconnected` con `reason`:
  `console_not_interactive`, `review_disconnected`,
  `evidence_unreadable_or_wrong_key`, `run_not_found` o `unexpected`. Nunca texto de
  excepción, rutas ni contenido. `do_not_replay` y
  `review_can_reopen_saved_evidence` se mantienen.

## Huella y alcance de sesión

Ficheros de código tocados (todos dentro de `_HARNESS`):
`src/agent/eval_campaign_runner.py`, `src/agent/eval_durable_review.py`,
`scripts/eval_console.py`. Comprobación local de `session_scope` entre `f4d8bd8`
(origin/main antes de specs/045) y el árbol actual:

```
before 08db4e70aa68424691b5d15cb090f56c347caf4a7fafeb612cf26c2b4c0c5f3d
after  08db4e70aa68424691b5d15cb090f56c347caf4a7fafeb612cf26c2b4c0c5f3d
SCOPE IDENTICAL; ficheros de código fuera de _HARNESS: ninguno
```

Dos tests de `tests/unit/test_eval_review_ux.py` fijan esto: los tres ficheros están en
`_HARNESS`, y editarlos no cambia `session_scope` mientras que tocar un fichero de
comportamiento sí. Si una tarea posterior toca otro fichero, la sesión cambiaría de
alcance y habría que hablarlo antes de publicar.

La **huella del arnés** (`source_fingerprint`) sí cambia: es otra imagen. Por tanto
hace falta SHA, CI del mismo SHA y publicación manual con **Actualizar evaluador**
([specs/041](../041-manual-eval-deploy/runbook.md)), sin CLI local. La publicación
sigue bloqueada mientras haya trabajos `NEEDS_APPROVAL` ajenos en Railway
([specs/042](../042-eval-validation-session/runbook.md)); no se cancelan ni aprueban
automáticamente. Hasta publicar, el evaluador desplegado conserva la consola anterior.

## Límites conocidos

- No se ha visto la consola en un terminal real, solo con dobles de prueba. Conviene
  revisar un caso real tras publicar.
- `Tools` pasó de una línea JSON a una sección `Tools (DATA):`.
- `run_not_found` agrupa run inexistente, ID inválido y caso desconocido.
- La tabla de siguiente paso cubre los estados conocidos; uno nuevo muestra «Sin acción
  sugerida» hasta que se añada.
