# Spec 043 — Panel FinOps y calidad en `/admin/dashboard`

Estado: implementado y validado localmente; UI ampliada el 2026-10-22.
Publicación/validación Railway de estos incrementos no realizada en esta sesión.
Fase 1 del plan de observabilidad (ADR-007 en borrador es la fase 3 y no es
prerrequisito). Tareas originales en `tasks.md`; operación en el
[runbook del dashboard](../../docs/runbooks-027-admin-dashboard.md).

## Problema

Los datos de coste, uso y calidad ya están en PostgreSQL, pero nadie los
consulta. Grafana (ADR-006) es metadata-only y sin IDs en métricas, así que no
puede responder: cuánto gasta cada usuario, por ruta/modelo, qué parte del coste
es estimada, cuántas propuestas se confirman o descartan, ni qué tools fallan.

## Alcance

Un panel de solo lectura en el dashboard admin existente, alimentado por
consultas agregadas sobre `ancora.llm_usage_events`,
`ancora.telegram_interactions` y `ancora.action_proposals`.

Fuera de alcance: Phoenix, trazas, contenido de conversaciones, escritura de
datos, presupuestos por usuario, alertas, gasto de `dream_runs` y de
`voice_preparations` sin evento (se declara en el panel como «no incluido»).

## Decisiones

1. **Sin migración ni flag nuevo.** Se activa con `ADMIN_DASHBOARD_ENABLED`; mismo
   token y mismas cabeceras de seguridad que el resto del panel.
2. **Capas.** `src/domain/finops/` (modelos Pydantic + servicio, sin Agno ni
   FastAPI) → `src/repositories/finops.py` (SQL `text()` con bind params) →
   rutas en `admin_dashboard.py`. Las rutas no contienen SQL.
3. **Coste** = `COALESCE(actual_cost, estimated_cost, 0)`, igual que
   `LlmUsageRepository.summarize_spend`. La paridad sólo vale para igual periodo
   y sin voz sin evento: las barras de presupuesto del hard stop sí incluyen esa
   voz, los KPIs del panel no. Se muestra además el desglose por `cost_source`.
4. **Atribución a usuario** por `llm_usage_events.interaction_id` →
   `telegram_interactions.telegram_user_id`.
5. **Seudónimo de usuario.** El panel nunca muestra `telegram_user_id`: muestra
   `u-` + 8 hex de `HMAC-SHA256(clave, "ancoramind/finops-user/v1:" + id)`, usando
   `TELEGRAM_PAIRING_CODE_PEPPER` ya obligatorio para el panel (sin secreto
   nuevo). Estable entre peticiones, no reversible desde la respuesta.
6. **Ventana.** Parámetro `days` entero 1–90 (por defecto 30), días UTC.
   Fuera de rango ⇒ 422. Sin `days` libre ni SQL dinámico.
7. **Presupuesto.** El resumen incluye gasto del mes en curso frente a
   `cost_governance.monthly_budget_usd` y `daily_budget_usd` del snapshot activo,
   o `null` si no hay gobernanza configurada.

## API (todas `GET`, `Authorization: Bearer ADMIN_DASHBOARD_TOKEN`)

| Ruta | Contenido |
|---|---|
| `/admin/dashboard/api/finops` | Totales (coste, tokens, llamadas, errores, coste medio por interacción), serie diaria, desglose por usuario seudonimizado, por ruta efectiva y modelo, por `cost_source`, y presupuesto |
| `/admin/dashboard/api/quality` | Interacciones por estado, total de tool calls, propuestas por `tool_name` × `status` × `consent_mode`, proporciones de ejecución/descarte/caducidad sobre resueltas, latencia p50/p95 y TTFT, reintentos y fallbacks |

## Privacidad

Las consultas no seleccionan `payload_ciphertext`, `action_proposals.payload`,
`arguments_fingerprint` ni ninguna columna de texto libre. Solo se leen
identificadores, estados, contadores, costes y tiempos. Un test falla si una
consulta del repositorio referencia esas columnas. Las respuestas no incluyen
`telegram_user_id`, `chat_id` ni `agno_session_id`.

## UI

`dashboard.html`: FinOps/calidad en **Resumen**, tabla de propuestas en
**Propuestas**, selector compartido 7/30/90 días. Administración y Prompts son
otras pestañas, no métricas de esta spec. La salud compacta reutiliza el mismo
request que el detalle de Administración. Sin librerías/scripts externos;
CSS/JS inline bajo la CSP existente. Los datos del panel se insertan con
`textContent`, no con `innerHTML`.

- Coste diario: fechas izquierda→derecha y columnas de altura proporcional, altura
  fija para 90 días, etiquetas espaciadas, tooltip/foco y detalle desplegable con
  importes exactos. Días UTC sin registro quedan como huecos, no como coste cero.
- Dos anillos con leyendas/valores/porcentajes y tablas: origen por importe USD
  (`cost_source`, no proveedor ni llamadas) e interacciones por cantidad. Estos
  estados incluyen rejected/ignored aunque no contribuyan al coste/uso LLM.
- Tres barras independientes 0–100 %: ejecutadas/descartadas/caducadas. Denominador
  común = esos tres estados resueltos, excluyendo pendientes/en curso. Incluyen
  ejecutadas autoautorizadas; no miden aprobación humana. **Sin umbrales** 90/10,
  alarmas ni juicios de calidad (decisión del propietario).
- Sin propuestas resueltas: ausencia de datos, no 0 %. Sin gasto/interacciones:
  mensajes explícitos, sin anillos ficticios. Valores cero reales se conservan.

## Criterios de aceptación

1. Rutas sin token o con token distinto ⇒ 401; con `ADMIN_DASHBOARD_ENABLED=false`
   no existen.
2. `days` fuera de 1–90 ⇒ 422.
3. El coste usa actual sobre estimado y coincide con `summarize_spend` para el
   mismo periodo cuando no hay voz sin evento (exclusión declarada).
4. El gasto de un usuario no se mezcla con el de otro; el seudónimo es estable y
   distinto por usuario, y no contiene el ID.
5. Interacciones `rejected`/`ignored` no aportan coste ni aparecen como uso LLM.
6. Ninguna respuesta contiene contenido, `payload`, IDs de Telegram ni de sesión.
7. Sin datos en la ventana, el panel muestra ceros y tablas vacías, sin error.
8. Ruff, mypy y las suites unitaria e integración (PostgreSQL local) pasan.

## Riesgos y límites

- Las cifras reflejan el ledger: no incluyen Dream ni voz sin evento, y el coste
  estimado no es factura. Se rotula así en el panel.
- Con pocos usuarios el seudónimo es fácil de asociar por el propio operador; es
  una protección frente a capturas y exportaciones, no anonimización.
- Consultas sobre hasta 90 días: dependen de `idx_llm_usage_created_at`. Medir con
  `EXPLAIN` sobre datos locales antes de dar por buena la ventana máxima.

## Verificación de gráficos — 2026-10-22

Incremento `64bd683`: navegador con respuestas sintéticas (90 días, layout móvil,
gasto cero/ausencia de datos, categorías, escape de etiquetas y barras sin
umbrales); 83 focales passed, suite 2229 passed/1 skipped, Ruff y mypy 186 fuentes
correctos. No consultas de producción ni inferencia. La ejecución JS offline
de `tests/unit/test_admin_dashboard_charts.py` usa Node si está disponible
(sin dependencia nueva de runtime); se omite en entornos Python sin Node.
Sin cambio de APIs, cálculo del ledger, DB ni prompts. No es evidencia remota
ni repetición de la medición PostgreSQL original de `explain.md`.
