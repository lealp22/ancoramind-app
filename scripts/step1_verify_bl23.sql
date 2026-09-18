-- Paso 1 BL-23: verificación E2E solo-lectura (metadata, sin contenido personal).
-- Pegar en el SQL editor de Supabase sustituyendo <BOT_ID>, <UPDATE_ID>,
-- <UPDATE_ID_1>, <UPDATE_ID_2> y <CORRELATION_ID>. Nunca selecciona ciphertext.

-- 0. Últimas interacciones (contexto)
SELECT id AS correlation_id, bot_id, telegram_update_id, telegram_message_id,
       chat_id, telegram_user_id, update_type, status,
       model_call_count, gateway_request_count, tool_call_count,
       estimated_cost, actual_cost, config_revision,
       error_class, error_detail_code,
       received_at, accepted_at, agent_started_at, response_ready_at,
       delivery_started_at, completed_at
FROM ancora.telegram_interactions
ORDER BY received_at DESC
LIMIT 20;

-- 1a. Acceptance A/B: un update -> 1 interacción + N deliveries (2ª duplicate=true)
SELECT i.id AS correlation_id, i.bot_id, i.telegram_update_id, i.status,
       i.model_call_count, i.gateway_request_count, i.tool_call_count,
       count(d.id) AS delivery_count,
       count(d.id) FILTER (WHERE d.duplicate) AS duplicate_count,
       array_agg(d.railway_request_id ORDER BY d.received_at, d.id) AS railway_request_ids,
       array_agg(d.delivery_status ORDER BY d.received_at, d.id) AS delivery_statuses
FROM ancora.telegram_interactions i
LEFT JOIN ancora.telegram_deliveries d ON d.interaction_id = i.id
WHERE i.bot_id = <BOT_ID> AND i.telegram_update_id = <UPDATE_ID>
GROUP BY i.id, i.bot_id, i.telegram_update_id, i.status,
         i.model_call_count, i.gateway_request_count, i.tool_call_count;
-- Esperado: 1 fila, delivery_count=2, duplicate_count=1, contadores de UN solo run.

-- 1a-bis. Deliveries ordenadas por correlation_id (detalle B)
SELECT d.received_at, d.railway_request_id, d.duplicate, d.http_status,
       d.delivery_status
FROM ancora.telegram_deliveries d
WHERE d.interaction_id = '<CORRELATION_ID>'::uuid
ORDER BY d.received_at, d.id;
-- Esperado: 1ª duplicate=false, 2ª duplicate=true, mismo correlation_id.

-- 1a-ter. Acceptance V: el duplicado no genera IA extra
SELECT i.id AS correlation_id, i.status,
       (SELECT count(*) FROM ancora.llm_usage_events u
         WHERE u.interaction_id = i.id) AS llm_events,
       (SELECT count(*) FROM ancora.logical_responses r
         WHERE r.interaction_id = i.id) AS logical_responses
FROM ancora.telegram_interactions i
WHERE i.id = '<CORRELATION_ID>'::uuid;
-- Esperado: llm_events y logical_responses de UN solo run con 2 deliveries.

-- 1b. Acceptance N/O: rechazados/ignorados sin IA
SELECT i.id AS correlation_id, i.telegram_update_id, i.status,
       i.error_class, i.error_detail_code,
       i.model_call_count, i.gateway_request_count,
       (SELECT count(*) FROM ancora.llm_usage_events u
         WHERE u.interaction_id = i.id) AS llm_events
FROM ancora.telegram_interactions i
WHERE i.bot_id = <BOT_ID> AND i.telegram_update_id IN (<UPDATE_ID_1>, <UPDATE_ID_2>)
ORDER BY i.telegram_update_id;
-- Esperado: rejected/ignored, user_not_allowlisted o non_private_chat,
-- model_call_count=0, gateway_request_count=0, llm_events=0.

-- Trazabilidad I por correlation_id (sin contenido)
SELECT i.id AS correlation_id, i.status, i.config_revision,
       i.agno_session_id, i.agno_run_id,
       i.model_call_count, i.gateway_request_count, i.tool_call_count,
       (SELECT count(*) FROM ancora.telegram_deliveries d
         WHERE d.interaction_id = i.id) AS deliveries,
       (SELECT count(*) FROM ancora.llm_usage_events u
         WHERE u.interaction_id = i.id) AS llm_events,
       (SELECT count(*) FROM ancora.logical_responses r
         WHERE r.interaction_id = i.id) AS logical_responses
FROM ancora.telegram_interactions i
WHERE i.id = '<CORRELATION_ID>'::uuid;
