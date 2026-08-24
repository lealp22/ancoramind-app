# AncoraMind — Guía de Despliegue E2E

> **Objetivo:** Lanzar AncoraMind completo con Telegram + PostgreSQL y validar
> todos los milestones (M1–M5) de extremo a extremo.

---

## 0. Requisitos previos

| Requisito | Verificación |
|---|---|
| Python 3.12+ | `python --version` |
| Git | `git --version` |
| ngrok | [descargar](https://ngrok.com/download) + cuenta gratuita |
| Cuenta de Telegram | [telegram.org](https://telegram.org) |
| API key de OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Docker Desktop | [docker.com](https://www.docker.com/products/docker-desktop/) (opcional, para PostgreSQL) |
| PostgreSQL 16+ | Si no usas Docker: [postgresql.org](https://www.postgresql.org/download/) |

---

## 1. Clonar e instalar

```bash
cd c:\Users\0020572\Documents\Formación\TheBridge
cd ancoramind-core

# Activar entorno virtual
.\.venv\Scripts\Activate.ps1

# Asegurar dependencias actualizadas
pip install -e ".[dev]"

# Verificar que todo importa
python -c "from src.main import create_app; print('OK')"
```

---

## 2. Crear el bot de Telegram

1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot`
3. Elige nombre: `AncoraMind POC`
4. Elige username: `ancoramind_poc_bot` (debe terminar en `bot`)
5. **Copia el token** — algo como `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
6. Envía `/setprivacy` → selecciona tu bot → **Disable** (necesitamos ver todos los mensajes)

---

## 3. Configurar PostgreSQL

### Opción A: Docker (recomendado)

```bash
# Iniciar PostgreSQL
docker compose up postgres -d

# Esperar a que esté listo
docker compose logs postgres | grep "database system is ready"

# Aplicar migraciones
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations\init.sql

# Verificar esquemas
docker compose exec postgres psql -U ancora -d ancoramind -c "\dt ancora.*"
```

Deberías ver:

```
         List of relations
 Schema |        Name         | Type  | Owner
--------+---------------------+-------+--------
 ancora | action_proposals    | table | ancora
 ancora | ai_extractions      | table | ancora
 ancora | calendar_events     | table | ancora
 ancora | documents           | table | ancora
 ancora | notes               | table | ancora
 ancora | reminders           | table | ancora
 ancora | vehicle_maintenance | table | ancora
 ancora | vehicles            | table | ancora
```

### Opción B: PostgreSQL local

```bash
psql -U postgres -c "CREATE USER ancora WITH PASSWORD 'ancora';"
psql -U postgres -c "CREATE DATABASE ancoramind OWNER ancora;"
psql -U ancora -d ancoramind -f migrations\init.sql
```

---

## 4. Configurar variables de entorno

```bash
copy .env.example .env
```

Editar `.env` con tus valores reales:

```env
# ⚠️ CAMBIAR — tu API key de OpenAI
OPENAI_API_KEY=sk-tu-api-key-real-aqui

# ⚠️ CAMBIAR — el token de @BotFather
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Desarrollo
APP_ENV=development

# PostgreSQL — si usas Docker con los valores por defecto
ANCORA_DATABASE_URL=postgresql+asyncpg://ancora:ancora@localhost:5432/ancoramind

# Opcional: PostgreSQL para Agno también
# AGNO_DATABASE_URL=postgresql+psycopg://ancora:ancora@localhost:5432/ancoramind

# Opcional: restringir usuarios (IDs de Telegram)
# ALLOWED_TELEGRAM_USER_IDS=123456789,987654321

# Documentos
DOCUMENT_STORAGE_PATH=./data/documents
```

---

## 5. Iniciar ngrok

```bash
# En una terminal aparte
ngrok http 7777
```

Verás algo como:

```
Forwarding  https://abc123-def.ngrok-free.app -> http://localhost:7777
```

**Copia la URL HTTPS** y añádela al `.env`:

```env
NGROK_URL=https://abc123-def.ngrok-free.app
```

---

## 6. Registrar el webhook en Telegram

```powershell
# PowerShell: carga las variables del .env
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#].*?)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}

# Registrar webhook
$url = "$env:NGROK_URL/telegram/webhook"
$token = $env:TELEGRAM_TOKEN
Invoke-RestMethod "https://api.telegram.org/bot$token/setWebhook?url=$url"

# Verificar
Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo"
```

Salida esperada:

```json
{
  "ok": true,
  "result": {
    "url": "https://abc123-def.ngrok-free.app/telegram/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

## 7. Lanzar AncoraMind

```bash
python -m src.main
```

Salida esperada:

```
[INFO] src.main: Starting AncoraMind — env: development
[INFO] src.main: Domain database initialized
[INFO] src.main: LLM model: gpt-4o
[INFO] src.main: Loaded 4 instruction blocks
[INFO] src.main: Note tools registered: remember_note, search_notes
[INFO] src.main: Document tools registered: search_documents, get_document, analyze_document
[INFO] src.main: Vehicle tools registered: find_vehicle, get_vehicle_summary, ...
[INFO] src.main: Reminder + Calendar tools registered: ...
[INFO] src.main: Total tools: 17
[INFO] src.main: AgentOS app created — webhook: /telegram/webhook
```

---

## 8. Verificación E2E — Acceptance Test (§57 del brief)

Abre tu bot en Telegram y envía estos mensajes. **Usa el orden indicado**
porque algunos pasos dependen de datos creados en pasos anteriores.

### 8.1 — Conexión básica (M1)

```
Tú: Hola
```
Esperado: saludo en español, identificándose como tu asistente personal.

```
Tú: ¿Cómo te llamas?
```
Esperado: "Me llamo AncoraMind."

```
Tú: ¿Qué hora es?
```
Esperado: usa la tool `get_current_datetime` y responde la hora actual.

### 8.2 — Memoria canónica (M2)

```
Tú: Recuerda que la plaza del garaje es la 42
```
Esperado: `remember_note` → "Nota guardada (id: ...)"

```
Tú: ¿Qué plaza de garaje tengo?
```
Esperado: `search_notes` → "Encontré 1 nota sobre 'plaza': [2026-08-24] La plaza del garaje es la 42"

```
Tú: Recuerda que el código de la puerta es 7743
Tú: ¿Qué me has apuntado?
```
Esperado: `search_notes` sin query → lista las 2 notas recientes.

### 8.3 — Documentos (M3)

```
Tú: [envía una imagen cualquiera o un PDF]
```
Esperado: AncoraMind responde con:
- "📄 [filename] recibido y archivado"
- ID del documento
- Tipo detectado
- Resumen (si aplica)
- Acciones sugeridas

```
Tú: ¿Qué documentos tengo?
```
Esperado: `search_documents` → lista documentos con fecha, tamaño, tipo.

### 8.4 — Vehículos (M4)

> ⚠️ Para testing E2E, inserta un vehículo directamente en PostgreSQL
> (la tool dedicada de creación se añadirá en iteración futura):

```sql
INSERT INTO ancora.vehicles (user_id, make, model, year, registration, nickname)
VALUES ('TU_TELEGRAM_USER_ID', 'Ford', 'Mondeo', 2020, '1234ABC', 'el coche');
```

Donde `TU_TELEGRAM_USER_ID` es tu ID numérico de Telegram
(visible en logs como session_id: `tg:ancoramind:123456789`).

```
Tú: ¿Qué coches tengo?
```
Esperado: `find_vehicle` → lista el Ford Mondeo.

```
Tú: Dime el resumen del Ford
```
Esperado: `get_vehicle_summary` → marca, modelo, año, matrícula, total intervenciones, último mantenimiento.

```
Tú: Registra un cambio de aceite del Ford del 12 de agosto de 2026,
    124.350 km, en Taller Martínez, coste 286,40 €
```
Esperado: `propose_vehicle_maintenance` → propuesta con todos los datos + "¿Confirmas el registro?"

```
Tú: Sí
```
Esperado: `execute_vehicle_maintenance` → "✅ Mantenimiento registrado" con fecha, importe, ID.

```
Tú: ¿Cuándo fue la última revisión del coche?
```
Esperado: `get_vehicle_summary` → muestra la intervención recién registrada.
**Este dato viene de PostgreSQL, no de memoria conversacional.**

### 8.5 — Recordatorios y Calendario (M5)

```
Tú: Recuérdame llamar al dentista el próximo jueves a las 17:30
```
Esperado: `propose_reminder` → propuesta + "¿Confirmas la creación?"

```
Tú: Sí
```
Esperado: `execute_reminder` → "✅ Recordatorio creado: Llamar dentista"

```
Tú: Tengo dentista el jueves 28 de agosto a las 17:30
```
Esperado: `propose_calendar_event` → propuesta + "¿Confirmas añadir este evento?"

```
Tú: Sí
```
Esperado: `execute_calendar_event` → "✅ Evento añadido al calendario"

```
Tú: ¿Qué recordatorios tengo?
```
Esperado: `list_reminders` → muestra el recordatorio del dentista.

```
Tú: ¿Qué tengo el jueves?
```
Esperado: `check_calendar` → muestra el evento del dentista.

### 8.6 — Verificación de procedencia

```sql
SELECT
    m.date,
    m.description,
    m.source_document_id,
    d.original_filename
FROM ancora.vehicle_maintenance m
LEFT JOIN ancora.documents d ON m.source_document_id = d.id
WHERE m.user_id = 'TU_TELEGRAM_USER_ID'
ORDER BY m.date DESC;
```
---

## 9. Troubleshooting

### "Token must contain a colon"
Tu `TELEGRAM_TOKEN` en `.env` no es válido. Verifica que copiaste el token completo de @BotFather (formato `123456789:ABCdef...`).

### "connect ECONNREFUSED 127.0.0.1:5432"
PostgreSQL no está corriendo:
```bash
docker compose up postgres -d
```

### El webhook no recibe mensajes
```bash
curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getWebhookInfo"
```
Si `pending_update_count > 0` pero no llegan, verifica que ngrok esté corriendo y que `NGROK_URL` coincida con la URL de ngrok.

### ngrok muestra error 502
AncoraMind no está corriendo. Lanza `python -m src.main` en otra terminal.

### Las tools de dominio no aparecen (solo 1 tool)
`ANCORA_DATABASE_URL` no está configurada o PostgreSQL no es accesible. Verifica los logs: "ANCORA_DATABASE_URL not set — domain tools skipped".

### "relation ancora.notes does not exist"
No aplicaste las migraciones:
```bash
docker compose exec -T postgres psql -U ancora -d ancoramind < migrations\init.sql
```

---

## 10. Siguientes pasos

- [ ] Usar el asistente durante varios días con documentos reales
- [ ] Evaluar la calidad de las extracciones IA
- [ ] Ajustar prompts según comportamiento observado
- [ ] Ejecutar regresiones (`pytest tests/unit/`)
- [ ] M6+: añadir `pgvector` para búsqueda semántica si se justifica
- [ ] M6+: background worker para disparar recordatorios (AgentOS Scheduler / cron)