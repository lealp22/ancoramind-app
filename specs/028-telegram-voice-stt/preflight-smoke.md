# Preflight y smoke gobernado — 2026-10-07

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

## Privacidad: puerta todavía NO superada

El endpoint documenta balanceo entre proveedores; no aplica controles `order`,
`only`, `allow_fallbacks`, `data_collection` ni `sort` por petición. No afirmar
proveedor fijo, ausencia de fallback upstream, ZDR ni retención nula del audio.
La documentación general de privacidad no demuestra condiciones específicas de
STT ni de todos sus proveedores. Requiere confirmación oficial de retención,
entrenamiento/logging y aplicabilidad de políticas de cuenta/BYOK a audio.

Decisión pendiente: aceptar explícitamente esa limitación SOLO para audio
sintético en smoke, o estudiar proveedor fijo detrás del Gateway con revisión
de ADR-005. No hay aceptación implícita para audio personal ni para producción.

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