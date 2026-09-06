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
| Unit tests | ✅ 101 passing |

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

## E2E pendiente (T7)

- [x] Configurar `AGNO_DATABASE_URL` con Session pooler Supabase
- [x] Configurar `ANCORA_DATABASE_URL` con Session pooler Supabase
- [ ] Telegram: guardar y recuperar una nota; confirmar fila en `ancora.notes`
- [ ] Telegram: subir documento; confirmar objeto en Storage y fila en
      `ancora.documents`
- [ ] Telegram: propose/execute de vehículo; confirmar propuesta ejecutada y
      fila en `ancora.vehicles`

El valor de `SUPABASE_SERVICE_ROLE_KEY` nunca debe copiarse en este documento
ni en logs/commits.