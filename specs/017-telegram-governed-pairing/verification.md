# Verification: 017 — Governed Telegram Pairing

> **Status:** 🔶 T1–T4 local implementation complete as of 2026-09-27; controlled Telegram/Railway E2E remains pending.

## Preparación conjunta onboarding/admin — 2026-10-17

- Baseline local limpio `bbed7bf`. Sin cambio de código de producto, migraciones,
  flags, allowlist ni secretos operativos; no acceso a producción en esta ventana.
- Nuevo `tests/integration/test_onboarding_admin_flow.py`: 7 casos ASGI con
  servicios/repos reales y PostgreSQL loopback/base `_test`. Panel emite/lista
  invitación, `/pair` redacta código y entrega outbox sin Agent, pendiente bloquea,
  CLI aprueba/rechaza/revoca, update nuevo refleja autorización o revocación.
- Manual y autoaprobación opt-in validados; código HMAC al persistir, listado sin
  código/hash, duplicado exacto, auditoría actor/motivo y estados rechazado,
  invitación revocada/expirada/agotada/código inválido sin acceso. Expiración usa
  sólo reloj de fixture SQL local, nunca el de producción.
- El sender es simulado y el runner falla si se invoca: sin Telegram ni LLM.
  Se comprueba admisión tras aprobar; no ejecución/cancelación del Agent.
- Unitarias focales admin/pairing/CLI/runtime: **70 passed** (incluidas 32 nuevas).
  Integración conjunta nueva + pairing repo/admission existente: **27 casos**,
  incluidos en suite completa **183 passed, 1 STT live skipped** (forzado OFF).
  Unitarias globales **1536 passed**; Ruff global, `mypy src/` (174 módulos)
  limpios. Advertencia OTLP local `localhost:4318` sin Collector al terminar
  unitarias; no invalida las aserciones ni observa el Collector productivo.
- Preparación y guion remoto en `docs/preflight-onboarding-admin.md`.
  Pendientes T4 y segunda cuenta real; el verde local no cierra BL-24/43 ni
  autoriza un rollout. BL-49/50/51 permanecen registrados y abiertos.

## Local verification required

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests/unit/test_telegram_pairing.py -q
python -m pytest tests/unit/test_telegram_pairing_script.py -q
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
  access or code arguments. CLI hardening tests cover actor requirements,
  non-2xx exit status and bearer non-disclosure.
- [ ] Controlled Railway E2E preserves Telegram update idempotency and outbox delivery.

## Evidence (local, 2026-09-27)

- `test_run_e2e_powershell.py` normaliza exclusivamente whitespace de `stderr`
  antes de comprobar mensajes de error: Windows PowerShell puede insertar saltos
  de línea al mostrar rutas con espacios (`The Bridge`), sin alterar el contrato
  de salida ni ocultar el código de salida no exitoso.
- `python -m pytest tests/unit/ -q` → 506 passed.
- `python -m pytest tests/integration/ -q` → 71 passed.
- `ruff check src/ tests/ scripts/ migrations/` and `git diff --check` → passed.
- `mypy scripts/telegram_pairing.py` → passed. Desde specs/019, `mypy src/`
  también está limpio (105 módulos); desde specs/020 es gate del job `quality`.
- No public webhook was registered and no Telegram account was contacted during this validation.