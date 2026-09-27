# Spec: 020 — Mypy CI Gate

> **Backlog:** calidad estática
> **Status:** completada (2026-09-27)
> **Target:** convertir `mypy src/` en una comprobación obligatoria de CI sin
> relajar la configuración estricta ni ampliar el alcance a tests o scripts.

---

## Contexto

La spec 019 cerró `mypy src/` sin errores: 105 módulos comprobados con
`strict = true`. La aprobación explícita incorpora el mismo comando al job
`quality`, para impedir que una regresión de tipos entre en `main`.

## Implementación aprobada

Añadir al job existente `quality` de `.github/workflows/ci.yml` un paso explícito:

```yaml
- name: Type check
  run: mypy src/
```

El paso se ejecuta después de Ruff y antes de los tests unitarios.
No se añade un job separado ni se ejecuta `mypy` sobre `tests/`, `scripts/` o
migraciones en esta fase: el contrato validado y limpio es exactamente `src/`.

## Must Have

- Mantener `[tool.mypy] strict = true` e `ignore_missing_imports = true` tal como
  se validó en specs/019; no añadir ignores globales, casts masivos ni exclusiones
  para hacer pasar CI.
- Usar el mismo comando local y CI: `mypy src/`.
- Hacer fallar el job `quality` si el chequeo detecta cualquier error.
- Mantener Ruff y las suites existentes sin cambios de alcance.
- Documentar la decisión y la evidencia de la primera ejecución verde en CI.

## Won't Have

- Cambiar tipos de producción salvo una regresión real expuesta por la primera
  ejecución del gate.
- Incluir tests, scripts o migraciones en el gate inicial.
- Añadir servicios externos, credenciales o ejecución de inferencia.
- Reconfigurar mypy para silenciar errores.

## Criterios de adopción

1. Un responsable aprueba explícitamente convertir el check informativo en gate.
2. Antes del cambio, una ejecución local limpia confirma:
   `mypy src/`, `pytest tests/unit/ -q`, Ruff y `git diff --check`.
3. La PR que modifica CI muestra una ejecución verde del job `quality` en GitHub
   Actions sobre Python 3.12.
4. Si aparece una incompatibilidad específica de runner/paquete, se documenta y
   se corrige de forma acotada; no se desactiva el modo estricto como atajo.

## Evidencia de cierre

- La ejecución del job `quality` en GitHub Actions quedó verde tras subir el
  cambio que añade `Type check` (`mypy src/`), confirmado el 2026-09-27.
- El gate se ejecuta en `ubuntu-latest` con Python 3.12, entre Ruff y los tests
  unitarios, sin ampliar el alcance fuera de `src/`.

## Rollback

Si el gate bloquea CI por un problema reproducible de infraestructura y no por un
error de tipos del producto, revertir exclusivamente el paso `Type check` y abrir
una incidencia con el log saneado. La configuración de mypy y las correcciones de
tipos ya fusionadas no se revierten como parte de ese rollback.