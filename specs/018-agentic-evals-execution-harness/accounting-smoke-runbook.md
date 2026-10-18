# Prueba única de contabilidad — ejecutada y revocada

## Resultado real aportado por el propietario

`smoke_accounting_verified`, SHA db0c59be0b2eeb807d4222aeb5a62b622d90b200,
fuente108c410d…/plan8f3e4a51… esperados; clave exclusiva
`ancoramind-evals-accounting-87a125a812bd`. **1 POST / 1 model call**,
inference_started=true, campaign_approved=false. Gasto inicial0, final y delta
**0,0000353 USD**; header Gateway **0,0000353 USD**, reconciliación exacta y
por debajo del nominal0,01. Estimación de reserva Core
0,0005143999999999999 USD, no confundirla con coste real observado.

Segundo reporte del propietario: **smoke_key_revoked_verified**, mismo alias.
Cleanup confirmado; el permission_cleanup_required del reporte de smoke queda
satisfecho por ese segundo reporte. No repetir smoke ni borrar marca/reserva.
Ejecución humana autorizada, no ejecución remota del agente; evidencia metadata-only.

**Investigación de contabilidad cerrada en este alcance:** cadena live de esta
petición contabilizada y revocación comprobadas. No prueba universal de techo de
factura/fallos, no resultado semántico ni aprobación de campaña. Siguiente paso
directo es decidir campaña sintética existente; no nuevas rondas de contabilidad.
Los apartados siguientes conservan procedimiento y verificaciones previas.

## Decisión y alcance

Propietario autoriza explícitamente UNA prueba pagada sintética y modificación
temporal de clave eval, no la campaña: LLMAccess → Gateway r4, un intento, max64
tokens salida/timeout30s, sin tools/DB de negocio/retry/fallback/replay. Presupuesto
nominal0,01 USD con posible exceso de petición en curso aceptado, sin prometer
techo exacto. La clave upstream compartida5 USD no se toca ni se considera saldo
aprobado. Éxito con gasto propio positivo finito cierra investigación contable;
fallo/coste ausente/resultado ambiguo → parar sin otra inferencia.

Control de reloj al preparar: 2026-10-18T05:56:06Z. La clave read-only
`ancoramind-evals-access-238d37ae3e0e` caducó 02:08:48Z: no ampliar una credencial
caducada ni reutilizarla. Para ejecutar se necesita sustitución explícita por
clave dedicada de smoke. Se prepara generador sólo para cuando el operador esté
listo; **no se ha creado ninguna clave nueva por el agente**. El operador recibe
alcance de la sustitución antes de ejecutar el paso admin.

## Helper y aislamiento

`scripts/eval_accounting_smoke.py` es tooling local del operador, no incluido
en imagen eval db0c59b. Pegar por stdin, **no guardar en /app**, no reconstruir
bot/evaluador ni cambiar identidad/snapshot/plan. Se reutilizan fixture sintética
ya versionada y LLMAccess; no prompt nuevo de producción ni Agent/tools.

- Admin, shell **LiteLLM**: usa master ambiente sólo en loopback para crear una
  clave dedicada nueva `ancoramind-evals-accounting-<aleatorio>`, sólo r4,
  duración30min, max_budget0,01 sin reset, concur1/RPM1/TPM2000. Rutas GET models/
  key-info y chat-completions, no otras capacidades. Verifica campos persistidos
  y scope antes de entregar secreto únicamente a `/dev/tty`. Queda esperando
  Enter; finalmente elimina su clave y confirma alias ausente. No modifica claves
  existentes. Cerrar/proceso muerto puede impedir cleanup: expiración es backstop,
  no prueba de revocación; revisar alias concreto si pasa.
- Smoke, shell **evals**: entrada oculta `getpass`, identidad exacta SHA db0c59b,
  fuente108c410d…, plan8f3e4a51…, mount real y gate específico de la autorización.
  Lectura gasto propio inicial0 y restricciones antes de reservar; creación
  exclusiva `accounting-smoke-v1.reserved.json` **independiente del plan campaña**.
  Cualquier intento consume reserva: no borrarla ni cambiar volumen/nombre/key
  para repetir. Report metadata-only `accounting-smoke-v1.report.json`.
- Una primitiva ainvoke gobernada, no SDK/provider directo; max1 model/request,
  salida64, 30s, snapshot histórico sin mutarlo. Petición fuerza num_retries0,
  fallbacks[] y provider.allow_fallbacks=false; HTTP guard niega segunda llamada,
  otros orígenes/métodos/endpoints o parámetros ampliados. Transport sin retry/
  redirect/proxy ambiente, no streaming/tools. No implica garantía sobre conducta
  interna del proveedor; configuración explícita de no fallback en la petición.
- Captura sólo x-litellm-response-cost numérico si existe. Gasto propio antes/
  después, hasta6 GET separados2s, no reintento de inferencia. Delta positivo finito
  <=0,01 y header coherente si existe → smoke_accounting_verified. El importe Core
  calculado por snapshot se etiqueta como tal, no se vende como factura proveedor.
  Model reply/ID externo/clave/argumentos no van a stdout/estado; output SDK
  suprimido. No observador de campaña ni flags ANCORA_EVAL_*APPROVED de campaña.

## Pasos, sólo cuando ambas shells estén listas

1. Mantener shell LiteLLM y shell ancoramind-evals abiertas y en privado, sin
   grabación/log forwarding de terminal. No volver a ejecutar generadores antiguos.
2. En PowerShell local copiar **admin**:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
$source = Get-Content -Raw -Encoding UTF8 "$root\scripts\eval_accounting_smoke.py"
("python - --role admin <<'PY'`n" + $source + "`nPY`n") | Set-Clipboard
```

3. Pegar en shell **LiteLLM**. Crea sustituta nueva y muestra secreto en terminal
   privada y JSON smoke_key_ready. **No pulsar Enter todavía ni cerrar**: espera
   a que termine smoke en la otra shell. Si error/ambiguo, no crear otra.
4. En PowerShell local copiar **smoke** (sobrescribe portapapeles de código):

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
$source = Get-Content -Raw -Encoding UTF8 "$root\scripts\eval_accounting_smoke.py"
("python - --role smoke <<'PY'`n" + $source + "`nPY`n") | Set-Clipboard
```

5. En shell **evals**, exportar sólo la URL privada y gate de esta aprobación:

```sh
export ANCORA_EVAL_GATEWAY_URL='http://litellm.railway.internal:4000/v1'
export ANCORA_EVAL_ACCOUNTING_SMOKE_APPROVED='one-call-0.01-usd'
```

6. Pegar bloque smoke, después copiar la **clave SMOKE nueva** desde terminal
   LiteLLM y pegarla en prompt oculto. No master ni clave antigua ni alias. Una
   sola ejecución: no repetir aunque JSON indique fallo/timeout/coste no visto.
7. Obtener JSON. Siempre, tanto si termina como si falla/cancela, volver a shell
   **LiteLLM y pulsar Enter**. Esperado `smoke_key_revoked_verified`. Si fallo de
   cleanup, conservar alias y revisar revocación dirigida; no tocar otras claves.
8. Enviar sólo JSON smoke y JSON revocación, nunca secreto/respuesta. Limpiar
   portapapeles/scrollback según política. No borrar reserva; conservar reporte.

No pedir nueva campaña ni lanzar cinco casos por este éxito. Si positivo, se
presentará decisión de campaña 0,10 USD adicionales; total nominal con smoke0,11.
Si no, cerrar con fallo concreto sin encadenar más experimentos.

## Verificación local

- 13 tests focales nuevos: LLMAccess real sobre MockTransport, exactamente un POST
  aun con503/timeout, conservación de reserva/bloqueo replay/coste ausente,
  verificación restricciones/expiración, entrega sólo TTY y revocación incluso si
  falla verificación admin. Sin llamadas reales a Gateway/proveedor.
- Imagen sellada db0c59b `--network none --tmpfs /eval-state`: helper inyectado por
  stdin sobre código sellado sin modificarlo, LLMAccess/HTTP mock1POST, reconciliación
  positiva y replay bloqueado. El tmpfs es sólo fixture descartable local, **no**
  sustitución del volumen persistente Railway. Sin TTY falla antes de red/modelo.
- Suite global **1714 unitarias passed**, cobertura80,58 %, Ruff/mypy src limpios.
  Sin nuevas integraciones PostgreSQL, despliegues, claves reales ni inferencia.
  Pendiente ejecución del operador/reporte real y confirmación de revocación.