# Medición `EXPLAIN` — Spec 043 T8

Fecha: 2026-10-20. PostgreSQL del `docker compose` local (no Supabase), base
temporal `ancoramind_explain` creada desde `migrations/init.sql` y borrada después.
Datos **sintéticos**, sin contenido personal.

## Datos

| Tabla | Filas | Reparto |
|---|---|---|
| `telegram_interactions` | 18 000 | ~87 días, 3 usuarios; 10 % `rejected`, ~12 % `failed_definitive` |
| `llm_usage_events` | 54 000 | 3 eventos por interacción, `actual_cost` en 1 de cada 3 |
| `action_proposals` | 3 000 | ~83 días |

Equivale a ~200 interacciones/día, muy por encima del uso actual. `ANALYZE` ejecutado
antes de medir. `EXPLAIN (ANALYZE)` ejecuta la consulta (todas son de solo lectura).

## Ventana de 90 días (abarca el 100 % de las filas)

| Consulta | Tiempo | Plan |
|---|---|---|
| `totals` | 133 ms | Seq Scan en ambas tablas |
| `daily` | 93 ms | Seq Scan en ambas tablas |
| `by_user` | 135 ms | Seq Scan en ambas tablas |
| `by_route_model` | 35 ms | Seq Scan en ambas tablas |
| `by_cost_source` | 36 ms | Seq Scan en ambas tablas |
| `latency` | 39 ms | Seq Scan en ambas tablas |
| `interactions_by_status` | 4,7 ms | Seq Scan |
| `tool_calls_total` | 2,9 ms | Seq Scan |
| `proposals` | 1,1 ms | Seq Scan |

Suma secuencial ≈ 480 ms. Cada ruta lanza una parte de ellas (`/finops` 5, `/quality` 4).

## Ventana de 7 días (~8 % de las filas)

| Consulta | Tiempo | Plan |
|---|---|---|
| `totals` | 20 ms | Bitmap Index Scan en `idx_llm_usage_created_at` |
| `by_user` | 26 ms | Bitmap Index Scan en `idx_llm_usage_created_at` |
| `interactions_by_status` | 1,0 ms | Index Scan en `idx_telegram_interactions_received_at` |
| `proposals` | 1,4 ms | Seq Scan (sin índice por `created_at`) |

## Conclusión

- Con 90 días el planificador elige Seq Scan porque la ventana cubre toda la tabla:
  es la decisión correcta, no una falta de índice. Con ventanas cortas usa
  `idx_llm_usage_created_at` y `idx_telegram_interactions_received_at`.
- La ventana máxima es aceptable a este volumen. No se añade ningún índice.
- **Límite de la medición:** una sola ejecución por consulta, sin repetir, así que los
  tiempos son orientativos (la primera consulta puede incluir calentamiento de caché).
  No es Supabase: la red, el hardware y las estadísticas pueden cambiar los planes.
- **Vigilar:** `action_proposals` no tiene índice por `created_at`; hoy cuesta ~1 ms
  con 3 000 filas. Reevaluar si la tabla crece en órdenes de magnitud.
- **Escala:** el coste crece linealmente con las filas del ledger. A ~10× el volumen
  medido, la ventana de 90 días rondaría el segundo; si llegara ahí, valorar
  cachear la respuesta unos minutos antes que añadir índices.
