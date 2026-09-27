# Tasks — Spec 020: Mypy CI Gate

> **Status:** completada (evidencia CI confirmada el 2026-09-27).

- [x] T1 · Documentar el baseline limpio de specs/019 y el comando exacto.
- [x] T2 · Definir el alcance inicial (`mypy src/`) y los límites explícitos.
- [x] T3 · Definir criterio de adopción, evidencia CI y rollback acotado.
- [x] T4 · Obtener aprobación para modificar `.github/workflows/ci.yml`.
- [x] T5 · Añadir el paso `Type check` al job `quality` después de Ruff y antes de
      los tests unitarios.
- [x] T6 · Verificar una ejecución verde en GitHub Actions, registrar la evidencia
      CI y actualizar el estado de esta spec.