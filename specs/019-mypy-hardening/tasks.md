# Tasks — Spec 019: Incremental mypy Hardening

> **Baseline:** 93 errores / 14 archivos (`mypy src/`, 2026-09-27)

- [x] T1 · Separar y validar los contratos `str` (ingestión documental) y
      `RunOutput` (Agent) en `GovernedInteractionRunner`; añadir test negativo
      para salida documental no textual.
- [x] T2 · Corregir repositorios de lectura `notes`, `vehicles` y `maintenance`.
- [x] T3 · Tipar helpers y eliminar cascadas en tools de vehículos,
      mantenimiento, recordatorios y calendario.
- [x] T4 · Corregir `reminders`, `actions` y `calendar/provider`, más contratos
      `RETURNING` y estrechamiento revelados en `documents` e `interactions`.
- [x] T5 · Ejecutar y documentar el conteo global final, tests y lint.