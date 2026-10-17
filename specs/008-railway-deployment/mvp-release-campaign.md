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
| 4. Imagen/PDF escaneado (BL-1/6) | Adjuntar → conservar → extracción visual → resumen/consulta con procedencia | Pendiente; no habilitar rutas ni gastar inferencia adicional implícitamente |
| Paralelo: invitaciones/admin (BL-24/43) | Canje manual y autoaprobado, revocación, aislamiento y acceso administrativo protegido | Pruebas locales verdes; configuración y E2E Railway pendientes |
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

## Invitaciones y administración: preparación paralela

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