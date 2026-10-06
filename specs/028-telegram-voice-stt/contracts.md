# Contratos propuestos — specs/028

> T2, 2026-10-06: modelos/puertos/políticas puros implementados en
> `src/domain/speech/`; infraestructura, evidencia durable y wiring pendientes.
> Usar Pydantic v2/modelos inmutables y Protocol; domain sin Agno/SDKs físicos.

## Entrada y preparación

| Contrato | Campos / responsabilidad |
|---|---|
| `TelegramAttachment` extendido | `kind=voice`, file_id acotado, duración declarada, MIME opcional, size_bytes opcional; referencia cifrada, no bytes |
| `VoiceInputOrigin` | interaction_id, bot_id, chat_id, user_id, accepted_at, message_id, generación y origen original/reenviado/editado; resuelto por canal/Core, no por STT |
| `ValidatedVoiceAudio` | bytes transitorios (`repr=False`), MIME/codec verificados, duración real finita >0 y <=300, tamaño real <=10 MiB; sin filename original |
| `SpeechInputPolicy` | enabled=false por defecto, límites, formatos, timeout operativo; rechaza metadata inválida y archivo real inconsistente |

Metadata ausente de tamaño/MIME no implica rechazo automático: validar bytes.
Duración declarada ausente/no válida rechaza la referencia; duración real mayor
que límite rechaza antes de STT. No fiarse de extensión ni de MIME arbitrario.
Parser/decoder determinista acotado, sin ejecutar archivos; dependencia concreta
de inspección/conversión documentada en `inspection-design.md`, no instalada.

## STT gobernado

Puerto conceptual:

`SpeechToTextPort.transcribe(audio: ValidatedVoiceAudio, *, execution_context: ExecutionContext) -> SpeechToTextResult`

- `SpeechToTextResult`: texto (`repr=False`, no vacío, longitud máxima validada),
  duración procesada, idioma opcional, referencias de uso/llamada. No extrae
  acciones, permisos, user_id ni proposal_id. Nunca exportar `model_dump` completo.
- `SpeechBillingPolicy`: tarifa Decimal USD/segundo >=0, quantum >0, mínimo >=0,
  versión y unidad `duration_seconds`; valores finitos. Cálculo determinista de
  estimación/cota, compatible con límites de coste del contexto.
- `GovernedSpeechToTextAccess`: infraestructura propietaria del cliente físico,
  resolve ruta lógica `ancoramind-stt` → alias versionado por snapshot, valida
  política/gasto/deadline, reserva estimación y registra intento/resultado/uso.
  Cliente sólo dentro de esa frontera; ninguna creación de provider en domain.
- Uso durable: interaction_id, call_id, revisión, ruta/alias, proveedor/modelo,
  segundos facturables, bytes, estimación/coste real/cost_source, latencia, estado,
  código de error acotado, retries=0. Contadores STT separados de turns de chat,
  pero incluidos en gasto y requests de la interacción. No tokens ficticios.
- Revisión de config sin sección STT sigue válida; enabled=true requiere ruta,
  tarifa y capacidades válidas. Configurar legacy/texto no exige credenciales STT.
- Persistir intención durable de llamada antes de enviar: exclusividad por
  interaction_id/call_id; fallo de persistencia previa bloquea el proveedor.
  Distinguir fallo conocido sin petición de fallo tras envío ambiguo. Fallo de
  auditoría posterior no habilita repetir ni oculta gasto reservado pendiente.

## Preparación / entrega

- `VoicePreparationPort`: coordina referencia → descarga → inspección → STT
  bajo claim exclusivo del processor. No pertenece al webhook HTTP; se devuelve
  2xx tras admisión durable sin esperar STT.
- `PreparedVoiceInput`: texto cifrado/referencia a resultado, origen validado y
  snapshot/contexto fijado; no una nueva identidad ni un segundo update.
- Repository: reclamar preparación atómicamente y hacer transiciones condicionales;
  persistir transcripción cifrada/resultados antes de ruta Agent/consentimiento;
  recover clasifica in-flight sin reenvío. SQL parametrizado/user-scoped.
- Agent runner: aceptar contexto capturado o una extensión equivalente que
  garantice snapshot/reservas compartidos; media=() para voz, sólo texto al modelo.

## Consentimiento

`parse_voice_consent_intent(text) -> confirm | discard | None` reconoce frase
completa, usando reglas estrechas del parser actual para Sí y equivalentes para
No. No interpreta callback_data de STT, citas o «sí y borra otra cosa».

`VoiceConsentEvidence` vincula interacción admitida original, resultado STT
exitoso persistido y principal. No puede construirse a partir de documentos,
historial ni argumentos del modelo. No incluir la transcripción en el token
de permiso o en telemetría; referencia durable suficiente.

El resolver Core lista exactamente una confirmable del mismo principal y
generación; verifica entrega anterior al accepted_at y caducidad al claim.
Confirmación: mismo claim/ejecutor gobernado, consumo único. Descarte: transición
condicional pending → discarded con evidencia auditada; sin ejecución. Si la
propuesta cambió durante STT, rechazo determinista. Ningún flag habilita legacy
como fallback para ejecutar una confirmación vocal.

## Errores acotados

Categorías objetivo: voice_disabled, voice_origin_not_allowed,
voice_duration_exceeded, voice_too_large, voice_format_not_allowed,
voice_empty_or_invalid, stt_route_unavailable, stt_tariff_unavailable,
stt_budget_exceeded, stt_timeout, stt_failed, stt_result_empty,
stt_result_invalid, stt_result_ambiguous. Traducción a respuesta española
determinista por categoría; nunca reenviar mensajes crudos del proveedor.

Timeout o error tras envío no prueba ausencia de cargo; registrar ambiguo y
mantener reserva. Resultado demasiado largo/no válido no se trunca para convertirlo
en un «Sí». No fallback a documento o modelo de chat.