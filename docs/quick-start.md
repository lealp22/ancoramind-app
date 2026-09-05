# AncoraMind — Guía de Arranque Rápido

> Para arrancar después de la primera configuración (credenciales ya en `.env`).
> Primera vez: ver [docs/deployment-e2e.md](deployment-e2e.md).

## Arranque (4 pasos)

### 1. PostgreSQL

**Git Bash / PowerShell (igual):**
```bash
cd /c/Users/0020572/Documents/Formación/TheBridge/ancoramind-core
docker compose up postgres -d
```

### 2. ngrok (ventana nueva, dejar abierta)

**Git Bash / PowerShell (igual):**
```bash
~/tools/ngrok http 7777
```

Copiar la URL HTTPS que muestra (ej: `https://xxx.ngrok-free.dev`)

### 3. Registrar webhook (⚠️ cambia cada vez que reinicies ngrok)

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

### 4. Lanzar AncoraMind

**Git Bash / PowerShell (igual):**
```bash
python -m src.main
```

---

## Parada

1. `Ctrl+C` en la consola de AncoraMind
2. `Ctrl+C` en la ventana de ngrok
3. `docker compose down`

---

## Verificación rápida

**Webhook (Git Bash / PowerShell):**
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
```

**Tablas del dominio (esperado: 8 filas):**
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
| ECONNREFUSED 5432 | `docker compose up postgres -d` |
| Webhook 404 Not Found | Token mal cargado — repetir la carga de `.env` del paso 3 |
| `pending_update_count > 0` | Mensajes encolados; llegan al arrancar AncoraMind |
| Solo 1 tool en logs | Falta `ANCORA_DATABASE_URL` en `.env` o PostgreSQL caído |

---

## Alternativa: script automatizado

Si prefieres bash script en vez de los pasos manuales:

```bash
bash scripts/run-e2e.sh --check   # solo verificar prerrequisitos
bash scripts/run-e2e.sh           # secuencia completa
bash scripts/run-e2e.sh --reset   # resetear webhook antes de registrar
```