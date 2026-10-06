# Spec: 028 — Notas de voz Telegram y STT gobernado

> **Backlog:** BL-26
> **Status:** T2 implementado localmente (políticas/contratos/tests); runtime pendiente
> **Fecha:** 2026-10-06
> **Target:** nota de voz privada autorizada → STT gobernado → solicitud o
> consentimiento determinista → respuesta textual, sin duplicar efectos.

## 1. Alcance acordado

- Entrada: `message.voice` original de un usuario autorizado en chat privado.
- Duración máxima: **300 segundos (5 minutos), inclusive**. La duración declarada
  permite rechazo temprano; antes de STT se valida también la duración real.
- Tamaño propuesto para el MVP: **10 MiB (10 * 1024 * 1024 bytes), inclusive**,
  independiente de la duración. Es un límite de producto, pendiente de validar
  en el piloto, no un requisito del proveedor. Descarga streaming acotada.
- Primera ruta de formato: OGG/Opus validado por contenido, no sólo por MIME.
  Si las muestras reales requieren otro formato, ampliar política y tests antes
  de aceptarlo. Conversión únicamente si la ruta STT elegida la requiere.
- Respuesta textual mediante la outbox existente. Voz no se archiva como documento.
- Transcripción como mensaje del usuario: mismas tools y gobernanza que texto,
  sin elevar permisos ni añadir subagentes o una tool STT decidida por el LLM.
- **«Sí» y «No» por voz son alternativas válidas al texto/botones**, con los
  controles deterministas de §3. No obligar a confirmar otra vez por escrito.
- Activación mediante flag nuevo, apagado por defecto; texto/fotos/documentos
  siguen funcionando cuando voz está desactivada. Voz desactivada produce una
  respuesta acotada sin descargar, transcribir ni ejecutar al Agent.

Fuera de alcance: TTS (BL-27), música/`message.audio`, audio como documento,
video, diarización, clonación de voz, biometría de hablante, OCR, almacenamiento
documental del audio y publicación/activación remota en este incremento.

## 2. Coste: límite temporal, no segundo presupuesto manual STT

No se exige introducir un techo USD independiente para cada nota de voz.
Para una ruta con facturación por duración, el coste se deriva de la duración
validada y una **tarifa versionada** del snapshot. El contrato representa tarifa
por segundo, unidad de redondeo y mínimo facturable; no supone proporcionalidad
perfecta ni que todos los proveedores facturen igual.

`billable_seconds = max(minimum_seconds, ceil(duration / quantum) * quantum)`

`estimated_cost_usd = billable_seconds * rate_usd_per_second`

La cota STT por nota se deriva de 300 segundos y esos mismos parámetros. Duración
limita una nota, pero no la suma de muchas notas ni el coste posterior del Agent:
se mantienen rate limits, gasto diario/mensual/por ruta y presupuesto de la
interacción existentes. Reservar coste **antes** de la petición y contabilizar
STT incluso si no hay Agent (confirmación, error o transcripción vacía).

Tarifa ausente/no válida o esquema de facturación no soportado: fail-closed antes
del proveedor. Cero es válido sólo para una ruta explícitamente configurada sin
coste. Conservar estimación si el proveedor no informa coste real; nunca inventar
coste cero. Reconciliar coste real sin sobrescribir tarifa/alias históricos.
No se fija modelo, precio real ni timeout operativo sin verificar Gateway y piloto.

## 3. Consentimiento verbal

La transcripción de una nota de voz **actual, original y admitida** puede ser
evidencia candidata de intención, no autorización por sí misma. La identidad
proviene de Telegram; no se identifica a la persona por su voz. La transcripción
STT mantiene procedencia confiable del canal y contenido no confiable.

- Sólo frase aislada reconocida por parser determinista: «Sí»/«Si» y «No»,
  con mayúsculas y puntuación terminal limitada; sin extracción de palabras
  dentro de frases, citas, historial, documentos o respuestas del Agent.
- No interpretar cadenas de callback ni comandos `/new` o `/help` sintetizados
  por STT como eventos de control. Los comandos requieren texto original.
- Confirmar/descartar sólo con exactamente una propuesta pendiente, presentada,
  vigente del mismo usuario/bot/chat y generación de conversación. Varias → pedir
  selección sin escoger la última; cero → respuesta determinista sin efectos.
- El `accepted_at` de la voz debe ser posterior a la entrega verificada de la
  propuesta. Comprobar caducidad de nuevo al hacer claim tras STT. La demora de
  transcripción no convierte un «sí» anterior en consentimiento posterior.
- Claim atómico y revalidación de payload/propiedad, sin LLM para interpretar
  consentimiento. Un «sí» válido no necesita un Agent run. «No» descarta, no
  ejecuta ni concede permiso. Añadir equivalente escrito «No» sin regresiones.
- Duplicados, carreras y reutilización del evento no crean varios claims/efectos.
- Audio reenviado, editado, con entrada mezclada/caption, corrupto, vacío o STT
  fallido no es confirmación. Un rechazo que parezca consentimiento no se delega
  al Agent para que autorice. No asumir confidence si el proveedor no la ofrece.
- La aceptación del riesgo residual de error STT permite esta UX; no afirmar que
  transcribir «Sí» prueba biométricamente la intención. Evaluar silencios, ruido,
  negaciones y alucinaciones en corpus consentido antes de activar.

Este contrato extiende para voz la exclusión histórica de adjuntos de
specs/022/consent-design.md; NO la relaja para documentos, fotos ni audio de
terceros. Se conservan los invariantes normativos de AGENTS.md/architecture.

## 4. Integración y estados durables

El normalizador actual sólo conserva photo/document. El processor genera una
instrucción documental cuando hay adjunto sin texto y reclama `agent_started`
antes de descargar. Introducir una rama voz separada, nunca ese fallback.

Diseño objetivo de preparación (subestado durable, no estado sólo en memoria):

`accepted → preparing [claim exclusivo] → downloaded → transcribing → transcribed`

Desde `transcribed`: consentimiento determinista → outbox, o solicitud → claim
`agent_started` → Agent → outbox. Las confirmaciones válidas usan cero Agent runs.
No persistir `downloaded` como señal de que los bytes transitorios siguen
disponibles después de reiniciar. Crash con trabajo reclamado sin finalización:
fallo controlado si se prueba que no hubo petición/efecto; de otro modo ambiguo,
sin replay automático. Crash tras STT o tras claim de acción: no retranscribir
ni reejecutar. Nueva petición del usuario para reintento explícito.

Capturar un snapshot/contexto antes de STT y conservar esa revisión para el
Agent de la misma interacción. No inventar un Agent ejecutado para tener un
`ExecutionContext`: preasignar correlación/run previsto, persistir inicio real
sólo en el claim del Agent. Conservar deadline de procesamiento separado de
duración del audio y coordinar presupuesto STT/Agent sin resetear reservas.

Audio transitorio en memoria acotada; cualquier temporal imprescindible se
elimina en success/error/cancel. Texto transcrito persistido cifrado con retención
no mayor que payload Telegram. Audio/transcripción, filenames, file IDs, URL con
token y cuerpos/excepciones del proveedor nunca salen a logs/OTel. Señales de
etapas metadata-only; progreso UX BL-32 no bloquea entrega textual final.

## 5. Dependencias y gates

- `AgnoLLMAccess.model_for()` devuelve Model de chat: diseñar acceso STT gobernado
  explícito, no disfrazar audio como chat ni introducir provider directo.
- Extender config/ledger para duración, tarifa y uso STT con compatibilidad hacia
  atrás. Migración Alembic + init.sql si cambian tablas/constraints.
- Consentimiento determinista actual depende de `governed_consent_enabled`.
  `_execute_claimed()` todavía sólo informa confirmación: cerrar ese wiring de
  BL-40/specs/023 antes de declarar E2E de «sí» → ejecución real. No habilitar
  una ruta alternativa de ejecución desde el LLM.
- El parser escrito actual sólo acepta «Sí»; descarte escrito/verbal y validación
  de procedencia necesitan implementación y pruebas, no sólo reutilizarlo.
- Verificar endpoint STT, soporte Gateway, tarifa, retries efectivos y límites
  del proveedor antes de seleccionarlo. Sin fallback directo; un intento STT
  como máximo por update, también en Gateway.

## 6. Entregables y referencias

- `contracts.md`: contratos propuestos, aún no conectados al runtime.
- `acceptance.md`: matriz de aceptación y nivel de evidencia requerido.
- `tasks.md`: incrementos y dependencias de implementación.
- `verification.md`: evidencia obtenida, separada de aceptación pendiente.

Referencia externa revisada el 2026-10-06: Telegram Bot API `Voice`/`getFile`,
https://core.telegram.org/bots/api#voice y
https://core.telegram.org/bots/api#getfile. Metadata declarada no sustituye
validación del archivo. No incorporar precios del backlog como tarifas verificadas.