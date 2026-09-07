# Verification: 007 — Supabase Infrastructure

> Estado: **PASS parcial** — infraestructura, PostgreSQL, Storage, seguridad e
> integración directa verificados; E2E Telegram pendiente.

## Entorno

- Proyecto: `ancoramind_project` (`asnsqdbsogpxqpweyxui`)
- Región: `eu-west-1`
- PostgreSQL: 17
- Fecha: 2026-09-06

## Verificación automatizada

| Check | Resultado |
|---|---|
| Migración `ancora_baseline` | ✅ Aplicada |
| Tablas en schema `ancora` | ✅ 8, todas vacías al inicio |
| Bucket `ancora-documents` | ✅ Privado, límite 20 MB |
| pgvector | ✅ 0.8.2 disponible; no instalado (por diseño) |
| Storage real | ✅ upload → exists → download idéntico → delete |
| Storage backend local | ✅ Retrocompatibilidad conservada |
| Session pooler Agno (psycopg) | ✅ Conexión real |
| Session pooler Core (asyncpg) | ✅ Conexión real |
| Runtime schema configurado | ✅ `PostgresDb.db_schema == "agno_runtime"` |
| Repositorios reales | ✅ notes, vehicles, ActionProposal lifecycle |
| Aislamiento cross-user | ✅ Notes y vehicles no devuelven datos de otro user_id |
| Limpieza del smoke test | ✅ Sin datos temporales residuales |
| Unit tests | ✅ 108 passing |

## Seguridad

- Las tablas `ancora` no tienen grants para `anon`, `authenticated` ni
  `service_role`; no están expuestas a esos roles mediante las API de datos.
- `public.rls_auto_enable()` era `SECURITY DEFINER` ejecutable por dichos roles.
  Se aplicó la migración `secure_rls_auto_enable_function` para revocar esos
  permisos; Supabase Security Advisor quedó sin avisos.
- Si en el futuro se expone el schema `ancora` o se conceden grants, deberá
  habilitarse RLS con políticas antes de exponerlo.

## Correcciones descubiertas durante la verificación

1. `SUPABASE_URL` debe ser `https://<ref>.supabase.co`; el host
   `<ref>.storage.supabase.co` no es la URL base del cliente.
2. `AGNO_DATABASE_URL` debe usar `postgresql+psycopg://`; una URL
   `postgresql://` hace que SQLAlchemy intente cargar `psycopg2`.
3. Agno soporta `db_schema`, pero no se estaba configurando. Se fijó
   `db_schema="agno_runtime"` para mantener la separación obligatoria.
   La presencia física de sus tablas se comprueba al iniciar/persistir la
   primera sesión de Telegram, porque `create_app()` por sí solo no las crea.
4. Telegram entrega fotos como built-in `images` y documentos como `files`.
   `analyze_document` solo declaraba `files`, por lo que las fotos no llegaban
   a la tool. Ahora acepta ambos y obtiene bytes con `aget_content_bytes()`.
5. OpenRouter emitió tool calls vacías también en streaming. El filtro inicial
   solo cubría la ruta no-streaming; `SafeOpenRouter` filtra ahora después de
   que Agno consolide los deltas.
6. `find_vehicle` consultaba literalmente `6789-XYZ`, mientras la matrícula
   canónica era `6789XYZ`. Ahora reintenta con la referencia normalizada si la
   búsqueda literal no devuelve resultados.
7. El skill de documentos estaba comentado y además indicaba erróneamente que
   no se llamara `analyze_document`. Ahora está activo y exige una sola llamada
   cuando el mensaje contiene un adjunto. Cambio evaluable.

## E2E Telegram — iteración 1 (2026-09-07)

| Flujo | Resultado |
|---|---|
| Nota remember/search | ✅ PASS; fila verificada en `ancora.notes` |
| Imagen | ❌ `analyze_document` recibió `files=None`; sin fila ni objeto |
| Vehículo propose/execute | ✅ PASS; propuesta `executed` y Toyota persistido |
| Búsqueda `6789-XYZ` | ❌ No coincidió literalmente con `6789XYZ` |
| Segundo intento de búsqueda | ❌ La tool válida encontró el Toyota, pero una tool call vacía paralela dejó el run en `ERROR` |

Evidencia canónica:

- Nota `5f66ba35-a899-4831-a92b-3e6ef8a758ab` para `user_id=452022640`.
- Propuesta `bd6f276a-ef9f-4893-a1ee-eb9363caedd7`: `executed`.
- Toyota Corolla 2021 `4598c35e-a6c6-4988-a48b-a2b96947f55c`, matrícula
  `6789XYZ`.
- Las tablas internas de Agno se crearon en `agno_runtime`, no en `public`.

Después de los fixes se verificó directamente:

- `find_vehicle("6789-XYZ")` encuentra el Toyota canónico.
- Agno `Image` → `analyze_document` → Supabase Storage + `ancora.documents`.
- MIME `image/jpeg`, descarga con bytes idénticos y cleanup sin residuos.
- 108 tests passing.

## E2E pendiente (T7)

- [x] Configurar `AGNO_DATABASE_URL` con Session pooler Supabase
- [x] Configurar `ANCORA_DATABASE_URL` con Session pooler Supabase
- [x] Telegram: guardar y recuperar una nota; confirmar fila en `ancora.notes`
- [ ] Telegram: subir documento; confirmar objeto en Storage y fila en
      `ancora.documents` — **pausado por BL-18** (alternativa a ngrok)
- [ ] Telegram: repetir búsqueda del vehículo con matrícula formateada —
      **pausado por BL-18**

El valor de `SUPABASE_SERVICE_ROLE_KEY` nunca debe copiarse en este documento
ni en logs/commits.