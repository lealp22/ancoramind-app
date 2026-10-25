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
-- Cuenta en cuántas sesiones hay un dato con formato de DNI o tarjeta que ADEMÁS
-- supera su dígito de control. No muestra el dato: devuelve conteos. Lee texto de
-- conversaciones personales; ejecútalo sólo si necesitas esa cifra y no copies filas.
--
-- Versión 2. La primera buscaba sólo la FORMA y dio 20 de 21 sesiones "con tarjeta":
-- era ruido. Una run de Agno está llena de identificadores y métricas de 16 dígitos,
-- y cualquiera encaja en la forma. Ahora:
--   * Sólo se escanea el texto de mensajes (`content`) y de resultados de tools
--     (`result`), no los ids, marcas de tiempo ni métricas.
--   * La tarjeta debe pasar Luhn y no ser un único dígito repetido (0000... pasa
--     Luhn pero no es una tarjeta). El DNI debe cumplir la letra de control.
--   * IBAN omitido: su control (módulo 97 sobre un número de ~30 dígitos) no cabe
--     de forma fiable en SQL sin una función propia, y esa función no es de sólo
--     lectura. Si lo necesitas, hazlo con el enmascarador real (src/observability/
--     masking.py) sobre una exportación, no aquí.
-- Sigue siendo una cota, no una medida exacta: falsos negativos si el dato está
-- partido o escrito de otro modo (el enmascarador de la app tiene el mismo límite).
WITH textos AS (
  -- Un texto por fila: cada `content` de mensaje y cada `result` de tool.
  SELECT s.session_id, x.txt
  FROM agno_runtime.agno_sessions s
  CROSS JOIN LATERAL jsonb_array_elements(
         CASE WHEN jsonb_typeof(s.runs) = 'array' THEN s.runs ELSE '[]'::jsonb END) AS r
  CROSS JOIN LATERAL (
    SELECT m ->> 'content' AS txt
    FROM jsonb_array_elements(
           CASE WHEN jsonb_typeof(r -> 'messages') = 'array' THEN r -> 'messages' ELSE '[]'::jsonb END) AS m
    UNION ALL
    SELECT t ->> 'result'
    FROM jsonb_array_elements(
           CASE WHEN jsonb_typeof(r -> 'tools') = 'array' THEN r -> 'tools' ELSE '[]'::jsonb END) AS t
  ) x
  WHERE x.txt IS NOT NULL
),
candidatos_tarjeta AS (
  -- 13-19 dígitos, con espacios o guiones opcionales, sin dígitos pegados alrededor.
  SELECT session_id,
         regexp_replace(m[1], '[^0-9]', '', 'g') AS digitos
  FROM textos,
       LATERAL regexp_matches(txt, '(?<![0-9])([0-9](?:[ -]?[0-9]){12,18})(?![0-9])', 'g') AS m
),
tarjetas_validas AS (
  SELECT DISTINCT session_id
  FROM candidatos_tarjeta c
  WHERE digitos !~ '^(.)\1+$'  -- un solo dígito repetido no es una tarjeta
    AND (
      -- Luhn: desde el último dígito (ord = 0), se doblan los de posición impar.
      SELECT sum(CASE WHEN d.ord % 2 = 1
                      THEN (CASE WHEN d.v * 2 > 9 THEN d.v * 2 - 9 ELSE d.v * 2 END)
                      ELSE d.v END)
      FROM (
        SELECT substr(c.digitos, length(c.digitos) - g + 1, 1)::int AS v, g - 1 AS ord
        FROM generate_series(1, length(c.digitos)) AS g
      ) d
    ) % 10 = 0
),
candidatos_dni AS (
  SELECT session_id, upper(m[1]) AS dni
  FROM textos,
       LATERAL regexp_matches(txt, '(?<![0-9A-Za-z])([0-9]{8}[- ]?[A-Za-z])(?![0-9A-Za-z])', 'g') AS m
),
dni_validos AS (
  SELECT DISTINCT session_id
  FROM candidatos_dni
  WHERE substr('TRWAGMYFPDXBNJZSQVHLCKE',
               (substr(regexp_replace(dni, '[- ]', '', 'g'), 1, 8)::int % 23) + 1, 1)
        = right(regexp_replace(dni, '[- ]', '', 'g'), 1)
)
SELECT (SELECT count(*) FROM agno_runtime.agno_sessions)     AS sesiones_totales,
       (SELECT count(*) FROM tarjetas_validas)               AS sesiones_con_tarjeta_que_pasa_luhn,
       (SELECT count(*) FROM dni_validos)                    AS sesiones_con_dni_valido;
