# AncoraMind — Guía de Arranque Rápido

> **ngrok no se usa en este proyecto** desde el incidente de seguridad de red
> del 2026-09-07 (BL-18) — no reabrir ese canal sin autorización explícita.
> El flujo vigente para probar con Telegram real es GitHub → Railway (dominio
> HTTPS estable). Esta guía es el día a día una vez el servicio Railway ya
> existe. Para crearlo por primera vez: ver
> [deployment-railway.md](deployment-railway.md).

## Arranque día a día (Railway)

El dominio de Railway es estable entre deployments y el webhook de Telegram
**se registra una sola vez** contra él
(`deployment-railway.md` §5) — no hay que repetirlo en cada sesión de trabajo,
solo si cambia el dominio, el token o el secret.

### 1. Subir el cambio

```bash
git push origin <tu-rama>
# o, tras aprobar la Pull Request:
git push origin main
```

Railway observa `main` (o la rama configurada) y despliega automáticamente
tras un CI verde (`deployment-railway.md` §6). Comprueba el estado del
deployment en el dashboard de Railway o con:

```bash
curl -s https://<service>.up.railway.app/health
```

### 2. Probar en Telegram

Con el deployment en estado saludable, el bot ya está escuchando en el
dominio Railway — no hace falta ningún paso adicional de túnel o webhook.
Escribe directamente al bot.

### 3. Si el webhook no está registrado (servicio nuevo o rotación de secretos)

Solo en ese caso, desde una terminal local con `.env` apuntando al mismo
`TELEGRAM_TOKEN`/`TELEGRAM_WEBHOOK_SECRET_TOKEN` que Railway:

```bash
python scripts/telegram_webhook.py set --base-url https://<service>.up.railway.app
python scripts/telegram_webhook.py status
```

Detalle completo en [deployment-railway.md](deployment-railway.md) §5.

---

## Desarrollo local sin Telegram real

Para iterar código sin desplegar ni tocar el bot (tests, lint, probar la app
arranca sin errores):

```bash
python -m src.main
```

Localmente requiere `.env` con `TELEGRAM_TOKEN` (la app registra las rutas de
Agno aunque no reciba updates reales sin un webhook público). Sin
`ANCORA_DATABASE_URL` arranca igual pero sin domain tools (degradación
graceful) — ver [development.md](development.md).

### Alternativa: PostgreSQL y storage locales

Si `.env` apunta a `localhost` y usa `DOCUMENT_STORAGE_BACKEND=local`:

```bash
docker compose up postgres -d
```

Al terminar:

```bash
docker compose down
```

Antes de la primera ejecución, o tras una migración nueva, aplicar
`migrations/init.sql` (bootstrap fresh) o `alembic upgrade head`.

---

## Verificación rápida (contra Railway)

**Webhook:**
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
```

**Tablas del dominio (local, 8 filas esperadas):**
```bash
# Git Bash
docker compose exec postgres psql -U ancora -d ancoramind -c "\dt ancora.*"

# PowerShell
docker compose exec postgres psql -U ancora -d ancoramind -c '\dt ancora.*'
```

Probar en Telegram:
- `"Hola"` → responde identificándose
- `"¿Qué hora es?"` → usa `get_current_datetime`
- `"¿Qué plaza de garaje tengo?"` → recupera notas desde PostgreSQL

---

## Troubleshooting express

| Síntoma | Solución |
|---|---|
| Error 404 de OpenRouter | El modelo caducó — cambiar `LLM_MODEL` en `.env` |
| Bot no responde | ¿deployment Railway saludable (`/health`)? ¿webhook registrado contra el dominio actual? |
| Error de columna/tabla inexistente al proponer una acción | Faltan migraciones — `alembic upgrade head` contra `ANCORA_DATABASE_URL` |
| `ECONNREFUSED 5432` con BD local | `docker compose up postgres -d` |
| Error de conexión Supabase | Comprobar que el proyecto está activo y que ambas URLs usan el Session pooler (puerto 5432) |
| `No module named psycopg2` | `AGNO_DATABASE_URL` debe empezar por `postgresql+psycopg://` |
| Storage Supabase falla | `SUPABASE_URL` debe ser `https://<ref>.supabase.co`, no `<ref>.storage.supabase.co` |
| Webhook 404 Not Found | Token mal cargado al registrar el webhook — repetir con el `.env` correcto |
| `pending_update_count > 0` | Mensajes encolados; llegan en el siguiente deployment saludable |
| Solo 1 tool en logs | Falta `ANCORA_DATABASE_URL` en Railway o PostgreSQL/Supabase caído |

---

## Script automatizado

```powershell
.\scripts\run-e2e.ps1 -Check   # solo verificar prerrequisitos
.\scripts\run-e2e.ps1 -PublicBaseUrl https://<service>.up.railway.app
.\scripts\run-e2e.ps1 -Reset -PublicBaseUrl https://<service>.up.railway.app
```

El script PowerShell soporta además un flujo local con ngrok como alternativa
histórica (`sin -PublicBaseUrl`) — **no usar esa rama en esta red** sin
autorización explícita (BL-18). Usa siempre `-PublicBaseUrl` apuntando al
dominio Railway.
