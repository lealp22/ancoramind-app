# AncoraMind — Runbook del dashboard de administración (BL-43 / spec 027)

> **Alcance:** cómo arrancar y acceder a `GET /admin/dashboard` (invitaciones,
> runtime-config, salud, enlaces). El dashboard está apagado por defecto y
> convive con `scripts/runtime_config.py`/`scripts/telegram_pairing.py` sin
> reemplazarlos.

**Estado operativo acordado 2026-10-17:** panel y pairing permanecen habilitados
en Railway tras las pruebas. El default OFF no implica apagarlos al cerrar un
E2E; cualquier desactivación global requiere acuerdo explícito. Revocar un
evaluador no exige quitar el panel ni las APIs al operador.

## 1. Invariantes operativos

- **Sólo detrás de HTTPS.** El token viaja como `Authorization: Bearer` sin
  cifrado propio — la confidencialidad en tránsito depende por completo de
  que el dominio sea HTTPS (como ya es el caso en Railway). Nunca lo expongas
  en un túnel o puerto HTTP sin TLS fuera de `APP_ENV=development` en
  `localhost`.
- **`ADMIN_DASHBOARD_TOKEN` es un secreto propio**, distinto de
  `RUNTIME_CONFIG_ADMIN_TOKEN`. El dashboard vive en un navegador — más
  expuesto que una terminal — así que `RUNTIME_CONFIG_ADMIN_TOKEN` nunca debe
  pegarse en su campo de login ni guardarse en ese navegador.
- El token sólo se guarda en `sessionStorage` del navegador (nunca
  `localStorage`): se borra al cerrar la pestaña y, además, tras 30 minutos
  sin actividad.
- Las mutaciones (crear invitación, crear revisión, activar, rollback) exigen
  actor y motivo igual que los CLI existentes. Usa un actor identificable
  (`operator@example.com`); nunca nombres genéricos.
- Un cambio hecho desde el dashboard y uno hecho desde el CLI son
  equivalentes: ambos operan sobre la misma instancia de `RuntimeConfigManager`
  / el mismo `TelegramPairingService`. No hay un "modo dashboard" separado.

## 2. Flags y secretos

```env
ADMIN_DASHBOARD_ENABLED=true
ADMIN_DASHBOARD_TOKEN=<bearer-aleatorio-distinto-de-RUNTIME_CONFIG_ADMIN_TOKEN>

# Prerrequisitos ya compartidos con el resto de /admin/*:
ANCORA_DATABASE_URL=<url-postgres>
TELEGRAM_PAIRING_CODE_PEPPER=<secreto-hmac-independiente>

# Opcionales — enlaces mostrados en el panel "Enlaces"; vacío = fila oculta.
ADMIN_LINK_GRAFANA_URL=
ADMIN_LINK_RAILWAY_URL=
ADMIN_LINK_SUPABASE_URL=
ADMIN_LINK_OPENROUTER_URL=
ADMIN_LINK_LITELLM_URL=
```

Sin `ANCORA_DATABASE_URL`, `ADMIN_DASHBOARD_TOKEN` o
`TELEGRAM_PAIRING_CODE_PEPPER` la app falla al arrancar
(`ValueError: ADMIN_DASHBOARD_ENABLED requires: ...`) en vez de servir el
dashboard sin esas garantías.

**Rotación:** cambiar `ADMIN_DASHBOARD_TOKEN` en Railway invalida todas las
sesiones abiertas del dashboard al momento (cada pestaña deberá volver a
pedir el token nuevo); no afecta a `RUNTIME_CONFIG_ADMIN_TOKEN` ni a los CLI.

## 3. Arrancar y acceder

Para **preparación local de onboarding sin arranque operativo**, usar
`docs/preflight-onboarding-admin.md`: pruebas ASGI/DB dedicada, sin Telegram,
LLM ni `.env` de producción. El arranque siguiente corresponde a un entorno
de desarrollo previamente aislado y configurado, no a reutilizar secretos/BD
productivos para probar el panel.

**Local (desarrollo):**

```powershell
.venv\Scripts\Activate.ps1
# .env ya debe tener ADMIN_DASHBOARD_ENABLED=true + ADMIN_DASHBOARD_TOKEN + ANCORA_DATABASE_URL + TELEGRAM_PAIRING_CODE_PEPPER
python -m src.main
```

Abre `http://localhost:7777/admin/dashboard` (o el puerto de
`AGENT_OS_PORT`/`PORT`). Introduce el token y un actor identificable; la
sesión se mantiene mientras la pestaña siga abierta y con actividad.

**Railway (producción/staging):** configura las variables de §2 como
secretos del servicio, espera un deployment `SUCCESS`, y abre
`https://<servicio>.up.railway.app/admin/dashboard`. No lo abras nunca por un
dominio/puerto sin TLS.

## 4. Qué hace cada panel

La información se organiza en tres pestañas (también navegables con las flechas,
Inicio y Fin):

- **Resumen** — FinOps y calidad, hasta «Interacciones por estado», y una línea
  de salud por servicio: `app: 🟢healthy | database: 🟢healthy | gateway: 🔘disabled`.
  `🟠` indica degradación y `❔` estado desconocido. La línea no se parte; en
  pantallas pequeñas tiene desplazamiento horizontal. «Refrescar salud» actualiza
  tanto el resumen como el detalle de Administración con una sola consulta a
  `/health/readiness`. Un error muestra «Salud no disponible», no estados antiguos.
- **Propuestas** — tabla por tool, estado y modo de consentimiento. Comparte la
  ventana de 7/30/90 días con Resumen; cambiarla en cualquiera actualiza ambas
  vistas. Es de sólo lectura, no confirma ni ejecuta propuestas.
- **Administración** — invitaciones, runtime config, salud detallada y enlaces.

Cambiar de pestaña sólo cambia la vista: no hace peticiones ni mutaciones. Las
operaciones administrativas y su autenticación permanecen como antes.

### Gráficos de Resumen

- **Coste por día:** columnas de altura proporcional al coste, fechas de izquierda
  a derecha y altura fija incluso con 90 días. Se muestran hasta tres etiquetas
  de fecha; cursor/foco y «Ver importes por día» permiten leer todos los valores.
  Sólo se dibujan días UTC con registros; los huecos se conservan sin inventar
  días con coste cero. Un registro de coste cero se marca en la base.
- **Origen del coste:** anillo por importe USD (no por número de llamadas), con
  leyenda, porcentajes y tabla. Es la fuente del coste registrado (`cost_source`),
  no el proveedor/modelo. Sin gasto no hay reparto ni anillo ficticio.
- **Interacciones por estado:** anillo por cantidad, con leyenda, porcentajes y
  tabla; incluye rechazadas/ignoradas aunque no ejecutaran el Agent.
- **Resultados de propuestas:** tres barras independientes 0–100 % para ejecutadas,
  descartadas y caducadas, con numerador y total resuelto. Denominador = suma de
  esos tres estados, no pendientes/en curso. Incluye ejecutadas autoautorizadas;
  no mide aprobación humana ni establece calidad. Sin umbrales, alarmas ni colores
  de juicio. Sin propuestas resueltas se muestra ausencia de datos, no 0 %.

Todo se renderiza localmente con HTML/CSS y los agregados existentes, sin recursos
externos, inferencia ni peticiones adicionales. La paleta distingue categorías,
no severidades; las tablas/leyendas conservan valores exactos y acceso textual.

- **Invitaciones** — crea (`issue_invitation`) y lista (`list_invitations`)
  invitaciones de pairing (BL-24). El código generado se muestra **una sola
  vez**: cópialo y entrégalo por un canal privado aprobado antes de refrescar
  o cerrar sesión; no quedará recuperable después. La casilla "Auto-aprobar"
  concede acceso en el mismo paso en que la persona canjea el código
  (`/pair <código>`), sin que tengas que aprobar la solicitud después — útil
  si no vas a estar disponible, pero el código pasa a ser el único factor de
  confianza: combínalo con un "usos máximos" ajustado al número exacto de
  personas (ver `docs/runbooks-017-telegram-pairing.md` §1). El resto de
  operaciones de pairing (aprobar/rechazar solicitud, revocar
  invitación/autorización) sigue siendo exclusivo de
  `scripts/telegram_pairing.py` — este incremento no las añadió al dashboard.
- **Runtime config** — paridad completa con `scripts/runtime_config.py`:
  status, validar (pega el JSON completo en el `<textarea>`, igual que
  `--config archivo.json`), crear revisión, activar y rollback por número de
  revisión. Antes de activar o hacer rollback, refresca el status para
  confirmar `expected_current_revision` — el backend rechaza con 409 si la
  revisión activa cambió entre medias.
- **Salud** — refleja `GET /health/readiness` tal cual, sin autenticación
  adicional (ese endpoint ya es público y metadata-only).
- **Enlaces** — abre Grafana/Railway/Supabase/OpenRouter/LiteLLM Gateway en
  pestaña nueva. Supabase y LiteLLM Gateway muestran además el estado
  (`healthy`/`degraded`/…) que ya calcula `HealthRegistry` para `database` y
  `gateway`.

## 5. Triage seguro

| Señal | Acción |
|---|---|
| `GET /admin/dashboard` → 404 | `ADMIN_DASHBOARD_ENABLED` no está activo en ese servicio; no es un fallo, revisa las variables del entorno objetivo. |
| `401` en cualquier llamada `/admin/dashboard/api/*` | Token ausente/incorrecto, o se pegó `RUNTIME_CONFIG_ADMIN_TOKEN` por error — ambos son secretos distintos. |
| Sesión pide el token de nuevo sin que la cerraras | Han pasado 30 min sin actividad en la pestaña; es el comportamiento esperado, no un fallo. |
| `409` al activar/hacer rollback | La revisión activa cambió desde el último status (otra persona o el CLI la cambiaron); refresca el status y repite con el `expected_current_revision` correcto. |
| `503` en cualquier operación de runtime-config | Control plane de base de datos no disponible; tratar como fail-closed, revisar conectividad de PostgreSQL antes de reintentar. |
| Un enlace no aparece en el panel | Su `ADMIN_LINK_*_URL` está vacío; es intencional (fila oculta), no un error. |
