# Preflight y smoke gobernado — 2026-10-07

## Ensayo autorizado bajo incertidumbre de facturación — 2026-10-07

El propietario elige `openai/whisper-large-v3-turbo` y acepta preparar un ensayo
bajo incertidumbre. Esta modalidad NO declara tarifa verificada y NO modifica
la configuración de producción. No se ha ejecutado inferencia en esta entrega.

Modalidades mutuamente excluyentes:
- Tarifa verificada: `ANCORA_STT_SMOKE_TARIFF_VERIFIED=1`, como antes.
- Ensayo incierto: omitir ese flag y usar
  `ANCORA_STT_SMOKE_BILLING_UNCERTAINTY_ACCEPTED=1`,
  `ANCORA_STT_SMOKE_MODEL=openai/whisper-large-v3-turbo`,
  `ANCORA_STT_SMOKE_UPSTREAM_KEY_CONFIRMED=1`.

Para el ensayo incierto, reserva conservadora fija de **0.03 USD**: tasa
experimental 0.0001 USD/s, quantum 1 s, mínimo experimental 300 s, versión
`smoke-estimate-unverified-r1`. Estos parámetros son una reserva operacional,
NO la tarifa ni el mínimo real del proveedor ni una cota garantizada de factura.
Audio artificial inspeccionado de máximo 15 s, una llamada Core, ningún retry.

Controles requeridos antes de enviar:
- Clave OpenRouter dedicada al ensayo con límite real configurado de **0.05 USD**,
  sin otros consumidores. Confirmar que es la misma clave inyectada en Gateway.
  El smoke consulta `/api/v1/key` y rechaza límite ausente, no finito o superior
  al `ANCORA_STT_SMOKE_EXTERNAL_LIMIT=0.05`, o restante inferior a 0.03 USD.
- Presupuestos Core diario/mensual de 0.05 USD en DB aislada y virtual key Gateway
  restringida al alias. Cambiar su presupuesto del preflight (0.01 USD) a 0.05
  USD al preparar el ensayo; no usar clave maestra para transcribir.
- No atribuir al Gateway una garantía de coste upstream. El límite OpenRouter
  es control de cuenta; liquidaciones en curso y redondeos pueden afectar el
  importe final. Revisar uso antes/después sin audio ni texto en evidencia.
- Comparar ledger estimado y facturación real; `actual_cost` desconocido NO vale
  cero. La reserva de 0.03 USD no acredita facturación efectiva de 0.03 USD.

La clave previa de uso general con límite 5 USD no satisface este ensayo de
0.05 USD. No reducirla ni rotarla silenciosamente: preparar una clave dedicada
en el dashboard y cargarla por canal de secretos, nunca en chat/logs/commits.
Si no hay clave limitada verificable, la llamada queda bloqueada aunque esté
aceptada la incertidumbre. El opt-in de ejecución sigue OFF por defecto.

## Avance técnico: Gateway aislado y audio artificial

2026-10-07: `scripts/stt_gateway_preflight.py` ejecutado contra la imagen fijada.
Gateway dedicado en loopback 4001, DB efímera distinta de desarrollo/producción,
clave temporal de 30 minutos restringida a `ancoramind-stt-smoke-r1` y presupuesto
Gateway de 0.01 USD. `/v1/models` devuelve solo ese alias; petición multipart al
alias `not-authorized` rechazada. Ninguna petición al alias autorizado ni inferencia.
El proyecto y DB efímera se destruyen al terminar; la clave no se imprime/persiste.

Audio generado localmente con System.Speech (voz de síntesis instalada, no
grabación/clonación), convertido con FFmpeg Docker a mono OGG/Opus: duración
ffprobe 11.479167 s, 94762 bytes. Ficheros transitorios fuera del repositorio,
borrados después del preflight. Generar otro cuando el smoke esté desbloqueado.

GET público de endpoints turbo devuelve DeepInfra 0.00000333 USD/s y Groq
0.0000111111111111 USD/s. La tarifa mínima del catálogo NO es una cota de todos
los proveedores. Sin proveedor fijable por petición no activar esa tarifa como
garantía máxima. Mínimo/quantum/contraste de factura siguen pendientes; no poner
`ANCORA_STT_SMOKE_TARIFF_VERIFIED=1` por conveniencia.
`whisper-1` figura con un endpoint OpenAI y 0.0001 USD/s; su ficha documenta
facturación al segundo más cercano, pero no prueba un mínimo cero ni que el
conjunto de proveedores permanezca fijo.

Fuentes consultadas: catálogo `/api/v1/models/.../endpoints`, ficha oficial
https://openrouter.ai/openai/whisper-1 y tutorial STT. Para desbloquear la puerta
actual se requiere confirmar mínimo/quantum efectivos con OpenRouter, o diseñar
una autorización explícita de ensayo bajo incertidumbre de facturación con cota
externa real. El límite de virtual key por sí solo no garantiza el coste upstream.
No falsear el gate de tarifa existente. Smoke real aún no ejecutado.

RGPD/GDPR europeo y AI Act están identificados explícitamente en
`docs/production-security-privacy.md`; aceptación MVP ≠ cumplimiento legal.

## Evidencia pública (sin inferencia)

GET público `/api/v1/models?output_modalities=transcription`, sin clave ni audio,
devuelve estos candidatos. `pricing.prompt` se conserva como dato crudo del
catálogo; la documentación distingue Whisper por duración de otros STT por tokens.

| Modelo | pricing.prompt crudo | 300 s nominales si tarifa/segundo |
|---|---|---|
| openai/whisper-large-v3 | 0.0000075 | 0.00225 USD |
| openai/whisper-large-v3-turbo | 0.00000333 | 0.000999 USD |
| openai/whisper-1 | 0.0001 | 0.03 USD |

No son presupuestos aprobados ni cotizaciones: falta confirmar unidad efectiva,
mínimos/redondeos y contraste con factura. No seleccionar automáticamente modelo
ni convertir estos datos en una revisión runtime. Repetir preflight antes del smoke:

```powershell
python -m scripts.stt_catalog_preflight
```

Fuentes primarias revisadas:
- https://openrouter.ai/blog/tutorials/transcription-on-openrouter/
- https://openrouter.ai/docs/guides/privacy/data-collection
- https://openrouter.ai/api/v1/models?output_modalities=transcription

## Privacidad: aceptación ampliada para el MVP — 2026-10-07

El endpoint documenta balanceo entre proveedores; no aplica controles `order`,
`only`, `allow_fallbacks`, `data_collection` ni `sort` por petición. No afirmar
proveedor fijo, ausencia de fallback upstream, ZDR ni retención nula del audio.
La documentación general de privacidad no demuestra condiciones específicas de
STT ni de todos sus proveedores. Requiere confirmación oficial de retención,
entrenamiento/logging y aplicabilidad de políticas de cuenta/BYOK a audio.

El propietario decide mantener OpenRouter para el trabajo del MVP y documentar
las limitaciones para una futura apertura pública. Esta preferencia de arquitectura
NO amplía el consentimiento de datos ni autoriza un despliegue.

Autorización explícita recibida el 2026-10-07 en la conversación de trabajo:

> Autorizo una prueba de transcripción mediante OpenRouter con audio generado
> artificialmente, sin datos personales ni voz de personas reales. Acepto que esta
> ruta no garantiza proveedor fijo ni retención cero de extremo a extremo. Esta
> autorización no habilita audio personal, Telegram ni producción.

Alcance: una prueba de transcripción con voz artificial, texto inventado y sin
clonación de voz. No pedir una nueva aceptación del mismo riesgo para ese smoke.
No marcarlo como ejecutado: tarifa, mínimos/redondeos, Gateway aislado y
credenciales deben estar verificados antes de enviar. No hay autorización para
reintentar resultados ambiguos, un segundo audio de 5 minutos, publicación de
aliases en producción, activación de flags o tratamiento de mensajes personales.
Los flags de opt-in siguen OFF hasta satisfacer esos requisitos operativos.

### Puertas antes de una apertura pública

- Revisar retención, entrenamiento, logging, subproveedores y políticas de cuenta
  específicas de STT; no asumir ZDR a partir de nuestra limpieza local.
- Evaluar consentimiento/información al usuario y requisitos aplicables de datos,
  contratos y jurisdicción con asesoramiento adecuado; este documento no es una
  determinación de cumplimiento legal.
- Reevaluar OpenRouter frente a proveedor fijo detrás del Gateway (p. ej. OpenAI
  o Groq con controles verificados) o STT autohospedado; cualquier cambio de ruta
  seguirá ADR-005 y requerirá evidencia actualizada, no un bypass del dominio.
- Validar privacidad de audio y transcripción en toda la cadena, coste real,
  controles de gasto, temporales efímeros, logs metadata-only y benchmark/piloto.

### Ampliación posterior del propietario (prevalece sobre el alcance anterior)

> Autorizo también la habilitación de audio personal, Telegram y producción.
> Lo comentado aplica para todo el contexto de AncoraMind. Ante resultado ambiguo
> se debe indicar al usuario que no se puede entender el audio (sin reintentos).

Se acepta para el MVP la misma limitación de proveedor no fijo y retención cero
no garantizada, incluyendo audio personal y canal Telegram en producción.
La autorización inicial se conserva arriba como historia, no como restricción
vigente. No es una garantía de privacidad ni aprobación en nombre de terceros.
Antes de una apertura pública se mantienen las revisiones descritas arriba.

Autorización de alcance no equivale a activación técnica: tarifa, permisos,
Gateway, smoke, controles y piloto deben validarse antes de activar voz.
No se han cambiado flags ni desplegado por registrar esta decisión.
El smoke preparado sigue usando únicamente audio artificial.

Ante fallo STT ambiguo: respuesta determinista «No he podido entender el audio.
Por favor, envía tus indicaciones de nuevo.» Sin Agent, mutación ni retranscripción.
La notificación usa el outbox durable y no autoriza reintentar un envío ambiguo.
Si el proceso cae antes de persistir el aviso, la recuperación continúa cerrando
sin replay; entrega del aviso tras ese reinicio aún requiere implementación.

## Smoke preparado, desactivado por defecto

`tests/integration/test_stt_live_smoke.py` usa DB de tests existente, preparación
exclusiva, inspector FFmpeg, tarifa/snapshot explícitos, reserva y ledger reales,
adaptador GovernedSpeechAccess y limpieza terminal. No llama Agent/Telegram ni
ejecuta propuestas. No activa la revisión; no publica alias. El pytest fixture
trunca los datos de tests: NUNCA apuntar ANCORA_TEST_DATABASE_URL a desarrollo,
producción ni a una DB compartida. Igual que el resto de integration, usar una
DB dedicada y ejecutar separadamente sin otros workers/suites.

Requisitos previos, sin ejecutar todavía:
1. Gateway local aislado con imagen fijada, sin logging de contenido, retries ni
   fallback; alias nuevo y clave virtual restringida, creados bajo autorización.
2. Audio OGG/Opus hablado sintético de 10–15 s, ruta absoluta, <=10 MiB;
   FFmpeg/ffprobe en PATH. El archivo fuente suministrado por el operador NO se
   borra; el inspector elimina sus copias temporales. No activar VOICE_ENABLED.
3. Confirmar tarifa/quantum/mínimo y privacidad; no rellenar valores supuestos.
4. Clave virtual desde entorno seguro; no pegarla en chat/argumentos ni logs.
5. Aceptación explícita de una llamada pagada; nunca ejecutar la suite completa
   con el opt-in habilitado (cada ejecución nueva puede facturar otra llamada).

Variables requeridas (sin valores por defecto de consentimiento o tarifa):
`ANCORA_STT_SMOKE_APPROVED=1`, `ANCORA_STT_SMOKE_SYNTHETIC=1`,
`ANCORA_STT_SMOKE_PRIVACY_ACCEPTED=1`, `ANCORA_STT_SMOKE_TARIFF_VERIFIED=1`,
`ANCORA_STT_SMOKE_AUDIO`, `ANCORA_STT_SMOKE_GATEWAY` (HTTP loopback /v1),
`ANCORA_STT_SMOKE_ALIAS` (versionado), `ANCORA_STT_SMOKE_RATE` (USD/segundo),
`ANCORA_STT_SMOKE_QUANTUM`, `ANCORA_STT_SMOKE_MINIMUM`,
`ANCORA_STT_SMOKE_TARIFF_VERSION`, `ANCORA_STT_SMOKE_VIRTUAL_KEY`.

También se requieren `ANCORA_STT_SMOKE_EXTERNAL_LIMIT`,
`ANCORA_STT_SMOKE_DAILY_LIMIT` y `ANCORA_STT_SMOKE_MONTHLY_LIMIT` (USD,
límites agregados explícitos del ensayo; no un techo manual STT por llamada).
El gasto agregado leído pertenece a la DB aislada; no representa gastos de
producción ni otras cuentas. Verificar además el límite real externo de la clave.

Solo tras autorización y requisitos satisfechos:
```powershell
python -m pytest tests/integration/test_stt_live_smoke.py -q --tb=no --show-capture=no
```
No usar `--showlocals`, SQL echo, logs HTTP DEBUG o trazas de contenido.
Deshabilitar el opt-in al terminar. Sin retries automáticos: un fallo post-envío
es ambiguo y no autoriza repetir. Las variables de opt-in son barreras de operador,
no prueba criptográfica de consentimiento ni inspección de configuración upstream.

## Criterios y limitaciones

- Resultado no vacío, exactamente un evento durable completado y reserva de
  una llamada; no imprimir transcripción ni audio. Timeout Gateway 60 s y plazo
  compartido 120 s, no confundir con duración máxima de audio 300 s.
- Prueba negativa de alias no autorizado por separado ANTES de enviar audio real.
- Verificar en Gateway el número de envíos: un evento Core no prueba intentos
  internos del proxy/upstream. Revisar metadata operativa sin contenido.
- `usage.cost` está documentado por OpenRouter, pero el adaptador actual no lo
  persiste. `actual_cost` queda desconocido; confirmar preservación en LiteLLM
  y reconciliar factura antes de cerrar T6. Este smoke no prueba ese requisito.
- La base de test se limpia al terminar; conservar evidencia metadata-only
  externamente aprobada si se necesita trazabilidad histórica del ensayo.
- Segundo audio de 5 minutos requiere nueva autorización. Calidad/negaciones,
  consentimiento vocal, errores adversariales reales y piloto quedan en T7.

## Referencia de seguridad para apertura p?blica

Ver docs/production-security-privacy.md: GDPR/AI Act, ZDR, proveedores, derechos, DPIA, retenci?n e incidentes; checklist de evidencia pendiente, no certificaci?n.
