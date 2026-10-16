# Verification: 036 — Evidencia previa y validación pendiente

> **Fecha de registro:** 2026-10-14.
> **Estado:** desplegado y validado E2E parcialmente hasta 2026-10-16;
> Con runtime rev. 8 constan AC1–AC7 (AC3/AC7 asistidos); AC5 acreditado con
> trazas recuperadas en §11. AC8–AC9 y gates locales revalidados en §12.
> Evaluación real de instrucciones y cierre global pendientes; BL-48 abierto.
> Actualización posterior: variantes revisables BL-46 superadas (§13); preparación
> del harness real autorizada, preflight sin inferencia listo (§14). No se sustituye
> su gate formal por la evaluación manual Telegram (decisión del propietario).

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
- [x] AC3: varias propuestas y selección individual en el mismo turno.
  Pasos 8/9 asistidos con delegación explícita: dos bloques, «Sí» ambiguo sin
  ejecución, confirmación de una y descarte de otra por botones; IDs/efectos verificados.
- [x] AC4: descarte y consulta posterior sin tarea, repropuesta ni inventario
  no solicitado; campaña rev. 8/r4 del 2026-10-16 (paso 3).
- [x] AC6: nueva petición explícita crea otra propuesta; anterior descartada
  intacta y cero tareas; campaña rev. 8/r4 del 2026-10-16 (paso 4).
- [x] AC5 parcial: lectura real de pendientes vacíos con rev. 8 y `r4`;
  interacción `27e99491-bed0-4399-aada-995de477963c`, dos tools y `agent_final`.
- [x] AC5 restante: lectura con propuestas realmente confirmables y exclusión
  de descartadas/ejecutadas/caducadas en campaña controlada.
  Pasos 5–7: recuento positivo, detalle bajo petición y respuesta vacía tras
  caducidad correctos; entonces faltaba evidencia de tool concreta y no se
  infirió del contador. Recuperada posteriormente en §11.
  Paso 9: consulta final vacía tras ejecución/descarte. El límite de trazabilidad
  de esos pasos queda resuelto por las cuatro trazas recuperadas en §11.
- [x] AC7: alta título-solo, completar/reabrir y nota/búsqueda sin botones;
  paso 10 asistido autorizado, cuatro auditorías terminales y hashes válidos.
- [x] AC8: horas/zonas, límites, escapado, payload/hash y rechazo de consentimiento
  inválido; ver matriz determinista aislada en §12, no evaluación semántica LLM.
- [x] AC9: OFF y fallo de entrega sin ejecución ni presentación ficticia;
  cuatro variantes de fallo y regresiones terminales contra PostgreSQL en §12.
- [x] Gates locales: 1433 unitarias, cobertura 80 %, 173 integraciones
  PostgreSQL superadas y una STT live omitida; Ruff/mypy/Collector verdes (§12).
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

### Paso 3 — AC4: descarte y consulta acotada, sin repropuesta

- El propietario recibió «❌ Propuesta descartada.» y, tras consultar todas
  las tareas, «La lista «Validación cierre 16 octubre» no tiene tareas.».
  La respuesta aportada no ofrece reproponer ni inventaría otras propuestas.
- Lectura canónica a las 14:48:20 UTC: propuesta
  `5345640e-0af8-4790-b666-d577bee186db` `discarded`,
  `failure_reason='user_declined'`, completada a las 14:46:23 UTC, sin
  interacción confirmante y con el hash de payload previo intacto.
- La lista de campaña continúa con cero tareas; cero propuestas posteriores
  de alta de tarea en esa lista a la hora de la comprobación. No hubo escritura
  ni repropuesta automática observada.
- Descarte: interacción `eff73891-9077-4b76-b3e0-38bf328c5367`,
  `callback_query` `completed`, cero tools y cero llamadas LLM.
- Consulta: interacción `38a26d15-4b55-4ada-a0f4-141b153186e5` `completed`,
  revisión 8, ruta `ancoramind-default-r4`, dos llamadas LLM completadas,
  dos tools y cero retries. No creó propuestas; los contadores no identifican
  por sí solos las tools concretas.
- Ambas interacciones tienen `agent_final` completada y un chunk completado
  con message ID, sin `failure_notice`. **AC4 superado para este recorrido**;
  BL-48 permanece abierto. Siguiente AC6: nueva petición explícita, propuesta
  con ID nuevo sin revivir la descartada ni escribir antes de confirmar.

### Paso 4 — AC6: repropuesta explícita con ID nuevo, sin ejecución

- El propietario pidió explícitamente volver a proponer y recibió un único
  bloque de alta de tarea, mismos campos legibles e instrucción con botones
  Sí/No. «Ahora sí, vuelve a proponer» no produjo ejecución ni consentimiento.
- Lectura canónica a las 14:59:05 UTC: nueva propuesta
  `682679c6-c66f-4b42-9770-51a436589474`, interacción origen
  `926658af-ae42-4993-81bd-ecdfb0355095` `completed`, revisión 8, ruta
  `ancoramind-default-r4`, dos tools, dos llamadas LLM completadas y cero
  retries. `agent_final` y un chunk completados con message ID; sin aviso de fallo.
- Nueva fila en `pending_confirmation`/`explicit_confirmation`, sin
  confirmación; presentada a las 14:57:47 UTC, ventana hasta 15:12:47 UTC.
  Payload y hash iguales a los de la propuesta anterior por ser la misma
  petición; **ID e interacción origen diferentes**.
- La propuesta anterior `5345640e-0af8-4790-b666-d577bee186db` permanece
  `discarded`/`user_declined`, sin confirmación y con hash intacto. No se
  reabrió ni reintentó. La lista sigue con cero tareas.
- **AC6 superado para este recorrido**; BL-48 sigue abierto. Aprovechar la
  nueva propuesta pendiente para la lectura positiva de AC5 antes de descartarla:
  debe aparecer solo la confirmable, no la anterior descartada ni la lista
  ya ejecutada. La consulta no confirma ni amplía su ventana de 15 minutos.

### Paso 5 — AC5 positivo: recuento correcto, identificación insuficiente

- El propietario mantuvo los botones sin pulsar y preguntó qué propuestas
  tenía pendientes. Respuesta aportada: «Tienes una propuesta pendiente de
  confirmación.». No identifica la acción solicitada: no se considera validada
  la lista detallada de pendientes por ese texto.
- Interacción `a55dda40-7fb9-417b-a0ea-032fd6fe0037`, recibida a las
  15:06:09 UTC, `completed`, revisión 8, ruta `ancoramind-default-r4`, dos
  llamadas LLM completadas, dos tools, cero retries y cero propuestas creadas.
  `agent_final` completada y un chunk completado con message ID; sin aviso de fallo.
- A las 15:07:56 UTC el mismo usuario tiene exactamente una propuesta
  confirmable según los criterios de `list_pending` (scope usuario):
  `682679c6-c66f-4b42-9770-51a436589474`, todavía pendiente, presentada y
  válida hasta 15:12:47 UTC. La lista creada sigue ejecutada, la propuesta
  anterior descartada y la lista de campaña con cero tareas. El recuento
  coincide; ni esta consulta ni el texto aportado autorizan una escritura.
- **Límite:** dos tools no prueban por sí solas que se invocó
  `list_pending_proposals`; tampoco prueban qué registros leyó o excluyó.
  No se inspecciona contenido conversacional de la DB interna de Agno.
- Revisión local: la tool devuelve `tool_name`, resumen acotado de payload y
  vencimiento en `untrusted_results`, no solo un recuento. El prompt Telegram
  prohíbe ampliamente un resumen de propuesta pendiente dentro de `answer`,
  mientras reserva `proposal_text` para propuestas creadas en el turno. Es una
  posible ambigüedad de instrucciones que puede explicar la omisión; este único
  resultado no demuestra la causa. No se cambia prompt ni modelo durante la prueba.
- Siguiente comprobación dirigida: pedir identificar la acción pendiente sin
  confirmarla, antes de que expire. AC5 detallado sigue pendiente; no cerrar BL-48.

### Paso 6 — AC5: detalle correcto bajo petición; caducidad natural posterior

- El propietario recibió «La propuesta consiste en añadir «Revisar seguro»,
  con prioridad alta y fecha límite 20 de octubre de 2026.». Los tres campos
  coinciden con el payload de la propuesta nueva; no pide confirmar de nuevo
  ni afirma ejecución. Esto acredita detalle correcto al pedirlo expresamente,
  no resuelve la omisión de detalle de la primera consulta general.
- Interacción `cbe01267-4eed-45cf-9e4a-d6e727347c12`, recibida a las
  15:11:38 UTC, antes del vencimiento 15:12:47 UTC. `completed`, revisión 8,
  ruta `ancoramind-default-r4`, dos tools y dos llamadas LLM completadas,
  cero retries. `agent_final` y un chunk completados con message ID;
  ninguna propuesta creada ni aviso de fallo. No se deduce tool concreta
  a partir del contador agregado.
- A las 15:12:48 UTC la propuesta `682679c6-c66f-4b42-9770-51a436589474`
  aún conserva estado almacenado `pending_confirmation`, pero su ventana ya
  venció y **no es confirmable**. No se confunde el estado de fila con
  elegibilidad: `list_pending` exige también `expires_at > now()`.
- A las 15:13:03 UTC: cero propuestas confirmables del usuario, cero propuestas
  nuevas de tarea en la campaña después de la repropuesta explícita y cero
  tareas canónicas. La consulta no renovó el TTL ni autorizó ninguna escritura.
- El siguiente paso cambia por la caducidad natural: no confirmar, no recrear
  ni descartar antes de probar la exclusión. Pedir de nuevo pendientes y
  comprobar respuesta vacía sin inventario desde historial. Esta consulta
  sigue pendiente de envío real por el propietario; AC5 completo no se cierra.

### Paso 7 — AC5: respuesta vacía después de caducar

- El propietario preguntó de nuevo por pendientes y recibió «No tienes ninguna
  propuesta pendiente de confirmación ahora mismo.». No muestra la propuesta
  caducada, ni la descartada o ejecutada, ni ofrece recrearlas.
- Interacción `4f8603d4-bd83-4522-996d-ca8705f00ba9`, recibida a las
  15:15:09 UTC, después del vencimiento 15:12:47 UTC. `completed`, revisión 8,
  ruta `ancoramind-default-r4`, dos tools, dos llamadas LLM completadas y cero
  retries. Respuesta `agent_final` completada, un chunk completado con message ID.
- Lectura canónica a las 15:18:30 UTC: cero propuestas confirmables del usuario,
  cero propuestas creadas por esa interacción y cero tareas en la lista de
  campaña. La propuesta caducada conserva `pending_confirmation`, sin
  `confirming_interaction_id`: no se renovó ni ejecutó por consultar.
- Exclusión semántica tras caducidad observada con el baseline rev. 8/r4. Sigue
  sin demostrarse el nombre de las tools invocadas a partir de los contadores;
  no se da por probado ese requisito de lectura real ni se cierra AC5 completo.
- El propietario plantea automatizar la campaña mediante Playwright. Solo se
  inspeccionaron pestañas: el servidor expone `about:blank`, no la sesión de
  Telegram del navegador del propietario. No se enviaron mensajes ni pulsaron
  botones. La campaña sigue siendo manual hasta acordar acceso y alcance; no se
  mezcla evidencia manual con una eventual ejecución asistida/delegada.

### Paso 8 — AC3 asistido por Playwright: dos propuestas, sin consentimiento

- El propietario inicia sesión manualmente en el navegador Playwright. Se
  comprueba el chat `ancoramind_project_bot` y la respuesta previa de pendientes
  vacíos, sin navegar por otros chats. A las 15:22:54 UTC: lista de campaña
  única, cero tareas y cero propuestas confirmables del usuario.
- Se envía por la UI real una petición de dos tareas en «Validación cierre
  16 octubre»: «Revisar póliza prueba AC3» y «Revisar recibo prueba AC3», ambas
  con prioridad alta, indicando no confirmar ni ejecutar ninguna. Es entrada
  asistida, no escrita personalmente por el propietario ni update fabricado.
- El DOM del mensaje recibido muestra exactamente dos bloques «Propuesta:
  Añadir tarea», cada uno con su título, prioridad «alta» e instrucción de
  consentimiento. El teclado tiene dos filas, cada una con Sí/No. No hay
  narración duplicada del Agent. La inspección visual/DOM no demuestra por sí
  sola qué ID lleva cada callback; falta probar selección individual.
- Interacción `3ee18d70-b71c-46db-846b-7e2710bedac2`, recibida 15:23:09 UTC,
  `completed`, revisión 8, ruta `ancoramind-default-r4`, cuatro tools, tres
  llamadas LLM completadas, cero retries. `agent_final` completada y un chunk
  completado con message ID.
- Lectura canónica 15:23:27 UTC: dos propuestas `pending_confirmation` y
  `explicit_confirmation`, ambas para la lista de campaña, `priority='high'`,
  sin fecha ni descripción y sin interacción confirmante:
  - póliza: `c033f4b5-6b52-4549-b69c-2e959e18a60e`;
  - recibo: `fdb76b52-46e9-40f5-8dc4-fc86faef33d9`.
  Ambas presentadas 15:23:21 UTC, vencimiento 15:38:21 UTC. Cero tareas
  canónicas: proponer no ejecutó ninguna.
- No se pulsa Sí/No ni se envía un texto de consentimiento. El «Sí» ambiguo
  también se trata como consentimiento para delimitar la delegación; la siguiente
  fase requiere decisión del propietario. AC3 sigue parcial y BL-46/48 abiertos.

### Paso 9 — AC3 asistido: selección individual con autorización acotada

- El propietario autoriza exclusivamente enviar «Sí» ambiguo, confirmar la
  póliza por botón, descartar el recibo por botón y consultar tareas/pendientes.
  No autoriza otras mutaciones, limpieza ni iniciar AC7. Todo se realiza en
  Telegram Web mediante Playwright; SQL solo de lectura. No son pulsaciones
  personales del propietario: se registra consentimiento delegado de prueba.
- Preflight 15:25:49 UTC: exactamente los dos IDs del paso 8 confirmables en el
  mismo bot/chat, payloads intactos y cero tareas. No se recrean propuestas.
- **«Sí» ambiguo:** interacción `6efa6ec2-e751-4ae3-88be-10d31e4168e2`,
  recibida 15:26:08 UTC. Respuesta «Tienes varias propuestas pendientes.
  Responde «Sí <ID>»:» seguida de los dos IDs. Ambas siguen pendientes, sin
  confirmante y cero tareas. `completed`, cero tools/LLM; `agent_final` y un
  chunk completados. No se infiere fallo de autorización de la exposición de IDs;
  el mensaje pide selección, no concede consentimiento por lote.
- **Confirmar póliza:** clic en Sí de la primera fila del mensaje del paso 8.
  Respuesta «✅ Operación ejecutada y registrada.». El ID
  `c033f4b5-6b52-4549-b69c-2e959e18a60e` pasa a `executed`, modo
  `explicit_confirmation`, `confirmed_at=15:26:47.630249Z`,
  `completed_at=15:26:47.819792Z`; confirmante
  `f771bbb7-6d91-4a73-96b3-e0ef703ca35f`, recibida 15:26:46 UTC,
  `completed`, cero tools/LLM. `agent_final` y un chunk completados.
  Existe exactamente una tarea de campaña:
  `0e5efc7b-b87e-43b9-bf77-746b4a8297a5`, «Revisar póliza prueba AC3»,
  pendiente y prioridad `high`. El recibo continúa pendiente: no hubo lote.
- **Descartar recibo:** clic en No de la segunda fila del mismo mensaje.
  Respuesta «❌ Propuesta descartada.». El ID
  `fdb76b52-46e9-40f5-8dc4-fc86faef33d9` pasa a `discarded`,
  `failure_reason='user_declined'`, `completed_at=15:27:06.036395Z`,
  sin confirmante. Interacción `40cd28ad-c120-47e6-ac41-1428a55b4d9e`,
  recibida 15:27:05 UTC, `completed`, cero tools/LLM; `agent_final` y un
  chunk completados. La póliza sigue ejecutada y sigue habiendo una sola tarea.
- **Consulta de tareas:** interacción `b7c40c0b-567a-4340-a2e4-9312a5297934`,
  recibida 15:27:30 UTC. Respuesta «En la lista aparece una tarea: Revisar
  póliza prueba AC3 — pendiente, prioridad alta y sin fecha límite.». No narra
  propuestas, ofrece recrearlas ni muestra la tarea descartada.
- **Consulta de pendientes:** interacción `f8178073-7f3e-4c8c-aabe-69bd6bbff951`,
  recibida 15:28:03 UTC. Respuesta «No tienes ninguna propuesta pendiente de
  confirmación ahora mismo.». Ambas consultas `completed`, revisión 8, ruta
  `ancoramind-default-r4`, dos tools/dos llamadas LLM completadas cada una,
  cero retries y cero propuestas creadas; `agent_final` y un chunk completados.
  El contador no identifica las tools: AC5 conserva ese límite de evidencia.
- Foto final 15:28:22 UTC: cero propuestas confirmables del usuario y exactamente
  la tarea de póliza pendiente; sin duplicación observada. Los callbacks quedan
  vinculados al ID esperado por su transición/efecto, no solo por orden visual.
  **AC3 superado en esta ejecución asistida**; no prueba doble clic/concurrencia.
  Se conserva el dato sintético autorizado, sin borrado automático. Delegación
  completada: detenerse antes de AC7; BL-46/48 siguen abiertos.

### Paso 10 — AC7 asistido: cuatro escrituras triviales y dos consultas

- El propietario autoriza exclusivamente crear «Validar reapertura AC7» solo
  título en la lista de campaña, completarla, reabrirla, consultar la lista,
  guardar la nota sintética acordada y buscarla. Se conservan los datos.
  Ejecución asistida por Telegram Web/Playwright; SQL solo de lectura, sin
  botones, reenvíos, borrado ni cambios de configuración.
- Preflight 15:33:15 UTC: lista existente, solo la póliza de AC3 pendiente,
  ninguna tarea con el título AC7 en ella, cero notas con el contenido exacto
  autorizado y cero propuestas confirmables. Runtime activo 8 y default
  `ancoramind-default-r4`, embeddings `ancoramind-embeddings-r1` verificados.
- Peticiones y evidencia durable (horas UTC, 2026-10-16):

  | Paso | Interacción | Recibida | Auditoría | Tools / LLM |
  |---|---|---|---|---|
  | Crear título-solo | `59c7c657-cf00-4e50-b22d-eea51b1ebbf1` | 15:33:40 | `940bf75a-0764-430e-a5c3-2ef58868b196` | 2 / 2 |
  | Completar | `18ef6ff6-8758-4504-967e-305266341ce8` | 15:34:24 | `cf6dd134-547f-4e5b-a1ff-d8e3fb770a76` | 4 / 4 |
  | Reabrir | `751395e6-6c46-4930-996d-47c41dc07128` | 15:35:01 | `bf571553-b8ba-4dd2-bfeb-9681a518f794` | 4 / 4 |
  | Consultar lista | `0920cd15-d798-42f9-bbf5-f6e4737b60b4` | 15:35:27 | ninguna | 3 / 3 |
  | Guardar nota | `3c95c1ae-7508-4fe0-b407-4ccc0d5a395b` | 15:35:48 | `b5426857-22c3-41f9-80bf-2ae68b903b4b` | 2 / 2 |
  | Buscar nota | `94d41296-25f2-4a43-99ea-b7d3694cb63d` | 15:36:33 | ninguna | 2 / 2 |

- Las seis interacciones: `completed`, revisión 8, llamadas LLM completadas
  en `ancoramind-default-r4`, cero retries, `agent_final` completada y un
  chunk completado con message ID cada una, sin aviso de fallo. No se deducen
  nombres de tools de lectura del contador agregado.
- Respuestas de mutación observadas en DOM: tarea añadida, marcada como
  completada, reabierta y «Nota guardada.». Ninguna pide confirmar ni tiene
  botones. La consulta muestra dos tareas pendientes (póliza y reapertura);
  la búsqueda devuelve exactamente «Prueba sintética AC7 del 16 de octubre de
  2026: comprobar memoria de notas», también sin botones ni repropuestas.
- Tarea nueva `db15bec2-e8c4-4928-a9fe-afee85260a89`: único ejemplar en la
  lista `f2001d4b-413e-408b-9b99-ccafa33500c0`, sin prioridad, descripción ni
  fecha. Estado observado tras cada mutación: `pending` → `done` → `pending`.
  La nota exacta es única: `0f4bf955-0fb1-4ea7-b761-6cdb8ed494b3`.
- Las cuatro auditorías tienen `self_authorized`/`executed`, origen en su
  interacción y bot/chat correctos, `executed_at`/`completed_at` presentes,
  sin `presented_at`, `confirmed_at` ni `confirming_interaction_id`. Sus
  payloads son solo título/lista, item/status (`done` o `pending`) y contenido
  de nota, respectivamente. Recalculados localmente con `payload_hash` del
  dominio: **4/4 coinciden** con los hashes persistidos. La atomicidad ante
  fallo está cubierta por integración aislada, no se induce un fallo en producción.
- Foto final 15:37:01–15:37:23 UTC: exactamente cuatro filas de auditoría desde
  preflight, todas triviales; cero propuestas confirmables, una nota de campaña y
  dos tareas pendientes. La póliza AC3 conserva sus campos anteriores; sin
  duplicación observada ni mutaciones adicionales. Runtime sigue en revisión 8.
- **AC7 superado en esta ejecución asistida**, con datos sintéticos conservados.
  Termina la autorización; AC5/trazabilidad y AC8–AC9 siguen pendientes en sus
  respectivos alcances. BL-46/48 no se cierran por este único paso.

## 11. AC5 — recuperación de trazas existentes, 2026-10-16

Sin nuevos mensajes ni botones Telegram, sin modificar datos canónicos,
configuración, despliegues o controles. El árbol inicial estaba limpio en
`602d7ed7d47c734092e8ce0ba434b498911b1643`; la evidencia anterior ya estaba
comiteada. La sesión Grafana requirió autenticación al comienzo y quedó
disponible durante esta revisión; no se solicitan ni extraen secretos.

- Instancia: `https://tinyvan1950.grafana.net`, datasource Tempo
  `grafanacloud-traces` (`grafanacloud-tinyvan1950-traces`).
- Ventana absoluta: **2026-10-16 15:04:00–15:31:00 UTC**. Búsquedas y lectura
  de las cuatro trazas por ID: HTTP 200; solo se extrae metadata permitida.
- Consulta TraceQL reproducible, sustituyendo el UUID por la interacción:

  ```traceql
  { name = "ancora.tool.call" && span.ancora.correlation_id = "<interaction_id>" }
    | select(span.ancora.tool.name, span.agno.run_id, span.runtime_config.revision)
  ```

`ancora.correlation_id` es el ID de interacción (`TelegramInteraction.correlation_id`),
no una columna adicional en DB. El `agno.run_id` de cada traza coincide con el
persistido en `ancora.telegram_interactions`; todas las interacciones están
`completed`, revisión 8. No se consulta la DB interna de Agno.

| Caso previo | Interacción/correlación | `agno.run_id` | Trace ID | Span de `list_pending_proposals` / hora UTC |
|---|---|---|---|---|
| Paso 5, positivo | `a55dda40-7fb9-417b-a0ea-032fd6fe0037` | `a6b7a0dd-0407-46fb-b461-6cb412f9cf4c` | `1782bc5d6e4b31cef92724111efcc9dc` | `6a6b84a26b1907ff` / 15:06:12.862 |
| Paso 6, detalle | `cbe01267-4eed-45cf-9e4a-d6e727347c12` | `e40a030a-a904-4803-ad78-bc51f78b5c53` | `fa48efe74726c2083c20443ef8455601` | `e357ad376fc4426f` / 15:11:43.788 |
| Paso 7, tras caducidad | `4f8603d4-bd83-4522-996d-ca8705f00ba9` | `28281920-617d-4c71-a057-e767df9632f9` | `ccb28f0ede9b2f87c5051460857e6437` | `7e3a48d32656bfa4` / 15:15:14.725 |
| Paso 9, tras ejecución/descarte | `f8178073-7f3e-4c8c-aabe-69bd6bbff951` | `a4725492-a2d5-4ba5-8f45-2875e3541b04` | `95646f57e0d4605769b68c8ff2c2662b` | `d6d6ee96f25148de` / 15:28:07.648 |

En **4/4** se observa después `present_reply`, respectivamente en spans
`1b179de3542333a7`, `974b6212a8662575`, `9cb779b722c5bdc6` y
`45aa275db76f15d7`, con los mismos run/correlación/revisión. Los ocho spans
no tienen `error.type` y muestran estado OTel sin código explícito (UNSET);
no se describe ese estado como un OK explícito. La respuesta entregada y el
fin del run constan por separado en el ledger y en los pasos anteriores.

Contraste SQL solo de lectura, scoped al usuario de la campaña:

- `5345640e-0af8-4790-b666-d577bee186db`: `discarded` desde 14:46:23 UTC.
- `682679c6-c66f-4b42-9770-51a436589474`: presentada a 14:57:47 UTC, vence
  a 15:12:47 UTC; cubre las dos lecturas positivas y ya no es elegible en
  el paso 7, aunque conserve `pending_confirmation` en la fila.
- `c033f4b5-6b52-4549-b69c-2e959e18a60e`: `executed` a 15:26:47 UTC;
  `fdb76b52-46e9-40f5-8dc4-fc86faef33d9`: `discarded` a 15:27:06 UTC,
  antes de la consulta vacía del paso 9.

**AC5 superado para esta campaña rev. 8/r4:** la selección real de la tool
queda demostrada por spans nominados, no por el contador. Junto con las
respuestas y estados ya registrados se acredita lectura positiva/detallada y
exclusión de propuestas caducadas, ejecutadas y descartadas. Las trazas no
contienen ni se usan para reconstruir argumentos/resultados. La brevedad del
paso 5 no se reescribe: el detalle fue comprobado bajo petición en el paso 6.
BL-48 no se cierra por esta recuperación.

## 12. AC8–AC9 y gates locales aislados — 2026-10-16

Base local: SHA `602d7ed7d47c734092e8ce0ba434b498911b1643`, más el diff de
tests/documentación de esta revisión, todavía sin commit ni despliegue.
Python 3.12.10/Windows, PostgreSQL 16 Docker local. Fixtures únicamente en
`localhost:5432/ancoramind_test`; las migraciones usan bases temporales
dedicadas. Sender/runner simulados, sin inferencia ni Telegram real; exportación
OTLP local desactivada y token Telegram sintético. Consentimiento OFF y fallos
se inyectan en objetos de pruebas, nunca en la configuración productiva.

| Gate | Resultado final comprobado |
|---|---|
| `python -m pytest tests/unit/ -q --cov=src --cov-report=term` | **1433 passed**, **80.00 %** (mínimo 75 %) |
| `python -m pytest tests/integration/ -q` con DB obligatoria | **173 passed, 1 skipped**; STT live opt-in sin autorización, no falta de DB |
| `python -m ruff check src/ tests/ scripts/ migrations/` | Limpio |
| `python -m mypy src/` | Limpio, 172 archivos |
| `python scripts/run_evals.py --json` | Válido: 36 casos, 9 ejemplos provisionales de calibración; solo validación estática |
| Build `observability/Dockerfile` + `validate --config=/etc/otelcol/config.yaml` | Exit 0; imagen 0.138.0, valores dummy, `--network none` durante validate |

Los comandos se ejecutan desde la raíz del repositorio; la base y secretos de
producción no son destinos de fixtures. La suite global de integración incluye
4 pruebas de migración (fresh/upgrade con datos/downgrade/adopción de init SQL),
9 de repositorio actions, 18 de consentimiento, 15 de executor Core, 8 de
presentación y 4 de executor trivial. No se suman de nuevo como suites aparte.

### Matriz de evidencia determinista

| Alcance | Pruebas y aserciones relevantes |
|---|---|
| AC8, fechas/horas/zonas | `tests/unit/test_proposal_presentation.py`: 21 casos; fecha-sola, hora explícita, medianoche con offset o Z, fracciones, offsets negativos y de 45 minutos; recordatorio/evento no reinterpretados. Hash antes/después intacto, sin conversión de zona |
| AC8, límites/escapado | Mismo fichero y `tests/unit/test_telegram_markup.py`: truncado visual sin cambiar payload/hash, callbacks válidos y límites Telegram, payloads inválidos rechazados, HTML literal escapado y fallback seguro |
| AC8, no bypass | `tests/integration/test_proposal_consent.py` y `test_proposal_executor.py`: expiración, falta de presentación, principal ajeno, manipulación de payload/claim, concurrencia y uso único; `test_legacy_consent_boundary.py` excluye `execute_*` y rechaza APIs legacy |
| AC9, consentimiento OFF | `test_consent_off_preserves_read_answer_without_fictitious_presentation`: READ preservada, sin narración/botones ni presentación persistida; callback conocido no crea recordatorio ni invoca otra vez al Agent |
| AC9, fallo de entrega | `test_failed_or_partial_delivery_never_opens_consent_or_replays_agent`: primer/segundo chunk × definitivo/ambiguo; no abre presentación/TTL, callback no ejecuta, recuperación no reenvía ni reejecuta |
| Regresión terminal | Propuesta seguida de salida inválida no es confirmable; efecto trivial ya persistido se conserva sin duplicación/replay y se avisa consultar estado |

Refuerzo mínimo de tests, sin cambiar código funcional ni prompts:

- Tres variantes independientes en `tests/unit/test_todos_tools.py`: solo
  descripción, solo prioridad y solo fecha. Cada una solicita una propuesta
  con payload normalizado, no llama `TrivialExecutor` ni `add_item`, y no
  anuncia ejecución. Esto no reemplaza las variantes E2E Telegram de BL-46.
- Dos variantes temporales adicionales y aserciones de hash en el renderer:
  `23:59:59.999999-03:30` y `00:00:00.000123+05:45`, más comprobaciones
  de inmutabilidad en truncado, valores adversariales y timestamps existentes.

**AC8 y AC9 superados en el alcance determinista aislado exigido**, sin
demostrar resistencia semántica general del LLM mediante estos tests.
Gates locales verdes no equivalen a checks CI remotos del diff sin commit ni
prueban un nuevo SHA desplegado. Pendientes: E2E revisables descripción/fecha-sola
de BL-46 con nueva autorización, evaluación de instrucciones con LLM gobernado
y revisión final de cierre/versiones. **BL-46 y BL-48 permanecen abiertos.**

## 13. Variantes revisables restantes BL-46 — E2E asistido, 2026-10-16

Autorización explícita del propietario para continuar BL-46/48 y ejecutar las dos
variantes acordadas: descripción-sola y fecha-sola en la lista existente. Solo
crear propuestas, consultar, descartar individualmente con **No** y verificar;
nunca Sí, ni fixtures SQL, borrado, replay automático o cambios de controles.

### Preflight y versión realmente ejecutada

- Árbol limpio inicial, HEAD local `5df9273115d15843a5f743b7433a65dbce39a0c4`,
  cinco commits por delante de `origin/main`. Los resultados de §12 ya están
  comiteados por el propietario. GitHub no conoce aún ese SHA (check-runs HTTP
  422); no se afirma CI remoto para los commits locales.
- Deployment **sirviendo**: `838ab705-550c-43a9-a344-5dc1450ce73b`, SUCCESS,
  SHA `5f0132f89bde1d3287175a96d33e06e3991427d7`. GitHub check-runs de ese
  mismo SHA: `quality`, `integration`, `collector-config` completed/success.
  Sin diff en `src/`, `prompts/` ni assets de configuración frente a HEAD
  inicial. Este contraste se realiza **antes** de añadir la preparación T7 de §14.
- Railway tiene también app `7331ae20-e40f-42bb-b149-1bbc51cd5fcd` y Collector
  `4ba745b5-2c7a-459d-a2ea-52472de15e8b` en NEEDS_APPROVAL, no sirviendo;
  no se aprueban ni se confunden con los deployments SUCCESS. Collector activo
  `601ce607-cfd5-47c1-922e-3679c6e07aca`. No se modifica Wait for CI.
- Readiness 16:38:48 UTC: HTTP 200, `status=ok`, revisión 8; app, DB, Gateway,
  processor, worker y runtime healthy; `gateway_circuit=unknown`, no se transforma
  esa señal en healthy. Cola vacía. Ruta comprobada después en usage: r4.
- 16:38:00 UTC: lista `f2001d4b-413e-408b-9b99-ccafa33500c0` («Validación cierre
  16 octubre»), dos tareas originales, ningún título de las variantes y cero
  propuestas confirmables. Nota AC7 existente. Se conservan estos datos.

### Propuestas y descarte individual

| Variante | Interacción / recibida UTC | Propuesta | Payload específico y presentación |
|---|---|---|---|
| Solo descripción | `b9fc85ef-ebb0-4385-a63e-5cb7f2761b7e` / 16:38:59 | `195dce39-69c9-4ff1-8564-545bd27bb2da` | Título «Validar descripción BL46», descripción «Caso sintético de revisión de descripción», prioridad/fecha null; presentada 16:39:12, vence 16:54:12 |
| Solo fecha | `70f4eba1-5c23-455f-a700-0c635c44e47e` / 16:39:49 | `d6c4052f-d918-45cc-a4cc-12ea59bde66f` | Título «Validar fecha sola BL46», `due_date=2026-10-20T00:00:00`, prioridad/descripción null; presentada 16:40:04, vence 16:55:04 |

Ambas `create_todo_item`, lista de campaña exacta, `explicit_confirmation` /
`pending_confirmation`, `confirmed_at`/`executed_at` null. SQL antes de los
callbacks: **cero tareas con los dos títulos**. DOM: un bloque Core por petición,
título y campo opcional correctos, fecha «20 de octubre de 2026», una instrucción
de consentimiento y un par de botones por propuesta; sin anuncio de ejecución
ni resumen duplicado. No se deduce esa presentación solo de un schema válido.

Hashes recalculados localmente mediante `payload_hash('create_todo_item', payload)`:

- Descripción: `5154f7886da79b8cd8c9d5c7296b8833b22f5c38b25e25a7c0f76bec5660998c`.
- Fecha: `3a69e8d59157c9734ef4e3769ddc33bf3c846034d64f9285ba8ec4a72d5e27e9`.
- **2/2 coinciden**, también intactos después del descarte.

Consulta explícita de pendientes `6a604f65-1b64-44aa-88a0-d573a17c9aa4`, 16:40:38
UTC: enumera las dos propuestas y sus datos, sin añadir otras. Después:

- Un clic en **No** del bloque descripción: callback
  `522b4c29-664e-45cd-90b1-b03d65df701f`, recibido 16:41:29 UTC; `discarded`
  a 16:41:30. Verificación intermedia: la propuesta de fecha sigue pendiente.
- Un clic en **No** del bloque fecha: callback
  `a3fe0b56-4492-43aa-9f89-7e7115f3d93b`, recibido 16:41:46 UTC; `discarded`
  a 16:41:47. Ambas sin confirmación/ejecución/interacción confirmante.
- Los dos callbacks `completed`, **cero tools/cero llamadas LLM**; DOM responde
  «Propuesta descartada.» en ambos. Selectores acotados a un único bloque por
  título y botón No exacto; errores de localización previos ocurrieron antes del
  clic/envío, no son operaciones reintentadas tras resultado ambiguo.
- Consulta posterior de todas las tareas, incluidas completadas:
  `1b9928e5-6b0a-49a3-bafc-961d29be5c01`, 16:42:35 UTC. Muestra solo póliza
  y reapertura pendientes, sin completadas, inventario de propuestas ni oferta
  de reproponer lo descartado.

Cuatro turnos Agent: completed, revisión 8/r4; 3+2+2+3 llamadas LLM completadas,
cero retries; **0,01245380 USD estimados** (`pricing_snapshot`), coste real no
reportado (`actual_cost` null en 10/10), no se afirma coste cero. Las seis
interacciones tienen `agent_final` y un chunk completed con message ID; sin
`failure_notice`. SQL scoped a la identidad de campaña, sin contenido interno Agno.

### Trazas nominadas, no deducidas de contadores

Grafana Tempo `grafanacloud-traces`, ventana 16:38–16:44 UTC; búsquedas HTTP 200,
misma consulta de §11. `agno.run_id` coincide con ledger y revisión 8 en cada span:

| Interacción | Trace ID | Tools observadas en orden |
|---|---|---|
| `b9fc85ef-ebb0-4385-a63e-5cb7f2761b7e` | `db48b4c826c027ae84ae36351ff8870d` | `list_todo_lists` → `propose_todo_item` → `present_reply` |
| `70f4eba1-5c23-455f-a700-0c635c44e47e` | `99b244a4881cec12eff4c138c34a9925` | `propose_todo_item` → `present_reply` |
| `6a604f65-1b64-44aa-88a0-d573a17c9aa4` | `291a326d682a76f2495e9c4b91b7a66b` | `list_pending_proposals` → `present_reply` |
| `1b9928e5-6b0a-49a3-bafc-961d29be5c01` | `5c1aaf3512bba182a55253d4b01c0b8b` | `list_todo_lists` → `list_todo_items` → `present_reply` |

Foto final SQL 16:44:48 UTC: exactamente dos propuestas nuevas, ambas
descartadas; cero nuevas auditorías ejecutadas/triviales, cero confirmables,
dos tareas originales con **mismos campos y `updated_at` que en preflight**,
nota AC7 exacta única y revisión 8 intactas. No se crean tareas ni se eliminan
los datos sintéticos anteriores. **Variantes pendientes BL-46 superadas**.

## 14. Decisión de gate y preparación del harness real — 2026-10-16

El propietario elige expresamente **ejecutar el harness real aislado**, preparando
antes wiring/ruta/presupuesto/acceso seguro, y mantener BL-48 abierto hasta
resultados. No se sustituye ese gate por la evidencia manual del LLM en Telegram.

- `src/agent/eval_campaign.py`: plan secret-free, snapshot tipado explícito,
  ruta/capacidades/pricing, reserva total y límites no ampliables; construcción
  mediante `AgnoLLMAccess` Gateway-only, uso en memoria sin FK/DB productiva.
- `GovernedPhysicalEvalExecutor` acepta snapshot/límites de campaña, rechaza
  revisión incorrecta antes de resolver modelo, presupuestos independientes por
  caso y deadline; envío de `max_tokens` al SDK probado con HTTP simulado.
- `scripts/eval_preflight.py` no ejecuta inferencia; con `--check-gateway` solo
  GET `/v1/models`, sin redirects y exige clave restringida al alias exacto.
  Env específica, no .env ni credenciales ambiente; no se abre dominio/túnel.
- Candidato `evals/response_style/bl48-campaign-plan.json`: cinco casos BL-48,
  default/r4 revisión 8; hasta 6 model calls/6 requests, 12 tools, 120 s y
  1024 tokens de salida por caso. **0,02 USD estimados/caso; 0,10 USD total**.
  Es reserva estimada, no techo garantizado de facturación. Aprobación pendiente.
- Snapshot exportado de solo lectura a `runtime-rev8-snapshot.json`, sin secretos
  ni publicación/activación. Fingerprint de contenido eval
  `a41f255f1b4022bc5ac1c7efb35a02d82fb4ec2396d71f4991fea1db15f7cccc`.
  Plan checksum `8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139`.
- Hallazgo: checksum histórico rev. 8 `e2663c6a…db25` no reproducido localmente;
  `config_checksum` serializa `frozenset` sin ordenar y cambia entre procesos.
  Esa variación está probada; **no se afirma que explique por sí sola la
  discrepancia histórica**. No se cambia el checksum/policy productivo ni se
  simula otra revisión. El plan liga referencia histórica y fingerprint de
  contenido estable (capacidades ordenadas), no certifica el algoritmo anterior.
- Preflight candidato exit 0: `inference_started=false`, `gateway_access=not_checked`,
  `approval_status=pending_separate_approval`, `semantic_status=not_evaluated`.
  Fingerprint idéntico en tres procesos y tests con `PYTHONHASHSEED=1/2`.
- **1465 unitarias passed, 80,19 % cobertura; 173 integraciones passed, 1 STT live
  skipped**; Ruff global y mypy (173 archivos) limpios; catálogo estático 36 casos
  y 9 ejemplos provisionales. 36 pruebas focales de campaña/executor superadas,
  incluidas LLMAccess/SDK/terminal mediante HTTP mock, no proveedor real.

La preparación no incluye lanzador de campaña pagada, juez calibrado, credenciales
ni red nueva. Antes de ejecutar faltan aprobación exacta del plan/coste/privacidad,
acceso privado autorizado, clave exclusiva con alias y presupuesto externo
verificados y revisión del SHA evaluado. No se autoestablecen flags de aprobación
ni se desactiva la parada productiva. No se llama directamente al provider.
**BL-46 queda completado funcionalmente; BL-48 sigue abierto por ejecución real y
evaluación de instrucciones**, con scoring no evaluado hasta evidencia suficiente.