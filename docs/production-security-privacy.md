# Seguridad y privacidad para producción y apertura pública

Estado: checklist de diseño y evidencia pendiente — 2026-10-07. No certifica
cumplimiento ni sustituye evaluación legal especializada. Complementa
`docs/llm-security-hardening.md` (prompt injection), `docs/governance.md`
(autorización) y ADR-005/006 (inferencias y observabilidad).

## Marco europeo explícito: RGPD/GDPR

RGPD (GDPR en inglés) es el Reglamento (UE) 2016/679. El MVP no es por sí
mismo una exención. Debe evaluarse la aplicabilidad territorial/material y los
roles reales; la aceptación de riesgos por el propietario no sustituye una
base jurídica, contratos de encargado ni los derechos de otras personas.
El EU AI Act es otro marco, complementario: no reemplaza el RGPD.
La excepción de actividad exclusivamente personal/doméstica tampoco debe
extrapolarse automáticamente al servicio ofrecido a terceros.

Fuente oficial: https://eur-lex.europa.eu/eli/reg/2016/679/oj

### Alcance de la decisión MVP

El propietario acepta OpenRouter para audio personal/Telegram/producción MVP,
incluida ausencia de garantía de proveedor fijo/ZDR extremo a extremo. Ver
`specs/028-telegram-voice-stt/preflight-smoke.md`. No autoriza tratamiento en
nombre de terceros ni elimina obligaciones legales. No es evidencia de que
todos los controles técnicos estén activos. Voz sigue gated hasta validación.

## Gates verificables antes de ofrecer el servicio a terceros

| Área | Evidencia requerida | Estado |
|---|---|---|
| Inventario | Flujos audio/texto/documentos, Telegram, Gateway, OpenRouter, subproveedores, DB, storage, backups, historial Agent y telemetría | Pendiente consolidar |
| GDPR: roles y bases | Determinar responsable/encargados, finalidades y base jurídica por tratamiento; condiciones art. 9 para categorías especiales, si aplica | Revisión legal pendiente |
| Minimización/retención | Plazos por categoría; audio temporal no documental, texto cifrado temporal ≠ historial Agent; eliminación/backups y ejercicio de derechos probado | Parcial, evidencia end-to-end pendiente |
| Proveedores | DPA, subencargados, ubicaciones, acceso, entrenamiento, logs y retención por endpoint; transfers internacionales y garantías aplicables | Pendiente |
| ZDR | Condición contractual y configuración verificadas en TODA la cadena cuando se exige, no solo marketing/flag. Metadata/billing y excepciones diferenciadas | No demostrado STT OpenRouter |
| Derechos/transparencia | Información clara, acceso/rectificación/supresión/exportación y procedimiento verificable | Pendiente |
| Riesgo | Evaluar necesidad de DPIA (art. 35), realizarla cuando corresponda; justificar resultado, revisión periódica | Pendiente |
| Seguridad | Aislamiento usuario/chat/bot, secretos rotables, mínimo privilegio, cifrado, sandbox/recursos decoder, tmpfs, admission, idempotencia y consentimiento determinista | Parcial; validación efectiva producción pendiente |
| Incidentes | Detección, runbook, responsables, evidencia y evaluación de notificación conforme a plazos aplicables | Pendiente |
| AI Act | Roles proveedor/deployer y clasificación por uso; transparencia de interacción IA (art. 50), alfabetización IA (art. 4), usos prohibidos/alto riesgo si aplican | Evaluación pendiente |
| Evals | Negaciones/silencio/ruido, confirmación vocal, prompt injection, regresión y fallo sin replay | Parcial; benchmark real pendiente |

ZDR es un control útil, NO requisito universal autónomo del GDPR ni garantía
de cumplimiento. El GDPR exige protección por diseño/default, minimización,
seguridad y accountability entre otras obligaciones. DPIA depende del riesgo;
«datos sensibles» coloquialmente no equivale siempre a categorías del art. 9.
Una grabación de voz no es automáticamente biometría especial: analizar si se
trata para identificar unívocamente a una persona y qué contiene el audio.

El AI Act no convierte automáticamente un asistente en sistema de alto riesgo
por usar STT o tratar datos personales. Clasificación, obligaciones y fechas
deben revisarse por uso real y normativa vigente antes del lanzamiento. No
suponer que todas las obligaciones de modelos GPAI corresponden a AncoraMind.

## Inventario de copias de contenido conversacional (2026-10-25)

Primer paso del gate «Inventario». Lista **dónde puede quedar texto de una
conversación**, no los metadatos. «Verificado» significa comprobado en código o
en la base en esta fecha; «declarado» es lo que el propietario indica y no se ha
comprobado. Todo el contenido manejado hasta hoy es ficticio (ver
`docs/pilot-terms.md`); este inventario describe el estado que habría con datos
reales, que es cuando importa.

| Lugar | Qué contiene | Enmascarado | Retención | Estado |
|---|---|---|---|---|
| PostgreSQL `ancora` (Supabase) | Notas, documentos, extracciones, vehículos, recordatorios, eventos, listas, propuestas y su payload | No | Mientras exista el dato canónico | Verificado en código |
| Supabase Storage | Bytes de los documentos subidos | No | Mientras exista el documento | Verificado en código |
| `telegram_interactions` | Payload de entrada y respuesta, cifrado; metadatos | Cifrado, no enmascarado | Los estados terminales limpian el payload al terminar (`update_status`). Para `failed_ambiguous` existe `purge_expired_payloads` (7 días) | **La purga a 7 días no se ejecuta**: está implementada y probada, pero ningún código de producción la invoca (sólo tests). Verificado por búsqueda en el repositorio el 2026-10-25 |
| Agno `agno_runtime.agno_sessions` | Historial completo de cada sesión: mensajes, **resultado de cada tool** (incluidos `get_document`, `search_documents`, `search_web`, `analyze_document`) | **No** | **Ninguna** (BL-34 lo dejó pendiente) | Verificado por consulta el 2026-10-25: 21 sesiones, la más antigua de 31-90 días, sin purga; resultados de tools guardados |
| Phoenix (trazas enmascaradas) | Texto escrito por el usuario, respuesta final y argumentos `propose_*`, enmascarados; metadatos y mensaje de error de tools | Sí, por esquema y por patrón (ver «Límites del enmascarado») | 30 días, configurado por el propietario en Phoenix | Código listo con el flag **apagado**; la retención es declarada, no comprobada |
| Grafana Cloud | Metadatos técnicos (ids, rutas, tokens, coste, latencia, nombre de clase de error) | n/a, sin contenido | Según plan de Grafana | Verificado por test de extremo a extremo (specs/046 T7) |
| Log de consola de Railway | Texto de la excepción de una tool que falla, con traceback, escrito por el propio Agno | No | Según Railway | Observado en tests; **no controlado por la aplicación** |
| OpenRouter y proveedor del modelo | Prompt completo y respuesta, incluido el contenido de documentos | No | Fuera de nuestro control; sin ZDR demostrado | Ver gate «ZDR» |
| Telegram | La conversación en sí | Cifrado de transporte, no de extremo a extremo | Fuera de nuestro control | n/a |

Dos conclusiones que condicionan la apertura a terceros:

1. **El mayor almacén de contenido sin enmascarar y sin retención no es Phoenix,
   es el runtime de Agno.** Antes de admitir datos reales hace falta decidir su
   retención y si deben guardarse los resultados de las tools (BL-34). Phoenix, al
   exportar menos contenido y con plazo, añade menos exposición que esa tabla.
2. El enmascarado reduce el riesgo de Phoenix pero **no lo elimina** (siguiente
   sección). Una traza sigue siendo dato personal a efectos del RGPD.

### Phoenix: qué se captura, qué no y por qué

Decisión del propietario (ADR-007, 2026-10-23): copia **enmascarada** del contenido
de todos los usuarios autorizados, captura manual y 30 días. Está detrás de
`PHOENIX_TRACING_ENABLED` (apagado por defecto) y de cuatro variables que deben
estar completas; con cualquiera ausente el pipeline no se crea.

| Fuente | ¿Se captura? | Condición |
|---|---|---|
| Texto que el usuario escribe | Sí, enmascarado | No si procede de voz ni es el texto que el sistema inventa ante un adjunto sin texto |
| Respuesta final y argumentos de `propose_*` | Sí, enmascarados | Sólo si el turno no tuvo adjuntos y todas sus tools son de la lista segura; una tool nueva queda excluida hasta clasificarse |
| Metadatos de cada tool (nombre, orden, ok/error, duración, tamaño del resultado) | Sí | Siempre; el nombre sólo si la tool está registrada |
| Mensaje de error de una tool que falló | Sí, enmascarado | Sólo la primera línea, cortada antes de un valor citado y limitada a 300 caracteres |
| Resultado de tools de lectura, historial, resumen de compactación | **No** | — |
| Audio y transcripciones | **No** | La voz queda fuera por decisión del propietario; incluirla exige su propio análisis (BL-26) |
| Adjuntos, contenido y nombre de documentos, extracciones | **No** | Excluidos antes de crear el span |
| Identificador del usuario | Sólo un seudónimo | HMAC con clave propia, nunca derivada de otro secreto |

El tratamiento por campo de los argumentos de propuesta (`src/observability/
field_policy.py`): los identificadores personales (matrícula, bastidor, correo,
teléfono, IBAN, DNI) se sustituyen siempre; los identificadores internos se
conservan sólo si son UUID; los valores estructurados (fechas, importes, años) se
conservan sólo con su forma estricta y si no, salen como `[INVALIDO]`; el texto
libre se conserva y se enmascara por patrón.

### Límites del enmascarado

- Los patrones reconocen **formatos** (DNI/NIE, IBAN, tarjeta con Luhn, matrícula,
  bastidor, correo, teléfono, claves). **No** reconocen nombres propios,
  direcciones, lugares ni datos de salud en texto libre. Un título como «cita con
  el cardiólogo» o un apodo («el coche de María») se exporta tal cual.
- Es el límite aceptado en ADR-007. La salida técnica sería un reconocedor de
  entidades (descartado por ahora) o no capturar ciertos campos de texto libre.
- Los datos de salud pueden ser categorías especiales (art. 9 RGPD). Si el servicio
  se abre con datos reales, esta captura necesita base jurídica y análisis propios
  antes de activar el flag.
- El mensaje de error de una tool lo escribe el código o una librería y puede citar
  datos; el recorte y el enmascarado lo limitan, no lo anulan.

### Retención y borrado por usuario

- **Retención en Phoenix:** 30 días, configurada por el propietario en la
  instancia. No se ha comprobado desde el repositorio; verificarla en la
  instancia real es parte del runbook de activación (specs/046 T10, pendiente).
- **Borrado por usuario** (ejercicio de supresión): cada traza lleva el seudónimo
  del usuario, así que se localiza sin conocer su identificador. En el spike local
  se comprobó el procedimiento: listar los spans por el atributo `user.id`, recoger
  el `trace_id` de cada uno y borrar cada traza por la API de Phoenix. Pendiente
  para producción: paginar el recorrido, pausar la captura durante el borrado y
  repetirlo sobre la instancia real (el spike usó un backend SQLite desechable, no
  la PostgreSQL de producción).
- **Rotar `PHOENIX_USER_PSEUDONYM_KEY`** rompe la agrupación histórica por usuario:
  las trazas anteriores dejan de poder localizarse por usuario aunque sigan
  existiendo hasta su expiración. Documentarlo antes de rotar.
- **Fuera del alcance de este borrado:** el runtime de Agno, el log de Railway y el
  proveedor del modelo no se borran por esta vía.

### DPIA (art. 35 RGPD): qué dispara la necesidad y estado

No se ha realizado una DPIA. Para decidir si hace falta, estos son los factores
que concurrirían **si se admiten datos reales**, no una conclusión:

- Tratamiento a escala de conversaciones personales de varias personas.
- Posible presencia de categorías especiales (salud) en texto libre que el
  enmascarado no detecta.
- Copias del contenido en más de un sistema, una de ellas sin retención (Agno).
- Uso de un proveedor de IA sin garantía de no conservación.

Estado: **pendiente**, con revisión legal. El piloto actual no la requiere en la
práctica porque sólo admite datos ficticios; esa es precisamente la condición que
sostiene su alcance, y deja de valer en el momento en que se admita un dato real.

## Política operativa de voz

- Ambigüedad STT: «No he podido entender el audio. Por favor, envía tus
  indicaciones de nuevo.» Nuevo mensaje = nueva interacción; nunca retry del
  original ni autorización implícita para ejecutar acciones.
- Ambigüedad de ejecución de acciones NO se comunica como fallo de comprensión
  del audio; mantener auditoría/reconciliación sin duplicar efectos.
- No contenido en logs/OTel; errores de proveedor no se reenvían al usuario.
- Valorar proveedor fijo detrás del Gateway o STT propio si no se pueden
  verificar condiciones requeridas; no bypass de LLMAccess/gobernanza.

## Fuentes oficiales revisadas (2026-10-07)

- EDPB, protección por diseño/default:
  https://www.edpb.europa.eu/topics/ai-and-technology/privacy-by-design-and-by-default_en
- EDPB, DPIA:
  https://www.edpb.europa.eu/topics/accountability-and-compliance-tools/data-protection-impact-assessment_en
- Comisión, AI Act artículo 50:
  https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50
- OpenRouter, condiciones técnicas STT:
  https://openrouter.ai/blog/tutorials/transcription-on-openrouter/