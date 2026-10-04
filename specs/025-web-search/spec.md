# Spec: 025 — Búsqueda web gobernada

> **Backlog:** BL-30
> **Status:** Fase 1 implementada localmente (2026-10-04); validación con
> credencial Tavily real pendiente del propietario.
> **Decisión:** Tavily directo detrás de un puerto de dominio. La búsqueda es
> una capability de lectura externa limitada, no una inferencia LLM ni una
> mutación canónica.

---

## Objetivo

Permitir que AncoraMind consulte información pública actual cuando el usuario
lo pida, conservando el Core independiente del proveedor y evitando convertir
resultados web en instrucciones, memoria canónica o contenido de telemetría.

## Fase 1 — alcance implementado

### Contrato y arquitectura

```text
search_web (tool Agno fina)
  -> WebSearchService (validación, límites, cache transitoria)
  -> WebSearchPort
  -> TavilyWebSearchPort (httpx, POST https://api.tavily.com/search)
  -> envelope `untrusted_data` para el Agent
```

- `src/domain/web_search/` no importa Agno ni `httpx`.
- `src/agent/tavily_web_search.py` es el único cliente físico Tavily.
- `src/agent/tools/web_search.py` no genera respuestas desde una IA externa:
  entrega fuentes al modelo gobernado para que éste sintetice y cite URLs.
- El hook existente `tool_budget_hooks` contabiliza cada uso en runs gobernados;
  el límite total de tools por run continúa siendo la frontera transversal.

### Política v1

- Clasificación: **READ con efecto externo limitado**. No crea `ActionProposal`
  porque no escribe datos ni actúa sobre una cuenta del usuario, pero sí requiere
  activación administrativa explícita y límites deterministas.
- `WEB_SEARCH_ENABLED=false` por defecto. Activarlo exige `TAVILY_API_KEY`.
- El único endpoint habilitado es Search. No hay Extract, Crawl, Map, Research,
  ni fetch arbitrario de URL (evita la superficie SSRF y de ingestión amplia).
- Una consulta se normaliza a una línea, máximo 300 caracteres.
- Se rechazan patrones de email, teléfono y números largos antes de enviar la
  consulta al proveedor. Es una defensa conservadora, no un detector completo
  de datos sensibles: el modelo debe minimizar siempre la consulta.
- Tavily recibe `search_depth=basic`, `topic=general`, `max_results=1..5`,
  `include_answer=false`, `include_raw_content=false`, sin imágenes, con
  `safe_search=true`, sin auto-parámetros. El modelo de AncoraMind sintetiza.
- La caché es sólo en memoria del proceso (`WEB_SEARCH_CACHE_TTL_SECONDS`, 300
  por defecto). No persiste consultas, resultados ni URLs en PostgreSQL.
- Fallos de proveedor son respuestas españolas sin detalle de proveedor,
  consulta, cabeceras ni payload.

### Datos no confiables, privacidad y observabilidad

- Cada resultado pasa por `render_retrieved_records()` con
  `trust: "untrusted_data"`, origen `public_web`, URL, título, fecha publicada
  cuando exista y snippet acotado. Nunca es consentimiento ni instrucción.
- Se escapan `<`, `>` y `&` por el helper común; los campos tienen límites de
  longitud antes de entrar al contexto del Agent.
- No se añaden a logs, trazas ni métricas la consulta, URL, snippet, clave API,
  request ID ni respuestas del proveedor. El hook de tools conserva sólo sus
  atributos allowlisted existentes.

### Variables

| Variable | Default | Política |
|---|---:|---|
| `WEB_SEARCH_ENABLED` | `false` | Kill switch administrativo; requiere clave. |
| `TAVILY_API_KEY` | vacío | Secret Railway/local, nunca runtime config. |
| `WEB_SEARCH_TIMEOUT_SECONDS` | `8` | 0–30 s. Sin retry interno. |
| `WEB_SEARCH_MAX_RESULTS` | `5` | 1–5. |
| `WEB_SEARCH_CACHE_TTL_SECONDS` | `300` | 0–3600; 0 desactiva hits de caché. |

## Criterios de aceptación Fase 1

1. Con flag apagado, `search_web` no se registra ni se crea cliente Tavily.
2. Con flag encendido sin secreto, `Settings` falla al arrancar.
3. Toda petición Tavily usa el conjunto de parámetros fijo anterior; no puede
   solicitar respuestas generadas, raw content, crawl/extract ni imágenes.
4. Una misma consulta normalizada dentro del TTL reutiliza el resultado en
   memoria sin una segunda llamada de red.
5. Una consulta vacía, excesiva o potencialmente sensible no sale del proceso.
6. Resultados se presentan como `untrusted_data`, acotados, sin contenido de la
   consulta; el prompt instruye tratarlos como datos y citar fuentes.
7. Error HTTP, timeout o JSON inválido devuelve una respuesta estable y no filtra
   detalle de proveedor.
8. `pytest`, Ruff y mypy siguen verdes.

## Fase 2 — diferida: spike OpenRouter/LiteLLM

No implementar hasta que Fase 1 tenga validación real de producto, cuota y
privacidad. OpenRouter documenta su server tool `openrouter:web_search` como
beta: el modelo puede decidir 0..N búsquedas, `engine=auto` puede elegir búsqueda
nativa del provider o fallback Exa, y el coste de cada búsqueda se suma al coste
de tokens. Aunque acepta topes como `max_results`/`max_total_results` y filtros
de dominio, esa ejecución queda dentro de la petición de inferencia y hace menos
determinista la minimización/auditoría independiente de la consulta.

Antes de adoptar esa variante se requiere un spike aislado que pruebe, con la
versión real de LiteLLM y el Gateway del despliegue:

1. propagación íntegra de la tool server-side hasta OpenRouter y vuelta de URLs,
   snippets/citas al modelo;
2. límites duros de número total de búsquedas y resultados, coste/uso atribuible
   por `correlation_id` y compatibilidad con `ExecutionBudget`;
3. comportamiento `auto` vs `native` y estabilidad por modelo/alias;
4. filtros de dominio, privacidad/región, logging y ausencia de contenido
   personal en telemetría;
5. rechazo/fallo del server tool sin bypass directo ni retries amplificadas;
6. tests adversariales de inyección en snippets y compatibilidad de citas con
   Telegram HTML.

No sustituir Tavily Fase 1 ni activar una búsqueda nativa por alias hasta que el
spike satisfaga esos criterios y una decisión posterior actualice esta spec/ADR.
