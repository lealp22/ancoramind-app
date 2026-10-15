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
| Unit tests | ✅ 123 passing |

## Seguridad

- Las tablas `ancora` no tienen grants para `anon`, `authenticated` ni
  `service_role`; no están expuestas a esos roles mediante las API de datos.
- `public.rls_auto_enable()` era `SECURITY DEFINER` ejecutable por dichos roles.
  Se aplicó la migración `secure_rls_auto_enable_function` para revocar esos
  permisos; Supabase Security Advisor quedó sin avisos.
- Si en el futuro se expone el schema `ancora` o se conceden grants, deberá
  habilitarse RLS con políticas antes de exponerlo.


### RLS hardening — incremento 1 desplegado (2026-10-15)

- Inspección real previa: 24 tablas `ancora` sin RLS ni policies. `anon`,
  `authenticated` y `service_role` ya carecían de `USAGE` sobre el schema y de
  grants de tabla. El runtime SQL usa `postgres`, con `BYPASSRLS`.
- `SUPABASE_SERVICE_ROLE_KEY` sí es necesaria: `SupabaseDocumentStorage` la usa
  para el bucket privado `ancora-documents` (`storage.*`). No se revoca ni se
  modifica. Tampoco se le conceden permisos sobre `ancora`.
- Revisión local `0015_ancora_rls_hardening`: RLS en todas las tablas actuales,
  cero policies (default deny), revocación explícita actual y futura para
  `PUBLIC`, `anon` y `authenticated`. Downgrade deshabilita RLS pero no restaura
  privilegios amplios que esta revisión no necesita conceder.
- Esto protege frente a exposición accidental por Data API; no es aislamiento
  RLS efectivo frente a las credenciales backend privilegiadas. Ese segundo
  incremento requiere rol `NOBYPASSRLS`, propagación transaccional del
  `UserContext` y separación de runtime/worker/admission/admin.
- Verificación local: 1423 unitarias y 159 integraciones superadas; una prueba
  STT live omitida por diseño. Las 4 pruebas de migración PostgreSQL superan
  fresh install, upgrade/downgrade e idempotencia. Ruff global y `mypy src/`
  limpios; head `0015_ancora_rls_hardening`.
- Verificación productiva de solo lectura: `ancora.alembic_version` apunta a
  `0015_ancora_rls_hardening`; las 24 tablas tienen RLS habilitado, existen cero
  policies y no hay grants de tabla para `PUBLIC`, `anon`, `authenticated` ni
  `service_role`. Los tres roles Supabase tampoco tienen `USAGE` del schema.
- Security Advisor informa los 24 avisos `rls_enabled_no_policy` esperados por
  el diseño default-deny. Mantiene dos warnings independientes de este rollout:
  `voice_preparation_parent_guard` sin `search_path` fijado y `vector` instalado
  en `public`; requieren triage separado, no invalidan el hardening aplicado.

### Función de voz con `search_path` seguro — incremento local (2026-10-15)

- Supabase lint `0011_function_search_path_mutable` recomienda
  `search_path=''`; la función ya cualifica su única tabla como
  `ancora.voice_preparations`, por lo que el cambio no altera la resolución.
- Nueva revisión `0016_voice_guard_search_path`: `ALTER FUNCTION ... SET
  search_path=''`; downgrade simétrico con `RESET search_path`. `init.sql`
  define el mismo ajuste desde fresh bootstrap.
- Evidencia PostgreSQL real: `tests/integration/test_migrations.py` **4 passed**.
  Se comprueba en `pg_proc.proconfig` que head contiene `search_path=""`, el
  downgrade a 0015 lo retira y el upgrade lo restaura. Dos unit guards nuevos,
  Ruff y `mypy src/` limpios.
- Suite unitaria global: **1423 passed**. La integración global reprodujo dos
  veces el timing STT preexistente de 50 ms ya documentado en specs/034: 158
  pasan, una STT live se omite y el caso timeout falla antes de alcanzar el mock.
  El mismo test focal pasa **4/4**; no se atribuye causalidad a esta migración ni
  se modifica voz dentro de este incremento.
- Pendiente rollout productivo bajo el gate manual del mismo SHA y reconsulta de
  Security Advisor. Hasta entonces, producción continúa en head 0015 y el
  warning sigue abierto. El warning `extension_in_public` de `vector` no forma
  parte de este incremento.

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
- 123 tests passing.

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