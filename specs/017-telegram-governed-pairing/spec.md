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

- The invitation code is an onboarding credential, not authorization by
  default. It is generated with high entropy and stored only as a keyed HMAC
  hash. **The only opt-in exception is `auto_approve`** (see "T5 increment"
  below): an operator may explicitly flag an invitation, at issuance time, so
  its redemption grants authorization immediately. This never happens
  implicitly — it is a per-invitation choice made and audited by the issuing
  operator, not a relaxation of the default.
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

## T3/T4 local increments (2026-09-27)

- `/pair <code>` is parsed deterministically before Agent execution, is private
  chat-only, redacts its credential before durable interaction storage and writes
  a fixed safe reply to the transactional outbox.
- Admission accepts either the technical allowlist or a fresh active durable
  authorization lookup, so a revocation blocks the next new update without a
  restart.
- `scripts/telegram_pairing.py` operates the protected admin API for issuance,
  pending-request review and revocation. `docs/runbooks-017-telegram-pairing.md`
  defines rollout, rotation and approved E2E procedure.
- A real Telegram/Railway E2E still requires explicit webhook authorization and a
  non-production evaluator account.

## T5 increment: opt-in auto-approval (2026-10-05)

A single operator being unreachable must not block onboarding of people
already trusted enough to receive an invitation through a private channel.

- `PairingInvitationCreate`/`CreateInvitationRequest` gain `auto_approve: bool
  = False` (migration `0010_pairing_auto_approve` adds the column; default
  `false` for every existing/future invitation unless explicitly set).
- When `auto_approve` is true, `redeem_invitation()` creates the pairing
  request already `approved` — with `decided_by`/`decision_reason` taken from
  the invitation's own `created_by`/`reason` — and upserts the active
  authorization in the same transaction as the existing capacity/expiry
  bookkeeping. No separate `approve_request` call occurs.
- A new `PairingRedemptionStatus.AUTO_APPROVED` lets
  `TelegramInteractionService` send a distinct fixed reply
  (`PAIRING_AUTO_APPROVED_REPLY`, "✅ Acceso concedido…") instead of
  `PAIRING_PENDING_REPLY`. Every other outcome (expired/revoked/exhausted/
  already pending/already decided/invalid) is unchanged.
- Exposed through all three entry points: `scripts/telegram_pairing.py issue
  --auto-approve`, the admin API, and the BL-43 dashboard (with an inline
  warning that the code becomes the sole trust factor — pair with a tight
  `max_uses`).
- Tests: `tests/integration/test_telegram_pairing_repo.py` (atomic
  authorization grant), `tests/integration/test_telegram_admission_endpoint.py`
  (outbox reply + immediate admission of the next message, no manual
  approval), plus unit coverage for the service/admin API/CLI pass-through.