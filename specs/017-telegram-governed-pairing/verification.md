# Verification: 017 — Governed Telegram Pairing

> **Status:** 🔶 T1 implementation in progress as of 2026-09-27.

## Local verification required

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests/unit/test_telegram_pairing.py -q
python -m pytest tests/unit/ -q
python -m pytest tests/integration/test_migrations.py -q
ruff check src/ tests/ scripts/ migrations/
```

## Pending acceptance evidence

- A raw invitation code does not exist in PostgreSQL, JSON logs, OTel attributes
  or API responses after issuance.
- Two concurrent redemption attempts consume one capacity unit at most and create
  at most one pending request for the same invitation/user.
- Expired, exhausted, revoked and rejected paths make zero Agent/LLM calls.
- An active authorization admits a private update; a revocation blocks the next
  new update without requiring an app restart.
- Controlled Railway E2E preserves Telegram update idempotency and outbox delivery.