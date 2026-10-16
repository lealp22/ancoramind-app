# Tasks: 036 — Presentación única de propuestas en Telegram

> **Fecha:** 2026-10-14. **Estado a 2026-10-16:** desplegado, E2E AC1–AC7
> registrado con revisión 8/r4 (AC3/AC7 asistidos). AC5 trazado y AC8–AC9
> revalidados en aislamiento; gates locales verdes. Evaluación real de
> instrucciones y cierre global pendientes; ver `verification.md` §§11–12.

## T1 — Contrato Agent/Core de presentación

- [x] Revisar la composición en `src/domain/interactions/processor.py` y
      el contrato de resultados `propose_*`, conservando el bloque del Core
      como presentación autoritativa desde el payload persistido.
- [x] Definir e implementar el ajuste mínimo que evita repetir campos y
      confirmación sin eliminar respuestas READ de mensajes mixtos.
- [x] Cubrir varias propuestas, ausencia de propuestas, resultados de error
      y consentimiento OFF; no añadir un parser de consentimiento sobre
      prosa del LLM ni un borrado indiscriminado de su respuesta.
- **Listo cuando:** AC1–AC3 y AC9 quedan cubiertos en pruebas deterministas
  de composición; la obediencia del modelo real queda para T4/T5.

## T2 — Campos legibles en el renderer

- [x] Adaptar `src/domain/actions/presentation.py`: prioridades conocidas
      en español y vencimiento TODO legible a partir del valor persistido.
- [x] Mantener hora y semántica de zona cuando corresponda; no tratar todos
      los timestamps de medianoche como fechas sin hora.
- [x] Mantener límites, ocultación de identificadores y escapado posterior
      por `src/notifications/markup.py`; sin mutar payload ni hash.
- [x] Ampliar `tests/unit/test_proposal_presentation.py` con las prioridades,
      fechas, horas y zonas relevantes, valores no esperados y límites.
- **Listo cuando:** AC1 y AC8 se validan sin dependencias ni migraciones.

## T3 — Instrucciones concisas y coherentes

- [x] Alinear `prompts/tool_contract.md`, `prompts/soul.md`,
      `prompts/channels/telegram.md` y los skills afectados: no pedir al
      Agent un segundo resumen/consentimiento que ya presenta el Core.
- [x] Preservar la distinción trivial/revisable y las negativas/error:
      eliminar duplicación no implica relajar autorización ni esconder fallos.
- [x] No ofrecer automáticamente reproponer tras No; permitir una nueva
      propuesta cuando el usuario la solicite explícitamente.
- [x] Acotar consultas de tareas a tareas; cualquier afirmación sobre
      propuestas pendientes necesita `list_pending_proposals` y su alcance
      real. No consultar herramientas adicionales por mera proactividad.
- **Listo cuando:** no hay instrucciones contradictorias sobre quién
  presenta propuestas; AC4–AC7 están reflejados en los assets versionados.

## T4 — Pruebas y evaluación

- [x] Extender `tests/unit/test_interaction_processor.py` con mensajes
      simples/mixtos, varias propuestas y controles correspondientes.
- [x] Ejecutar regresiones unitarias de descarte, claim único, presentación verificada,
      expiración, principal, OFF y ausencia de `execute_*` en el Agent.
- [x] Ejecutar regresiones TODO/notas triviales y de consulta de pendientes.
- [x] Añadir casos sintéticos al catálogo/evaluación existente para resumen
      no duplicado, consulta tras descarte y nueva petición explícita.
      Identificar el cambio de prompts como cambio evaluable.
- [x] No atribuir validación semántica real al runner estático ni al harness
      sin inferencia: usar una ruta gobernada autorizada cuando esté disponible
      y registrar lo que quede sin verificar.
- [x] Corregir la regresión del contrato de presentación detectada el
      2026-10-15: el Agent no puede terminar con ambos campos vacíos antes
      de llamar una tool requerida; una propuesta creada usa un marcador no
      vacío que el Core reemplaza por el bloque canónico.
- [x] Segunda corrección tras preámbulos/falsas propuestas en pruebas manuales:
      retirar JSON mode/output_schema del bucle principal, usar cierre terminal
      `present_reply` con `tool_choice=required` y no entregar `proposal_text`
      sin filas persistidas. Cubrir request SDK real con HTTP simulado, hooks,
      presupuesto, saludos, READ, trivial, propuesta y turno mixto. Los mocks
      no acreditan la selección semántica del modelo real.
- [x] Ejecutar `pytest tests/unit/`, Ruff y `mypy src/`.
- [x] Revalidar gates locales 2026-10-16: 1433 unitarias, cobertura 80 %, 173
      integraciones y una STT live omitida; Ruff/mypy y build/validate Collector
      verdes. AC8–AC9 aislados, sin fixtures ni controles OFF en producción.
- [ ] Evaluar instrucciones con LLM real gobernado: no ejecutado; la prueba
      con Agno/modelo simulado verifica el protocolo de cierre, no semántica.
- **Listo cuando:** pruebas deterministas verdes y evidencia semántica
  distinguida de la mera validez del catálogo.

## T5 — E2E Telegram y cierre

- [ ] Solo tras autorización de despliegue, revisar checks del mismo SHA y
      registrar SHA/deployment. No reactivar Wait for CI automáticamente.
- [x] Repetir propuesta TODO con prioridad/fecha: bloque único y legible
      (AC1/AC2, paso 2).
- [x] Pulsar No y consultar todas las tareas: la rechazada no existe; no
      se ofrece automáticamente de nuevo ni se añade un inventario de propuestas.
- [x] Pedir pendientes explícitamente y pedir de nuevo la acción rechazada:
      lecturas reales y una nueva propuesta; trazas AC5 recuperadas en §11.
- [x] Validar respuesta mixta y varias propuestas, y regresión de triviales
      (incluidas completar/reabrir y nota) sin botones; pasos 2/8–10,
      distinguiendo ejecución personal de asistida autorizada.
- [ ] Actualizar `verification.md` y el estado de BL-48 solo con evidencia;
      no reescribir el historial de tareas completadas de specs anteriores.
- **Listo cuando:** se cumplen los criterios de cierre de `spec.md`.