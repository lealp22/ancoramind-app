# Tasks: 025 — Búsqueda web gobernada

## Fase 1 — Tavily directo

- [x] Puerto de dominio y modelos neutrales en `src/domain/web_search/`.
- [x] Servicio con validación, minimización, límites y caché sólo en memoria.
- [x] Adaptador Tavily HTTP con `httpx`, timeout y request surface fijo.
- [x] Tool `search_web` fina y resultados marcados como `untrusted_data`.
- [x] Configuración tipada, kill switch y secreto separado; registro condicional
      en `src/main.py` sin depender de `ANCORA_DATABASE_URL`.
- [x] Contrato de prompt, skill `prompts/skills/web_search.md`, `.env.example`
      y backlog actualizados.
- [x] Filtro de consultas alineado con ADR-007: `src/observability/masking.py`
      (detectores compartidos) + `tests/unit/test_masking.py` (corpus válido/
      inválido y falsos positivos sobre español cotidiano).
- [x] Casos de prompt injection web en `evals/security/cases.json` (6 casos,
      tag `web`) + `search_web` simulado en `src/agent/eval_tools.py`. Catálogo
      estático; ejecución con Agent real pendiente (misma aprobación que BL-8).
- [x] Validación local del servicio con la clave de `.env`:
      `scripts/validate_web_search.py` (rechazos, errores controlados, 5 fuentes
      reales, privacidad en logs). Resultado en `verification.md`.
- [ ] Validación del flujo del Agent por Telegram (Playwright sobre Telegram
      Web; el propietario inicia sesión). Bloqueada por el incidente de Railway.
- [ ] Opcional, bajo demanda: emitir `credits`/`cache_hit` como atributos
      allowlisted del span de la tool para poder contar uso de Tavily.

## Fase 2 — OpenRouter/LiteLLM (diferida)

- [ ] Ejecutar el spike y criterios de `spec.md` antes de tocar el Gateway,
      rutas runtime o la integración Tavily.
- [ ] Decidir si se mantiene Tavily, se añade un segundo proveedor detrás del
      mismo puerto o se sustituye después de una revisión explícita.
