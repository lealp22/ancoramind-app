# Inspección física — decisión T2 (2026-10-06)

Se selecciona **ffprobe + FFmpeg como candidato** del futuro adaptador de
infraestructura, no como dependencia instalada ni compatibilidad ya probada.
La documentación oficial permite inspeccionar container/streams, seleccionar
campos (`show_entries`) y obtener JSON: https://ffmpeg.org/ffprobe.html.
No añadir un parser OGG/Opus artesanal al dominio ni un wrapper Python sin necesidad.

El entorno local no tiene `ffprobe`/`ffmpeg` en PATH; el Dockerfile actual no los
instala. El puerto `VoiceAudioInspectorPort` evita acoplar domain a subprocess o
al binario. Verificar disponibilidad/versiones Windows y Linux en T4 antes de
cambiar Dockerfile o dependencias; no instalar nada como parte de T2.

Requisitos del adaptador pendiente:

- Sólo archivo temporal local con nombre generado; nunca URL/red suministrada
  por usuario, ni interpolación de shell. Restringir protocolos.
- Entrada <=10 MiB, tiempo/memoria/output acotados; cancelar y limpiar temporal
  incluso tras error o timeout. No loguear stderr bruto, rutas ni metadatos libres.
- Un solo stream de audio OGG/Opus; rechazo de streams extra, corrupción, duración
  ausente/no finita y archivos que excedan 300 s. Parsear duración como Decimal.
- Probar truncado/cabeceras falsas/checksums/streams encadenados. Probe de metadatos
  no equivale a decodificación íntegra: validar con decoder acotado y comprobar
  duración real antes de implementar `InspectedVoiceAudio` para producción.
- No detectar habla con duración/container: silencio/no-habla requiere resultado
  STT válido o detector explícito futuro, sin afirmar que T2 lo resuelve.

Los tests T2 usan bytes sintéticos marcados como tales y reportes de inspección
simulados; comprueban política, no integridad de un OGG real. Timeout operativo y
aprobación final de 10 MiB siguen pendientes. No habilitar voice hasta esos gates.