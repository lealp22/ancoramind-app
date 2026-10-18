# T7 — Contabilidad LiteLLM: investigación offline (2026-10-18)

## Alcance y conclusión

Propietario autoriza lecturas y pruebas locales, **sin inferencia**. Se verifica
la misma imagen fijada que Railway, ya disponible localmente:

`ghcr.io/berriai/litellm:v1.100.1@sha256:a3715fa7ad8387941ab697259bd2881d68931657247a41984f90fae6d11c62bf`

Inspección Docker confirma RepoDigest; dentro: LiteLLM 1.100.1, Python 3.13.15.
Sin pull, secretos heredados, mounts, puertos, DB ni red. No proxy server startup
ni llamadas completion/SDK: se importan funciones instaladas y se les pasan
objetos HTTP sintéticos. Los límites externos de DB/Redis se sustituyen por mocks
y cache en memoria donde se indica.

**Demostrado:** metadata de precios cero no impide contabilizar `usage.cost`.
Cadena sintética coste OpenRouter → calculator → callback → cola KEY → contador
en memoria → rechazo por presupuesto comprobada. **No demostrado:** coste real
recibido en Railway, persistencia de sus transacciones, configuración efectiva de
flags/reservas ni límite de factura 0,10 USD. No se aprueba campaña por esta prueba.
T7c-remoto/T7b/BL-48 abiertos; no cambio en claves/r4/settings/runtime del bot.

## Evidencia reproducible

Validación del incremento: **10 pruebas internas del probe en Docker passed**, y
**7 unitarias nuevas** de guardrails (rechazo de credenciales/versión antes de
importar biblioteca). Suite global **1701 unitarias**, cobertura **80,58 %**;
mypy src limpio en 175 archivos. Ruff global comprobado tras corregir newline.
No nuevas integraciones PostgreSQL: no hay modificación de dominio/repositorios
ni migración. Avisos conocidos de Collector local ausente durante unit tests, sin
fallos. Sin commit/push por el agente. Los 10 tests Docker son evidencia separada,
**no están incluidos** en el recuento 1701 ni en CI automáticamente.

Probe: `scripts/check_litellm_accounting_offline.py` (herramienta local, no incluida
en contenedor eval db0c59b). Se ejecuta por stdin en contenedor descartable con
`--network none`, y bloquea también socket.connect/getaddrinfo. Rechaza secretos
ambiente y versión distinta; no instala dependencias. Resultado final:

```json
{
  "status": "offline_accounting_verified",
  "litellm_version": "1.100.1",
  "tests_run": 10,
  "failed_tests": [],
  "network_attempts": 0,
  "inference_started": false,
  "live_spend_verified": false,
  "campaign_approved": false
}
```

Desde PowerShell local, sin pasar env del host al contenedor:

```powershell
@'
import subprocess
from pathlib import Path
root = Path(r'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core')
image = ('ghcr.io/berriai/litellm:v1.100.1@sha256:'
         'a3715fa7ad8387941ab697259bd2881d68931657247a41984f90fae6d11c62bf')
result = subprocess.run(
    ['docker', 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'python', image, '-'],
    input=(root / 'scripts/check_litellm_accounting_offline.py').read_bytes(),
    capture_output=True, timeout=120,
)
print(result.stdout.decode())
raise SystemExit(result.returncode)
'@ | python -
```

No ejecutar este probe en la shell de producción. No usar compose del Gateway ni
Settings del bot: podrían cargar credenciales/DB. El digest esperado en el JSON
es una constante de referencia; identidad de imagen la verifica la invocación
Docker por digest y la inspección previa, no una autoatestación del script.

## Diez pruebas sobre la biblioteca instalada

| Prueba | Resultado y alcance |
|---|---|
| Coste proveedor con mapa ausente/cero | `usage.cost=0.03` da 0.03, aun sin entrada local o con precio local0. |
| Metadata y coste son distintos | `/model/info` sintético conserva precio0; respuesta sintética cuesta0.03. No identifica origen del cero productivo. |
| Coste upstream0 | Calculator conserva0; no lo reemplaza por estimación. No permite concluir gratuito desde metadata. |
| Coste ausente/inválido | Sin mapa local, calculator lanza excepción; negativo -0.01 se acepta en esta frontera. No positivo garantizado ante upstream defectuoso. |
| Callback/cola/contador/budget | Transformación/cálculo/callback reales reciben0.03. Writer real produce entrada KEY0.03 en cola, contador DualCache real0.03. Se incrementa sintéticamente0.08 →0.11 y check real rechaza. |
| Umbral | Check acepta gasto0/0.09 y rechaza0.10/0.12 para max_budget0.10. No se usa reserva anticipada en esta prueba. |
| Coste no disponible en callback | Callback real emite failed_tracking_alert y no actualiza DB/counter; no lanza rechazo por presupuesto al caller de ese callback. |
| Updates deshabilitados | `disable_spend_updates=true` desactiva selección de tracking. Config local versionada no lo activa; no se verificó valor runtime efectivo. |
| Gasto no verificable | `get_current_spend` permite fallback0 por defecto; con `fail_closed_budget_enforcement=true` devuelve503 cuando DB/Redis no verifican. Es prueba de funciones con lecturas mockeadas, no fallo real de Redis. |
| Contador stale | Si contador0.01 va por debajo de gasto ya conocido0.10 y fuente autoritativa0.12, devuelve/repara0.12. DB/cache externa mockeadas. |

Detalle de la prueba de callback: `OpenrouterConfig.transform_response`,
`response_cost_calculator`, `_ProxyDBLogger.async_log_success_event`,
`DBSpendUpdateWriter.update_database`, `_update_key_db`, cola SpendUpdateQueue,
`increment_spend_counters`, incremento DualCache y `_virtual_key_max_budget_check`
son reales. `_batch_database_updates` se sustituye por su tramo KEY para no
actualizar entidades ajenas; se mockean construcción del log sintético, cache de
identidad, arranque del contador y transacciones/alertas externas. Se usa usuario
sintético sólo para evitar lookup de identidad y no se acredita spend de USER.
La cola **no se flushea a PostgreSQL**. El contador se comprueba antes del flush:
refuta que haya que esperar exclusivamente a la DB para comprobar la siguiente
petición, pero no garantiza el orden de todos los callbacks/concurrencia reales.

## Lectura de código y límites operativos

- `_get_proxy_model_info` conserva metadata y completa campos desde mapas.
  En imagen limpia la entrada no cualificada no devuelve precios; la metadata
  productiva0/0 no se reproduce con entrada vacía. No se ha leído registro privado
  ni configuración efectiva para identificar su origen exacto.
- OpenRouter transform añade usage.include si falta y extrae usage.cost al hidden
  header; calculator lo prioriza. La imagen consume el campo real, no un importe
  inventado a partir de metadata0. No se prueban respuestas reales ni streaming.
- Update writer puede encolar updates DB asincrónicos y callback actualiza
  contadores antes de terminar su trabajo. Error de construcción/escritura del
  log puede ser atrapado; un fallo de tracking genera alertas, no prueba de
  que la respuesta de inferencia se rechace. No hay garantía universal fail-closed
  sólo por existir `max_budget`.
- Umbral basado en gasto acumulado admite0.09 antes de conocer coste de la siguiente
  respuesta; ésta puede llevar a0.11. Las reservas anticipadas de otra configuración
  no se han probado ni habilitado aquí. No afirmar techo exacto0.10.
- Rechazo de gasto no verificable es opt-in en esta imagen; no se propone activar
  flags productivos sin decisión separada, pues cambia disponibilidad/costes del bot.
- OpenRouter upstream observado:5 USD compartidos, restante4,44046623; snapshot
  histórico20 USD. Ninguno concede permiso a gastar ese saldo para eval.

## Siguiente decisión, no ejecución

**Decisión de campaña recibida posteriormente:** propietario autoriza cinco casos
exactos/nominal0,10 USD adicional/clave exclusiva2h con revisión humana y revocación;
acepta snapshot histórico/diferencias y limitaciones. Investigación cerrada, no
nuevos smokes; [campaña aprobada](campaign-approved-runbook.md) preparada, resultados
humanos reales todavía pendientes. El smoke existente no se repite ni consume
reserva de campaña.

**Resultado posterior live:** propietario aporta smoke_accounting_verified,
1POST/1call, gasto propio0→0,0000353 USD, delta=header Gateway y clave smoke
87a125a812bd revocada según segundo reporte smoke_key_revoked_verified.
Se cierra investigación contable acotada; no volver a pedir pruebas de coste.
No se convierte en garantía universal de0,01/0,10 USD ni valida semántica; campaña
sigue sin aprobar. Evidencia completa en [smoke](accounting-smoke-runbook.md).

**Decisión posterior del propietario:** autoriza explícitamente el smoke único
nominal0,01 USD y modificación temporal de clave eval; no la campaña. La clave
anterior ya está caducada al preparar, así que se requiere sustituta dedicada al
estar listo el operador, no creación automática del agente. Helper/rutina de
revocación y prueba offline preparados en [runbook smoke](accounting-smoke-runbook.md).
Autorización de la prueba no se registra como inferencia ejecutada ni contabilidad
live validada: faltan JSON real y cleanup. No nuevas rondas de investigación.

### Revisión de evidencia existente autorizada — ronda cerrada

El propietario solicita revisar evidencia existente y acepta considerar pruebas
pagadas acotadas para salir del bucle. No equivale todavía a aprobar un importe
ni ejecutar inferencia. Se limita la investigación a una ronda, sin nuevas tools
de producción, modificaciones de permisos o llamadas al modelo.

Railway, lectura 2026-10-18T01:19:28Z: Gateway y evaluador Online, deployments
bf1c29d3/54892e8d sin cambios, una réplica cada uno, sin pending work. Config de
entorno (sin descifrar variables) confirma imagen fijada, endpoint privado litellm,
healthcheck readiness y una región/réplica. **No verifica settings efectivos**
disable_spend_updates/fail_closed_budget_enforcement, que no se han leído del proceso.

Consulta de logs Gateway desde 2026-10-15T20:38:38Z hasta el control, sin solicitar
campo message ni cuerpos/prompt/argumentos: filtros `response_cost`,
`"Error in tracking cost callback"` y `"Spend tracking"` devuelven cero filas.
No atribuirlo a ausencia de costes/errores: pueden no emitirse a ese nivel y son
filtros acotados, no acceso a ledger DB. Control de visibilidad `"chat/completions"`
devuelve 101 filas con límite100 (muestra truncada); sólo timestamps/severity,
sin mensajes. Confirma que hay logs de peticiones, no número total de inferencias
ni facturación. No claves, texto personal, spend logs DB ni valores env leídos.

**Decisión recomendada:** no más rondas de lectura para perseguir una garantía
absoluta que no ofrece el sistema. Proponer UNA prueba pagada sintética por la
frontera LLMAccess/Gateway, sin tools/DB productiva, un intento, max64 tokens de
salida, timeout30 s, sin retry/fallback/replay. Presupuesto nominal0,01 USD,
restringiendo sólo la clave eval a ese límite/ruta tras autorización específica;
la petición en curso puede sobrepasarlo y no se promete techo exacto de factura.
Releer spend propio antes/después sin contenido y exigir coste positivo finito
y atribución a esa clave. Resultado positivo cierra esta investigación y permite
pedir aprobación de campaña, no nuevas auditorías; error/coste ausente/resultado
ambiguo → detenerse y registrar fallo concreto, sin segunda inferencia.

La prueba NO está autorizada/ejecutada en esta revisión, no habilita flags de
campaña ni afirma verificación técnica antes de obtenerla. No modificar r4,
secreto upstream del bot, DB productiva ni reconstruir el candidato db0c59b.
Al finalizar smoke, retirar permiso de inferencia o revocar clave según decisión
explícita; no dejar una ampliación indefinida. La campaña de cinco casos estimada
0,10 USD es distinta: smoke añadiría0,01 USD nominal a su presupuesto, no ocultarlo
dentro del plan inmutable. Debe aprobarse esa suma si después se realiza campaña.

Investigación acotada completa: **no hay prueba de que la contabilidad esté rota
por metadata0**, sí hay prueba de que depende de un coste recibido y del estado
de tracking/contadores. Para elevar el presupuesto nominal eval a control externo
verificado faltaría una evidencia runtime sin contenido o un aislamiento aprobado;
esta prueba no sustituye ni autoriza esa decisión. No aprobar flags con valor
"verificado" basándose en el JSON offline. No se ha gastado ni reducido límites
del bot. La clave temporal sigue destinada sólo a lectura hasta su expiración.

Fuentes instaladas SHA-256 (también emitidas por el probe):

| Archivo bajo litellm/ | SHA-256 |
|---|---|
| llms/openrouter/chat/transformation.py | `8a7936d6dcca86bcddda9ac18d7cb6aaf76d98fc1bb73652f6abef659fa926f7` |
| cost_calculator.py | `77630d397d60939d3332f01fab1864e4af8640a8c3acddde777acbebc36ff566` |
| proxy/hooks/proxy_track_cost_callback.py | `fc5c3cfe313655e8417a278002b9179e56643238ea128c440f0a4156c6cf9f04` |
| proxy/auth/auth_checks.py | `a274e894661b279ab9df6d0c069816d7a089eca78f7b341da36793e737fefa50` |
| proxy/proxy_server.py | `bbf5cc6e23778e5f3e1d6684d4e1e655ca5a77021cac7fc8c55ff4f1e716986a` |
| proxy/db/db_spend_update_writer.py | `d2246b505db4cb153252cb65539e3d92defb8035c64f1d97feb962d1e67bf987` |