# T7 — Clave temporal: preparación autorizada, sin inferencia

## Estado y alcance

**Estado actual — reporte real del propietario:** `eval_gateway_read_only_verified`
desde evals, `restricted_alias_verified`, clave `ancoramind-evals-access-238d37ae3e0e`,
caducidad `2026-10-18T02:08:48.318000+00:00`, único modelo r4. Coinciden SHA
`db0c59be0b2eeb807d4222aeb5a62b622d90b200`, fuente
`108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82` y plan
`8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139`.
Presupuesto nominal 0,10 USD sin reset, gasto cero. Acceso privado y restricciones
releídas desde el evaluador quedan comprobados; `inference_enabled=false`,
`inference_started=false`, `pricing_verified=false`, aprobación separada pendiente.
No se ha evaluado al modelo ni demostrado un techo de facturación. La causa exacta
del primer intento bloqueado sigue sin confirmarse; este éxito no la identifica.
Los apartados siguientes conservan la secuencia histórica de preparación/intentos.

El propietario aporta mount/preflight/TTY correctos y autoriza explícitamente
crear clave exclusiva/expirable y comprobar acceso privado sin modelo. No autoriza
campaña, ampliación de presupuesto, clave del bot ni mutación de aliases/settings.

**Creación ejecutada por el propietario; acceso desde evals pendiente:** el JSON
aportado confirma `eval_key_read_only_ready`, alias
`ancoramind-evals-access-1eacd663da85`, expiración `2026-10-18T01:37:40.773000+00:00`,
modelo exclusivo r4, presupuesto 0,10 USD sin reset/gasto cero, concurrencia 1,
30 RPM/250000 TPM, puerto 4000 y las tres rutas de lectura previstas. Sin inferencia;
`campaign_approval=pending`, `pricing_verified=false`. Se registra sólo metadata,
no la clave. La lectura/verificación del registro y catálogo fue en loopback del
Gateway; todavía no demuestra acceso desde `ancoramind-evals`.

**Intento desde evals aportado después:** `eval_gateway_check_blocked`,
`inference_started=false`, sin detalle de etapa. Acceso no validado; causa remota
desconocida. Evaluador y Gateway Online, mismos deployments, sin pending work;
clave no caducada al control de reloj 2026-10-17T23:47:49Z (caduca 01:37:40Z).
No inferir de esos datos que la clave sea incorrecta o que falle la red.

**Clave perdida y retirada del alias:** el propietario informa pérdida del valor
y después aporta `eval_key_absent_verified` para
`ancoramind-evals-access-1eacd663da85`, `inference_started=false`, tras ejecutar el
procedimiento por alias exacto en LiteLLM. La consulta final confirma ausencia del
registro; el reporte no distingue si se borró en ese paso o ya no existía. No
reutilizar la clave anterior ni tratarlo como validación del acceso desde evals.

Se continúa con **una sola sustituta**, mismos controles de lectura/modelo,
2 h/0,10 USD sin reset, sin inferencia ni ampliación de autorización. La nueva
creación la ejecutará el propietario con el generador existente y devolverá sólo
metadata; todavía no hay reporte de nueva clave. Mantener abierta su terminal
privada de LiteLLM hasta introducir la clave en el prompt oculto de evals. Copiar
primero el código de diagnóstico y después el valor secreto para que el
portapapeles no se sobrescriba. No hace falta un gestor nuevo ni persistirla.
Si se bloquea o es ambiguo, parar y no repetir generación.

**Sustituta creada por el propietario (reporte recibido):**
`eval_key_read_only_ready`, alias `ancoramind-evals-access-238d37ae3e0e`, expiración
`2026-10-18T02:08:48.318000+00:00`. Mismos controles: único modelo r4, tres rutas
de lectura, 0,10 USD nominal sin reset/gasto cero, concurrencia 1, 30 RPM/250000 TPM,
puerto 4000. Inferencia deshabilitada/no iniciada, campaña pendiente y pricing
no verificado. Ya no repetir generación; usar esta clave en el prompt oculto del
comprobador actualizado. Acceso privado desde evals aún pendiente; no atribuir
la incidencia anterior a la clave perdida ni dar por resuelta su causa.

La creación no la ejecutó el agente: las herramientas disponibles
no ofrecen ejecución de comandos en los contenedores. No instalar CLI, crear
túneles/dominios ni extraer master key como atajo. La parte privilegiada la ejecuta
el propietario en la shell existente de **LiteLLM**, usando su master key ambiente
sin mostrarla ni trasladarla al evaluador. No usar `litellm_create_virtual_key.py`:
su allowlist base y ausencia de expiración no cumplen este alcance.

Gateway inspeccionado sólo lectura: imagen `v1.100.1`, digest
`a3715fa7ad8387941ab697259bd2881d68931657247a41984f90fae6d11c62bf`;
sin dominio/TCP proxy. Se contrastan tipos, generación y autenticación de la
[versión fijada](https://github.com/BerriAI/litellm/blob/v1.100.1/litellm/proxy/management_endpoints/key_management_endpoints.py)
y [documentación de claves](https://docs.litellm.ai/docs/proxy/virtual_keys).
La creación/verificación de restricciones queda acreditada por el reporte del
operador; conectividad privada desde evals, pricing y campaña siguen pendientes.

## Controles de la nueva clave (no se modifica ninguna existente)

- Alias único de gestión `ancoramind-evals-access-<aleatorio>`; único modelo
  permitido `ancoramind-default-r4`.
- Caducidad **2 horas desde la creación**, sin rotación automática.
- `max_budget=0.10` USD, gasto inicial cero, sin reset. Un presupuesto configurado
  y releído no demuestra el coste final ni su enforcement en inferencia. Puede
  haber contabilización diferida o coste de la última petición en curso.
- Concurrencia 1, 30 RPM, 250000 TPM. No cambian los límites del plan de cinco
  casos ni los límites productivos del bot.
- Por ahora sólo rutas **`/models`, `/v1/models`, `/key/info`**: sin ninguna ruta
  de inferencia o administración. `key_type=default` conserva esta lista explícita;
  `llm_api` la sustituiría por un grupo más amplio en esta versión. No usarlo.
- La clave verifica sus propias restricciones persistidas y catálogo antes de
  entregarse al operador. Campos/overrides ampliados o incumplidos → revocar sólo
  la clave recién creada, comprobar respuesta de borrado y detenerse.
- Error/timeout de creación ambiguo → **no repetir**; revisar por el alias seguro.
  No borrar ni rotar claves ajenas. Si falla la revocación, tratar como estado
  incierto aunque la clave creada sigue destinada sólo a lectura.

## 1. Crear desde la shell privada de LiteLLM

El script local `scripts/provision_eval_gateway_key.py` usa sólo stdlib,
`http://127.0.0.1:$PORT`, sin proxy/redirect/retry. GET modelos, POST crear,
GET info/modelos; POST borrar únicamente como compensación de la clave nueva.
No llama a modelos, no cambia settings/aliases ni reinicia servicios.

Para transferir **código sin secretos**, en PowerShell local:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
$source = Get-Content -Raw -Encoding UTF8 "$root\scripts\provision_eval_gateway_key.py"
("python - <<'PY'`n" + $source + "`nPY`n") | Set-Clipboard
```

Pegar el bloque en la shell **LiteLLM**, no en evals. No escribir archivos Python
en el contenedor, no redirigir a logs ni grabar la sesión. Se abre `/dev/tty` antes
de crear la clave: sin terminal privada se rechaza. La clave **se mostrará sólo
en esa terminal privada**. No se presupone ni se ha configurado un gestor de
secretos del propietario. Si ya utiliza uno, puede guardarla allí; no necesita
instalar/configurar ninguno para esta prueba efímera. Puede transferirla desde
esa terminal privada al prompt oculto del comprobador, sin archivo ni variable
persistente Railway, historial de comandos o chat. No imprimir variables.
Primero pegar el código del comprobador; después copiar la clave cuando aparezca
el prompt (copiar el código reemplaza el portapapeles). Limpiar portapapeles y
scrollback tras la transferencia, según política del equipo; no usar portapapeles
sincronizado ni grabación de terminal para secretos.

El JSON final en stdout es metadata-only: esperado `eval_key_read_only_ready`,
alias/expiración/puerto/límites y `inference_enabled=false`,
`inference_started=false`, `pricing_verified=false`, `campaign_approval=pending`.
Compartir sólo ese JSON. Si aparece `eval_key_blocked_or_ambiguous`, detenerse,
compartir sólo ese reporte y no repetir POST de generación.

## 2. Comprobar desde la shell existente del evaluador

El helper local `scripts/check_eval_gateway_access.py` **no se despliega ni copia
a `/app/scripts`**: cambiarlo rompería la huella del contenedor aprobado. Se pega
como bloque Python por stdin igual que arriba, con ese otro nombre de fichero.

Antes, establecer en la shell eval únicamente la URL privada no secreta:

```sh
export ANCORA_EVAL_GATEWAY_URL='http://litellm.railway.internal:4000/v1'
```

Usar `4000` sólo si coincide con `gateway_port` del reporte de creación;
en otro caso usar el puerto allí validado, sin probar puertos a ciegas. La red
privada `litellm.railway.internal` corresponde al endpoint ya configurado.

Transferir el segundo bloque desde PowerShell:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
$source = Get-Content -Raw -Encoding UTF8 "$root\scripts\check_eval_gateway_access.py"
("python - <<'PY'`n" + $source + "`nPY`n") | Set-Clipboard
```

Pegar en shell **ancoramind-evals**. Comprueba SHA/huella/plan del contenedor antes
de pedir la clave temporal por entrada oculta de TTY (`getpass`, fail-closed si
intentara recurrir a stdin con eco). Sólo GET modelos/info, sin crear reserva,
persistir clave ni cambiar entorno Railway. No usar la master key en este paso.

Esperado `eval_gateway_read_only_verified`, `restricted_alias_verified`, mismos
límites/caducidad y `inference_enabled=false`, `inference_started=false`,
`pricing_verified=false`, `approval_status=pending_separate_approval`.
Compartir sólo JSON. Esto no instala variables permanentes en evals: no se provoca
un rebuild ni se incorpora una clave en el contenedor o manifiesto de fuentes.

### Si el comprobador se detiene

El helper actualizado incluye únicamente `stage`, `error_class`, `http_status`
y `gateway_url_present` junto al estado/sin inferencia. Etapas posibles:
imports, source_identity, plan_snapshot, private_console, key_input,
gateway_settings, http_client, models_request, models_response, models_scope,
key_info_request, key_info_response, key_info_restrictions. Error class es una
allowlist fija; clases desconocidas se reducen a OtherError. No se imprimen URL,
clave, cuerpos/headers HTTP, mensajes de excepción ni traceback.

Para el intento fallido ya recibido, volver a copiar **sólo el comprobador
actualizado** y repetir únicamente los GET de diagnóstico desde la shell evals,
con la misma clave de lectura todavía vigente. No repetir creación ni habilitar
rutas. Si la URL sigue exportada, conservarla para diagnosticar el fallo original;
`gateway_url_present=false` permitirá identificar su ausencia sin mostrar variables.
No copiar este helper a `/app/scripts`: ejecutar por stdin conserva la identidad.
No añadir un retry automático: la repetición manual autorizada es de lectura,
nunca de inferencia ni de POST de generación. Si ya ha caducado, detenerse.

El mismo JSON genérico se reprodujo localmente con URL ausente, HTTP de error,
ConnectError y scope incorrecto. Esto explica el **déficit de diagnóstico**, no
la causa exacta de la incidencia remota. Pruebas nuevas ejecutan main completo
con HTTP simulado; incluyen camino correcto sin ampliar permisos y errores sin
filtraciones (incluidas clases de excepción con nombre sensible).

Validación del incremento diagnóstico: 13 pruebas nuevas (34 focales con creación),
suite global **1694 unitarias**, cobertura **80,58 %**, Ruff global/mypy src limpios.
Helper pegado por stdin en imagen db0c59b `--network none` sin TTY: informa etapa
private_console/OSError sin traceback/red/inferencia. No nuevas integraciones
PostgreSQL ni operaciones remotas de escritura; causa live pendiente del reporte.

## 3. Límites y continuación

Reportes de creación y comprobación desde evals recibidos: acceso privado, alias
exclusivo y presupuesto nominal releídos en Gateway. Pricing y enforcement de
facturación no comprobados; no marcar T7c, T7b ni BL-48 terminados. Antes de campaña
faltan aceptación de procedencia histórica del snapshot, revisión de pricing y
límites externos y aprobación explícita con revisor presente.
La clave no se regenera: si ha caducado o no se conserva su valor, detenerse y
revisar el siguiente paso, no repetir generación por defecto.

Incluso después: revisar pricing real de r4 y su correspondencia con snapshot,
aceptar procedencia histórica y presupuesto externo; aprobación de campaña
separada, ligada al SHA `db0c59b`, fuente `108c410d…` y plan `8f3e4a51…`.
No poner flags de aprobación. La clave creada **no puede inferir en su estado
previsto**; habilitar una ruta concreta necesitará nueva decisión y verificación,
sin regeneración automática. Si caduca antes, no sustituirla silenciosamente.
No probar `/chat/completions` ni siquiera como petición negativa en esta fase.

Los helpers son herramientas locales del operador, **no código bajo evaluación**
ni incluidos en la imagen db0c59b. No redeploy ni cambio de identidad para usarlos.

## Validación local de esta preparación

21 pruebas específicas superadas: alcance/presupuesto/expiración persistidos,
revocación de la clave nueva ante desviación/fallo de entrega, creación incierta
sin retry, secreto sólo en consola explícita, rechazo de rutas de inferencia,
redirects/proxy bloqueados (servidor HTTP sintético loopback). Suite global:
**1681 unitarias, 80,58 % cobertura**, Ruff global y mypy src (175 fuentes) limpios;
catálogo estático válido. Dos helpers comprobados en imagen db0c59b `--network none`
por stdin y sin TTY: fallan cerrados sin tracebacks ni inferencia. No prueba de
Gateway real ni de creación; no integraciones PostgreSQL nuevas. Avisos conocidos
de Collector local ausente durante unit tests, sin fallos. Sin commit/push ni
cambios remotos de estado en esta preparación.