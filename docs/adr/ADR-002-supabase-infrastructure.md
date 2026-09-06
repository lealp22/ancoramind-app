# ADR-002 — Supabase como infraestructura gestionada

> **Status:** Accepted (decisión del propietario 2026-09-05, implementada 2026-09-06)
> **Contexto:** BL-14. Este ADR documenta la decisión y sus límites.

---

## Contexto

Hasta ahora la infraestructura era 100% local: PostgreSQL en Docker y
documentos en filesystem. Eso es correcto para desarrollo, pero:

- no hay persistencia fuera del portátil (los datos viven en un volumen Docker);
- no hay camino natural a despliegue (Railway/VPS tendrían que gestionar BD);
- el propietario decidió explícitamente trabajar con Supabase desde ya.

## Decisión

Usar **Supabase** como proveedor de infraestructura gestionada:

1. **Base de datos** — el proyecto Supabase `ancoramind_project`
   (`asnsqdbsogpxqpweyxui`, eu-west-1) aloja PostgreSQL 17. Las dos URLs
   existentes (`agno_database_url` psycopg, `ancora_database_url` asyncpg)
   apuntan al **session pooler** de Supabase (IPv4, modo sesión).
2. **Storage de ficheros** — bucket privado `ancora-documents` (límite 20 MB)
   accedido con la Service Role Key **solo desde el servidor**.
3. **pgvector** — la extensión `vector` 0.8.2 está **disponible pero NO
   instalada**. Su activación se decide cuando BL-6 aporte contenido real de
   documentos; hasta entonces solo diseño.

## Consecuencias

### Lo que NO cambia (fronteras intactas)

- **§2.7 Separación de DBs** — Supabase es solo el *host* PostgreSQL. Sigue
  habiendo dos conexiones independientes (`agno_runtime` vs schema `ancora`)
  aunque físicamente compartan instancia. AncoraMind Core no toca tablas
  internas de Agno.
- **`DocumentStorage` Protocol** — Supabase es una implementación más
  (`SupabaseDocumentStorage`) junto a `LocalFileSystemStorage`. El dominio no
  sabe qué backend hay debajo.
- **Migraciones** — el schema del dominio sigue siendo propiedad de
  AncoraMind (`migrations/init.sql` como fuente; en Supabase aplicado como
  migración baseline `ancora_baseline`).

### Detalles técnicos de conexión

| Conexión | Driver | URL |
|---|---|---|
| Agno runtime | psycopg v3 (sync) | `postgresql+psycopg://postgres.<ref>:PWD@aws-1-eu-west-1.pooler.supabase.com:5432/postgres` |
| AncoraMind Core | asyncpg (async) | `postgresql+asyncpg://postgres.<ref>:PWD@aws-1-eu-west-1.pooler.supabase.com:5432/postgres` |

- **Session pooler (puerto 5432), no transaction pooler (6543):** asyncpg usa
  prepared statements, que el modo transacción de PgBouncer no garantiza.
- **Pooler, no conexión directa:** la conexión directa
  (`db.<ref>.supabase.co:5432`) es solo IPv6 en el free tier; el pooler
  funciona con IPv4.
- Las credenciales viven en `.env`, nunca en Git (§69 del brief).
- `create_db()` fija explícitamente `db_schema="agno_runtime"`. Sin este
  parámetro Agno crearía sus tablas en `public`, violando la separación
  obligatoria runtime/dominio.

### Limitaciones aceptadas

- **Free tier:** el proyecto se pausa tras ~1 semana de inactividad. Si la
  app está en uso no ocurre; si se pausa, se restaura desde el dashboard.
- **Storage keys existentes:** los documentos ya guardados en filesystem local
  no se migran automáticamente. Un `storage_key` solo es válido para el
  backend con el que se almacenó. Para el POC se acepta; una migración de
  datos futura podría copiar objetos entre buckets.
- **Work in progress del Pro plan:** branches de Supabase (dev/prod) quedan
  fuera de alcance hasta que se pague el plan o surja necesidad.
- Las tablas `ancora` no tienen grants para `anon`, `authenticated` ni
  `service_role`; la app accede por conexión PostgreSQL como `postgres`. Si
  en el futuro se expone `ancora` mediante PostgREST o se conceden grants,
  habrá que habilitar RLS y definir políticas antes de hacerlo.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Seguir con Docker local | Sin persistencia fuera del portátil; no da camino a despliegue |
| Railway Postgres | Menos integrado (storage aparte); Supabase da BD + storage + dashboard en uno |
| Neon | Solo BD; el storage habría que montarlo aparte (S3/R2) |
| Supabase Pro + branches | Coste prematuro para un POC |

## Re-evaluación

Reabrir esta decisión si: (a) el pausado del free tier resulta molesto en uso
real → upgrade a Pro; (b) aparecen requisitos de aislamiento dev/prod →
branches o segunda instancia; (c) el volumen de storage hace inviable el
free tier → R2/S3 detrás del mismo Protocol.
