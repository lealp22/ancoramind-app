# Spec: 017 — Governed Telegram Pairing

> **Backlog:** BL-24  
> **Status:** in progress (2026-09-27)

## Requirement

AncoraMind must onboard a bounded group of Telegram evaluators without opening
the bot to arbitrary users or relying on manual `telegram_user_id` allowlist
edits. An operator issues a temporary invitation; a person redeems it only from
a private chat; an operator explicitly approves the observed Telegram identity;
only then may durable admission authorize Agent execution.

## Security invariants

- The invitation code is an onboarding credential, not authorization. It is
  generated with high entropy and stored only as a keyed HMAC hash.
- Private-chat, webhook secret, rate/concurrency limits, durable idempotency and
  at-most-once execution from specs/013 remain mandatory.
- Pending, rejected, expired and revoked requests never reach the Agent or an
  LLM. `/pair` is resolved deterministically before any Agent execution.
- Every administrative mutation has a bearer-authenticated actor and reason.
  Raw codes, Telegram content and operator credentials never enter logs/OTel.
- Revocation is immediate for new admissions. Existing in-flight work preserves
  specs/013 no-replay semantics.

## Design

```text
operator API → invitation(code_hash, TTL, uses, audit)
private Telegram /pair <code> → atomic redeem → pairing request pending
operator API → approve request → active durable authorization
Telegram admission → technical allowlist OR active durable authorization
```

The administrative API reuses the existing disabled-by-default bearer and
`X-Ancora-Admin-Actor` pattern. It is not an Agent tool and has no browser CORS
surface. The issuance response returns the code once; subsequent reads expose
metadata only.

## First increment (2026-09-27)

- Tables, Alembic migration and idempotent fresh bootstrap schema.
- `TelegramPairingService` + parameterized repository for issue, approve,
  invitation revoke and authorization revoke.
- Disabled-by-default protected admin endpoints for issue, approval and revoke.

## Atomic redemption increment (2026-09-27)

- `redeem_invitation()` locks by Telegram user and invitation row, creates a
  pending request once, consumes capacity atomically and returns typed outcomes
  without retaining the raw code.
- Operator API lists bounded pending work and rejects requests with actor/reason.

## Next increment

- `/pair <code>` deterministic command/outbox response and admission integration
  that checks active authorizations without bypassing existing controls.
- Railway E2E and runbook.