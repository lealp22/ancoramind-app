# Spec: 036 — Presentación única de propuestas en Telegram

> **Backlog:** BL-48 — P1, calidad de la validación del MVP.
> **Fecha:** 2026-10-14.
> **Estado:** desplegado, E2E parcial; AC1/AC2/AC4/AC6 y AC3/AC7 asistidos constan con rev. 8;
> AC5 acreditado con trazas nominadas recuperadas; AC8–AC9 superados en aislamiento
> y gates locales verdes (1465 unitarias, 173 integraciones, 1 STT live omitida;
> incluye preparación local del harness, todavía no desplegada).
> Variantes revisables BL-46 también superadas (§13). Por decisión del propietario,
> BL-48 sigue abierto hasta harness real aislado: preparación/preflight sin
> inferencia en §14; presupuesto/acceso/ejecución y evaluación aún pendientes.
> **Autorización:** implementación, despliegue y rollout de runtime rev. 8
> aprobados; evidencia operativa registrada hasta 2026-10-16.
> **Relacionado:** BL-46/specs/035, BL-47 y BL-39/40/specs/023.

## 1. Problema y evidencia

Durante la prueba E2E de TODOs, el propietario solicitó una tarea con
prioridad alta y vencimiento el 20 de octubre de 2026. La respuesta presentó
dos veces título, prioridad y fecha, además de dos instrucciones de
confirmación: primero el texto del Agent y después el bloque del Core con
botones Sí/No. Este último usó `high` y `2026-10-20T00:00:00`.

La duplicación tiene un mecanismo comprobado: `InteractionProcessor`
concatena contenido del modelo y bloques de `render_proposal_block`, cuya
fuente es el payload persistido. Además, los prompts actuales piden al
Agent resumir la propuesta y solicitar confirmación; no delimitan quién
es dueño de esa presentación en Telegram.

El propietario pulsó No y recibió «Propuesta descartada». La siguiente
consulta de todas las tareas solo mostró «Comprar café» completada: el
descarte no produjo la escritura. La respuesta añadió que no había
propuestas pendientes y ofreció reproponer lo recién rechazado.

No se dispone de traza de tools de ese turno. La observación **no demuestra**
que `list_pending_proposals` no se invocara: el problema comprobado es el
contenido no solicitado, no un bypass de autorización ni un fallo probado
de BL-47. Más evidencia funcional y operativa en `verification.md`.

## 2. Resultado esperado

- Una única presentación de datos e instrucción de consentimiento por
  propuesta, generada por el Core desde lo guardado.
- Prioridades y fechas legibles sin modificar sus valores canónicos.
- Después de descartar, responder a la consulta solicitada, sin insistir
  en reproponer la acción rechazada.
- Cualquier afirmación sobre propuestas pendientes se apoya en una lectura
  actual de `list_pending_proposals`, nunca solo en historial conversacional.

Ejemplo de propuesta TODO (formato ilustrativo, no texto literal obligatorio):

```text
📋 Propuesta: Añadir tarea
   Título: Renovar el seguro
   Prioridad: alta
   Fecha límite: 20 de octubre de 2026
Pulsa ✅ Sí para confirmar o ❌ No para descartarla (válida 15 min).
[✅ Sí] [❌ No]
```

El nombre de la lista no se inventa desde el historial ni se obtiene del
UUID para decorar el bloque. Mostrarlo exigiría resolver el target con una
lectura autorizada; no es requisito de esta primera iteración.

Ejemplo de consulta posterior al descarte:

```text
Prueba Telegram 01
• ✅ Comprar café — completada

No hay tareas pendientes.
```

## 3. Alcance y límites

### Obligatorio

1. El Core conserva la presentación autoritativa y los botones. El Agent
   no repite campos ni pide de nuevo Sí/No para las propuestas que ese
   circuito presenta. Nunca anuncia ejecución por el mero hecho de proponer.
2. Mantener información útil independiente en peticiones mixtas: si el
   usuario pide una consulta y una propuesta en el mismo turno, no eliminar
   la respuesta a la consulta para ocultar la duplicación. Si se generan
   varias propuestas, cada una conserva su bloque y controles propios.
3. Traducir prioridades conocidas `high`/`normal`/`low` a
   «alta»/«normal»/«baja» en el renderer determinista.
4. Presentar el vencimiento TODO de este caso como fecha legible. No asumir
   que todo timestamp a medianoche es una fecha sin hora: eventos y
   recordatorios deben mantener hora y semántica de zona horaria. No
   interpretar fechas con el LLM ni perder información temporal.
5. No ofrecer automáticamente volver a crear una propuesta descartada.
   Una nueva petición explícita del usuario sí permite proponer de nuevo.
6. Una consulta de tareas no añade un inventario de propuestas. Cuando el
   usuario solicite ese estado, consultar `list_pending_proposals` y limitar
   la afirmación a su alcance real (hoy usuario, no inventar alcance de chat).
7. Alinear contrato, soul, política Telegram y skills afectados: evitar
   instrucciones contradictorias sobre resumir/pedir confirmación y
   distinguir `WRITE_TRIVIAL` de `WRITE_REVIEWABLE`. Prompts en Git; el cambio
   es evaluable y debe identificarse como tal al implementarse.

### Invariantes que no cambian

- El Core decide identidad, autorización, confirmación y ejecución.
- Payload, hash y datos guardados no cambian por formatearlos para el chat.
- Presentación verificada, TTL de 15 minutos, validación de principal y
  claims únicos se conservan. No botones ni propuestas ficticios.
- Consentimiento desactivado sigue sin ejecutar operaciones revisables.
- Triviales no generan un bloque Sí/No ni entran en el claim de confirmación.
- Escapado de HTML, límites de campos/chunks y entrega segura se mantienen.

### Fuera de alcance

- Confirmación por lotes (BL-45), undo, nuevos tiers o excepciones WRITE.
- Nuevos agentes, tools, providers, dependencias, flags o migraciones.
- Rediseño general del chat o nueva política de zona horaria.
- Filtros regex que intenten deducir de prosa libre del LLM qué consentir.
- Reintentos automáticos, cambios de auditoría, despliegue o escritura de
  fixtures en las bases productivas.

## 4. Diseño de implementación propuesto

Reutilizar la separación existente: renderer de propuestas del Core,
composición del procesador y assets de instrucciones. Las instrucciones
del Agent deben reconocer que el Core muestra la propuesta, en vez de
obligarlo a reproducirla. La traducción de campos vive en el renderer y
nunca se persiste de vuelta al payload.

**Contrato actual (corrección 2026-10-15):** `AgentReply` (Pydantic, dominio
sin Agno) separa `answer` de `proposal_text`. Se retiran `output_schema` y JSON
mode del bucle principal, introducidos el 2026-10-14. La partición se obtiene
mediante `present_reply`, herramienta terminal de presentación sin I/O canónico,
con `stop_after_tool_call=True`. Su descripción procede de
`prompts/skills/presentation.md`. `tool_choice="required"` impide finalizar con
un completion textual; saludos y aclaraciones terminan directamente mediante
esta herramienta, sin lecturas personales innecesarias. No fuerza una tool de
dominio concreta ni garantiza su elección semántica.

El runner acepta solo el resultado validado de una ejecución terminal exitosa,
única y última de `present_reply`; nunca prosa, JSON en `content` ni argumentos
sin ejecución. No hay parser/modelo secundario, reintento ni inferencia posterior
al cierre. La herramienta consume una llamada del presupuesto existente (12);
no se amplía ningún límite. El harness físico usa el mismo contrato, pero excluye
la presentación de los veredictos de tool calling de dominio.

El Core sustituye **solo** `proposal_text` cuando encuentra propuestas de
esa interacción y usuario. Conserva `answer` (READ, errores, resultado
trivial y advertencias necesarias que no consten en el bloque). Sin
propuestas, o con consentimiento OFF, descarta `proposal_text`: nunca entrega
una narración de propuesta como evidencia de persistencia. Si no queda respuesta
independiente, comunica que no se ha presentado ninguna propuesta. Un
adaptador de pruebas que devuelva texto sin propuestas sigue funcionando;
si crea propuestas sin partición se rechaza, no se analiza prosa para
deducir su contenido. `AgentReply` exige que al menos uno de sus campos
contenga texto no vacío: tras un `propose_*` correcto el Agent devuelve el
texto no autoritativo como `Propuesta creada.` en `proposal_text`, que el Core
sustituye por su bloque persistido. Un JSON con ambos campos vacíos no es una
respuesta válida ni una forma de omitir una tool requerida.

**Límite explícito:** el Core garantiza la sustitución del campo correcto y
que los bloques proceden de Postgres, pero la clasificación del texto en
`answer`/`proposal_text` sigue siendo probabilística. Si el modelo incumple
el contrato y duplica campos en `answer`, un esquema válido no lo detecta.
No se afirma garantía semántica con prompts, mocks ni `tool_choice`: requiere
evaluación y E2E reales. No se descarta toda la respuesta del Agent.

**Vencimiento TODO:** el modelo actual no conserva un indicador fecha-sola:
una fecha se normaliza como medianoche sin zona. El renderer adopta esa
convención solo en `due_date` TODO; conserva horas no nulas, fracciones y
offsets explícitos, incluida medianoche con zona. Eventos/recordatorios se
mantienen sin reinterpretación. No hay conversión de zona ni cambio de payload.

## 5. Criterios de aceptación

| ID | Caso | Resultado requerido |
|---|---|---|
| AC1 | Proponer tarea con prioridad alta y fecha | Una sola presentación de campos y un pedido de confirmación; prioridad y fecha legibles; pendiente, no guardada |
| AC2 | Consulta + propuesta en el mismo turno | Se conserva la respuesta READ y un solo bloque de la propuesta |
| AC3 | Varias propuestas en un turno | Un bloque por propuesta, con botones vinculados al ID correcto; sin consentimiento por lote |
| AC4 | Pulsar No y consultar todas las tareas | Propuesta descartada, tarea ausente; sin oferta de reproponer ni inventario de propuestas no solicitado |
| AC5 | Pedir explícitamente propuestas pendientes | Lectura real; propuestas descartadas, ejecutadas o caducadas no aparecen como pendientes |
| AC6 | Pedir explícitamente de nuevo la acción descartada | Nueva propuesta legítima, no ejecución ni reintento automático de la anterior |
| AC7 | Añadir tarea título-solo, completar/reabrir y guardar nota | Sigue la vía trivial sin botones de confirmación |
| AC8 | Hora, zona, límites y contenido adversarial | Sin pérdida temporal, bypass, HTML no escapado ni alteración del payload/hash |
| AC9 | Consentimiento OFF o entrega fallida | Sin ejecución ni presentación confirmable ficticia; conserva garantías existentes |

**Cierre:** tests de presentación/composición y regresiones de consentimiento
verdes, gates globales, evaluación de instrucciones y E2E Telegram de
AC1–AC7 con evidencia de la versión realmente desplegada. La documentación
actual no da por validado ninguno de esos cambios futuros.