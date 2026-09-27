# AncoraMind — Runbook de pairing Telegram gobernado (BL-24 / spec 017)

> **Alcance:** emitir invitaciones temporales, revisar solicitudes, aprobar o
> revocar acceso de evaluadores Telegram. El flujo está apagado por defecto y
> sólo se habilita para un E2E controlado o un cohort acotado. No registrar ni
> modificar un webhook de Telegram sin aprobación explícita.

## 1. Invariantes operativos

- La invitación es una credencial de onboarding, **no** autorización: sólo una
  solicitud aprobada crea una autorización durable activa.
- Comparte el código una sola vez y únicamente por un canal privado aprobado. No
  lo copies en tickets, capturas, logs, OTel, terminal compartida ni chats.
- Las mutaciones exigen `Authorization: Bearer`, actor y motivo. Usa un actor
  identificable, por ejemplo `operator@example.com`; nunca nombres genéricos.
- `/pair <code>` sólo es válido en un chat privado. Se resuelve antes del Agent,
  queda redactado en la interacción durable y entrega una respuesta fija por el
  outbox, sin LLM.
- Revocar una autorización bloquea el **siguiente** update nuevo. No reinyectar
  updates existentes ni intentar recuperar ejecuciones `agent_started`.

## 2. Flags y secretos para staging/Railway

Mantener estos valores como secretos/variables del servicio AncoraMind; nunca en
Git ni en una revisión runtime:

```env
# Prerrequisitos de admission durable.
TELEGRAM_ADMISSION_ENABLED=true
TELEGRAM_BOT_ID=<id-numerico-de-getMe>
TELEGRAM_WEBHOOK_SECRET_TOKEN=<secreto-aleatorio>
TELEGRAM_PAYLOAD_ENCRYPTION_KEY=<fernet-key>
TELEGRAM_PAYLOAD_KEY_VERSION=1

# Pairing: ambos flags son necesarios para el E2E operado por CLI.
TELEGRAM_PAIRING_ENABLED=true
TELEGRAM_PAIRING_ADMIN_ENABLED=true
TELEGRAM_PAIRING_CODE_PEPPER=<secreto-hmac-independiente-y-aleatorio>

# API administrativa protegida; comparte el bearer existente del control plane.
RUNTIME_CONFIG_ADMIN_TOKEN=<bearer-aleatorio>
```

`ANCORA_DATABASE_URL` también es obligatorio. Para un cohort de evaluadores,
puede dejarse `ALLOWED_TELEGRAM_USER_IDS` vacío: pairing es una segunda ruta de
admission durable, no una ampliación pública. Conserva IDs técnicos allí sólo si
son necesarios para operación de emergencia.

**Rotación:** no cambies `TELEGRAM_PAIRING_CODE_PEPPER` mientras existan
invitaciones activas, porque sus HMAC dejarían de poder canjearse. Primero revoca
las invitaciones activas, espera/limpia el cohort conforme a la política aprobada,
rota el secreto en Railway y emite invitaciones nuevas. Rotar el bearer exige
actualizar Railway y el entorno del operador; no imprimirlo para verificarlo.

## 3. CLI administrativo

El cliente `scripts/telegram_pairing.py` usa exclusivamente la API HTTPS
protegida; no conecta directamente a PostgreSQL. Requiere que
`TELEGRAM_PAIRING_ADMIN_ENABLED=true` esté activo en el servicio objetivo.

En la sesión de operador, configura secretos sólo como variables de entorno:

```powershell
$env:RUNTIME_CONFIG_ADMIN_TOKEN='<bearer-del-entorno-seguro>'
$env:RUNTIME_CONFIG_ADMIN_ACTOR='operator@example.com'
$baseUrl = 'https://<servicio-no-productivo>.up.railway.app'
```

Lista solicitudes pendientes (no requiere actor):

```powershell
python scripts/telegram_pairing.py list-pending --base-url $baseUrl --limit 25
```

Emite una invitación. El código aparece una única vez en la salida; entrégalo por
un canal privado y no conserves la salida de la terminal:

```powershell
python scripts/telegram_pairing.py issue --base-url $baseUrl `
  --expires-in-minutes 60 --max-uses 1 --reason 'E2E evaluator cohort'
```

Después del `/pair` privado, aprueba o rechaza por el UUID de solicitud listado:

```powershell
python scripts/telegram_pairing.py approve --base-url $baseUrl `
  --request-id <uuid> --reason 'identity verified for controlled E2E'

python scripts/telegram_pairing.py reject --base-url $baseUrl `
  --request-id <uuid> --reason 'evaluator not approved'
```

Detén distribución de una invitación o elimina acceso durable inmediatamente:

```powershell
python scripts/telegram_pairing.py revoke-invitation --base-url $baseUrl `
  --invitation-id <uuid> --reason 'E2E window closed'

python scripts/telegram_pairing.py revoke-authorization --base-url $baseUrl `
  --telegram-user-id <id> --reason 'E2E revocation check complete'
```

El CLI imprime respuestas JSON de la API. Para `issue`, esa respuesta contiene el
código efímero: no redirigir stdout a archivos, CI o herramientas de transcript.

## 4. E2E controlado pendiente de aprobación

1. Confirmar un servicio y una cuenta evaluadora **no productivos**. Aplicar las
   variables de §2 y esperar un deployment `SUCCESS`.
2. Ejecutar `alembic upgrade head` por el proceso de migración aprobado; no hacer
   DDL manual desde Railway. Comprobar `/health` y que la base incluye la revisión
   `0005_telegram_pairing`.
3. Con autorización explícita, inspeccionar el webhook actual. Registrar o cambiar
   el webhook sólo mediante `scripts/telegram_webhook.py set --base-url ...` y
   sólo si apunta a `/telegram/webhook` del servicio no productivo.
4. Emitir una invitación de un uso y, desde la cuenta evaluadora, enviar
   `/pair <code>` en chat privado. Debe llegar sólo la respuesta fija de solicitud
   recibida: ninguna inferencia ni herramienta.
5. Listar la solicitud; guardar únicamente UUID, timestamps, actor y estados como
   evidencia. Aprobarla y enviar un mensaje nuevo: debe ser admitido.
6. Revocar la autorización y enviar otro mensaje nuevo: debe ser rechazado. No
   copiar el contenido de mensajes a la evidencia.
7. Revocar la invitación si aún estuviera activa, deshabilitar los dos flags de
   pairing tras la ventana y redeployar. Si se registró el webhook sólo para esta
   prueba, decidir explícitamente si se conserva o se elimina; no borrarlo de
   manera implícita.

## 5. Triage seguro

| Señal | Acción |
|---|---|
| `503 Telegram admission temporarily unavailable` | Tratar como fail-closed; revisar conectividad/health de PostgreSQL sin reenviar el update. |
| `/pair` en grupo queda rechazado | Comportamiento esperado; pedir al evaluador que use chat privado. |
| `/pair` devuelve respuesta no enumerante | Comportamiento esperado para código inválido, expirado, agotado o revocado; no revelar cuál fue el motivo. |
| Usuario aprobado sigue rechazado | Revisar la solicitud/autorización y el `telegram_user_id` observado; nunca añadir el usuario temporalmente a la allowlist para saltar pairing. |
| Revocación no parece aplicar | Verificar que el mensaje es un update nuevo y que no se trata de un duplicado; no reiniciar como solución. |
