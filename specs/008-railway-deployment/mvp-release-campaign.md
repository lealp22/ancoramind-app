# Campaña de liberación incremental MVP — 2026-10-17

Fuente de prioridad: `BACKLOG.md`, decisión del propietario del 2026-10-17.
Este registro distingue preparación local, observación remota y E2E humano.
No sustituye la matriz A–Y ni cierra BL-23/39/40/48.

## Orden y evidencias de salida

| Entrega | Flujo real requerido | Estado en esta sesión |
|---|---|---|
| 1. Recordatorios (BL-1/M5) | Petición → propuesta → Sí → fila canónica → aviso recibido → consulta `fired`; fecha/hora local y ausencia de repetición observada | PASS: circuito local y E2E Telegram autorizado de un recordatorio no recurrente; consulta final por SELECT, sin nueva inferencia |
| 2. Vehículos/mantenimiento (BL-1/M4) | Registrar vehículo → confirmar → mantenimiento → confirmar → recuperar historial | PASS para alta e historial manual sin importe/factura; dos escrituras confirmadas y consulta real en Telegram |
| 3. Calendario/recurrencia/snooze (BL-1/41) | Evento con aviso → confirmar → consulta por rango → entrega → siguiente ocurrencia → aplazamiento confirmado | PASS funcional asistido: serie diaria limitada, dos avisos + snooze entregados; presentación incompleta pendiente BL-49, no UX family&friends validada |
| 4. Imagen/PDF escaneado (BL-1/6) | Adjuntar → conservar → extracción visual → resumen/consulta con procedencia | PDF sintético PASS; imagen parcial: fecha extraída pero omitida al consultar (BL-50). Dos originales y extracciones verificados; coste visual no disponible (BL-51) |
| Paralelo: invitaciones/admin (BL-24/43) | Canje manual y autoaprobado, revocación, aislamiento y acceso administrativo protegido | E2E manual y auto sin LLM PASS con account=2; mensaje automático correcto y revocación inmediata; panel HTTPS/auth/logout comprobados. Flags OFF al cierre. Aislamiento/inactividad/resto matriz pendientes; silencio sin acceso → BL-52 |
| Paralelo: Grafana (BL-33, demo) | Collector privado existente → series reales → dashboard importado | Dashboard v1 importado y consultado; alertas/degradación/rotación fuera de alcance |

## Baseline observado, sin desplegar desde esta sesión

- SHA: `b104d8fdcc04e476ce11263b7b3cda7291e24127`.
- CI del mismo SHA: `quality`, `integration` y `collector-config`: `success`.
- Railway `ancoramind-app/production`: app deployment
  `61c687a0-a856-4fbd-86ff-215ee9acf1aa`, finalmente `SUCCESS`, una réplica.
  Ya estaba en curso al empezar; no se lanzó ni aprobó otro deployment.
- Collector `e59dcb9a-b503-4d28-82a9-37333c1377c1`: `SUCCESS`, una réplica,
  sin dominio ni TCP proxy público. Secretos OTLP ya definidos; no se leyeron
  sus valores ni se crearon otros.
- Readiness observado `2026-10-16T23:55:34Z`: HTTP 200, DB/Gateway/processor/
  reminder-worker sanos, revisión runtime 8 y cero recordatorios vencidos.
  `gateway_circuit=unknown` no acredita estado cerrado ni prueba del circuit.
- Wait for CI sigue OFF; no se cambió configuración, webhook ni modelo.

## Entrega 1: prueba local integrada

`tests/integration/test_reminder_flow.py` conecta la tool real `propose_reminder`,
la presentación/confirmación del processor, `ProposalExecutor`, PostgreSQL real,
`RemindersWorker` y `TelegramNotifier` con transporte HTTP simulado.

Tres casos: confirmado/200, confirmado/503 seguido de 200, y descartado.
Se comprueba que antes de confirmar no hay fila ni aviso; tras confirmar hay
una sola fila con `source_action_id`, UTC normalizado y hora local conservada;
el 503 deja `pending`, la entrega pasa a `fired` con `fired_at`, y repetir botón
o ciclo no repite efectos en los caminos observados. Descartar no crea fila.

Límites: selección del modelo y Telegram están simulados. No se valida semántica
LLM, recepción humana, concurrencia de workers ni envío exactamente una vez
ante fallo de red ambiguo/crash entre envío y `mark_fired`. Mantener una réplica.
No se han insertado fixtures en Supabase ni enviado mensajes desde esta sesión.

### Procedimiento previsto para el recordatorio real

1. Con el propietario, pedir en el bot privado un recordatorio útil a pocos
   minutos vista, con nombre reconocible y hora/zona inequívoca.
2. Revisar el bloque canónico y pulsar Sí. No confirmar por el usuario desde
   scripts, no insertar por SQL ni reinyectar updates históricos.
3. Comprobar en lectura la fila/propuesta y sus timestamps/procedencia; esperar
   el polling configurado y verificar recepción humana del aviso.
4. Consultar los recordatorios mediante mensaje nuevo y verificar `fired`.
   Observar un ciclo posterior sin segundo aviso. Guardar sólo metadata técnica.
5. Si falla, registrar el estado y diagnosticar antes de repetir. No atribuir
   un nuevo intento a un update ambiguo ni ampliar gobernanza por hallazgos UX.

### E2E Telegram automatizado autorizado — PASS, 2026-10-17

Tras la preparación anterior, el propietario autorizó expresamente una única
petición a cinco minutos, incluida la confirmación por Playwright y la
comprobación del aviso, con los límites de inferencia vigentes. Esta autorización
acotada sustituye la intervención manual del paso 2 sólo para este caso:
se pulsó el botón Core de la propuesta revisada, sin escrituras SQL, replay,
segunda petición, nueva consulta LLM ni modificación de configuración.

Evidencia limitada a metadata; timestamps canónicos de PostgreSQL en UTC:

| Evidencia | Resultado |
|---|---|
| Interacción origen | `da42a3b1-e338-445d-982e-ad7a3082eb7a`, `completed`, recibida `00:13:46.519805Z` |
| Propuesta única | `5f9a33f1-dbbc-4522-b252-cc44acd8c6e5`, creada `00:13:52.553639Z`, terminal `executed` |
| Confirmación Core | `e83f099b-80f1-4dab-9331-59f49d56bd07`, `completed`; confirmada `00:15:02.393886Z`, ejecutada `00:15:02.573944Z` |
| Recordatorio único | `fc29046b-f55f-4096-a693-df77b31b19a5`, no recurrente, `source_action_id` enlazado a la propuesta |
| Hora programada | `00:18:50Z` = `02:18:50+02:00` Europe/Madrid; unos 303 s desde admission |
| Entrega durable | `fired_at=00:18:51.955389Z`, retraso observado **1,955389 s** |
| Recepción Telegram | Un aviso nuevo observado por Playwright, mensaje `14411`; petición `14408`, propuesta `14409`, acuse `14410` |
| Reobservación | Un solo aviso en el chat y una sola fila; SELECT final `00:21:03.180052Z`, más de dos ciclos después de `fired_at` |
| Inferencia | Rev. 8, `ancoramind-default-r4`; origen 3 model calls / 3 Gateway requests / 3 tool calls; confirmación 0/0/0 |
| Retry/fallback | Los tres eventos LLM `completed`, `retry_count=0`, `fallback_used=false` |
| Coste | Estimado agregado **0,00378450 USD**, `pricing_snapshot`; coste real no informado (`NULL`), no se interpreta como cero |

Readiness posterior HTTP 200, worker sano y cero vencidos. No se pulsó de nuevo
el botón para provocar un duplicado ni se creó otro recordatorio. La observación
sin duplicados en este recorrido no certifica exactly-once ante crash/timeout ni
cierra recurrencia/snooze, BL-23/39/40/48 o toda la matriz M5.

La consulta DB se hizo con transacción de sólo lectura y timeout. El proceso
local tenía `ANCORA_DATABASE_URL` apuntando a loopback: los primeros SELECT no
aportaron evidencia productiva. Se corrigió la fuente leyendo explícitamente
la URL Supabase ya existente en `.env`, sin imprimirla ni cambiar el entorno.
Para comparar tiempos se usa el reloj canónico DB: el navegador y el servidor
mostraron desfase, no se calcula latencia cruzando ambos relojes.

## Entrega 2: vehículo y mantenimiento — E2E autorizado PASS, 2026-10-17

El propietario autorizó continuar con el siguiente flujo. Se realizó por
Playwright en el mismo bot privado, sin cambio de baseline ni configuración:
un alta de vehículo ficticio sin matrícula/VIN, un mantenimiento ficticio sin
importe/documento/recordatorio y una consulta de vehículo e historial. Ningún
vehículo real se seleccionó como target ni se ejecutó una limpieza implícita.
Los datos de prueba quedan persistidos e identificados por su apodo; eliminarlos
requeriría otro alcance autorizado. No se usaron fixtures de integración remotos.

Antes de empezar, SELECT por usuario/apodo: **0 vehículos coincidentes**.
Tras cada propuesta presentada y antes de pulsar Sí: 0 filas canónicas del
vehículo/mantenimiento correspondientes. Se revisaron los campos visibles y
el target persistido; sólo se pulsó una vez el Sí de cada propuesta.

| Paso | Evidencia técnica |
|---|---|
| Vehículo propuesto | Origen `2757a84f-010c-4b3e-84ee-5ea74c66c4fe`; propuesta `e991ee70-5fbf-4ec0-a746-51549740b9a8`, `pending_confirmation` antes de confirmar |
| Vehículo confirmado | Confirmación `3ee2ac00-9571-4552-b7ff-69b62f3af290`; propuesta `executed`, `executed_at=00:26:13.457358Z`; vehículo `4fbed12d-455b-43f0-91c5-afe78675e86c` |
| Mantenimiento propuesto | Origen `965270ce-3968-47dc-9f49-de4e98590cda`; propuesta `9d04a474-5900-48a0-b50e-d493833ba42b`, `pending_confirmation`, FK al vehículo esperado |
| Mantenimiento confirmado | Confirmación `d862b99c-b134-470f-9dfb-7b68d7ede35d`; propuesta `executed`, `executed_at=00:27:45.182908Z`; fila `4b4deacb-da6c-4104-9e58-15aab8bf0eff`, `source_action_id` correcto |
| Lectura final | Interacción `05da8b1e-59ab-4122-a48d-05e6011743f9`, `completed` a `00:28:27.638217Z`; respuesta Telegram con el vehículo y exactamente un mantenimiento |
| Correspondencia UI | Mensajes `14412–14414`: alta/propuesta/acuse; `14415–14417`: mantenimiento/propuesta/acuse; `14418–14419`: consulta/respuesta |

Los campos ficticios recibidos en la consulta coinciden con los almacenados:
marca/modelo/año y apodo del vehículo; fecha `2026-10-17`, kilometraje 1000,
descripción/taller solicitados y un trabajo realizado. `cost_amount`,
`cost_currency` y `source_document_id` son NULL, sin importes inventados.
Auditoría final: **un vehículo, un mantenimiento y dos propuestas ejecutadas**;
ninguna propuesta nueva por la consulta READ. Todos los SELECT fueron scoped
por usuario, parametrizados y en conexión de sólo lectura con timeout.

### Inferencia y comprobaciones

| Interacción | Model / Gateway / tools | Coste estimado USD |
|---|---|---|
| Alta vehículo | 2 / 2 / 2 | 0,00253050 |
| Proponer mantenimiento | 3 / 3 / 3 | 0,00375380 |
| Consulta de historial | 3 / 3 / 3 | 0,00370210 |
| Ambas confirmaciones Core | 0 / 0 / 0 cada una | Sin inferencia |

Total inferencial estimado **0,00998640 USD**; coste real no informado. Todos
los eventos LLM consultados usan revisión 8/`ancoramind-default-r4`, sin retry
ni fallback. Las cinco interacciones están `completed`, sin error registrado.
Grafana mostró llamadas `find_vehicle` y `get_vehicle_maintenance_history`
completadas; son contadores agregados, no evidencia por sí solos de su run.

Pruebas focales existentes de modelos/dinero/servicio/tools: **41 passed**.
No hay cambio de producto, prompts, migraciones, flags ni despliegue. Los gates
globales de la preparación anterior siguen siendo el baseline local, no una
nueva ejecución de las suites completas para esta prueba documental.

Alcance no cubierto: factura/imagen/OCR, importe-divisa, normalización de
matrícula, ambigüedad entre varios vehículos, aislamiento multiusuario real o
regresión adversarial completa. No se cierra toda la vertical documental M4.
Observación UX no bloqueante: el bloque de mantenimiento no muestra el nombre
del vehículo objetivo; aquí se verificó su FK por SELECT antes de confirmar.
Se registra el hallazgo sin ampliar gobernanza ni cambiar código en esta ventana.

## Entrega 3: calendario/recurrencia/snooze — 2026-10-17

**PASS funcional asistido**, con limitaciones de presentación registradas en
BL-49: no es un PASS de revisión humana autosuficiente de la propuesta Telegram.
El propietario autorizó continuar con este flujo y se anunció su alcance antes
de empezar: una serie diaria de dos ocurrencias (ayer/hoy) y un snooze de 5 min
del aviso de ayer, sin repetición indefinida ni calendario externo.

### Baseline y alcance

- App Railway continúa en `b104d8f`, deployment
  `61c687a0-a856-4fbd-86ff-215ee9acf1aa` SUCCESS, CI del mismo SHA verde.
  HEAD local `9eb97fe` contiene la documentación/pruebas de la preparación y
  no está publicado; no se confundió su SHA con el código servido.
- Readiness inicial HTTP 200, revisión 8, DB/Gateway/processor/worker sanos.
- Cero eventos/recordatorios coincidentes con el título de prueba antes de
  empezar, verificados por SELECT parametrizado scoped al propietario.
- Se solicitaron fechas/offset explícitos: ancla `2026-10-16T02:43:00+02:00`,
  fin un minuto después, `daily`, intervalo 1 y `until` inclusivo
  `2026-10-17T02:43:00+02:00`. Aviso vinculado con antelación cero.
- Se comprobó el payload persistido antes del Sí: evento aún no escrito,
  frecuencia/límite/aviso correctos. Las escrituras se realizaron exclusivamente
  mediante el Core por botones Telegram, nunca por SQL. El provider persistido
  es `noop:…` (marcador sintético), no una sincronización externa.

### Recorrido y auditoría

| Paso | Evidencia |
|---|---|
| Crear evento con aviso | Origen `13dd6340-e933-4ce1-beed-c8bb8c2676be`; propuesta `2990107e-38db-42cb-8f9f-cdd11f665d94`; confirmación `8a002479-1bad-46ed-ad96-aaeae1701080` |
| Ejecución Core | Propuesta `executed`, `executed_at=00:38:14.726685Z`; evento `f799f761-c9b3-443a-a046-fa624f7577cd`, una sola fila anclada al 16/10 |
| Primer aviso, atrasado a propósito | Raíz `b400e668-0fc0-4558-ba59-54044a34d360`, `fired_at=00:38:54.422342Z`; aviso observado en mensaje `14423` |
| Avance de recurrencia | Hijo `ea84b794-adba-443d-aeec-bde297fbfbf4`, inicialmente `pending`, `trigger_at=00:43:00Z`, parent=raíz y misma regla/source_action_id |
| Consulta por rango 16–18/10 | Interacción `f0a3ae21-72aa-43b5-b739-e1e4f8ec64c9`, `completed`; respuesta `14425`: ocurrencias 16/17 a 02:43–02:44, ninguna el 18; sigue una sola fila de evento |
| Proponer snooze de raíz disparada | Origen `471e3ea2-e78d-4618-9451-a74900e0223d`; propuesta `565e79cd-3cc5-40d7-bfd8-ab3c0ce06dda`, target raíz y `minutes=5` verificados; sin copia canónica antes del Sí |
| Confirmar snooze | Confirmación `e061d5ff-b62e-45f8-9491-61934781c4e7`; propuesta `executed`, `executed_at=00:40:57.245380Z` |
| Copia snoozed | `8c78f37f-aa8a-42be-beb3-a5c0a6d18df9`, `trigger_at=00:45:57.315321Z`, parent=raíz, source_action_id=snooze, recurrence_rule=NULL |
| Segundo aviso de serie | `fired_at=00:43:55.391523Z`, **55,391523 s** tras su trigger, dentro de un polling de 60 s; mensaje `14429` |
| Aviso de snooze | `fired_at=00:46:55.954530Z`, **58,639209 s** tras su trigger; mensaje `14430` |

Los mensajes `14420–14422` corresponden a petición/propuesta/acuse del evento;
`14424–14425` a consulta/respuesta; `14426–14428` a snooze/propuesta/acuse.
Se observaron los tres avisos previstos. Al consultar a `00:47:13.489645Z`, las
tres filas estaban `fired`, sin cuarta ocurrencia ni recordatorio futuro.
El snooze no cambió el trigger del hijo diario ni la regla del evento.

### Consumo y pruebas

| Interacción | Model / Gateway / tools | Estimado USD |
|---|---|---|
| Proponer evento | 2 / 2 / 2 | 0,00252150 |
| Consultar calendario | 2 / 2 / 2 | 0,00253020 |
| Solicitar snooze | 4 / 4 / 5 | 0,00512830 |
| Dos confirmaciones | 0 / 0 / 0 cada una | Sin inferencia |

Total **0,01018000 USD estimados**; coste real no informado. Rev. 8/r4 en los
eventos de uso, retry_count=0, fallback_used=false. Cinco interacciones
`completed` sin error registrado; ninguna propuesta adicional de la lectura.
69 unitarias focales y 18 integraciones PostgreSQL loopback/base `_test`
superadas. Un preflight local sin `ANCORA_TEST_ADMIN_DSN` se detuvo antes de
ejecutar tests; se repitió usando los defaults locales comprobados del harness,
sin alterar el destino productivo. No cambios de código, flags, migraciones,
provider, despliegue, webhook ni límites de inferencia.

### Hallazgos y límites

- **BL-49, presentación pendiente:** el bloque Core del evento no muestra
  recurrencia/until/aviso; el snooze sólo muestra `snooze_reminder`, sin target
  ni minutos. Se informó del defecto y se confirmó sólo tras revisar el payload
  real por SELECT, dentro del alcance de prueba autorizado. Esto no es el flujo
  normal que debe exigirse al usuario family&friends: falta validarlo/corregirlo
  antes de declarar estas confirmaciones listas para participantes.
- El aviso vinculado duplica «Recordatorio:» y el mensaje atrasado atribuye el
  retraso a parada/reinicio, aunque aquí se programó un pasado deliberado.
  Observaciones de texto, no prueba de caída del servicio.
- Se valida recurrencia diaria acotada y expansión desde un ancla pasada;
  no es E2E de yearly/monthly, salto DST, retención a 90 días, aislamiento
  entre personas ni comportamiento exactamente una vez bajo red/crash.
- Los registros ficticios quedan persistidos para trazabilidad, sin avisos
  futuros de esta serie. No se ejecutó eliminación ni limpieza implícita.

## Entrega 4: imagen/PDF escaneado — 2026-10-17

**PDF sintético PASS; imagen parcial.** El propietario autorizó el siguiente
flujo acordado. Alcance anunciado: un PNG y un PDF raster de una página, sin
datos personales, envío único de cada uno y una consulta conjunta posterior.
Se pidió sólo archivo/resumen/consulta; ninguna acción derivada.

### Preparación y ruta existente

- Git limpio al empezar, HEAD local `b8170a4`; sus diferencias con el SHA
  servido no afectan la ingesta documental. Deployment app sigue en
  `61c687a0-a856-4fbd-86ff-215ee9acf1aa`, SHA `b104d8f`, SUCCESS.
  La consulta nueva de GitHub no devolvió evidencia utilizable de checks;
  el resultado verde anterior consta en el baseline de esta campaña.
- Readiness `00:55:25.613090Z`, HTTP 200, DB/Gateway/processor/worker sanos,
  revisión 8. Cero documentos de estos nombres antes de empezar; borrador vacío.
- Snapshot real: `ancoramind-vision` → **`ancoramind-vision-r1`**, capacidades
  vision/structured_output; default r4; embeddings r1. No se publicó r2 ni se
  cambió modelo, configuración, webhook, flags o despliegue.
- Límites activos por ejecución: 6 model calls, 8 Gateway requests, 12 tool
  calls, 120 s y 0,10 USD estimados. Pricing sólo incluye default-r4: no se
  infiere que la visión sea gratuita ni que el límite monetario cubra costes
  no medidos. Se acotó el ensayo a una página por adjunto.
- Fixtures generados con PyMuPDF ya instalado bajo
  `tmp/visual-e2e-20261017/` (ignorado por Git), etiquetas SIN VALIDEZ/datos
  ficticios. El PDF tiene sólo una imagen, `has_extractable_text=False`, y
  produce una página visual con el preparador real.
- Se envió el PNG como archivo, sin compresión Telegram: se valida imagen
  adjunta (`image/png`), **no** el camino de foto comprimida.
- El selector Playwright rechazó el primer path local antes de subir;
  se copiaron ambos fixtures a su raíz permitida `.playwright-mcp`, conservando
  hashes. No se repitió ningún envío al bot por ese ajuste local.

### Origen sintético y conservación

| Archivo | Bytes | SHA-256 |
|---|---|---|
| `ancora-visual-e2e-20261017-image.png` | 52254 | `2fbe54cd6b4c2c48b64357ffba056b147298411fd9c85f5a45b4943b606b0f06` |
| `ancora-visual-e2e-20261017-scan.pdf` | 56715 | `982b997332576c520772172ad2ad7ac1cddc1ba4ab938af764db6e98e465058a` |

- PNG: ficha de inventario; referencia IMG-ZAFIRO-731, fecha 17/10/2026,
  carpetas verdes, 7 unidades, estante azul. Estos valores no se dieron en
  la caption: debían leerse de los píxeles.
- PDF: recibo ficticio PDF-CORAL-946, 17/10/2026, material de demostración,
  2 unidades a 12,40 EUR, total 24,80 EUR. La caption tampoco incluía valores.
- Ambos originales se descargaron mediante lectura autenticada de Storage
  tras resolver sus filas scoped al propietario; los hashes coinciden con
  los fixtures y la DB. El PDF conservado sigue sin texto embebido. No se
  generaron URLs públicas ni se expusieron storage keys/credenciales.

### Interacciones y resultados

| Paso | Interacción | Mensajes Telegram | Resultado |
|---|---|---|---|
| PNG | `ecd6a642-27cb-4cd9-a533-610358315f69` | `14431–14432` | `completed` 00:57:28.034939–00:57:47.002593Z; archivo/extracción correctos, fecha ausente en respuesta |
| PDF raster | `88171316-8bbc-4cfb-b0e9-53bf68f1f3d4` | `14433–14434` | `completed` 00:59:09.441469–00:59:24.459411Z; todos los campos pedidos correctos |
| Consulta de ambos archivados | `4dff7922-9dcc-425c-a597-bae91457e107` | `14435–14436` | `completed` 01:00:37.376947–01:00:50.334270Z; nombres/IDs y datos recuperados, persiste omisión de fecha del PNG |

- Documento PNG `0c65df4b-c2f5-47a8-bcf5-90f4a1f2b4fd`, extracción
  `eed2f7bd-0c74-488a-9139-3b1ba515a17c`.
- Documento PDF `07dcb981-1789-446a-b9d0-e38c55865c4b`, extracción
  `eeccad07-f2e5-4f59-a2e0-b4d614b265a8`.
- Dos extracciones estructuradas correctas, modelo auditado como alias
  `ancoramind-vision-r1`, provider de adaptador `OpenAI`, prompt 1.2/schema 1.1.
  No se deduce de esa etiqueta el proveedor/modelo físico upstream.
- Ambas confianzas declaradas 0,99, **no precisión calibrada**. Suggested actions
  vacías. Dos índices `completed`, embeddings r1 de 1536 dimensiones.
- Final de lectura: siguen dos documentos/dos extracciones, cero propuestas
  creadas desde el comienzo del flujo. No hubo confirmaciones: adjuntar es
  intención de ingesta según la excepción documental existente.
- Consulta posterior: tres llamadas default-r4 y ninguna visión; no se volvió
  a hacer OCR. Cinco tools registradas, sin nuevas escrituras documentales.

### Hallazgo reproducido sin cambio de producto — BL-50

La extracción del PNG contiene `document_date=2026-10-17`, pero su `summary`
no incluye la fecha. `_extraction_record` sólo transmite tipo/resumen/confianza,
no campos estructurados como `document_date`, `entities` o `amounts`. Se pasó
la extracción persistida por ese helper local: la fecha desaparece del record.
Lo usan tanto la ingesta como `get_document`; explica que la fecha se pierda
en la respuesta inicial y la consulta. En el PDF todos los datos pedidos sí
están en el resumen y llegan correctamente. No es un fallo demostrado de OCR
ni se debe resolver inventando la fecha desde el filename/historial.

### Uso, coste y límites — BL-51

| Paso | Model / Gateway / tools del ledger | Visión | Estimado default USD |
|---|---|---|---|
| PNG | 3 / 3 / 2 | 1 llamada, 4887 ms | 0,00261610 |
| PDF | 3 / 3 / 2 | 1 llamada, 3457 ms | 0,00269750 |
| Consulta posterior | 3 / 3 / 5 | 0 llamadas | 0,00414860 |

Rev. 8 en los nueve eventos de uso, todos `completed`, retry_count=0,
fallback_used=false. **0,00946220 USD es sólo el subtotal estimado conocido
de conversación, no el total del flujo.** Ambas llamadas visuales tienen
estimated_cost/actual_cost NULL; las nueve no informan coste real.
Además, el índice confirma embeddings completados, pero el adaptador actual
no reserva esos HTTP en ExecutionBudget ni escribe LlmUsageRecorder; los
contadores model/Gateway anteriores no incluyen embeddings y no prueban el
total de solicitudes upstream. Brecha de contabilidad/gobernanza registrada
separadamente en BL-51; no hubo bypass ni modificación desde esta sesión.
No hacer un benchmark económico ni declarar cobertura completa del presupuesto
con este ledger incompleto. No se inició otra prueba inferencial.

### Verificación y alcance residual

- 53 unitarias documentales focales, **1504 unitarias globales**, y 7
  integraciones de repositorio documental contra PostgreSQL local `_test`:
  superadas. Advertencia OTLP local sin Collector `localhost:4318` al terminar
  la suite, no evidencia de caída del Collector productivo.
- No es benchmark representativo: fuentes sintéticas nítidas, español impreso,
  una página; no valida manuscritos, fotos degradadas, PDFs mixtos/largos,
  límite multipágina, aislamiento con segunda cuenta ni seguridad semántica.
- BL-6 no se cierra: falta resolver pérdida de campos (BL-50), contabilidad
  completa (BL-51) y acordar benchmark con ruta/precio/presupuesto. La migración
  a otro alias/modelo no forma parte de esta autorización.
- Los dos originales y extracciones quedan persistidos para trazabilidad;
  sin limpieza implícita ni mutaciones de vehículo/calendario/recordatorios.
  Cambios versionados de esta entrega: sólo documentación.
- Cierre a `01:04:51.887574Z`: readiness HTTP 200, revisión 8 y componentes
  DB/Gateway/processor/worker sanos; circuit sigue `unknown`. Dos documentos,
  dos extracciones y cero propuestas; último mensaje `14436`, borrador vacío.
  Ruff global, `mypy src/` (174 módulos) y `git diff --check` limpios.
  Sin commit ni despliegue desde esta entrega.

## Invitaciones y administración: preparación paralela

### E2E autoaprobado remoto autorizado, sin LLM — 2026-10-17

**PASS acotado de autoactivación**, pedido expresamente por el propietario.
Misma cuenta `account=2`/usuario `8887598395`, misma app/SHA `bee0062`. Se
preservan los cambios documentales del E2E manual; no implica cierre global.

#### Síntoma previo del propietario: no recibió respuesta

SELECT de metadata, sin leer el contenido del mensaje: interacción
`8625d9b1-068f-4d0d-85ec-7844b2b68380`, message_id `487`, recibida
`09:37:43.726371Z`, rejected/user_not_allowlisted; sin logical_response,
model/Gateway/tools=0. El acceso estaba revocado y los flags OFF tras la
ventana manual. No se reinyectó ni procesó ese mensaje libre tras el alta.

Causa verificada: la política de admisión rechaza sin autorización; el service
no crea respuesta para ese rechazo y el processor sólo reclama accepted/
response_ready. No demuestra fallo del modelo ni de entrega Telegram. Aviso
genérico Core propuesto en **BL-52**, no implementado. Debe preservar rechazo,
outbox/idempotencia y límites de notificación propios: los límites actuales
sólo se evalúan para accepted. No activar un Agent para responder a rechazados.

#### Habilitación, ejecución y cierre

- Baseline `5b7c5d96-30e1-42d6-9503-5aaff8924157` SUCCESS, tres flags false,
  cero pending/autorizaciones activas del evaluador, dos invitaciones existentes.
  Checks quality/integration/collector-config del SHA completo
  `bee00628841225c87721cc95cc8d5760abd7f9e9` success, revalidados.
- Reutilizados los secretos de la ventana anterior sin leerlos en outputs ni
  crear/rotar otros; tres flags temporalmente true. Habilitación deployment
  `ed35acaf-4777-4174-9391-4e3b9c5bcf98`, SUCCESS `09:42:59.420Z`.
- Login del panel, **Auto-aprobar marcado explícitamente**; emisión una vez y
  transferencia directa al chat sin imprimir código ni leer texto crudo del
  DOM. Invitación `ce9260d4-4436-436b-9c4b-ce930ab8d3c0`, max_uses=1,
  auto_approve=true, expires_at `09:48:27.031672Z`; termina exhausted, un uso.
- Solicitud `47cf9262-fe2f-452b-a5eb-5cedb837f3d0` approved desde su creación;
  requested_at=decided_at=authorized_at=`09:43:27.425177Z`, actor `lealp22` y
  motivo heredados de la invitación. **Ninguna llamada de aprobación manual.**
- Telegram mostró exactamente «✅ Acceso concedido. Ya puedes escribir con
  normalidad.»; `/help` posterior devolvió ayuda fija. No el texto de pending.
- Revocación API `09:44:30.120088Z`; siguiente `/help` rejected
  `09:44:30.504698Z`, antes del redeploy, sin reinicio.
- Logout borra sessionStorage; tres flags false. Deployment de cierre
  `13cf938f-595c-4509-be0d-463fceae1b95`, SUCCESS `09:45:31.843Z`, mismo SHA y
  una réplica. Allowlist comprobada igual; sin cambios webhook/modelo/runtime/
  Gateway/Collector. No se modificaron invitaciones ajenas ni el código previo.
- Cierre `09:46:15.953339Z`: readiness 200, rev.8, DB/Gateway/processor/worker
  sanos, circuit unknown; panel/APIs 404. Cuenta revocada, sin pending; código
  agotado. Por eso volver a escribir libremente en esa cuenta seguirá sin
  respuesta hasta alta nueva o implementación de BL-52. No dejarla activa para
  evitar silencio, ni ampliar acceso de forma implícita.

| Paso | Interacción | update_id / message_id Telegram | Estado |
|---|---|---|---|
| Canje auto | `68389d60-a1db-4743-9ba7-50ea50b322f7` | `978199103` / `488` | completed `09:43:29.358507Z` |
| `/help` inmediato | `e528d5e5-b100-4a63-a36a-7e55023ec236` | `978199104` / `490` | completed `09:43:57.812474Z` |
| `/help` revocado | `dc623e06-94cd-48a8-994c-c87ec49c3696` | `978199105` / `492` | rejected, user_not_allowlisted |

Tres interacciones: agent_started_at NULL, model/Gateway/tools=0 y cero
llm_usage_events. Dos outbox/entregas completed, un chunk cada una, message_id
`489` (acceso concedido) y `491` (ayuda). Sin inferencias, ningún coste LLM del
circuito. En el navegador IDs visuales `53–57`; no confundirlos con Bot API.
Después de revocar sólo aparece el `/help` propio, no respuesta adicional;
borrador vacío. No se volvió a analizar/capturar el comando con el código.

65 unitarias focales passed; suite global **1536 passed**, Ruff/mypy (174
módulos) limpios. Advertencia OTLP local sin Collector localhost:4318 no
invalida aserciones ni observa Collector remoto. Sin nueva ejecución de
integración local (la evidencia anterior 183/1 skipped sigue histórica).
Sólo documentación versionada, sin commit ni código de producto.

Pendientes: expiración/cupo/replay remoto, aislamiento real entre cuentas,
timeout del panel, aviso sin acceso BL-52 y demás gates del piloto. BL-49/50/51
continúan abiertos. No se incorporó un participante con datos personales.

### E2E manual remoto autorizado, sin LLM — 2026-10-17

**PASS del circuito manual; BL-24/43 no cerrados globalmente.** El propietario
facilitó `https://web.telegram.org/a/?account=2` y autorizó expresamente el
servicio actual, habilitación temporal y cierre posterior. Sólo comandos
deterministas `/start`, `/pair` y `/help`, sin datos documentales ni Agent.

#### Baseline, cambios temporales y cierre

- HEAD/producción al iniciar: `bee00628841225c87721cc95cc8d5760abd7f9e9`;
  deployment `aec207ca-6930-4e3c-b9d6-600d39bd06d3`, SUCCESS. Checks del mismo
  SHA `quality`, `integration`, `collector-config`: success, verificados por API.
  Wait for CI sigue desactivado y no se cambió.
- Tres flags ausentes (defaults OFF), panel y APIs pairing → 404. Admission y
  processor activos, allowlist técnica con un solo usuario, evaluador fuera.
  Runtime rev. 8 sin cambios. Inventario previo: cero solicitudes/autorizaciones;
  una invitación antigua `5826bff0-b642-4d57-93c8-5e4d5c1fa619`, vencida por
  fecha (05/10) aunque su estado siga `active`, sin usos; **no se tocó**.
- `RUNTIME_CONFIG_ADMIN_TOKEN` existente preservado. Añadidos sólo
  `ADMIN_DASHBOARD_TOKEN` y `TELEGRAM_PAIRING_CODE_PEPPER` ya preparados en el
  entorno local, comprobados distintos entre sí y del token CLI. Se transfirieron
  sin imprimir sus valores, mediante un puente temporal loopback cerrado tras
  usarse; no se subió `.env` ni se guardaron credenciales en Git/evidencia.
- Habilitados `TELEGRAM_PAIRING_ENABLED`, `TELEGRAM_PAIRING_ADMIN_ENABLED` y
  `ADMIN_DASHBOARD_ENABLED`; redeploy del mismo SHA
  `d4567737-ec8c-4fc1-b16a-099dd6259103`, SUCCESS `09:10:45.820Z`.
- Tras revocar el acceso, los tres flags quedan explícitamente **false** (antes
  ausentes). Redeploy de cierre `5b7c5d96-30e1-42d6-9503-5aaff8924157`, SUCCESS
  `09:15:14.507Z`, mismo SHA, una réplica. Secretos añadidos conservados según
  runbook; no rotados ni borrados. Sin cambios en webhook/allowlist/modelo,
  revisión runtime, Gateway o Collector.
- Cierre `09:15:57.731492Z`: readiness 200 y DB/Gateway/processor/worker sanos,
  revisión 8; circuit `unknown`. Panel y ambas APIs pairing/panel → 404.

#### Cuenta y auditoría de acceso

Identidad evaluadora observada desde el update autenticado: `8887598395`,
chat privado del mismo ID, no suministrada al LLM ni añadida a allowlist.
Operador de las decisiones: `lealp22`; motivos de prueba/cierre explícitos.

- Invitación emitida mediante el panel: `3cff13d0-cfad-4a27-b2ee-8298d8cb7f33`,
  un uso, manual (`auto_approve=false`), TTL 5 min, caduca `09:17:17.307893Z`.
  Se consumió una vez y terminó `exhausted`, use_count=max_uses=1.
- Solicitud `d1320fec-db10-44a3-a334-0c032d75ea96`: pending `09:12:17.777186Z`,
  approved por API administrativa protegida `09:13:12.414108Z`. El panel no
  tiene botón de aprobación; no se añadió uno ni se escribió SQL.
- Autorización revocada por API a `09:13:47.956743Z`; siguiente update rechazado
  sin reinicio, antes del redeploy de cierre. Cero solicitudes pending y cero
  autorizaciones activas del evaluador al terminar.

| Paso | Interacción | update_id / message_id Telegram | Resultado UTC |
|---|---|---|---|
| `/start` antes del alta | `1e1a2134-79c6-454c-b0ae-600e08df6a30` | `978199097` / `480` | rejected `09:06:32.405848`, user_not_allowlisted |
| Canje privado | `9d0b273f-7648-4de9-a71a-394f6ce6650f` | `978199098` / `481` | completed `09:12:20.007688`, respuesta fija de solicitud recibida |
| `/help` pending | `4a608602-5655-404c-be31-e347384c9bfb` | `978199099` / `483` | rejected `09:12:43.254004`, sin autorización |
| `/help` approved | `f856f68f-604e-47e1-9e2b-19af12066fac` | `978199100` / `484` | completed `09:13:22.440368`, ayuda fija recibida |
| `/help` tras revocar | `a9b5626c-abbc-49cc-a437-5cf83c9cb1e6` | `978199101` / `486` | rejected `09:13:48.447550`, sin reinicio |

Las cinco interacciones: agent_started_at NULL, model/Gateway/tools=0, cero
llm_usage_events. Coste inferencial de este circuito: **sin inferencias**, no
estimación de precio desconocido. Dos respuestas/outbox y dos entregas
`completed`, un chunk cada una, message_id `482` y `485`; ninguna respuesta
extra tras los rechazos. IDs visuales del navegador distintos de message_id
del Bot API, no intercambiarlos. Cero documentos/propuestas del evaluador.

#### Panel y límites de la evidencia

- Shell por HTTPS 200; JSON sin token, incorrecto o token CLI → 401; API CLI con
  token del panel → 401 y con token CLI → 200. Login correcto, tabla de
  invitaciones y revisión 8 visibles; no-store, DENY y CSP comprobados.
- Token presente en sessionStorage, no en localStorage; cierre explícito borra
  token/actor y vuelve al login. Se vació también el input oculto del token.
  No se esperaron 30 min: expiración por inactividad **no validada en real**.
- Incidencia de manejo de evidencia del agente: un filtro de diagnóstico para
  `/pair ` no reconoció el espacio no separable del DOM de Telegram y devolvió
  el código en una salida de herramienta. No se copia ese valor aquí. El código
  era de un uso y ya estaba agotado; autorización posteriormente revocada y
  flags OFF. Las lecturas posteriores reconocen whitespace Unicode o extraen
  sólo metadata. Esto no acredita ausencia absoluta de credenciales en el
  transcript y no debe describirse como ejecución íntegramente metadata-only.
- La redacción del payload durable fue comprobada localmente; no se verificó
  descifrado productivo en esta ventana (clave no disponible localmente). No
  se solicitó ni expuso esa clave para ampliar el ensayo.
- No se ejecutaron autoaprobación remota, expiración/cupo/replay remoto,
  aislamiento de datos/consentimiento entre dos cuentas, LLM ni benchmark. Se
  conserva la evidencia local previa; no cerrar T4 completo ni BL-24/43.
- Registros de acceso/interacciones conservados según política existente; no
  limpieza SQL, eliminación de chats ni revocación de invitaciones ajenas.
- Verificación local tras la ventana: 1536 unitarias passed, Ruff global y
  `mypy src/` (174 módulos) limpios, diff check limpio. No se repitió integración
  PostgreSQL en esta ventana; resultado previo 183/1 skipped no es una ejecución
  nueva. Se cerró pestaña admin; puente local detenido/eliminado; sin staged
  changes Railway. Cambios versionados sólo docs, sin commit en esta ventana.

### Preparación local autorizada — 2026-10-17

- Partida limpia en `bbed7bf` (la documentación de la entrega 4 ya estaba
  registrada en ese commit). Se confirmaron BL-49/50/51 documentados y abiertos.
- Sin consultas a infraestructura remota, nuevos secretos, allowlist, flags,
  despliegues, inferencia ni mensajes a participantes. Cambios sólo tests/docs.
- `tests/integration/test_onboarding_admin_flow.py` añade 7 casos ASGI reales
  contra PostgreSQL loopback/base dedicada `_test`, no DBs productivas. Conecta
  emisión/listado del panel, pairing privado, aprobación/rechazo CLI y admisión.
  Manual/auto, duplicado, redacción del código descifrado, HMAC, auditoría y
  revocación en update nuevo; los estados denegados no autorizan. Sender
  simulado y runner que falla si se invoca; cero uso LLM en estos casos.
- `tests/unit/test_admin_dashboard.py`: 32 casos nuevos (43 del fichero)
  cubren todas las ocho rutas JSON frente a token ausente/incorrecto/CLI,
  no-store y actor/motivo requerido en las cuatro mutaciones. Se desactiva
  lectura de `.env` en su helper. No se modificó implementación productiva.
- 70 unitarias focales passed; global **1536 passed**. Suite PostgreSQL local
  completa **183 passed, 1 STT live skipped** (opt-in forzado OFF). Las pruebas
  existentes de documentos/propuestas cubren aislamiento de repositorios;
  todavía no aislamiento E2E con dos cuentas. Ruff global/mypy src (174 módulos)
  limpios. Advertencia OTLP local sin Collector no demuestra caída remota.
- Checklist y comando reproducible con guard loopback/_test:
  `docs/preflight-onboarding-admin.md`, enlazado desde ambos runbooks.
- No cierre de BL-24/43: quedan navegador/HTTPS/sessionStorage/temporizador
  reales, cuenta evaluadora fuera de allowlist, alcance/retención/privacidad,
  secretos por canal seguro y ventana de rollout explícita. La prueba de
  admisión llega a `accepted`, no ejecuta el Agent tras aprobar ni promete
  cancelar trabajo anterior al revocar. No se amplió la campaña runtime-config.

### Observación remota previa (no revalidada en la preparación local)

La inspección de nombres de variables Railway no encontró
`TELEGRAM_PAIRING_ENABLED`, `TELEGRAM_PAIRING_ADMIN_ENABLED`,
`TELEGRAM_PAIRING_CODE_PEPPER`, `ADMIN_DASHBOARD_ENABLED` ni
`ADMIN_DASHBOARD_TOKEN`. El código usa defaults OFF; no se activó ningún flag.

Antes del primer participante:

1. Acordar cuenta evaluadora, alcance/retención del piloto y revisión de gates
   aplicables de `docs/production-security-privacy.md`. No tratar family&friends
   como exención ni reutilizar la aceptación de audio personal para terceros.
2. Preparar secretos independientes por el canal seguro del operador, flags y
   ventana de rollout conforme a `docs/runbooks-017-telegram-pairing.md` y
   `docs/runbooks-027-admin-dashboard.md`; comprobar CI del SHA y readiness.
3. Comprobar HTTPS, APIs sin token → 401 y login del operador. El panel permite
   emitir/listar y marcar Auto-aprobar; aprobar/rechazar y revocar siguen por
   CLI/API protegida, no por botones inexistentes del panel.
4. Validar `auto_approve=false`: canje → pendiente sin Agent → aprobación o
   rechazo administrativo. Validar `true`: canje → autorización activa
   atómica sin revisión posterior. Usar invitaciones de un uso y TTL acotado.
5. Usar una cuenta fuera de la allowlist técnica: revocar y comprobar el
   siguiente update; verificar también expiración/cupo/replay y aislamiento
   de datos/propuestas entre usuarios. No cambiar allowlist para saltar pairing.
6. Acordar cierre/rollback del piloto, revocar invitaciones/autorizaciones
   temporales y mantener códigos/tokens fuera de evidencias y logs.

## Grafana: entrega acotada realizada

- Datasource `grafanacloud-prom` confirmado y seis componentes saludables con
  muestras actuales; heartbeats de processor y reminder-worker con incremento.
- Dashboard `ancoramind-health` v1, 11 paneles, creado sin sobrescribir uno
  existente; datasource seleccionado al importar, sin tocar Collector ni app.
- URL: https://tinyvan1950.grafana.net/d/ancoramind-health/ancoramind-c2b7-salud-operativa
- Correcciones versionadas: `ancora_health_heartbeat_total` y
  `ancora_telegram_admissions_total`. Las consultas anteriores no coincidían
  con los nombres exportados.
- SHA-256 JSON canónico del fichero importado:
  `78fb0dedf1493fb03806910875910450e1a50a23fc84d9f39daeb7b42eaf948b`.
  Se verificó igualdad antes del POST; sólo se seleccionó el datasource.
- Las 17 expresiones del dashboard respondieron 200/success al consultar con
  ventana de 5 min. Salud/revisión/heartbeats tienen muestras actuales;
  admission/delivery/latencias/LLM dependen del tráfico y muestran históricos.
- No se observaron muestras en 24 h para circuit, budget-exceeded, coste real
  ni tokens. No se presentan como cero ni prueba de funcionamiento. Coste
  estimado sí tiene muestras, pero no sustituye silenciosamente al real.
- El panel de salud consultado por rango conserva instancias de deployments
  anteriores: para estado actual contrastar query instantánea y readiness.
- No se configuraron alertas, no se provocaron caídas, no se rotaron secretos.

## Gates locales de esta sesión

- Unit suite: **1504 passed**.
- Integration PostgreSQL loopback/base dedicada `_test`: **176 passed,
  1 STT live skipped**; ninguna conexión de tests a producción.
- Ruff global y `mypy src/`: limpios.
- Unit tests advirtieron exportación OTLP local sin Collector en
  `localhost:4318`; no falló la funcionalidad y no es fallo del Collector remoto.
- `git diff --check`: limpio. Cambios previos de `BACKLOG.md` preservados.