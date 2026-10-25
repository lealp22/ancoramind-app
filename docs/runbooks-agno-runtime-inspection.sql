-- Inspección de SOLO LECTURA del runtime de Agno (schema `agno_runtime`).
-- Contexto: BACKLOG BL-34 (retención/purga de sesiones pendiente) y specs/046
-- (qué contenido conversacional ya existe fuera de Phoenix).
--
-- Cómo usarlo
--   * Supabase: SQL Editor (no el Table Editor: `agno_runtime` es un SCHEMA, no una
--     tabla, y el Table Editor sólo lista `public` hasta que eliges el schema en el
--     desplegable). Ejecuta cada bloque por separado, en orden.
--   * Todas las consultas son SELECT. Ninguna modifica nada. Aun así, ejecútalas con
--     un rol de sólo lectura si tienes uno; el rol de la app puede escribir.
--   * NO VALIDADAS contra un PostgreSQL real: se escribieron sin acceso a una base
--     (sin Docker ni psql en el equipo donde se redactaron). La sintaxis se revisó a
--     mano. Si alguna falla, es un error del script, no del dato: no insistas ni
--     "arregles" ejecutando algo distinto sin releerlo. Supuestos: `runs` es JSONB
--     (así lo define Agno) y las tablas se llaman `agno_*`; la consulta 1 lo confirma.
--   * Las consultas 1-5 sólo cuentan y miden: no devuelven texto de conversaciones.
--     Las 6-7 devuelven NOMBRES DE CLAVES y tipos del JSON, nunca valores.
--     La 8 es opcional y devuelve contenido: léela antes de ejecutarla.
--
-- Tablas por defecto de Agno (todas con prefijo `agno_`): agno_sessions (la que
-- importa: guarda `runs`, el historial con mensajes y resultados de tools, en JSONB),
-- agno_memories, agno_metrics, agno_eval_runs, agno_knowledge, agno_traces,
-- agno_spans, agno_schema_versions, agno_culture, agno_learnings, ...
-- Las marcas de tiempo (`created_at`, `updated_at`) son BIGINT en segundos epoch.


-- ═════════════════════════════════════════════════════════════════════════════
-- 1. ¿Estoy mirando la base correcta? ¿Existe el schema y qué tablas tiene?
-- ═════════════════════════════════════════════════════════════════════════════
-- Si no devuelve filas, AGNO_DATABASE_URL apunta a OTRA base distinta de la que
-- estás consultando (o el schema se llama distinto). Compara `current_database()`
-- con el host de la variable en Railway antes de seguir.
SELECT current_database()           AS base_actual,
       current_user                 AS rol_actual,
       n.nspname                    AS schema,
       c.relname                    AS tabla,
       c.reltuples::bigint          AS filas_estimadas,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS tamano_total
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'agno_runtime'
  AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 2. Volumen y antigüedad de las sesiones (sin contenido)
-- ═════════════════════════════════════════════════════════════════════════════
SELECT count(*)                                              AS sesiones,
       count(DISTINCT user_id)                               AS usuarios_distintos,
       to_timestamp(min(created_at))                         AS sesion_mas_antigua,
       to_timestamp(max(updated_at))                         AS ultima_actividad,
       now() - to_timestamp(min(created_at))                 AS antiguedad_maxima,
       pg_size_pretty(pg_total_relation_size('agno_runtime.agno_sessions')) AS tamano_tabla
FROM agno_runtime.agno_sessions;


-- ═════════════════════════════════════════════════════════════════════════════
-- 3. ¿Hay retención? Sesiones por antigüedad
-- ═════════════════════════════════════════════════════════════════════════════
-- Si hay filas en los tramos de más de 30/90 días, nada las está purgando
-- (BL-34 lo dejó como pendiente). Es la cifra que importa para la DPIA.
SELECT CASE
         WHEN to_timestamp(coalesce(updated_at, created_at)) > now() - interval '7 days'   THEN '1) ≤ 7 días'
         WHEN to_timestamp(coalesce(updated_at, created_at)) > now() - interval '30 days'  THEN '2) 8-30 días'
         WHEN to_timestamp(coalesce(updated_at, created_at)) > now() - interval '90 days'  THEN '3) 31-90 días'
         ELSE                                                                                    '4) > 90 días'
       END AS tramo_desde_ultima_actividad,
       count(*) AS sesiones
FROM agno_runtime.agno_sessions
GROUP BY 1
ORDER BY 1;


-- ═════════════════════════════════════════════════════════════════════════════
-- 4. Cuánto pesa el historial por sesión (detecta sesiones que crecen sin límite)
-- ═════════════════════════════════════════════════════════════════════════════
-- `runs` es un array JSON: cada elemento es una ejecución. Sólo cuenta y mide.
SELECT count(*)                                                  AS sesiones_con_runs,
       round(avg(jsonb_array_length(runs)), 1)                   AS runs_medias,
       max(jsonb_array_length(runs))                             AS runs_maximas,
       -- pg_column_size mide lo almacenado en disco (puede estar comprimido por
       -- TOAST): es un orden de magnitud, no el tamaño exacto del JSON.
       pg_size_pretty(avg(pg_column_size(runs))::bigint)         AS tamano_runs_medio_en_disco,
       pg_size_pretty(max(pg_column_size(runs))::bigint)         AS tamano_runs_maximo_en_disco
FROM agno_runtime.agno_sessions
WHERE runs IS NOT NULL
  AND jsonb_typeof(runs) = 'array';


-- ═════════════════════════════════════════════════════════════════════════════
-- 5. ¿Guarda Agno los resultados de las tools? (cuántas llamadas, sin ver nada)
-- ═════════════════════════════════════════════════════════════════════════════
-- Cuenta ejecuciones de tool por nombre y cuántas llevan un resultado guardado.
-- `tool_name` es el nombre de una tool registrada, no contenido del usuario.
-- Si `con_resultado_guardado` > 0 para get_document / search_documents / search_web,
-- el contenido de documentos y de la web SÍ está en esta base, sin enmascarar.
SELECT t ->> 'tool_name'                                          AS tool,
       count(*)                                                   AS llamadas,
       count(*) FILTER (WHERE coalesce(t ->> 'result', '') <> '') AS con_resultado_guardado,
       count(*) FILTER (WHERE (t ->> 'tool_call_error') = 'true') AS con_error
FROM agno_runtime.agno_sessions s,
     jsonb_array_elements(CASE WHEN jsonb_typeof(s.runs) = 'array' THEN s.runs ELSE '[]'::jsonb END) AS r,
     jsonb_array_elements(CASE WHEN jsonb_typeof(r -> 'tools') = 'array' THEN r -> 'tools' ELSE '[]'::jsonb END) AS t
GROUP BY 1
ORDER BY llamadas DESC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 6. Forma del JSON de una run: SÓLO nombres de claves y tipos, nunca valores
-- ═════════════════════════════════════════════════════════════════════════════
-- Sirve para saber qué campos guarda Agno (messages, tools, input, content, ...)
-- y decidir qué consultar después, sin leer ninguna conversación.
SELECT k.key                         AS clave_de_run,
       jsonb_typeof(k.value)         AS tipo,
       count(*)                      AS veces
FROM (
  SELECT r
  FROM agno_runtime.agno_sessions s,
       jsonb_array_elements(CASE WHEN jsonb_typeof(s.runs) = 'array' THEN s.runs ELSE '[]'::jsonb END) AS r
  ORDER BY s.updated_at DESC NULLS LAST
  LIMIT 200
) recientes,
LATERAL jsonb_each(recientes.r) AS k
GROUP BY 1, 2
ORDER BY veces DESC, 1;


-- ═════════════════════════════════════════════════════════════════════════════
-- 7. Otras tablas de Agno con posible contenido: ¿están vacías o pobladas?
-- ═════════════════════════════════════════════════════════════════════════════
-- La app no usa memoria/cultura/learnings de Agno a propósito (la memoria canónica
-- está en `ancora`). Si alguna tiene filas, hay datos que nadie esperaba.
SELECT 'agno_memories' AS tabla, count(*) AS filas FROM agno_runtime.agno_memories
UNION ALL SELECT 'agno_learnings',   count(*) FROM agno_runtime.agno_learnings
UNION ALL SELECT 'agno_culture',     count(*) FROM agno_runtime.agno_culture
UNION ALL SELECT 'agno_knowledge',   count(*) FROM agno_runtime.agno_knowledge
UNION ALL SELECT 'agno_traces',      count(*) FROM agno_runtime.agno_traces
UNION ALL SELECT 'agno_spans',       count(*) FROM agno_runtime.agno_spans
UNION ALL SELECT 'agno_eval_runs',   count(*) FROM agno_runtime.agno_eval_runs
UNION ALL SELECT 'agno_metrics',     count(*) FROM agno_runtime.agno_metrics
ORDER BY filas DESC;
-- Nota: si una de estas tablas no existe, esa línea falla con "relation does not
-- exist". Es normal (Agno crea las tablas bajo demanda). Quita esa línea y repite.


-- ═════════════════════════════════════════════════════════════════════════════
-- 8. OPCIONAL — comprobar si hay datos con formato sensible. DEVUELVE CONTENIDO.
-- ═════════════════════════════════════════════════════════════════════════════
-- Sólo cuenta cuántas sesiones contienen algo con forma de DNI/IBAN/tarjeta.
-- No muestra el dato: devuelve conteos. Es un cálculo sobre texto de conversaciones
-- personales; ejecútalo sólo si decides que necesitas esa cifra, y no copies filas.
-- Aproximación por forma, SIN validar el dígito de control: sobreestima (cualquier
-- 8 dígitos + letra cuenta). Sirve para saber si "hay algo", no cuánto es real.
-- Usa `\y` (límite de palabra) y `E'...'` para no depender de la configuración de
-- barras invertidas del cliente.
SELECT count(*) FILTER (WHERE runs::text ~* E'\\y[0-9]{8}[A-Z]\\y')                            AS sesiones_con_forma_de_dni,
       count(*) FILTER (WHERE runs::text ~* E'\\yES[0-9]{2}[0-9 ]{18,}')                       AS sesiones_con_forma_de_iban,
       count(*) FILTER (WHERE runs::text ~  E'\\y[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{4}\\y') AS sesiones_con_forma_de_tarjeta,
       count(*)                                                                               AS sesiones_totales
FROM agno_runtime.agno_sessions;
