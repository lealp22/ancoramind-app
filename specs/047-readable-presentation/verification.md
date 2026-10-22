# BL-55 (fechas) / BL-53 — Presentación legible

Implementación local, 2026-10-22. **Cambio evaluable** de prompts y presentación
visible; sin nueva gobernanza, infraestructura, migraciones o inferencia real.
BL-55 está duplicado en BACKLOG con evaluación académica; este incremento se
refiere exclusivamente a fechas y no renumera esa otra entrada.

## Contrato y alcance

- `src/domain/preferences/display.py`: `YYYY-MM-DD` para fecha sola;
  `YYYY-MM-DD HH:MM` para fecha-hora. Segundos no cero se conservan; fracciones
  no cero muestran seis dígitos, sin redondeo. Más de seis dígitos o conversión
  no representable: original intacto, no corrección silenciosa.
- Se usa `resolve_user_timezone(UserContext)` existente. Las propuestas Core
  reciben esa zona desde la identidad de la interacción, no del LLM. Instantes
  aware se convierten; naive se localizan con esa zona mediante el mecanismo
  ya existente. Sin zona disponible se dice «sin zona horaria»; fold/gap naive
  conserva el original con advertencia, no elige un instante.
- Se mantiene zona IANA y offset UTC legibles junto a la hora. Es deliberado:
  dos `02:30` del mismo día pueden representar instantes distintos durante DST.
  La fecha sola no incorpora zona. Medianoche de eventos/recordatorios sigue
  mostrando `00:00`; sólo TODO opta por su convención histórica naive-midnight.
- Renderer Core: calendario (inicio/fin/límite inclusivo), recordatorios y
  fechas TODO/mantenimiento. Lecturas/propuestas/replies de tools de calendario
  y recordatorios usan la misma función. No es un reformateador global de texto;
  el prompt exige al Agent respetar zona y precisión de resultados.
- UUIDs **documentales**: prompt Telegram + documentos pide nombre/procedencia
  por defecto, ID verificado sólo a petición explícita o diagnóstico del propio
  documento. Homónimos: usar procedencia o preguntar, no elegir arbitrariamente.
  No se eliminan IDs de tools, scope, persistencia, callbacks ni auditoría; no se
  filtran UUIDs con regex sobre la salida final. La excepción nunca permite IDs
  de usuarios, rutas, secretos ni datos ajenos.
- Tres casos evaluables nuevos (`response_style.document_*`) y fixtures de
  documentos/homónimos en tools simuladas; campaña histórica BL-48 sin modificar.
  Validación de catálogos y tests de instrucciones **no equivalen** a evaluación
  semántica del modelo ni E2E Telegram. No se ha ejecutado inferencia pagada.

## Prueba y límites

Regresiones de fecha sola, medianoche, UTC/offsets, invierno/verano, ambos lados
del fold/gap, segundos/microsegundos, input inválido, HTML y hash inmutable.
Integración PostgreSQL local: propuesta persistida → Core → HTML, con zona
resuelta, payload/hash/status intactos y cero eventos/avisos nuevos.

Validación final: **2211 unitarias passed/1 skip**, cobertura **81,69 %**;
**218 integraciones PostgreSQL locales passed/1 STT skip**; Ruff global y
`mypy src/` (186 archivos), 45 casos de catálogos y `git diff --check` limpios.
El código de producto no cambió después de las integraciones; los últimos
añadidos fueron tests y endurecimiento del exporter experimental desconectado.

En esta máquina el proceso
hereda `WEB_SEARCH_ENABLED=true`; el test de wiring que espera el default falla
con esa variable. Se valida la suite en proceso hijo con **sólo esa variable
retirada**, usando `sys.executable` del venv. No se modifica `.env`, el test ajeno
ni la funcionalidad web. Los avisos del exporter de métricas a `localhost:4318`
sin Collector no indican fallo de los tests ni conexión a producción.

Fuera de alcance: cambios de parser, instantes almacenados, normalización de
payload, consentimiento/ejecución, UUIDs de otros dominios, timestamps técnicos
de auditoría/telemetría, formato de todos los campos históricos/documentales y
worker outbound. Publicación, CI del SHA y E2E natural requieren ventana propia.
