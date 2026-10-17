# Verification: 027 — Pantalla de administración centralizada

> **Status:** 🔶 implementación local completa (2026-10-05); validación manual
> en Railway parcial: login/HTTPS, emisión manual y logout validados 2026-10-17;
> inactividad, runtime-config completo y resto de matriz pendientes.

## Emisión autoaprobada desde panel — 2026-10-17

Segunda ventana remota autorizada: Auto-aprobar marcado al emitir un uso/TTL
5 min; el mismo evaluador fuera de allowlist recibe acceso concedido y ayuda
sin llamada de aprobación manual ni LLM. Emisión/canje confirmados por DB.
No cambio de producto/runtime-config. Logout/sessionStorage y flags OFF al
cierre, cuenta revocada, servicio sano/rev.8; deployment final
`13cf938f-595c-4509-be0d-463fceae1b95` SUCCESS, SHA `bee0062`. Sin secretos
nuevos ni valores/código en evidencia de esta ventana. Detalle en campaña.
Timeout real y resto de matriz siguen pendientes; silencio sin acceso
registrado BL-52, no corregido. 1536 unitarias/Ruff/mypy superados.

## Panel real en ventana autorizada — 2026-10-17

Mismo SHA `bee0062`, CI verde. Habilitación temporal, shell HTTPS 200;
API sin token/incorrecto/token CLI → 401; token del panel no sirve para API CLI.
Login correcto, emisión de invitación manual de un uso/TTL 5 min, listado y
salud/revisión visibles. Token en sessionStorage, ausente de localStorage;
logout borra token/actor y vuelve al login. Input oculto vaciado al cerrar.
Cabeceras no-store/DENY/CSP comprobadas. No esperar 30 min ≠ validar timeout.

Invitación canjeada por segunda cuenta fuera de allowlist; aprobación/revocación
mediante API CLI, sin botones nuevos. Sin LLM/runtime-config ni escrituras SQL.
Deployments temporales `d4567737-ec8c-4fc1-b16a-099dd6259103` y cierre
`5b7c5d96-30e1-42d6-9503-5aaff8924157`, SUCCESS. Tres flags false, rutas
administrativas de pairing/panel 404, servicio sano/rev.8; acceso evaluador revocado.

Incidencia de transcript: filtro de diagnóstico no reconoció whitespace Unicode
en `/pair` y devolvió código ya agotado. No se copia aquí; acceso cerrado.
No generalizar a garantía absoluta de metadata-only. Detalle y UUIDs en campaña
MVP «E2E manual remoto autorizado, sin LLM». BL-43 sigue parcial: falta matriz
restante, no se modificó runtime-config para probar onboarding.

## Preparación local para onboarding — 2026-10-17

- 32 casos añadidos en `tests/unit/test_admin_dashboard.py`: las ocho rutas
  JSON rechazan credenciales ausentes/incorrectas/token CLI (401, no-store),
  y las cuatro mutaciones exigen actor/motivo (422). Requests de esquema
  válido para comprobar autenticación; validación de config no es mutación.
- Settings del helper unitario sin lectura de `.env`. Sin cambios de producto.
- `tests/integration/test_onboarding_admin_flow.py`: 7 casos nuevos con
  panel/API CLI/admisión y servicios/repos PostgreSQL reales, sólo loopback
  `_test`; emisión del panel y decisiones CLI actúan sobre las mismas filas.
  Código de un uso, manual/auto, rechazo/expiración/revocación/cupo, auditoría,
  redacción y revocación efectiva en update nuevo; sin Agent/LLM/Telegram.
- 70 unitarias focales, 1536 globales; integración completa 183 passed,
  1 live STT skipped. Ruff global y `mypy src/` (174 módulos) limpios.
- Pruebas ASGI, no navegador: no afirman login/inactividad/sessionStorage/HTTPS
  reales. El HTML shell es público; datos JSON protegidos. El panel no incluye
  aprobar/rechazar/revocar, que se operan por CLI/API protegida.
- Checklist: `docs/preflight-onboarding-admin.md`. E2E remoto y apertura del
  piloto siguen pendientes; no se activaron flags ni cambió runtime-config.

## Local verification required

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests/unit/test_admin_dashboard.py tests/unit/test_telegram_pairing.py tests/unit/test_runtime_config_admin.py -q
python -m pytest tests/unit/ -q
python -m pytest tests/integration/ -q
ruff check src/ tests/ scripts/ migrations/
mypy src/
```

## Pending acceptance evidence

- [x] `ADMIN_DASHBOARD_ENABLED=true` sin `ANCORA_DATABASE_URL`,
  `ADMIN_DASHBOARD_TOKEN` o `TELEGRAM_PAIRING_CODE_PEPPER` falla al arrancar
  (fail-closed), igual que las otras banderas admin.
- [x] Cada ruta JSON del dashboard (`/admin/dashboard/api/*`) exige
  `Authorization: Bearer <ADMIN_DASHBOARD_TOKEN>`; `RUNTIME_CONFIG_ADMIN_TOKEN`
  nunca es aceptado ni enviado por la página.
- [x] Crear una invitación devuelve el código una sola vez y no persiste el
  código en claro; listar invitaciones nunca expone `code_hash`.
- [x] Status/validar/crear revisión/activar/rollback de runtime-config operan
  sobre la misma instancia de `RuntimeConfigManager` que el admin API HTTP —
  un cambio hecho desde el dashboard se refleja en
  `GET /admin/runtime-config/status` (y viceversa).
- [x] El panel de enlaces oculta las URLs no configuradas y adjunta
  `health_status` a Supabase/LiteLLM Gateway desde `HealthRegistry`.
- [x] `scripts/runtime_config.py` y `scripts/telegram_pairing.py` siguen
  funcionando sin cambios de comportamiento.
- [x] Toda respuesta bajo `/admin/dashboard*` incluye
  `Content-Security-Policy`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` y
  `Cache-Control: no-store`.
- [x] El JS cierra la sesión (borra `sessionStorage`, pide el token de nuevo)
  tras 30 minutos sin actividad del ratón/teclado/scroll/touch.
- [x] Confirmar en Railway que el dominio del dashboard es HTTPS (2026-10-17; no hay
  enforcement a nivel de aplicación todavía — ver nota abajo).
- [ ] Validación manual en Railway: abrir `/admin/dashboard`, iniciar sesión,
  crear una invitación de prueba, hacer un ciclo completo de runtime-config
  (validar → crear revisión → activar → rollback) y confirmar que el panel de
  salud refleja `/health/readiness` en vivo.

## Nota: por qué no hay un rechazo HTTP→HTTPS a nivel de aplicación

Se consideró que el backend rechazara peticiones a `/admin/dashboard*` cuyo
`request.url.scheme` no fuera `https` fuera de `APP_ENV=development`. No se
implementó: Railway termina TLS en su borde y reenvía al contenedor por HTTP
plano, y `uvicorn`/Starlette no están configurados hoy para confiar en la
cabecera `X-Forwarded-Proto` (no hay `--proxy-headers`/`ProxyHeadersMiddleware`
en `src/agent/server.py`). Sin esa configuración, `request.url.scheme` sería
siempre `"http"` dentro del contenedor — un chequeo así bloquearía el
dashboard también en producción. Añadir esa confianza en la cabecera
reenviada es un cambio transversal (afecta a toda la app, no sólo al
dashboard) y queda fuera de este incremento; mientras tanto, la garantía de
HTTPS sigue siendo la misma que ya tiene el resto de `/admin/*`: el dominio de
Railway nunca se expone por HTTP.

## Evidence (local, 2026-10-05)

- Nuevos módulos: `src/agent/admin_dashboard.py`,
  `src/agent/admin_dashboard_static/dashboard.html`.
- `src/repositories/pairing.py` y
  `src/domain/interactions/pairing_service.py` ganan `list_invitations`.
- `src/main.py` instala `install_admin_dashboard` tras validar
  `validate_admin_dashboard_settings`, siguiendo el mismo patrón fail-closed
  de las otras tres banderas `/admin/*`.
- `src/agent/agent_os_rest_guard.py` no requirió cambios: su exclusión de
  prefijo `/admin` ya cubre `/admin/dashboard*`.
