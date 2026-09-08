# Spec: 008 — Railway Deployment Automation

> **Backlog:** BL-18
> **Status:** implemented (repository preparation); infrastructure deployment pending
> **Target:** Desplegar AncoraMind fuera del equipo local mediante Railway, con
> CI/CD desde GitHub y webhook HTTPS estable para Telegram.

---

## Requirement

La validación Telegram quedó pausada por una alerta de red asociada a ngrok. El
servicio debe poder ejecutarse en Railway sin túneles desde el equipo local,
manteniendo Supabase como PostgreSQL canónico y Storage de documentos.

### Must Have

- Servicio HTTP compatible con Railway: escucha `PORT` y `0.0.0.0` fuera de
  desarrollo; `reload=False` en producción.
- Healthcheck `GET /health` configurado. AgentOS ya lo proporciona.
- Build reproducible desde el `Dockerfile` incluido en Git.
- `railway.json` versionado: Dockerfile, start command, healthcheck y restart
  policy.
- GitHub Actions en push/PR sobre `main`: lint de producción (`src/` + script
  de webhook) + unit tests.
- Documentación para activar Railway Auto Deploy + **Wait for CI**.
- Webhook Telegram registrado una sola vez contra un dominio HTTPS estable,
  protegido por `TELEGRAM_WEBHOOK_SECRET_TOKEN`.
- Script sin secretos en salida para `set`, `status` y `delete` del webhook.

### Should Have

- Configuración de Railway como código, no solo dashboard.
- Dominio Railway inicial y dominio propio opcional.
- Rollback y healthcheck documentados.
- Estrategia de staging futura con segundo bot de Telegram.

### Won't Have (esta spec)

- Crear un proyecto Railway, cobrar un plan o desplegar la aplicación.
- Migrar PostgreSQL/Storage desde Supabase a Railway.
- Crear staging o PR environments activos: compartir un bot no es seguro porque
  Telegram solo permite un webhook por token.
- Ejecutar migraciones DDL desde Railway: el baseline Supabase ya está aplicado.

---

## Design

### Runtime

`resolve_server_config()` resuelve el servidor de forma determinista:

| Entorno | Host default | Puerto | Reload |
|---|---|---|---|
| `development` | `localhost` | `7777` | sí |
| otro (`production`) | `0.0.0.0` | `PORT` → `AGENT_OS_PORT` → `7777` | no |

Railway inyecta `PORT`; la app usa el mismo puerto que Railway consulta para
`/health`.

### Delivery pipeline

```text
feature branch → PR → GitHub Actions (ruff + pytest)
               → merge main → Railway Wait for CI
               → build Dockerfile → /health 2xx → tráfico nuevo
```

Si falla CI, Railway marca el deployment `SKIPPED`. Si falla `/health`, Railway
no activa la nueva versión; se puede hacer rollback a un deployment previo desde
el dashboard.

### Webhook

El script `scripts/telegram_webhook.py` se ejecuta localmente después del primer
deployment exitoso. Lee secretos de `.env` o variables del proceso, registra:

`https://<dominio>/telegram/webhook`

con `secret_token`. No registra el webhook en cada commit: el dominio Railway
es estable entre deployments.

### Entornos

Inicialmente: un solo entorno `production`, restringido por
`ALLOWED_TELEGRAM_USER_IDS`. Staging requerirá un segundo bot/token y, antes de
usar datos reales, su propia configuración Supabase.

---

## Success Criteria

1. `pytest tests/unit/` y el lint de los módulos productivos de despliegue
   (`main`, configuración del servidor, webhook y script) pasan en GitHub
   Actions. El lint global queda fuera por deuda previa registrada en BL-19.
2. `railway.json` define `GET /health` y política de reinicio.
3. Con `APP_ENV=production PORT=8080`, el servidor se configura para
   `0.0.0.0:8080` y sin autoreload.
4. El `Dockerfile` construye la aplicación desde una copia limpia del repo.
5. El script de webhook nunca imprime `TELEGRAM_TOKEN` ni el secret token.
6. Antes de activar el canal: proyecto Railway conectado a GitHub, rama `main`,
   Auto Deploy y Wait for CI habilitados, variables cargadas y dominio generado.