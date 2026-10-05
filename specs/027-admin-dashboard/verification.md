# Verification: 027 — Pantalla de administración centralizada

> **Status:** 🔶 implementación local completa (2026-10-05); validación manual
> en Railway pendiente.

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
- [ ] Confirmar en Railway que el dominio del dashboard es HTTPS (no hay
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
