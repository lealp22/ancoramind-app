# Verification: 036 — Evidencia previa y validación pendiente

> **Fecha de registro:** 2026-10-14.
> **Estado:** desplegado y validado E2E parcialmente hasta 2026-10-16;
> Con runtime rev. 8 constan AC1/AC2 y AC5 (lista vacía); fallo terminal seguro
> validado previamente. AC4 tiene evidencia funcional histórica, no acredita por
> sí sola el baseline actual. Matriz restante pendiente.

## 1. Evidencia funcional aportada por el propietario

### Flujo trivial TODO — resultado esperado confirmado

1. Crear «Prueba Telegram 01» generó propuesta con botones Sí/No.
2. Pulsar Sí confirmó la ejecución.
3. Añadir «comprar café» sin campos opcionales inicialmente falló y no
   persistió. Tras actualizar el esquema, respondió que se había añadido
   sin pedir confirmación; la consulta mostró una sola tarea pendiente.
4. El propietario confirmó que completar, ejecutar `/new` y consultar
   completadas funcionaron como se esperaba.

Esto cubre un recorrido concreto de BL-46, no toda su matriz: no se probaron
en este intercambio notas ni reapertura ni todos los casos de revisión.

### Flujo revisable con descarte — correcto funcionalmente, redundante en UX

Petición: añadir «Renovar el seguro» con prioridad alta y vencimiento el
20 de octubre de 2026 a «Prueba Telegram 01».

- Agent: enumeró título, prioridad y vencimiento, y pidió confirmar.
- Core: añadió otro bloque con título, `high`, `2026-10-20T00:00:00`, TTL
  de 15 minutos y botones Sí/No.
- Pulsar No devolvió «Propuesta descartada».
- Consulta posterior: solo «Comprar café» completada; la rechazada ausente.
- La respuesta añadió que no había propuestas pendientes y ofreció
  reproponer la tarea descartada sin petición del usuario.

**Límite de evidencia:** no se recogió la traza de tools de ese último
turno. No se puede concluir que la afirmación de pendientes se hiciera sin
`list_pending_proposals`. Sí se observa contenido ajeno a la consulta y
una invitación innecesaria a rehacer lo rechazado.

## 2. Evidencia operativa anterior a esta documentación

Consultas y operación realizadas en esta conversación, antes de BL-48:

- Railway, `ancoramind-app` / `production`: deployment
  `8cdfccf0-17fd-4088-b88d-5a41346cea53`, estado SUCCESS, SHA
  `40159b7dc5960acb54ff6b824fcbc83eca874630`.
- Supabase canónico estaba en `0012_document_content_hash`, sin
  `action_proposals.consent_mode`. Alembic aplicó `0013_session_token_index`
  y `0014_write_trivial_consent_mode` al destino verificado.
- Consulta posterior confirmó revisión 0014, columna NOT NULL con default
  `explicit_confirmation`, CHECK de los dos modos y el índice de sesiones.
- `/health` y `/health/readiness` devolvieron HTTP 200 / `status=ok`.
- 44 unitarias específicas y 1332 unitarias globales pasaron. Hubo avisos
  de exportación de métricas al Collector local ausente, sin fallos de tests.
- Sin reinicio/redeploy ni fixtures productivos. No se ejecutaron fresh
  install, downgrade ni integración aislada en esa operación.

El contexto anterior sitúa la prueba, pero no es una validación futura de
BL-48 ni motivo para cerrar BL-47 o todos los pendientes de specs/035.

## 3. Verificación de este incremento documental

- En el incremento inicial se crearon `spec.md`, `tasks.md` y este registro,
  enlazados desde BL-48, con toda implementación pendiente en aquel momento.
- Lectura final revisada; UTF-8, ausencia de espacios finales, referencias
  locales, unicidad de BL-48 y tareas de implementación pendientes verificadas.
- `git diff --check` limpio. No se ejecutan suites de código para este
  incremento exclusivamente documental.
- En ese incremento documental código, prompts, migraciones y configuración
  quedaron sin cambios; la implementación posterior se registra en §4.

## 4. Implementación local (tras autorización, 2026-10-14)

- Contrato `AgentReply(answer, proposal_text)`, validado por Agno/Pydantic
  dentro del runner gobernado. JSON mode con `parser_model=None`: sin nueva
  ruta/modelo ni inferencia extra. Una salida inválida no se envía ni reintenta.
- Composición con propuestas reales scoped por interacción/usuario: sustituye
  solo narración de propuestas y mantiene READ, errores y advertencias.
  Composición anterior al chequeo de vacío permite propuesta-only sin preámbulo.
- Prioridades en español y fecha TODO legible, con conservación de horas,
  fracciones y offsets, payload/hash, límites y escapado de Telegram.
- Prompts de contrato/soul/Telegram/skills alineados; no inventario espontáneo
  de pendientes ni invitación a rehacer lo descartado. Reminders se alinea
  sin incorporarlo al listado de skills de la factory (wiring sin ampliar).
- Cinco casos sintéticos añadidos; catálogo total de 32. Simuladores TODO y
  lectura de pendientes añadidos al harness sin importar I/O de producción.

### Primer intento local, insuficiente (2026-10-15)

- Se observó en OpenRouter una respuesta JSON válida pero vacía
  (`{"answer":"","proposal_text":""}`) después de razonar sobre una tool,
  sin llamada de herramienta. La causa local comprobable era que el contrato
  `AgentReply` y el prompt permitían ambos campos vacíos; Agno aceptaba esa
  salida final y el procesador la marcaba como `EmptyAgentResponse` si no
  existía una propuesta persistida.
- Se hizo que `AgentReply` rechazase ambos campos vacíos o solo con espacios. El
  prompt ordenaba llamar la tool antes de devolver el JSON final y exigía el
  marcador no autoritativo `Propuesta creada.` después de un `propose_*`
  exitoso; el Core sigue sustituyéndolo por el bloque canónico.
- Una reproducción local con Agno 2.9.0, SDK OpenAI-compatible y transporte
  HTTP simulado confirmó que aquella request enviaba `tools` junto con
  `response_format={"type":"json_object"}`, y que Agno antes aceptaba la
  respuesta vacía sin ejecutar tools. No se llamó a OpenRouter, LiteLLM,
  Supabase ni Railway durante esta corrección.

### Segunda corrección local tras pruebas manuales fallidas (2026-10-15)

- El propietario observó preámbulos finales («Déjame consultar tus listas») y
  una propuesta narrada sin botones. El primer intento no restauraba el tool
  calling: solo sustituía el vacío por texto. La causalidad semántica exacta
  sigue sin probarse con una comparación real del mismo modelo/proveedor.
- Se retiran `output_schema` y `use_json_mode` del Agent principal y del harness
  físico; el request ya no lleva `response_format`. `present_reply` conserva
  la partición como herramienta terminal (`stop_after_tool_call=True`) con
  contrato en Git y `tool_choice=required`. No hay parser, modelo extra ni
  request posterior al cierre. Consume presupuesto de herramienta sin ampliar
  los límites. Saludos y aclaraciones pueden cerrarse sin llamar tools de datos.
- El runner exige una única ejecución terminal exitosa y valida su resultado,
  no acepta una frase/JSON en `content` como respuesta final. El Core descarta
  `proposal_text` sin propuestas de esa interacción/usuario y no fabrica botones;
  mantiene el `answer` de lecturas, errores y turnos mixtos.
- SDK OpenAI-compatible real y Agno, con `httpx.MockTransport` y modelo gobernado,
  cubren listas, tareas por ID resuelto, propuesta, saludo, turno mixto y trivial.
  Se verifica ausencia de `response_format` y del sufijo JSON generado por Agno,
  `tool_choice`, replay de resultados de tools, ejecución, presupuesto/hooks y
  auditoría de uso. Los completions prematuros y resultados terminales fallidos,
  vacíos, duplicados o no finales se rechazan. Esto prueba protocolo con un
  proveedor simulado, **no** selección semántica del modelo real ni E2E Telegram.
- Sin inferencia real, despliegue, migraciones, cambios de modelo/Gateway ni
  fixtures productivos. Validación real del SHA queda pendiente antes de cierre.
- Verificación final local de esta segunda corrección: `pytest tests/unit/ -q`
  **1418 passed**; Ruff global limpio; `mypy src/` limpio (172 archivos).
  `scripts/run_evals.py --json`: **36 casos válidos**, 6 categorías y 9 ejemplos
  sintéticos de calibración; no equivale a ejecutar un juez ni un modelo real.
  La matriz HTTP simulada incluye también not-found y error de lectura.
  Avisos del Collector local ausente al exportar métricas, sin fallos de tests.
  No se ejecutó integración PostgreSQL en esta corrección.

### Prueba y límites de evidencia

- Pruebas nuevas: partición estricta, prosa no validada rechazada, composición
  simple/mixta/múltiple, botones por ID, outbox cifrado, vacío sin propuesta,
  fallo sin entrega confirmable, trivial sin botones, advertencia conservada,
  fechas/horas/offsets, campos inesperados y HTML escapado.
- Una prueba ejecuta el Agent real de Agno con modelo en memoria y fake
  `LLMAccess`: parsea `AgentReply` con **una** llamada, sin red/credenciales.
- Integración PostgreSQL ejecutada contra Docker local: **159 passed, 1 skipped**;
  la omisión corresponde a STT live y no a falta de PostgreSQL.
- `scripts/run_evals.py`: 32 casos válidos en 6 categorías; no scoring semántico.
- `pytest tests/unit/ -q`: **1368 passed** (36 más que el baseline de 1332).
- Ruff global y `mypy src/` (169 archivos) limpios.
- `pytest tests/integration/ -q`: **159 passed, 1 skipped** (2026-10-15).
- Revalidación global vigente: **1421 unitarias**; Ruff global y `mypy src/`
  limpios. Los contadores anteriores se conservan como evidencia de la sesión
  original de implementación.
- Avisos de Collector local ausente en exportación de métricas, sin fallo de tests.
- **Sin deploy, migraciones ni escritura de fixtures en Supabase/Railway.**

**No se prueba obediencia semántica real:** el modelo todavía debe colocar
correctamente cada frase en su campo y respetar las instrucciones tras No.
No se marca AC1/AC4 como E2E superado por haber validado mocks o catálogos.

## 5. Pendiente de verificar antes de cerrar BL-48 (actualizado 2026-10-16)

- [x] AC1/AC2: tarea con prioridad/fecha y respuesta mixta, bloque único sin
  escritura previa a confirmar; campaña rev. 8/r4 del 2026-10-16 (paso 2).
- [ ] AC3: varias propuestas y selección individual en el mismo turno.
- [ ] AC4/AC6: consulta tras descarte y nueva petición sobre el baseline actual.
- [x] AC5 parcial: lectura real de pendientes vacíos con rev. 8 y `r4`;
  interacción `27e99491-bed0-4399-aada-995de477963c`, dos tools y `agent_final`.
- [ ] AC5 restante: lectura con propuestas realmente confirmables y exclusión
  de descartadas/ejecutadas/caducadas en campaña controlada.
- [ ] AC7: regresiones triviales (TODO/notas).
- [ ] AC8–AC9: horas/zonas, límites, escapado, payload/hash y consentimiento.
- [x] Integración PostgreSQL aislada: 159 superadas, una STT live omitida.
- [ ] Evaluación de instrucciones y E2E real del SHA autorizado.

No se marca como superado un criterio de la mejora solo porque el circuito
de consentimiento anterior funcionó.

## 6. E2E productivo parcial e incidente de cierre — 2026-10-16

- SHA `00f0d0f` desplegado en Railway. La repetición de «¿Tengo alguna
  propuesta pendiente de confirmación?» ejecutó dos llamadas LLM sin retry ni
  fallback y una tool según el contador durable corregido, pero no persistió
  respuesta lógica ni inició delivery. La interacción terminó
  `failed_ambiguous`, con `agent_run_failed_after_claim`; Telegram quedó sin
  respuesta.
- Mecanismo comprobado: la lectura ocurrió (`tool_call_count=1`), pero el segundo
  turno no cerró con una ejecución válida y terminal de `present_reply`;
  `reply_from_run` rechazó correctamente la salida. No se entregó prosa no
  validada, no se reintentó inferencia y no hubo mutación canónica.
- Corrección local: error tipado `InvalidPresentationOutputError` en Core y
  aviso fijo metadata-safe mediante outbox secundaria idempotente
  `response_kind='failure_notice'`, sin cambiar `failed_ambiguous`, crear
  `agent_final`, reejecutar el Agent ni afirmar el resultado de una acción.
  Texto: indica que no hubo respuesta válida, que no habrá retry automático y
  que se consulte el estado antes de repetir una acción.
- Validación local: 1428 unit; 161 integration, 1 STT live omitida por diseño;
  Ruff y `mypy src/` limpios. Pendiente CI, deploy manual y nuevo E2E; BL-47/48
  no se cierran aún.

### Revalidación del aviso y diagnóstico de ruta

- SHA `a0ace40` desplegado. Una nueva consulta en sesión limpia volvió a ejecutar
  dos llamadas LLM y una tool, sin retry/fallback, y terminó
  `InvalidPresentationOutputError`; no creó propuestas ni respuesta principal.
  La outbox secundaria `failure_notice` quedó `delivered` con message ID y el
  usuario recibió el texto fijo previsto. El mecanismo de seguridad queda
  validado E2E.
- La ejecución correcta anterior y las dos fallidas usaron el mismo alias
  `ancoramind-default-r5`. La revisión 5 introdujo `r5` para comparar
  `xiaomi/mimo-v2.6-pro`; la revisión 6 lo conservó y añadió embeddings. El
  incumplimiento terminal es reproducible con `r5` y no depende del historial.
- No se relaja `present_reply`, no se acepta texto libre y no se reintenta. Se
  prepara un candidato aditivo basado en la revisión 6 que cambia solo default
  `r5 → r4` (GPT-6 Luna) y pricing canónico `0.10/0.50`, conservando
  `ancoramind-embeddings-r1` y el resto de límites. Asset:
  `configs/ancoramind-default-r4-with-embeddings.json`. Pendiente publicación en
  Git, CI y activación CAS como revisión nueva; sin inferencia adicional todavía.

### Cambio de ruta y E2E BL-47 superado

- Asset publicado en SHA `5f0132f`, CI completo en verde y deployment Railway
  `838ab705-550c-43a9-a344-5dc1450ce73b` `SUCCESS`.
- `status` confirmó revisión 6 activa y `validate` devolvió `valid=true`. El
  operador ejecutó por error `create-revision` dos veces: revisiones 7 y 8 son
  inmutables, válidas y byte-a-byte equivalentes (checksum
  `e2663c6a…db25`). La 7 quedó inactiva; no se editó ni eliminó.
- Revisión 8 activada por CAS `6 → 8`, auditada con actor
  `assistant-r7-rollout`. Conserva `ancoramind-embeddings-r1`, cambia únicamente
  default a `ancoramind-default-r4` (GPT-6 Luna) y pricing canónico `0.10/0.50`.
  Readiness confirmó revisión 8 y todos los componentes healthy.
- E2E único posterior: la consulta explícita de propuestas pendientes respondió
  correctamente. Ledger: interacción `completed`, `config_revision=8`, dos
  llamadas LLM, `tool_call_count=2` (lectura + `present_reply`), ruta efectiva
  `ancoramind-default-r4`, cero retries/fallback/error. Outbox `agent_final`
  completada y entregada en un chunk; cero propuestas nuevas y cero
  `failure_notice` tras el switch.
- **BL-47 queda validado E2E para la lectura sin propuestas confirmables.** BL-48
  sigue abierto: esta evidencia cubre AC5 y el mecanismo de fallo seguro, no
  sustituye AC2/AC3/AC6–AC9 ni la matriz trivial completa.

## 7. Cierre de brechas deterministas — 2026-10-16

Sin modificar código funcional, prompts ni configuración, se añaden ocho pruebas
de integración en `tests/integration/test_proposal_presentation.py`. Usan el
procesador, repositorios, outbox y executor Core reales contra PostgreSQL aislado;
runner y sender son scripted, sin inferencia ni Telegram externos.

- **AC2/AC3/AC6, frontera Core:** READ independiente preservada con dos bloques y
  pares de botones para sus IDs persistidos; payload/hash intactos. Un «Sí» sin ID
  no autoriza ninguna cuando hay varias. Elegir una escribe solo su recordatorio;
  doble pulsación no duplica. Descartar la otra no invoca al Agent y una nueva
  petición simulada crea nuevos IDs sin revivir ni ejecutar las anteriores.
- **AC9:** consentimiento OFF no entrega narración ni controles ficticios y el
  callback no ejecuta. Cuatro variantes de error de entrega (primer/segundo chunk,
  definitivo/ambiguo) no abren `presented_at`/TTL ni permiten confirmar mediante
  un ID conocido; recuperación no reejecuta el Agent ni reenvía chunks inciertos.
- **Fallo terminal:** si la salida es inválida tras crear propuesta, solo se
  entrega `failure_notice`, sin controles, `agent_final` ni confirmabilidad. Si
  ya hubo escritura trivial, conserva el efecto y su auditoría, advierte consultar
  estado y nunca reejecuta la mutación tras recuperación.
- Otras cuatro pruebas en `tests/integration/test_trivial_executor.py` cubren
  AC7 en Core: alta/completar/reabrir/nota con auditoría terminal atómica, rechazo
  de target ajeno y rollback real ante fallo tras INSERT de auditoría o antes
  del commit. Ver evidencia de specs/035.
- Gates: **1428 unit passed; 173 integration passed, 1 STT live skipped**;
  Ruff global y `mypy src/` limpios; catálogo estático válido (36 casos).
  La suite global detectó una prueba STT con deadline de 50 ms que podía expirar
  durante I/O DB previo al proveedor; se fija en el test armando la cancelación
  real de asyncio dentro del stub STT. No cambia el timeout productivo.
- **Límite:** estas pruebas no validan selección de tools, partición semántica,
  ausencia de insistencia ni presentación real del modelo/cliente Telegram.
  No cierran BL-46/48 ni sustituyen la matriz E2E pendiente.

### Próxima campaña Telegram preparada (no ejecutada)

Mantener runtime rev. 8 / `ancoramind-default-r4` y registrar SHA/deployment
realmente activos antes de empezar. No hace falta desplegar estas pruebas para
validar el producto actual. El propietario envía las peticiones y decide cada
confirmación; no se fabrican updates ni se insertan fixtures productivos por SQL.
Usar una lista sintética identificable y detener la campaña si falla un paso:

1. **Preparación:** pedir crear «Validación cierre 16 octubre»; comprobar bloque
   único y confirmar solo esa lista. Si existe, consultarla y reutilizarla sin
   duplicarla. Nada de borrar datos previos automáticamente.
2. **AC2:** «Muéstrame las tareas de Validación cierre 16 octubre y propón añadir
   Revisar seguro con prioridad alta y fecha límite 20 de octubre de 2026».
   Conservar la consulta READ y un bloque Core legible; no hay tarea canónica
   antes de Sí. Pulsar No y consultar tareas (**AC4**): ausente y sin insistencia.
3. **AC6:** pedir explícitamente de nuevo esa tarea con prioridad/fecha. Exigir
   nuevo ID; descartar para no ejecutar la anterior ni dejarla pendiente.
4. **AC3/AC5:** pedir dos tareas distintas con prioridad alta en esa misma lista.
   Exigir dos propuestas persistidas/botones ligados a cada ID y consulta real
   de pendientes. Un «Sí» solo pide elegir, sin escribir. Confirmar una por su
   botón y descartar la otra; consultar tareas y pendientes. No habilitar lote.
5. **AC7:** añadir tarea «Validar reapertura» solo título; completar, reabrir y
   consultar. Pedir guardar una nota sintética y buscarla. Sin botones, cada
   efecto con auditoría `self_authorized`/`executed`.
6. **Cierre:** comprobar estados de cada propuesta/tarea, cero pendientes
   confirmables de esta campaña y ninguna duplicación. La limpieza destructiva
   es opcional y requiere su propia propuesta/confirmación, nunca SQL directo.

Evidencia por paso: IDs de interacción/propuesta (sin texto personal en logs),
config revision/ruta, conteos tools/LLM, outbox entregada y auditoría de mutación;
verificación visual por el propietario de la semántica y los botones. Sin retry
automático tras fallo ambiguo: consultar estado antes de repetir.
AC8/AC9 de fallo/OFF se verifican en entorno aislado; no se apagan controles ni
se corta Telegram/Gateway productivo para provocar estos escenarios.

### Preflight de la campaña — 2026-10-16 14:31 UTC

- Railway conserva deployment `838ab705-550c-43a9-a344-5dc1450ce73b`, SHA
  `5f0132f`, `SUCCESS`; el deployment documental `a4a69f1` sigue
  `NEEDS_APPROVAL`, sin aprobarlo ni alterar el entorno.
- Consulta canónica read-only: revisión activa 8, default
  `ancoramind-default-r4`, embeddings `ancoramind-embeddings-r1`.
- GET `/health` y `/health/readiness`: ambos 200.
- Para el principal de la interacción E2E anterior
  `27e99491-bed0-4399-aada-995de477963c`: cero listas con el nombre exacto
  «Validación cierre 16 octubre» y cero propuestas confirmables del mismo
  bot/chat a la hora del preflight. No se consultó contenido personal ni
  se insertaron fixtures; estos recuentos son solo una foto previa.
- Las pruebas y priorización anteriores están en commit local `c5807a4`,
  aún no publicado. No cambia el código funcional respecto al desplegado.
- Próximo paso requiere entrada real del propietario: pedir crear esa lista
  y revisar el bloque/botones antes de decidir la confirmación. No hay aún
  ejecución ni resultado E2E nuevo que marcar como superado.

### Paso 1 — Lista sintética propuesta, aún sin confirmar

- El propietario recibió un único bloque «Propuesta: Crear lista de tareas»,
  nombre exacto de campaña, instrucción de confirmación y botones Sí/No; sin
  narración duplicada del Agent según la respuesta aportada.
- Lectura canónica a las 14:34:40 UTC: interacción
  `e84a7b81-9068-48ee-a4f6-e80aa3b20648` `completed`, revisión 8, ruta
  `ancoramind-default-r4`, dos llamadas LLM completadas, dos tools, cero retries.
- Propuesta `3b7cc465-407d-4c12-b70c-5f9de39a9909` en
  `pending_confirmation`/`explicit_confirmation`, sin confirmación atribuida.
  Presentada a las 14:33:25 UTC, ventana hasta 14:48:25 UTC. `agent_final`
  completada, un chunk completado con message ID; sin `failure_notice`.
- Cero listas canónicas del mismo usuario con ese nombre: proponer no creó
  todavía la lista. Paso de presentación superado para crear lista; no equivale
  a AC1 (tarea con prioridad/fecha) ni valida aún ejecución o resto de campaña.
- Pendiente: decisión real del propietario mediante el botón y verificación de
  una única lista/auditoría ejecutada. No se confirmó mediante SQL ni herramientas.

### Paso 1 — Confirmación por botón y lista creada

- El propietario pulsó Sí y recibió «✅ Operación ejecutada y registrada.».
- Lectura canónica a las 14:37:03 UTC: propuesta
  `3b7cc465-407d-4c12-b70c-5f9de39a9909` `executed`, modo
  `explicit_confirmation`, `completed_at=2026-10-16T14:36:11Z`.
- Interacción confirmante `fbbcf50a-a4f5-4a6b-bb16-eab25095216d` de tipo
  `callback_query`, `completed`, cero tools y cero llamadas LLM. Respuesta
  lógica `agent_final` completada y un chunk completado con message ID.
- Existe exactamente una lista canónica con el nombre de campaña para ese
  usuario: `f2001d4b-413e-408b-9b99-ccafa33500c0`, todavía sin tareas.
  No hay duplicación observada; este paso no prueba concurrencia/doble pulsación.
- Preparación de campaña superada: proponer no escribió, confirmación humana
  por botón ejecutó y auditó sin inferencia. Siguiente: AC1/AC2 con consulta
  READ + propuesta de tarea con prioridad/fecha, sin confirmar de momento.

### Paso 2 — AC1/AC2: consulta y propuesta revisable en el mismo turno

- El propietario recibió «La lista no tiene tareas todavía.» y un único bloque
  de propuesta con «Revisar seguro», prioridad «alta», vencimiento «20 de
  octubre de 2026», una instrucción de confirmación y botones Sí/No. No hubo
  duplicación ni se perdió la respuesta READ según el texto aportado.
- Lectura canónica a las 14:40:20 UTC: propuesta
  `5345640e-0af8-4790-b666-d577bee186db`, interacción origen
  `8667dced-f658-49d2-bd50-b2d8def6fbc8` `completed`, revisión 8, ruta
  `ancoramind-default-r4`. Tres llamadas LLM completadas, cuatro tools,
  cero retries; los contadores no identifican por sí solos las tools concretas.
- Payload persistido apunta a la lista de campaña
  `f2001d4b-413e-408b-9b99-ccafa33500c0`: `priority='high'`,
  `due_date='2026-10-20T00:00:00'`, `description=null`. Hash recalculado con
  `payload_hash('create_todo_item', payload)` coincide con el persistido.
- Estado `pending_confirmation`/`explicit_confirmation`, sin confirmación.
  Presentada 14:39:13 UTC, ventana hasta 14:54:13 UTC. `agent_final` y su único
  chunk completados con message ID, sin `failure_notice`. La lista sigue con
  **cero tareas**: la propuesta revisable aún no ejecutó la escritura.
- **AC1/AC2 superados para este recorrido sobre el baseline actual.** No se
  cierra BL-48; siguiente paso AC4: propietario pulsa No y después consulta
  todas las tareas, sin repropuesta automática ni inventario ajeno a la consulta.