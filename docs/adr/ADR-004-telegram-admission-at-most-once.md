# ADR-004 — Telegram admission con ejecución Agent at-most-once

> **Status:** Accepted — implementado localmente (T2–T14, diseño aprobado
> 2026-09-13); rollout Railway completo y Collector/Grafana pendientes —
> specs/013/verification.md, BL-23
> **Contexto:** hardening del canal Telegram tras un incidente de amplificación
> de inferencias y el assessment del endpoint AgentOS de Agno 2.9.0.

---

## Contexto

La interfaz Telegram instalada de Agno recibe `update_id`, responde `2xx` antes
de ejecutar el Agent y deduplica durante 60 segundos en memoria. Esa protección
se pierde en restarts/deploys, no se comparte entre procesos y no permite
correlacionar deliveries de Railway con una interacción durable.

Además, la configuración actual no aplica realmente
`ALLOWED_TELEGRAM_USER_IDS` como allowlist y permite grupos si se menciona al
bot, contradiciendo la política private-chat-only de AncoraMind.

El requisito es:

```text
same bot identity + same Telegram update_id
=> at most one Agent execution
=> at most one persisted logical response/action
```

## Decisión

AncoraMind será propietario del endpoint de admission de Telegram, aunque Agno
continúe siendo el runtime del Agent.

1. **Identidad durable** — `UNIQUE(bot_id, telegram_update_id)` en PostgreSQL.
2. **Deliveries separadas** — cada request HTTP registra
   `X-Railway-Request-Id`; varias deliveries pueden apuntar a la misma
   `correlation_id`.
3. **Ack durable** — un update nuevo recibe `2xx` solo después de persistir el
   input normalizado necesario para procesarlo.
4. **Duplicado** — recibe `2xx` y no vuelve a ejecutar IA, tools, respuestas ni
   acciones.
5. **Admission determinista** — secret, private chat, allowlist, rate limit y
   capacidad de cola se evalúan antes de Agno.
6. **At-most-once estricto** — `accepted` puede recuperarse; después de
   `agent_started` no hay replay automático. Un resultado incierto queda
   `failed_ambiguous`.
7. **Idempotencia defensiva** — propuestas, acciones y respuestas tienen claves
   únicas aunque el Agent no se relance.
8. **Outbound** — una entrega Telegram incierta no se reenvía automáticamente,
   porque `sendMessage` no ofrece idempotency key.

## Consecuencias

### Positivas

- El mismo update no puede disparar varias ejecuciones Agent bajo la topología
  inicial de una réplica y el claim durable.
- Los retries de Telegram dejan de ser una fuente de amplificación.
- Rate limiting e idempotencia quedan correctamente separados.
- Private chats y allowlist se convierten en barreras de código.
- La interacción puede reconstruirse desde Railway hasta Agno y el Gateway.

### Negativas

- Una caída después de `agent_started` puede dejar al usuario sin respuesta.
- Se introduce un ledger, payload cifrado, worker y outbox.
- El streaming visible de Telegram se desactiva inicialmente para persistir una
  respuesta lógica antes de enviarla.
- Exactly-once externo no es posible sin soporte de Telegram.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Deduplicación RAM de Agno | TTL limitado; no durable, auditable ni multi-proceso |
| Rate limiting como sustituto | No reconoce la identidad de una reentrega |
| `message_id` como única key | La identidad de delivery adecuada es `update_id` por bot |
| Responder `2xx` antes de persistir | Puede perderse el update aceptado tras un crash |
| Effectively-once con replay del Agent | Repite inferencia probabilística, coste y posibles tools distintas |
| Exactly-once outbound | Telegram Bot API no proporciona idempotency key para `sendMessage` |

## Re-evaluación

Reabrir si:

- Telegram introduce idempotency keys outbound;
- se adopta una cola externa con garantías de procesamiento distintas;
- se escala a varias réplicas y los claims PostgreSQL/advisory locks resultan
  insuficientes;
- el coste de respuestas perdidas por `failed_ambiguous` supera el riesgo de
  replay.
