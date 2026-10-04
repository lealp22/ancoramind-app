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
- [ ] Validación manual con una API key Tavily de entorno no productivo.

## Fase 2 — OpenRouter/LiteLLM (diferida)

- [ ] Ejecutar el spike y criterios de `spec.md` antes de tocar el Gateway,
      rutas runtime o la integración Tavily.
- [ ] Decidir si se mantiene Tavily, se añade un segundo proveedor detrás del
      mismo puerto o se sustituye después de una revisión explícita.
