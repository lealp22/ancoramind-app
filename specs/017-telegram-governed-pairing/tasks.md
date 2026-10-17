# Tasks: 017 — Governed Telegram Pairing

## T1: SDD and durable operator control plane

- [x] Create spec, tasks and verification artifacts.
- [x] Add idempotent schema + Alembic revision for invitations, requests and authorizations.
- [x] Store invitation codes only as keyed hashes, with TTL/use counters and audit fields.
- [x] Implement protected issue/approve/revoke API using existing bearer + actor contract.
- [x] Add unit tests for secret handling and admin authentication.

## T2: Atomic redemption

- [x] Implement repository/service redeem with `FOR UPDATE` plus per-user advisory lock.
- [x] Enforce expiry, status, capacity, duplicate redemption and one pending request per user.
- [x] Add operator request list/reject endpoints with audited decisions.
- [x] Add unit + PostgreSQL integration tests for concurrent/replayed redemption.

## T3: Telegram and admission integration

- [x] Parse `/pair <code>` deterministically in a private chat before Agent execution.
- [x] Persist/deliver a fixed safe response via the durable outbox; never log the code.
- [x] Consult active durable authorization in admission, retaining technical allowlist as an operator path.
- [x] Prove pending/rejected/expired/revoked users have zero Agent/LLM calls.
- [x] Test immediate revocation for a subsequent update and at-most-once behavior for duplicate updates.

## T4: Operations and closure

- [x] Add administrative CLI/runbook and production rollout flags.
- [x] Manual subset on current Railway service with second evaluator account,
  no LLM: pending/approve/help/revoke, outbox and flags/access closure (2026-10-17).
- [x] Auto-approved subset with same evaluator, no LLM: opt-in issue, granted
  reply, immediate help, revoke and flags/access closure (2026-10-17).
- [ ] Complete remaining remote matrix; manual subset is not full T4 closure.
- [ ] Execute controlled Railway E2E with a non-production evaluator account.
- [ ] Record evidence with metadata only and update BACKLOG.md on closure.