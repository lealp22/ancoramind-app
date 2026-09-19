# Tasks: 014 — Agentic Evals Foundation

## T1: Contrato y datasets

- [x] Definir contrato JSON v1 documentado en `evals/README.md`.
- [x] Crear catálogos sintéticos para las cinco categorías de gobernanza.
- [x] Incluir expectativas de tool requerida/vetada, confirmación y resultado.
- [x] Mantener datos sintéticos: sin PII, secretos, mensajes de Telegram ni
      documentos reales.

## T2: Runner determinista

- [x] Crear `scripts/run_evals.py` con solo biblioteca estándar.
- [x] Validar schema version, categoría/ruta, IDs únicos, campos requeridos y
      contradicciones required/forbidden.
- [x] Añadir selección por categoría, salida JSON y códigos de salida aptos para CI.
- [x] No llamar a LLM, tools, base de datos ni servicios externos.

## T3: Tests y documentación

- [x] Añadir `tests/unit/test_eval_catalog.py`.
- [x] Documentar formato, ejecución y límites del incremento en `evals/README.md`.
- [x] Actualizar `docs/governance.md`, `docs/development.md`, `AGENTS.md` y BACKLOG.

## T4: Próximo incremento (no incluido)

- [ ] Diseñar un adaptador que ejecute cada caso contra un Agent gobernado sin
      persistir contenido personal, evaluando solo metadata permitida.
- [ ] Definir scoring de respuesta/criterios semánticos y baseline por ruta lógica.
- [ ] Integrar el modo LLM en CI/E2E con presupuesto y credenciales explícitas.