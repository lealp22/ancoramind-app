# Preparación local de onboarding/admin — BL-24/43

Fecha: 2026-10-17. **No autoriza rollout ni incorporación de participantes.**
Actualización: posteriormente se autorizó y ejecutó **sólo el circuito manual
remoto sin LLM** en el servicio actual, con segunda cuenta `account=2`; passed,
autorización revocada y tres flags OFF al cierre. No es apertura del piloto ni
matriz completa. También se ejecutó después el circuito autoaprobado sin LLM:
mensaje de acceso concedido, ayuda inmediata y revocación correctos; flags OFF
al cierre. No requiere aprobación manual. Silencio de cuentas sin acceso
registrado BL-52. **Actualización posterior:** BL-52 desplegado y E2E de
aviso/cooldown/renovación superado; panel y pairing permanecen ON por decisión
del propietario, sin rollback automático. La cuenta evaluadora sigue revocada.
Evidencia en specs/037 y campaña. Los flags OFF anteriores son históricos,
no el estado live actual. Registro de cambios/deployments/incidencia de redacción de
código agotado en la campaña, «E2E manual remoto autorizado, sin LLM».
Complementa `runbooks-017-telegram-pairing.md`, `runbooks-027-admin-dashboard.md`
y la campaña en `specs/008-railway-deployment/mvp-release-campaign.md`.

## 1. Alcance de la preparación

- Rutas FastAPI reales bajo transporte ASGI en memoria; servicios/repositorios
  de pairing reales contra PostgreSQL local en base dedicada `_test`.
- Settings de la prueba nueva con `_env_file=None`, identidades sintéticas,
  tokens ficticios independientes y clave de cifrado temporal. No importar
  `src.main`, arrancar sus workers ni usar el `.env` operativo para esta prueba.
- El nombre de DB en Settings de esa prueba es un marcador: la conexión real
  la proporciona `get_session` inicializado por la fixture de integración.
- `/pair` y sus respuestas fijas se procesan con un runner que falla si se
  invoca y un sender simulado. Telegram, proveedor LLM y navegador no se usan.
- Un mensaje posterior aprobado se comprueba hasta estado `accepted`; no se
  ejecuta el Agent. La prueba de revocación concierne al siguiente update nuevo,
  no promete cancelar trabajo ya admitido/en curso.

## 2. Matriz local

| Caso | Evidencia |
|---|---|
| Pairing manual | Emisión desde API del panel → hash persistido → canje privado → outbox sin Agent → bloqueo pending → aprobación por API CLI → admisión → revocación → rechazo nuevo |
| Autoaprobación explícita | Misma emisión con `auto_approve=true`, autorización atómica al canjear y sin solicitud pendiente; revocación posterior |
| Credenciales de superficie | Las ocho rutas JSON del panel rechazan token ausente, incorrecto o el token CLI con 401 para peticiones de esquema válido; el token del panel no aprueba por la API CLI |
| Auditoría administrativa | Mutaciones del panel sin actor/motivo → 422; creación/decisión/revocación preservan actor/motivo/timestamp |
| Código confidencial | Emitir devuelve código; listar no devuelve código ni hash; almacenamiento HMAC y payload de `/pair` descifrado sin código original |
| Idempotencia | Duplicado exacto de update de canje → una respuesta lógica; cobertura previa de private-only y carrera sobre un uso |
| Estados denegados | Rechazado, invitación revocada/expirada/agotada o código inválido → respuesta fija no enumerante, sin autorización ni Agent |
| Aislamiento de datos | Pruebas existentes de documentos/propuestas impiden lectura/acción de B sobre A; no sustituyen el E2E de dos cuentas |

Pruebas nuevas: `tests/integration/test_onboarding_admin_flow.py` (7 casos) y
32 casos añadidos a `tests/unit/test_admin_dashboard.py`. Las pruebas anteriores
de pairing/admisión/CLI siguen siendo parte del baseline.

### Ejecución segura de la integración local

Desde la raíz del repositorio, PowerShell, usar el venv. El guard evita un
destino custom/remoto y exige base dedicada; la fixture recrea esa base y
trunca sus tablas. No ejecutar dos sesiones de integración simultáneamente.

```powershell
@'
import os, subprocess, sys
from sqlalchemy.engine.url import make_url
assert not os.environ.get("ANCORA_TEST_DATABASE_URL"), "Custom DB not allowed here"
admin = make_url(os.environ.get(
    "ANCORA_TEST_ADMIN_DSN", "postgresql://ancora:ancora@localhost:5432/ancoramind"
))
assert admin.host in ("localhost", "127.0.0.1", "::1"), "Loopback only"
assert os.environ.get("ANCORA_TEST_DATABASE", "ancoramind_test").endswith("_test")
os.environ["ANCORA_TEST_REQUIRE_DB"] = "1"
raise SystemExit(subprocess.call([
    sys.executable, "-m", "pytest", "tests/integration/test_onboarding_admin_flow.py",
    "tests/integration/test_telegram_pairing_repo.py",
    "tests/integration/test_telegram_admission_endpoint.py", "-q",
]))
'@ | .\.venv\Scripts\python.exe -
```

No arrancar `python -m src.main` contra el `.env` de producción para demostrar
este circuito. No convertir fixtures de integración en registros productivos.

## 3. Decisiones pendientes antes de cualquier E2E remoto

- [ ] Elegir entorno/bot objetivo y SHA autorizado; confirmar CI del mismo SHA,
  readiness y rollback. Mantener Wait for CI según el gate manual acordado.
- [ ] Identificar operador y segunda cuenta evaluadora, fuera de la allowlist
  técnica; canal privado para el código. No añadir la cuenta a la allowlist.
- [ ] Acordar alcance/duración, aviso de privacidad, datos sintéticos, retención,
  retirada y revisión de los gates de `production-security-privacy.md`.
- [ ] Preparar secretos mediante el canal seguro del operador: token propio del
  panel, token del CLI y pepper HMAC independientes. No pegarlos en evidencias,
  prompts, capturas, URL ni código versionado. No reutilizar los ficticios.
- [ ] Autorizar flags concretos y ventana operativa. No habilitar nada por haber
  pasado tests. Pairing requiere admission durable y su cifrado/webhook secret.
- [ ] Verificar HTTPS real del panel/API; sin TLS sólo loopback de desarrollo.
  CORS/proxy, timeout de sesión y comportamiento del navegador no están
  demostrados por ASGI. Token del panel nunca sustituye el del CLI.
- [ ] Inventariar invitaciones/autorizaciones previas antes de la prueba; no
  revocar las de otros usuarios durante el cierre ni tocar el webhook por defecto.

## 4. Guion remoto (circuitos manual/auto ejecutados; resto pendiente)

1. Panel habilitado: HTML shell/login accesible; JSON sin token o con token
   erróneo → 401. Login correcto permite listar. Flag OFF → rutas ausentes/404.
   No confundir shell público con datos administrativos públicos.
2. Emitir invitación manual de un uso, TTL corto (mínimo API 5 min), actor y
   motivo. Entregar por canal privado, sin grabar el código. `/pair` debe producir
   sólo respuesta fija; antes de aprobar no hay acceso al Agent.
3. Listar y aprobar mediante CLI/API protegida, **no hay botón de aprobación en
   este panel**. Usar un update nuevo `/help` como prueba inicial sin inferencia;
   mantener la comprobación funcional con LLM como ventana aparte autorizada.
4. Revocar autorización por CLI/API y enviar otro update nuevo: acceso denegado.
   No repetir/reinyectar updates anteriores ni reiniciar para simular revocación.
5. Ensayar autoaprobación con invitación independiente opt-in; repetir el cierre.
   Rechazo/expiración/revocación de invitación/cupo y duplicado deben mantener
   respuesta no enumerante. Para expiración real esperar TTL; no modificar SQL
   ni adelantar el reloj productivo.
6. Con dos cuentas admitidas y fixtures sintéticos propios, verificar que B no
   ve documentos de A ni puede confirmar sus propuestas. Delimitar previamente
   la ventana/coste si se consulta mediante Agent: no está autorizada aquí.
7. Comprobar sesión del navegador: almacenamiento por pestaña, cierre explícito,
   inactividad, cabeceras no-store y ausencia de secretos en logs. No confundir
   comprobaciones estáticas con ejecución real del temporizador.
8. Cerrar sólo las invitaciones/autorizaciones de la ventana, revisar pending y
   aplicar el rollback aprobado. Evidencia metadata-only: UUIDs, actor, estados,
   timestamps, SHA/deployment y resultados. Nunca códigos ni bearer.

No activar/rollback runtime-config para probar onboarding: esa superficie tiene
su campaña y permiso propios. No ampliar ahora botones/roles/capabilities.

## 5. Condiciones de salida y límites del piloto

- Preparación y circuitos manual/auto remotos terminados ≠ BL-24/43 cerrados:
  se probaron HTTPS/login/emisión/logout y ayuda sin LLM; faltan resto de matriz
  remota, timeout real e aislamiento de datos entre cuentas.
- BL-49, BL-50 y BL-51 siguen documentados y abiertos en `BACKLOG.md`: no
  ofrecer calendario/snooze con confirmación incompleta, no declarar completa
  la consulta documental ni ampliar inferencia visual sin resolver/decidir sus
  limitaciones de campos y contabilidad.
- No confundir la preparación de acceso con aprobación de todos los gates
  técnicos, operativos o de privacidad para ofrecer el servicio a terceros.
