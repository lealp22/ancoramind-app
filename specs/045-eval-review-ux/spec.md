# 045 — Legibilidad de la revisión humana de evals

Estado: propuesta, sin implementar. Sin inferencia, despliegue ni claves nuevas.

## Problema

Revisar un caso con `eval_console.py review` es incómodo, aunque hoy el cuello de
botella real es la cadena operativa (publicar → `session-init` → `run`). Evidencia
leída en el código (2026-10-20):

1. `review_saved` crea un `TerminalCampaignReviewer` **por criterio** y cada uno
   vuelca el bloque completo del caso. Con N criterios se imprime N veces.
2. `console_data` serializa cada campo con `json.dumps`: un muro de JSON.
3. Cualquier excepción imprime `eval_console_blocked_or_disconnected`, sin motivo.
4. `status` y `session-status` solo devuelven JSON, sin resumen ni «siguiente paso».

## Decisión del propietario

Un fail (o `x`) **sigue deteniendo** el caso y los siguientes, como en specs/040.
No se cambia. Se registra para que no se reabra por error.

## Alcance

### A. Caso impreso una sola vez

El bloque del caso se imprime una vez por caso en cada invocación de `review` y,
a continuación, los criterios pendientes seguidos. Si se retoma un caso a medias,
se imprime una vez al reanudar. Sin cambios en etiquetas, autosave por criterio,
ni en el orden o las reglas de parada.

### B. Formato legible

Secciones etiquetadas, una por campo (Input, Contexto, answer, proposal_text,
Propuestas, Presentación Core, Hechos de tools), con diccionarios y listas en
líneas `clave: valor` indentadas, en lugar de un JSON compacto.

Se conserva el contrato de seguridad de specs/040 §7: todo dato (DATA) escapa
controles, bidi y caracteres de formato (`\uXXXX`), incluido el salto de línea
dentro de un valor. La estructura de líneas la genera solo la consola, y cada
línea de datos lleva un prefijo fijo para que un valor no pueda imitar una
sección ni los controles `[p]/[f]/[x]`.

### C. Motivos de error cerrados

`eval_console_blocked_or_disconnected` añade `reason` de una lista cerrada
(consola no interactiva, revisión desconectada, evidencia ilegible o clave
incorrecta, run inexistente, inesperado). Nunca texto de excepción, rutas,
contenido ni argumentos. Lo no reconocido es `unexpected`. Se mantienen
`do_not_replay` y `review_can_reopen_saved_evidence`. Las salidas
`eval_session_blocked` no cambian.

### D. Estado legible

`status --run ID --human` y `session-status --human` imprimen texto: estado de
ejecución, una línea por caso (técnico, semántico, criterios revisados/total),
saldo de sesión y **siguiente paso** de una tabla fija. Ningún siguiente paso
sugiere `run` para reconectar ni relanzar. Sin `--human`, la salida JSON es
idéntica a la actual.

### E. Sin cambio (decisión registrada)

Ver «Decisión del propietario». No hay flag ni modo para continuar tras un fail.

## Restricciones

- **Sin módulo nuevo bajo `src/` ni `scripts/`.** Los ficheros fuera de la
  allowlist `_HARNESS` de `eval_validation_session.py` cambian el scope de la
  sesión. Toda la lógica va en `eval_console.py`, `eval_campaign_runner.py` y
  `eval_durable_review.py`, ya excluidos del scope.
- Sin dependencias, red, provider, `LLMAccess` ni escritura de contenido en logs.
- Sigue exigiéndose terminal TTY para etiquetar.
- La huella del harness cambia: requiere commit, CI del mismo SHA y publicación
  manual (specs/041). No amplía el gasto ni crea aprobación nueva (specs/042).

## Aceptación

1. Un caso de N criterios imprime su bloque una vez; reanudar a medias, una vez.
2. Controles, bidi y formato salen escapados en todas las secciones; un valor con
   saltos de línea no crea una línea con apariencia de sección o de criterio.
3. Las etiquetas guardadas y su orden son idénticos a los de hoy; fail/x detiene.
4. Cada excepción conocida produce un `reason` de la lista; una desconocida,
   `unexpected`; ninguna salida contiene texto de excepción.
5. `--human` imprime un siguiente paso para cada estado conocido y nunca `run`
   como forma de reconectar. Sin `--human`, JSON byte a byte igual.
6. Tests sin red ni inferencia; Ruff, mypy y suites unitaria/integración pasan.
