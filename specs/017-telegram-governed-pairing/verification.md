# Verification: 017 — Governed Telegram Pairing

> **Status:** 🔶 Implementación local completa; E2E manual y autoaprobado
> Telegram/Railway sin LLM superados el 2026-10-17. Aislamiento y resto de matriz
> remota pendientes; no cierre global de BL-24.

## E2E autoaprobado con segunda cuenta — 2026-10-17

Pedido expresamente por el propietario. Un uso/TTL 5 min/Auto-aprobar=true
emitido desde panel; cuenta revocada previamente, fuera de allowlist. Canje
crea approved+autorización en el mismo instante y Telegram muestra «✅ Acceso
concedido. Ya puedes escribir con normalidad.»; `/help` funciona sin aprobación
manual. Revocar bloquea siguiente update sin reinicio. Tres interacciones sin
Agent/LLM, dos entregas completadas. Sin reenviar mensaje libre previo.

Habilitación `ed35acaf-4777-4174-9391-4e3b9c5bcf98`, cierre
`13cf938f-595c-4509-be0d-463fceae1b95`, SUCCESS, SHA `bee0062` con CI verde.
Tres flags false/cuenta revocada/código exhausted/ningún pending; readiness
200/rev.8, rutas admin 404. Secretos previos preservados y sin cambios de
allowlist/webhook/modelo/runtime. UUIDs y tiempos en campaña, sección
«E2E autoaprobado remoto autorizado, sin LLM». Sin código de invitación en
outputs de esta ventana. 1536 unitarias/Ruff/mypy limpios; no nueva integración.

Falta de respuesta al mensaje del propietario reproducida por metadata:
rejected/user_not_allowlisted sin outbox. Mejora genérica sin LLM registrada
BL-52, no implementada; mantener denegación/idempotencia y límites propios.

## E2E manual con segunda cuenta — 2026-10-17

Servicio actual y flags temporales autorizados expresamente. Cuenta fuera de
allowlist: `/start` rechazado → canje privado → pending bloquea `/help` →
aprobación API → ayuda recibida → revocación API → siguiente `/help` rechazado
sin reinicio. Cinco interacciones, cero Agent/model/Gateway/tools/usage LLM.
Invitación de un uso agotada, autorización revocada, sin pending al terminar.
Dos entregas outbox completadas. Cambios SQL sólo mediante APIs de producto;
SELECTs de verificación scoped/read-only, sin fixtures productivos.

SHA `bee0062` con CI verde; habilitación deployment `d4567737-ec8c-4fc1-b16a-099dd6259103`,
cierre `5b7c5d96-30e1-42d6-9503-5aaff8924157`, ambos SUCCESS. Tres flags OFF,
readiness 200/rev.8, panel/APIs 404 al cierre. Secretos nuevos de panel/pepper
conservados; token CLI previo, allowlist y webhook preservados.

**Límites:** sin autoaprobación/replay/expiración remotos ni aislamiento de datos.
Un filtro diagnóstico del agente devolvió el código agotado al no reconocer
whitespace Unicode; no se incluye su valor en docs. Acceso ya revocado; no se
declara evidencia íntegramente metadata-only. Payload cifrado productivo no
descifrado en esta ventana. Evidencia/IDs/incidencia: campaña MVP, sección
«E2E manual remoto autorizado, sin LLM».

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
- [x] Controlled manual Railway E2E delivers pairing/help via outbox without LLM
  (2026-10-17); temporary evaluator access and flags closed afterwards.
- [x] Remote opt-in auto-approval returns granted reply and immediately admits
  `/help`, with no manual approval/LLM; revoked/flags OFF afterwards (2026-10-17).
- [ ] Remote duplicate-update/replay and full controlled matrix.

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