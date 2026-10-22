# Selección de modelo y proyección de coste

> Documento de soporte para el entregable (módulo 1 del rúbrico, ver
> `docs/academic-rubric-gap-analysis.md`). Fotografía del 2026-10-22: las cifras
> proceden de campañas E2E reales, pero **son estimaciones de la plataforma, no
> facturación**. Revisar si cambia el modelo, el precio o el patrón de uso.

## 1. Qué se usa hoy

| Elemento | Valor vigente |
|---|---|
| Modelo físico | GPT-6 Luna (`openrouter/gpt-6-luna`) |
| Alias gobernado | `ancoramind-default-r4` (runtime config revisión 8) |
| Precio de referencia | **0,10 USD / 1M tokens de entrada; 0,50 USD / 1M de salida** |
| Embeddings | `ancoramind-embeddings-r1` (`openai/text-embedding-3-small`) |
| Reintentos / fallback entre modelos | 0 / 0 (el fallo es visible, no se oculta) |
| Fallback de proveedor dentro de OpenRouter | Activado (`openrouter_provider_fallback`): OpenRouter puede enrutar entre sus proveedores del mismo modelo |

El modelo se cambia publicando un alias nuevo y activando una revisión, sin
redeploy ni mutar el alias en uso (ADR-005). La mecánica está en
`docs/runbooks-013.md` §2.2; este documento cubre el *por qué* y el *cuánto*.

> **Nota de consistencia.** `specs/013-llm-access-governance/configs/ancoramind-default-r4.json`
> declara 0,43 / 0,87 USD/M, mientras que el snapshot activo (rev. 8,
> `evals/response_style/runtime-rev8-snapshot.json`) y
> `ancoramind-default-r4-with-embeddings.json` declaran 0,10 / 0,50. Este
> documento usa el de la revisión activa. Conviene reconciliar el fichero suelto.

## 2. Por qué este modelo

### 2.1 Requisitos de la ruta `ancoramind-default`

La ruta declara tres capacidades obligatorias: `text`, `tool_calling` y
`structured_output`. Es lo que necesita un agente único que decide qué tool
invocar y entrega su respuesta mediante `present_reply` (`tool_choice=required`).
Por eso el criterio no es "el mejor modelo", sino **el más barato que ejecute
tool calls de forma fiable**.

### 2.2 Qué se sabe, y qué no

Hechos documentados en el repositorio:

- Un modelo gratuito (`minimax/minimax-m3:free`, vía OpenRouter) emitió un *tool
  call* vacío que rompió el turno siguiente (BL-16, specs/006). Esto motivó el
  filtro `ToolCallSafetyMixin` y es la razón por la que la fiabilidad de tool
  calling pesa más que el precio en la elección.
- Se preparó `z-ai/glm-5.3-flash` como alternativa (specs/013, Fase 6), con
  precio de referencia de 0,15 USD/M de entrada y 0,50 USD/M de salida,
  multimodal y 1 048 576 tokens de contexto. Se usó para ensayar el cambio de
  modelo en caliente y el rollback (2026-09-19).
- El candidato GPT-6 Luna se preparó como `r3` (estado documentado el
  2026-09-28) y el default vigente es `r4`/rev. 8. El backlog fija que **no se
  abre otro experimento de modelo** mientras se valida este baseline
  (`BACKLOG.md`, bloque P0).

**Lo que no está documentado:** el motivo concreto de pasar de GLM a GPT-6 Luna
y una comparación de calidad entre ambos con las mismas pruebas. No se
reconstruye aquí: afirmarlo sin evidencia sería inventarlo.

### 2.3 Comparativa con la evidencia disponible

| Criterio | GPT-6 Luna (vigente) | GLM 5.3 Flash (alternativa ensayada) |
|---|---|---|
| Entrada / salida (USD por 1M) | 0,10 / 0,50 | 0,15 / 0,50 (endpoint Z.AI; otros proveedores 0,075–0,45 de entrada) |
| Tool calling y salida estructurada | Sí; E2E de vehículos, calendario, recordatorios y TODO | Sí declarado en OpenRouter; ensayado solo para el cambio en caliente |
| Contexto | No fijado en la ruta (`null`) | 1 048 576 tokens |
| Evidencia de calidad con tareas de AncoraMind | E2E real, ver §3 | Ninguna comparable |

Las evals semánticas con juez aún no se han ejecutado (BL-8), por lo que **no
hay medición de calidad que permita afirmar que uno sea mejor**. La decisión
vigente se sostiene en coste bajo, capacidades requeridas y funcionamiento
comprobado en los E2E.

### 2.4 Criterios para reevaluar

Reabrir la elección si ocurre cualquiera de estas:

1. Fallos de tool calling o salida terminal inválida (`InvalidPresentationOutputError`)
   con frecuencia apreciable.
2. El coste real, una vez reconciliado, supera de forma sostenida la estimación.
3. El precio de la ruta sube o aparece un modelo con las mismas capacidades a
   menor coste.
4. Se ejecuta el juez LLM (BL-8) y mide una diferencia de calidad.

## 3. Coste medido

Base: interacciones reales en Telegram sobre rev. 8/`ancoramind-default-r4`, sin
reintentos ni fallback (`specs/008-railway-deployment/mvp-release-campaign.md`).
Cada coste es la **estimación de la plataforma** con el `pricing_snapshot`; el
coste real devuelto por el proveedor está en `NULL` en todas las campañas y no
se interpreta como cero.

| Interacción | Llamadas al modelo | USD estimados |
|---|---:|---:|
| Alta de vehículo | 2 | 0,00253050 |
| Proponer mantenimiento | 3 | 0,00375380 |
| Consultar historial | 3 | 0,00370210 |
| Proponer evento de calendario | 2 | 0,00252150 |
| Consultar calendario | 2 | 0,00253020 |
| Snooze | 4 | 0,00512830 |
| Recordatorio (origen) | 3 | 0,00378450 |

- **Media: 0,0034 USD por interacción** (7 interacciones, ~2,7 llamadas cada una,
  ~0,0013 USD por llamada). Rango 0,0025–0,0051.
- Las confirmaciones («Sí») las resuelve el Core y **no usan inferencia**: no
  cuestan nada.
- Los comandos `/help` y `/new`, los descartes y el aviso de acceso tampoco.
- El techo por interacción es 0,10 USD (≈ 30 veces la media), de modo que actúa
  como protección contra bucles y no como previsión de gasto.

## 4. Proyección por niveles de uso

Supuestos: **0,0034 USD por interacción** (media medida), 30 días, 10 interacciones
con inferencia por usuario y día. El rango bajo/alto usa el mínimo y el máximo
medidos.

| Nivel | Usuarios | Interacciones/mes | USD/mes (media) | Rango |
|---|---:|---:|---:|---|
| Piloto family&friends | 5 | 1 500 | **5,13** | 3,78 – 7,69 |
| Ampliado | 20 | 6 000 | **20,53** | 15,13 – 30,77 |
| Abierto | 100 | 30 000 | **102,65** | 75,64 – 153,85 |

Lectura:

- El piloto previsto (muy pocas personas, unos días, `docs/pilot-terms.md`) cuesta
  del orden de unos pocos dólares al mes.
- El coste escala de forma lineal con las interacciones. El gasto crece con el
  uso, no con la infraestructura de inferencia.
- Lo que no entra: Railway, Supabase, Grafana Cloud, Tavily (1 crédito por
  búsqueda web) y voz. Son costes fijos o de otro proveedor.

### 4.1 Qué corta el presupuesto antes

Los topes activos (rev. 8) limitan el gasto aunque el uso crezca:

| Tope | Valor | Interacciones que permite (a 0,0034 USD) |
|---|---|---|
| Ruta `ancoramind-default`, mensual | 10 USD (corte duro al 90 %) | ~2 600 al mes (~88 al día) |
| Global mensual | 20 USD (corte duro al 90 %) | ~5 300 al mes |
| Diario | 1 USD | ~260 al día |

**Consecuencia:** el nivel *Ampliado* (6 000 al mes) **superaría el tope de la
ruta** y el *Abierto* sería bloqueado por presupuesto a los pocos días. Es
intencionado en el piloto, pero habría que subir los topes antes de ampliar
usuarios. El control de gasto funciona como diseñado: falla cerrado, no
silenciosamente.

## 5. Límites de esta proyección

- **Estimación, no facturación.** El coste real del proveedor no está reconciliado
  (`NULL`); la reconciliación con OpenRouter sigue pendiente
  (`specs/013-llm-access-governance/verification.md`).
- **Muestra pequeña:** 7 interacciones sintéticas de campañas de validación, no
  tráfico de usuarios. Las conversaciones largas, con historial o con documentos
  gastarán más entrada que estos casos.
- **Las 10 interacciones por usuario y día son un supuesto**, no una medición.
- No incluye visión/OCR, embeddings, voz ni resúmenes de compactación de contexto,
  que usan otras rutas con su propio precio.
- Los precios de los modelos cambian; el `pricing_snapshot` fija el de cada llamada.

## 6. Cómo mantenerlo vivo

1. Tras cada campaña, añadir las interacciones nuevas a la tabla de §3.
2. Cuando el coste real deje de ser `NULL`, comparar contra la estimación y
   ajustar el supuesto de §4.
3. Si cambia el modelo, publicar un alias nuevo (ADR-005) y rehacer §2.3 y §3
   con la evidencia de ese modelo; no editar el alias en uso.
