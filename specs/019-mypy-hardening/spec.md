# Spec: 019 — Incremental mypy Hardening

> **Backlog:** deuda técnica local
> **Status:** completada localmente (2026-09-27)
> **Target:** reducir de forma incremental la deuda de tipos de `mypy src/` sin
> relajar el modo estricto, ocultar errores con casts globales ni cambiar las
> garantías de gobernanza.

---

## Baseline

El 2026-09-27, `python -m mypy src/` reporta **93 errores en 14 archivos**.
Los grupos iniciales son repositorios SQLAlchemy, helpers sin anotar en tools,
diccionarios genéricos y el runner de interacción gobernado.

## Must Have

- Mantener `mypy` estricto definido en `pyproject.toml`; no añadir exclusiones ni
  desactivar códigos de error para reducir el contador.
- Corregir por grupos cohesivos con tipos y guards que representen el contrato de
  runtime real.
- Ejecutar tests dirigidos, Ruff y `mypy` sobre el alcance en cada grupo; medir
  el contador global al cierre.
- Priorizar primero fronteras de ejecución/gobernanza y después repositorios y
  adaptadores de tools.

## Won't Have

- Convertir `mypy src/` en gate CI en este incremento.
- Reescribir repositorios o cambiar SQL/datos canónicos salvo que sea necesario
  para expresar correctamente el contrato existente.
- Usar `Any`, `cast`, `# type: ignore` o configuración menos estricta para
  silenciar un error sin una justificación de interoperabilidad localizada.

## Plan de reducción

1. `GovernedInteractionRunner`: separar la salida `str` del pipeline documental
   y `RunOutput` del Agent, preservando los checks de contenido textual.
2. Repositorios de lectura (`notes`, `vehicles`, `maintenance`): guards de filas
   opcionales y modelos de retorno.
3. Helpers de tools (`vehicles`, `maintenance`, `reminders`, `calendar`):
   anotaciones concretas que eliminen cascadas de llamadas no tipadas.
4. Repositorios restantes (`reminders`, `actions`) y provider calendar.
5. Repetir `mypy src/`, documentar el baseline final y los límites residuales.