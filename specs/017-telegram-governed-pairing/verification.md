# Verification: 017 — Governed Telegram Pairing

> **Status:** 🔶 T1–T4 local implementation complete as of 2026-09-27; controlled Telegram/Railway E2E remains pending.

## Local verification required

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests/unit/test_telegram_pairing.py -q
python -m pytest tests/unit/ -q
python -m pytest tests/integration/ -q
ruff check src/ tests/ scripts/ migrations/
```

## Pending acceptance evidence

- [x] A raw invitation code is HMAC-hashed at rest. For `/pair`, the raw code is
  redacted before the encrypted interaction payload/outbox is persisted and is
  never added to logs or telemetry attributes.
- [x] Two concurrent redemption attempts consume one capacity unit at most and create
  at most one pending request for the same invitation/user.
- [x] Pending, rejected, expired, exhausted and revoked states have no active
  durable authorization; they cannot create an Agent/LLM execution. `/pair`
  itself is persisted as `response_ready` with a deterministic outbox reply, so
  the processor delivers it without claiming the Agent.
- [x] An active authorization admits a private update; a revocation blocks the next
  new update without requiring an app restart.
- [x] A duplicate `/pair` update is idempotent by `bot_id + update_id`: one pairing
  request and one logical response are persisted.
- [x] Operator CLI and documented staging flags use only the bearer-protected
  admin API; mutations require an auditable actor and reason, without direct SQL
  access or code arguments.
- [ ] Controlled Railway E2E preserves Telegram update idempotency and outbox delivery.

## Evidence (local, 2026-09-27)

- `python -m pytest tests/unit/ -q` → 490 passed.
- `python -m pytest tests/integration/ -q` → 71 passed.
- `ruff check src/ tests/ scripts/ migrations/` and `git diff --check` → passed.
- No public webhook was registered and no Telegram account was contacted during this validation.