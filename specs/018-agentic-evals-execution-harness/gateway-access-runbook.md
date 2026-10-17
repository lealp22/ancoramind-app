# T7 — Clave temporal: preparación autorizada, sin inferencia

## Estado y alcance

El propietario aporta mount/preflight/TTY correctos y autoriza explícitamente
crear clave exclusiva/expirable y comprobar acceso privado sin modelo. No autoriza
campaña, ampliación de presupuesto, clave del bot ni mutación de aliases/settings.

**Preparado localmente, NO ejecutado en Railway:** las herramientas disponibles
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
La compatibilidad live sigue pendiente hasta obtener el reporte, sin suponerla.

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
en esa terminal privada**; guardar en un gestor de secretos y limpiar el scrollback
si procede, nunca enviarla en chat. No imprimir variables de entorno.

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

## 3. Límites y continuación

Hasta ambos reportes, clave/acceso/budget **pendientes**, no validados por tests
mockeados. No marcar T7c, T7b ni BL-48 terminados por preparar scripts.

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