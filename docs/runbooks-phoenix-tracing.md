# AncoraMind — Runbook de trazas de contenido enmascarado en Phoenix (BL-56 / specs/046)

> **Alcance:** configurar, activar, verificar, apagar y borrar por usuario la copia
> enmascarada de conversaciones en Phoenix. El flag está **apagado** y ninguna
> variable `PHOENIX_*` existe hoy en `ancoramind-app` (comprobado por nombre el
> 2026-10-25). No activar sin cumplir la §1. Las partes que no se han podido probar
> contra la instancia real figuran como **comprobar**, no como hechos.

## 0. Qué es y qué no es

- Pipeline separado del de Grafana (ADR-007). Grafana sigue sin contenido.
- Copia **enmascarada e incompleta**: reconoce formatos (DNI, IBAN, tarjeta,
  matrícula…), no nombres, direcciones ni salud. Ver
  `docs/production-security-privacy.md` («Límites del enmascarado»).
- Fail-open: Phoenix caído, mal configurado o lento no afecta a Telegram, al Core ni
  a la inferencia. Si algo falla, **se pierden trazas, nunca respuestas**.
- Apagar es siempre seguro y no requiere redeploy de Phoenix (§6).

## 1. Condiciones previas a activar (gate de specs/046)

No poner `PHOENIX_TRACING_ENABLED=true` hasta que **todas** se cumplan:

| # | Condición | Cómo se comprueba | Estado a 2026-10-25 |
|---|---|---|---|
| 1 | `docs/pilot-terms.md` publicado en `PILOT_NOTICE_URL` **con la sección de Phoenix** y sin el aviso al operador | Abrir la URL y leerla | **Pendiente** |
| 2 | SHA desplegado con CI verde y deployment `SUCCESS` (§2) | Checks del mismo SHA en GitHub | **Pendiente** |
| 3 | Retención real de Phoenix = 30 días (§3.2) | Comprobar en la instancia | **Declarada, no comprobada** |
| 4 | Conexión privada comprobada desde `ancoramind-app` (§4) | Prueba de alcance | **Pendiente** |
| 5 | Verificación E2E con el propietario (§5) | Ejecutarla | **Pendiente** |
| 6 | Procedimiento de borrado por usuario ensayado en la instancia real (§7) | Ensayo con datos sintéticos | **Solo probado en un backend local desechable** |

Decisiones del propietario que condicionan este runbook (no reabrir sin su visto bueno):
captura manual, todos los usuarios autorizados, retención de 30 días, voz excluida.

## 2. Despliegue del código (T11)

Wait for CI permanece desactivado por decisión del propietario (AGENTS.md §10). No
habilitarlo.

1. Subir el commit a `main` lo decide el propietario. Los commits locales no
   desplegados no están en Railway.
2. En GitHub, abrir **Actions** y comprobar que el run del **mismo SHA** pasó los
   tres jobs: `quality` (Ruff, mypy, historial de prompts, tests unitarios),
   `integration` (PostgreSQL con Docker) y `collector-config`.
3. Desplegar manualmente ese SHA y registrar: SHA completo, `deployment_id`,
   resultado de los checks y hora UTC.
4. Con el flag apagado el despliegue **no cambia el comportamiento**: no se crea
   provider, exporter ni conexión (criterio de aceptación 1 de la spec).

## 3. Phoenix: comprobaciones en la instancia

El servicio `Phoenix` (imagen `arizephoenix/phoenix:15.1.0`) y su Postgres propio
(`Postgres-lM2q`) ya existen en el proyecto `ancoramind-app`.

### 3.1 Variables del servicio Phoenix (sólo nombres verificados)

El servicio tiene definidas, entre otras: `PHOENIX_ENABLE_AUTH`,
`PHOENIX_DEFAULT_RETENTION_POLICY_DAYS`, `PHOENIX_GRPC_PORT`, `PHOENIX_PORT`,
`PHOENIX_TELEMETRY_ENABLED`, `PHOENIX_SQL_DATABASE_URL`, `PHOENIX_SECRET`. Se ha
verificado que **existen**; **no se ha leído ningún valor**. No pegar sus valores en
tickets, capturas ni este repositorio.

### 3.2 Retención de 30 días — comprobar

La variable `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` existe. Su valor es lo que el
propietario declara como 30, pero **no está comprobado**. Antes de activar:

1. En Railway, servicio `Phoenix` → **Variables**, confirmar que vale `30`.
2. Esa variable fija el valor por defecto de proyectos nuevos. En la UI de Phoenix,
   abrir el proyecto `ancoramind` (se crea con la primera traza) y confirmar su
   política de retención. Si el proyecto ya existía con otra política, la variable
   no la cambia: corregirla en la UI.
3. Si el valor real no es 30, **corregir el texto de `docs/pilot-terms.md`** o el
   valor, antes de activar.

### 3.3 Autenticación

`PHOENIX_ENABLE_AUTH` está definida. Comprobar que la UI pide credenciales y que la
contraseña inicial por defecto se cambió (el propietario indicó que se cambió el
2026-10-20). La API key del sistema que usará la app se crea en la UI de Phoenix
(**Settings → API Keys → System**). Guardarla sólo como secreto de Railway.

### 3.4 Dominio público — decisión vigente

**Por ahora no se retira el dominio público** de Phoenix (decisión del propietario,
2026-10-25). El servicio sigue accesible por internet en
`phoenix-production-34fa.up.railway.app`. Mientras sea así:

- La autenticación es la única barrera. Mantener `PHOENIX_ENABLE_AUTH` activo y la
  política de contraseñas fuerte.
- **La app nunca debe usar ese dominio** como destino de exportación (§4): enviaría
  contenido enmascarado por internet público.
- Aunque el dominio siga abierto, con datos reales sería el primer punto a cerrar.
  Retirarlo no afecta a la app porque ésta usa la red privada.

## 4. Variables de `ancoramind-app` (staged, sin activar)

Definirlas en **staged** con el flag a `false`, y aplicarlas en un despliegue
manual. Nombres y significado:

| Variable | Valor | Notas |
|---|---|---|
| `PHOENIX_TRACING_ENABLED` | `false` hasta §5 | Interruptor general |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://phoenix.railway.internal:<puerto-gRPC>` | **Red privada**; nunca el dominio público. Debe empezar por `http://` o `https://` y no llevar espacios |
| `PHOENIX_API_KEY` | API key de **sistema** de Phoenix | Secreto. Sólo en Railway |
| `PHOENIX_USER_PSEUDONYM_KEY` | ≥ 32 caracteres aleatorios | Secreto, **independiente de cualquier otro**. Ver abajo |
| `PHOENIX_PROJECT_NAME` | `ancoramind` (por defecto) | Nombre del proyecto en la UI |

**Puerto gRPC — comprobar.** El exporter usa OTLP por **gRPC**. Phoenix escucha gRPC
por defecto en `4317` y existe `PHOENIX_GRPC_PORT` en su servicio, pero no se ha leído
su valor. Confirmarlo en las variables del servicio `Phoenix` (el HTTP/UI usa
`PHOENIX_PORT`, que **no** es el de gRPC). Si el puerto es otro, usarlo en el
endpoint.

**Generar la clave de seudónimos** (no reutilizar ni derivar de otra):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

- Con cualquiera de las cuatro variables ausentes o inválidas el pipeline **no se
  crea**, aunque el flag sea `true` (fail-closed de configuración). La app arranca
  igual y, si el flag está en `true`, registra un aviso de nivel `WARNING`:
  `Phoenix tracing is enabled but inactive; missing or invalid: <NOMBRES>`. Sólo
  nombres, nunca valores. Con el flag en `false` no se registra nada. Ese aviso es
  el único síntoma visible de una variable mal escrita.
- **Rotar** `PHOENIX_USER_PSEUDONYM_KEY` rompe la agrupación histórica por usuario:
  las trazas anteriores siguen existiendo hasta expirar pero ya no se localizan por
  usuario (afecta al borrado, §7). No rotarla sin necesidad.
- Si el flag está a `true` y Phoenix no responde, la app **sigue funcionando** y
  pierde trazas (§8).

**Prueba de alcance privada — comprobar.** Desde un shell del servicio
`ancoramind-app` (Railway → servicio → shell), comprobar que el nombre resuelve y
el puerto responde, sin enviar contenido:

```sh
getent hosts phoenix.railway.internal
```

Si no resuelve, ambos servicios deben estar en el mismo proyecto y entorno
(`production`). No continuar hasta que resuelva.

## 5. Activación controlada y verificación E2E (T12)

Sólo con la §1 completa y con el propietario presente. Se activa para **todos los
usuarios autorizados** a la vez (decisión de specs/046): no hay lista parcial.

1. Poner `PHOENIX_TRACING_ENABLED=true` y desplegar manualmente. Registrar SHA y
   `deployment_id`.
2. Comprobar en los logs de arranque la línea
   `AncoraMind Phoenix masked content tracing configured` (nivel `INFO`). Si en su
   lugar aparece `Phoenix tracing is enabled but inactive; missing or invalid: …`,
   falta o es inválida alguna variable (§4) y el pipeline **no está activo**. Si no
   aparece ninguna de las dos, el flag no llegó a `true` o el procesador de
   Telegram no está habilitado (`TELEGRAM_PROCESSOR_ENABLED`), porque el pipeline se
   crea junto al runner del procesador.
3. Con **datos sintéticos** enviar por Telegram, en este orden, y anotar el resultado
   (tabla de casos de este paso):

| Mensaje | Debe verse en Phoenix | No debe verse |
|---|---|---|
| «Apunta una nota: comprar pan» | Mensaje, tool `propose_note`, respuesta | — |
| «Mi DNI es 12345678Z, guárdalo en una nota» | `[DNI]` | `12345678Z` |
| «Busca mi factura» (usa `search_documents`) | La llamada a la tool como metadato | El contenido que devuelve; la respuesta del modelo |
| Una nota de voz | **Nada** de ese turno | Cualquier texto de la transcripción |
| Un adjunto con pie de foto | El pie de foto | Nombre y contenido del archivo; respuesta del modelo |

Pasos siguientes de la activación (continúan la numeración del paso 3):

- **Paso 4.** Para cada caso, localizar la traza por `correlation_id` (el de
  `telegram_interactions`) en la UI de Phoenix y comprobar la columna «No debe
  verse». **Si algo de esa columna aparece, apagar de inmediato (§6)** y abrir un
  hallazgo; no seguir probando.
- **Paso 5.** Provocar un fallo controlado (p. ej. un adjunto no soportado) y
  comprobar que el turno falla igual que sin Phoenix y que la traza lleva el nombre
  de la clase de error y no su texto.
- **Paso 6.** Con la app activa, comprobar que Grafana **no** muestra ningún atributo
  de contenido en los mismos turnos.

## 6. Apagado

El apagado es seguro, inmediato y reversible:

1. Poner `PHOENIX_TRACING_ENABLED=false` y desplegar. La app deja de crear el
   provider; no se necesita tocar Phoenix.
2. Las trazas ya guardadas **permanecen** hasta que expiren (30 días) o se borren
   (§7). Apagar no las elimina.
3. Para parar la exportación sin redeploy, no hay interruptor en caliente: el flag se
   lee al arrancar. Es una limitación conocida; la alternativa de emergencia es
   detener el servicio `Phoenix` (la app lo tolera, §8).

## 7. Borrado por usuario (supresión)

Cada span lleva `user.id` = seudónimo HMAC del usuario. El procedimiento ensayado
en el spike (backend local, no la instancia real) es:

1. Calcular el seudónimo del usuario. Requiere `PHOENIX_USER_PSEUDONYM_KEY`, que se
   pasa por una variable de entorno **de la sesión**, nunca como argumento (los
   argumentos quedan en el historial del shell):

   ```powershell
   $env:PSEUDO_KEY = Read-Host "Clave de seudónimos" -MaskInput
   python -c "import os, sys; from src.observability.phoenix_export import user_pseudonym; print(user_pseudonym(sys.argv[1], os.environ['PSEUDO_KEY'].encode()))" <telegram_user_id>
   Remove-Item Env:PSEUDO_KEY
   ```

   Comprobado el 2026-10-25 con una clave de prueba: el valor impreso coincide con
   el que guarda el pipeline para ese usuario. `Read-Host -MaskInput` exige
   PowerShell 7; en Windows PowerShell 5.1 usar `Read-Host -AsSecureString` o
   definir la variable en una sesión que no se registre.
2. Listar los spans del proyecto filtrando por el atributo
   `GET /v1/projects/ancoramind/spans?attribute=user.id:<seudónimo>` y recoger el
   `context.trace_id` de cada resultado. **Paginar** hasta agotar los resultados.
3. Borrar cada traza: `DELETE /v1/traces/<trace_id>` (espera `204`).
4. Repetir el listado y comprobar que no queda ningún span de ese usuario y que los
   de otros usuarios siguen.

Limitaciones a tener en cuenta:

- **Todos los spans de una traza pertenecen al mismo usuario** (la captura fija el
  seudónimo en cada span), por eso borrar la traza entera es seguro. No borrar por
  nombre de span ni recorrer datos de otros usuarios.
- Pausar la captura (§6) mientras dura el borrado evita que lleguen trazas nuevas.
- **No probado en la instancia real.** Antes de depender de este procedimiento,
  ensayarlo allí con un usuario sintético y comprobar que la autenticación de la API
  (Bearer con la API key) funciona igual que en el ensayo local.
- No borra otras copias: el runtime de Agno, el log de consola de Railway y el
  proveedor del modelo quedan fuera (ver el inventario).
- Si se rotó la clave de seudónimos, las trazas anteriores a la rotación no se pueden
  localizar por usuario; sólo expirarán por retención.

## 8. Diagnóstico

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| No aparece la línea de arranque «masked content tracing configured» | Flag a `false`, o falta/es inválida alguna variable `PHOENIX_*`, o el procesador de Telegram está deshabilitado | Buscar el `WARNING` «enabled but inactive; missing or invalid: …» (§4). Si no hay ni línea ni aviso, revisar el flag y `TELEGRAM_PROCESSOR_ENABLED` |
| El flag está a `true`, la app responde, y Phoenix no recibe nada | Endpoint o puerto gRPC incorrectos, o la API key no es de sistema | Comprobar §4 (puerto y alcance privado). No hay error visible por diseño: es fail-open |
| Faltan trazas de turnos concretos | Se descartaron a propósito: voz, adjuntos o tool no clasificada | Esperado. Ver la tabla de captura en `docs/production-security-privacy.md` |
| Una traza lleva `[INVALIDO]` | Un valor no tenía la forma estricta de su campo (fecha, id, importe) | Esperado ante un argumento anómalo del modelo; no es un fallo |
| Una traza lleva `unknown_tool` | El modelo llamó a una tool que no existe en el registro | Esperado; si ocurre mucho, revisar el prompt |
| Latencia mayor tras activar | El spike midió ≈ +33 % por run, **sin red** y sin SLO aprobado | No hay umbral aceptado; medir con export real durante la verificación y decidir |
| Tool nueva sin trazas de respuesta | Está sin clasificar en `phoenix_capture.py` | Clasificarla (hay un test de deriva que lo exige) |

Ante cualquier sospecha de que aparece contenido que no debería: apagar (§6), anotar
el `correlation_id` y no copiar el contenido a ningún ticket.

## 9. Lo que este runbook no cubre

- Retirada del dominio público de Phoenix: aplazada por decisión del propietario
  (§3.4).
- Retención y purga del runtime de Agno (BL-34) y de los payloads ambiguos de
  `telegram_interactions`: pendientes, ver el inventario de privacidad.
- Una DPIA y la revisión legal: pendientes, necesarias antes de datos reales.
