# AncoraMind — Guía de Arranque Rápido

> Para arrancar después de la primera configuración (credenciales ya en `.env`).
> Primera vez: ver [docs/deployment-e2e.md](deployment-e2e.md).

## Arranque con Supabase (3 pasos)

Si `.env` usa el session pooler de Supabase y
`DOCUMENT_STORAGE_BACKEND=supabase`, **no hay que arrancar Docker**.

> Si acabas de cambiar de Docker local a Supabase, abre una terminal nueva o
> vuelve a cargar `.env` antes de ejecutar la app. Las variables ya exportadas
> en el terminal tienen prioridad sobre el fichero `.env`.

### 1. ngrok (ventana nueva, dejar abierta)

**Git Bash:**
```bash
~/tools/ngrok.exe http 7777
```

**PowerShell:**
```powershell
& "$HOME\tools\ngrok.exe" http 7777
```

Copiar la URL HTTPS que muestra (ej: `https://xxx.ngrok-free.dev`)

### 2. Registrar webhook (⚠️ cambia cada vez que reinicies ngrok)

**Git Bash:**
```bash
source <(grep -v '^#' .env | sed 's/^/export /')
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=URL_DE_NGROK/telegram/webhook"
```

**PowerShell:**
```powershell
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#].*?)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}
$url = "$env:TELEGRAM_TOKEN/setWebhook?url=URL_DE_NGROK/telegram/webhook"
Invoke-RestMethod "https://api.telegram.org/bot$url"
```

Debe responder: `{"ok":true,...,"description":"Webhook was set"}`

### 3. Lanzar AncoraMind

**Git Bash / PowerShell (igual):**
```bash
python -m src.main
```

---

## Parada

1. `Ctrl+C` en la consola de AncoraMind
2. `Ctrl+C` en la ventana de ngrok

Supabase es gestionado: no hay ningún contenedor que detener.

---

## Alternativa: PostgreSQL y storage locales

Si `.env` apunta a `localhost` y usa `DOCUMENT_STORAGE_BACKEND=local`, antes
del paso 1 hay que arrancar PostgreSQL:

```bash
docker compose up postgres -d
```

Al terminar:

```bash
docker compose down
```

---

## Verificación rápida

**Webhook (Git Bash / PowerShell):**
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
```

**Tablas del dominio local (esperado: 8 filas):**
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
| Bot no responde | ¿ngrok corriendo? ¿webhook con URL actual? ¿AncoraMind corriendo? |
| `ECONNREFUSED 5432` con BD local | `docker compose up postgres -d` |
| Error de conexión Supabase | Comprobar que el proyecto está activo y que ambas URLs usan el Session pooler (puerto 5432) |
| `No module named psycopg2` | `AGNO_DATABASE_URL` debe empezar por `postgresql+psycopg://` |
| Storage Supabase falla | `SUPABASE_URL` debe ser `https://<ref>.supabase.co`, no `<ref>.storage.supabase.co` |
| Webhook 404 Not Found | Token mal cargado — repetir la carga de `.env` del paso 2 |
| `pending_update_count > 0` | Mensajes encolados; llegan al arrancar AncoraMind |
| Solo 1 tool en logs | Falta `ANCORA_DATABASE_URL` en `.env` o PostgreSQL caído |

---

## Script automatizado

El script detecta si la BD es local o Supabase. Solo arranca Docker y aplica
`migrations/init.sql` en modo local:

```bash
bash scripts/run-e2e.sh --check   # solo verificar prerrequisitos
bash scripts/run-e2e.sh           # secuencia completa
bash scripts/run-e2e.sh --reset   # resetear webhook antes de registrar
```