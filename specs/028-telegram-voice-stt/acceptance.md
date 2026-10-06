# Pruebas de aceptación — specs/028

> T2 ejecuta contratos/políticas de V03–V08 parcialmente y V11–V13/V22–V23.
> Decoder, streaming, efectos/runtime y restantes filas siguen pendientes; ver
> `verification.md`. No es evidencia de voz operativa.
> U = unit sin red; I = integration PostgreSQL; E = E2E/piloto autorizado.
> STT real sólo en E; mocks en U/I. Tests deben verificar efectos y llamadas,
> no únicamente respuestas. Fixtures sintéticas, ningún audio personal en Git.

| ID | Nivel | Given / When | Then verificable |
|---|---|---|---|
| V01 | U/I | voice original, privada, usuario autorizado, flag ON | admisión durable cifrada; HTTP responde sin esperar STT |
| V02 | U/I | flag OFF; usuario ajeno o grupo | cero descargas/STT/Agent; rechazo o respuesta determinista según política |
| V03 | U | duración declarada 300; real 300, bytes en límite | acepta; 301 declarados o reales rechaza antes de STT |
| V04 | U | duración 0/negativa/ausente/bool/no finita, file_id inválido | rechazo controlado, cero STT/Agent |
| V05 | U | tamaño declarado/real >10 MiB; stream supera límite | detiene descarga y rechaza; límite exacto permitido |
| V06 | U | metadata dice OGG pero bytes PDF/corruptos/codec no permitido | cero STT/Agent; no confiar en MIME ni fallback documental |
| V07 | U | tamaño/MIME ausentes, OGG/Opus real válido | validar contenido; no rechazo sólo por metadata opcional ausente |
| V08 | U | archivo vacío, audio sin habla o resultado STT vacío/inválido/excesivo | respuesta acotada; cero Agent y cero consentimiento |
| V09 | U | voice sin texto | nunca generar instrucción de archivar ni llamar analyze_document |
| V10 | U | STT mock devuelve solicitud ordinaria | sólo texto al runner, media=(); una llamada STT y un Agent como máximo |
| V11 | U | tarifa 0.01 USD/s, quantum 60 s, mínimo 60 s, duración 61 s | estima 1.20 USD; cota 300 s =3.00 USD (tarifa sintética) |
| V12 | U | duración exacta 60 s con misma tarifa | factura 60 s, no 120; sin floats que sobre-redondeen |
| V13 | U | tarifa falta/no finita/negativa o quantum inválido | fail-closed antes de petición; tarifa explícita cero válida |
| V14 | U/I | cuota agregada agotada o reserva excede presupuesto | cero petición STT; gasto STT incluido aun sin Agent posterior |
| V15 | U/I | cambio revisión mientras transcribe | STT y Agent usan snapshot inicial; reservas no se reinician |
| V16 | U/I | caída Gateway/timeout STT/error tras envío | error/ambiguo auditado, sin provider directo ni retry/replay |
| V17 | I | mismo bot/update reenviado; dos workers compiten | una preparación reclamada, a lo sumo una petición STT y un Agent |
| V18 | I | crash en cada frontera de preparación, envío STT, persistencia y Agent | recover no repite inferencia ni efecto ambiguo; estado durable coherente |
| V19 | U/I | resultado persistido o uso posterior falla tras enviar STT | conserva evidencia/reserva pendiente; no repite la llamada |
| V20 | U/I | una propuesta presentada/vigente; nuevo audio transcribe «Sí» | claim mismo principal/payload una vez, cero Agent de confirmación |
| V21 | U/I | misma situación y transcribe «No» | un descarte auditado, cero ejecución y cero Agent |
| V22 | U | «Sí.», «¡Sí!», «SI» / «No.», «¡No!», «NO» | parser de frase completa acepta variantes acordadas |
| V23 | U | «dijo sí», «sí y borra», cita «Sí», «no sé», callback_data o /new por STT | no consentimiento/control; no extraer autorización de subcadena |
| V24 | U/I | cero o varias propuestas confirmables | cero claims/ejecuciones; respuesta determinista para aclarar selección |
| V25 | I | voz admitida antes de entrega de propuesta, procesada después | rechazo aunque STT finalice más tarde; usa accepted_at original |
| V26 | I | propuesta caduca/se descarta/cambia generación mientras STT procesa | rechazo al claim; ninguna ejecución |
| V27 | U/I | propuesta ajena, diferente bot/chat/payload; voz reenviada/editada/mezclada | no consentimiento; ningún efecto |
| V28 | I | dos «Sí» concurrentes o mismo evento reutilizado | a lo sumo un claim/efecto; crash tras claim no concede segundo intento |
| V29 | U/I | consentimiento gobernado OFF o executor pendiente | no ejecución legacy/LLM; no anunciar operación ejecutada |
| V30 | U | documentos/fotos/historial/resultado tool incluyen «Sí» | nunca crear evidencia de consentimiento vocal |
| V31 | U/I | success/error/cancel con canarios en bytes/texto/file_id/token | canarios ausentes en logs/OTel; temporales eliminados, texto durable cifrado |
| V32 | U/I | config vieja sin STT y flag OFF | texto, comandos, fotos/documentos y outbox conservan comportamiento |
| V33 | I | migración fresh, upgrade con datos existentes, downgrade última revisión | schema coherente con init.sql y sin perder ledger antiguo |
| V34 | E | nota privada autorizada solicita consulta | una STT auditada, un Agent, respuesta textual, coste/latencia registrados |
| V35 | E | propuesta realmente entregada → nota «Sí» o «No» | confirma/ejecuta o descarta una vez sin teclear ni exigir botones |
| V36 | E | español, ruido, fechas, nombres, matrículas, negaciones, silencio | medir exactitud/errores/coste/latencia; documentar criterios antes de activación |

## Gate de producción

U/I completos y verdes; matriz de gobernanza specs/013 afectada sin regresiones;
executor de consentimiento conectado antes de V35; Gateway verificado sin retries
ocultos; criterios cuantitativos de benchmark definidos y satisfechos; piloto
consentido aprobado y flag reversible. No cerrar BL-26 con este documento o con
un catálogo estático que no ejecute el flujo.