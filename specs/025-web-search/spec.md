# Spec: 025 — Búsqueda web gobernada

> **Backlog:** BL-30
> **Status:** Fase 1 implementada localmente (2026-10-04); validación con
> credencial Tavily real pendiente del propietario. Filtro de consultas
> alineado con ADR-007 (2026-10-21): detectores compartidos en
> `src/observability/masking.py`; no requiere que el ADR esté aceptado.
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
- Se rechaza la consulta (`sensitive_query`) antes de enviarla al proveedor si
  `src/observability/masking.py` detecta algún identificador sensible. Los
  detectores son los de ADR-007, compartidos y sin duplicar patrones aquí:
  tarjeta (Luhn), IBAN (módulo 97), DNI/NIE (letra de control), matrícula
  actual y anterior, VIN, email, teléfono, tokens (prefijo conocido o cadena
  larga de alta entropía) y, como red de seguridad, números de 8+ dígitos.
  Es una defensa conservadora, no un detector completo: no reconoce nombres,
  direcciones ni datos de salud, y el modelo debe minimizar siempre la consulta.
  Aquí se rechaza, no se enmascara: una consulta con marcadores no es útil.
- Contrapartida aceptada: códigos públicos largos (p. ej. un VIN o una
  referencia de producto de 17 caracteres) se rechazan y el usuario debe
  reformular. Se prefiere el falso positivo al envío de un dato personal.
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

## Parámetros de Tavily evaluados y descartados (2026-10-21)

Se evaluó si otros parámetros del endpoint Search mejoraban los resultados
(docs.tavily.com, Search API). **Decisión: Fase 1 mantiene el request fijo
(`basic`, sin `country`/`language`, sin `include_answer`). No reabrir sin
evidencia nueva.**

| Parámetro | Decisión | Motivo |
|---|---|---|
| `include_answer` | Descartado | La respuesta la genera un LLM de Tavily: inferencia fuera de `LLMAccess` (sin Gateway, presupuesto, ruta versionada ni trazabilidad; principio 9 de AGENTS.md) y duplica la síntesis del Agent con una respuesta no respaldada por las fuentes citadas. |
| `search_depth=advanced` | Descartado | 2 créditos en vez de 1. En la prueba perdió fuentes neutrales (Banco de España, Wikipedia) a favor de bancos comerciales, un resultado con 154 caracteres y fragmentos de ~2100 que la tool recorta a 1600. No hay presupuesto por run para créditos de Tavily, así que el coste se duplicaría sin control. |
| `country` + `language` | Descartado por falta de efecto medible | Ver prueba. Efecto dentro del ruido entre ejecuciones idénticas; no justifica dos variables de configuración, tests y un cambio evaluable. |
| `auto_parameters` | Sigue apagado | Según la documentación puede subir a `advanced` (2 créditos) sin avisar. |
| `topic`, `time_range`, `include_domains`, `exact_match` | Fuera de alcance | Exigirían que el modelo los elija, ampliando la superficie de la tool y los evals de inyección. Candidatos de una fase posterior. |

**Prueba realizada (10 créditos, consultas en español, 5 resultados):**

| Consulta | `basic` | `basic` + `country=spain`, `language=es` |
|---|---|---|
| ¿Qué es la inflación? | 1/5 dominios `.es` | 2/5 |
| ¿Cómo funciona el IRPF? | 2/5 | 2/5 |
| ¿Qué requisitos tiene la ITV? | 4/5 | 4/5 |
| ¿Qué es un agujero negro? (global) | 0/5 | 1/5 |

Con `country`/`language`, los resultados cambian en uno o dos dominios y en
ambos sentidos (en IRPF sale `finect.com` y entra `sumup.com`). En la
inflación, `basic` devolvió Perú y México, y con los parámetros desaparecieron,
pero una repetición de `basic` otro día ya había mostrado una composición
distinta, así que no se puede separar el efecto del ruido. En la consulta global
no empeora. Escribir la consulta en español ya prioriza fuentes en español.

**Limitaciones de la prueba:** 4 consultas, una métrica burda (el sufijo `.es`
no mide calidad: `bbva.com` o `finect.com` son españolas sin él) y sin juicio
sobre el contenido. Una decisión contraria requeriría ~15 consultas, una
métrica mejor y comparar varias ejecuciones de la misma configuración para
medir el ruido propio.

**Problema residual y vía preferida:** aparecen vídeos de YouTube en 2 de 4
consultas y fuentes de otros países. Se corrige mejor desde el prompt
(`prompts/skills/web_search.md`: priorizar fuentes oficiales y nombrar el país
o tipo de cada fuente), sin coste en créditos. Es un cambio evaluable
(AGENTS.md §10.4) y no está hecho.

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

### Revisión documental (2026-10-09) — sin acceso al Gateway/LiteLLM real

Antes de montar el spike contra infraestructura real, se revisó la
documentación pública actual de OpenRouter y LiteLLM para los 6 criterios de
arriba. **No sustituye el spike** (ningún criterio se verificó contra el
Gateway desplegado; esto es solo literatura), pero ya adelanta un hallazgo
que cambia la recomendación por defecto:

1. **Activación confirmada, tres formas equivalentes:** sufijo `:online` en
   el nombre del modelo, plugin `web` con parámros (`engine`, `mode`,
   `max_results` 1–10, `search_prompt`, `include_domains`/`exclude_domains`),
   o el server tool explícito `openrouter:web_search`. El resultado llega al
   modelo como anotaciones `url_citation` (OpenAI-compatible) con
   `url`/`title`/`content` (fragmentos de 2000–4000 caracteres de Exa).
2. **🔴 Hallazgo que bloquea la adopción tal cual:** no hay ningún parámetro
   documentado para fijar un **número máximo de búsquedas por petición** —
   solo `max_results` acota resultados *dentro* de cada búsqueda, no cuántas
   búsquedas decide hacer el modelo (0..N, confirmado también en la
   documentación de activación). Esto es incompatible con el modelo de
   gobernanza actual de AncoraMind: `ExecutionBudget.reserve_model_call()`
   exige conocer y reservar el coste **antes** de la llamada
   (`src/domain/llm_access/models.py`); un coste que solo se conoce después
   de que el modelo decidió cuántas búsquedas hacer (cada una facturada,
   p. ej. $0.007/búsqueda con Exa) rompe esa invariante de "sin sorpresas de
   presupuesto a mitad de ejecución" sin un control adicional que hoy no
   existe en el lado del cliente.
3. **`engine=auto` vs `native`:** sin garantía documentada de estabilidad
   por modelo — `auto` cae a Exa si el proveedor no tiene búsqueda nativa,
   sin lista cerrada de qué modelos la tienen. Confirma el riesgo ya
   anotado en el criterio 3 original.
4. **Filtros de dominio sí existen** (`include_domains`/`exclude_domains`),
   parcialmente cubriendo el criterio 4; privacidad/región y ausencia de
   contenido personal en telemetría siguen sin poder verificarse sin
   credenciales reales.
5. **Coste por motor variado y no uniforme:** Exa $0.007/búsqueda (hasta 10
   resultados, +$0.001 por extra), Perplexity $0.005, Parallel
   $0.001–0.005, Firecrawl por créditos propios, más tokens de
   procesamiento — ninguno de estos aparece reflejado hoy en
   `SpeechBillingPolicy`-equivalente alguno para búsqueda; haría falta una
   política de tarifa nueva y versionada antes de poder auditar coste real
   por `correlation_id` (criterio 2, segunda mitad).
6. **LiteLLM** tiene seguimiento propio de coste de búsqueda
   (`usage.prompt_tokens_details.web_search_requests`, `web_search_options`)
   pero orientado a la tool nativa de proveedores que soporta directamente
   (OpenAI, etc.); no hay confirmación documental de que ese tracking
   también capture `plugins`/`:online` reenviado específicamente a través
   del adaptador `openrouter/` de LiteLLM — sigue siendo una pregunta para
   el spike real, no resuelta por esta revisión.

**Recomendación (no vinculante, a confirmar en el spike real si se
retoma):** mantener Tavily (Fase 1) como la única vía de búsqueda web.
Adoptar el server tool de OpenRouter requeriría primero resolver el punto 2
— sin un tope duro de número de búsquedas conocido *antes* de la llamada,
no hay forma limpia de preservar la garantía de presupuesto reservado que
el resto de capacidades gobernadas de AncoraMind ya cumplen (voz, embeddings,
extracción documental). Si en el futuro OpenRouter/LiteLLM documentan un
límite duro de búsquedas por petición, revisar esta sección antes de
replantear el spike.
