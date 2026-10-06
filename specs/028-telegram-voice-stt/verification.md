# Verificación — specs/028

## Incremento de diseño (2026-10-06)

Se han creado alcance, contratos propuestos, tareas y matriz de aceptación;
BL-26 apunta a specs/028. No hay cambios en runtime, proveedores, configuración
remota, migraciones ni prompts. No se ha activado voz ni gastado inferencia.

Verificación local ejecutada con `.venv/Scripts/python.exe`:

- `-m pytest tests/unit/ -q`: **770 passed**, 48.94 s.
- `-m ruff check src/ tests/ scripts/ migrations/`: **All checks passed**.
- `-m mypy src/`: **Success**, 126 source files; exit 0.
- `git diff --check`: exit 0.
- Telegram Bot API oficial Voice/getFile revisada para los contratos de metadata
  y descarga; proveedor/tarifas/endpoint STT no seleccionados ni validados aún.

Estos resultados son regresión de código existente, NO pruebas ejecutables de
voz. V01–V36 siguen pendientes. T2 convierte contratos/políticas en código y
tests; U/I/E se implementan en sus incrementos respectivos. No se han ejecutado
integration PostgreSQL ni E2E/inferencia real en este incremento documental.

Hallazgo de dependencia: `_execute_claimed()` del processor devuelve actualmente
una respuesta de confirmación y no conecta ejecución automática; el parser
escrito sólo acepta Sí y el consentimiento está condicionado por flag. Ningún
resultado de este incremento prueba que botones estén habilitados en producción.

## T2 — políticas y contratos ejecutables (2026-10-06)

Implementado `src/domain/speech/` (models, ports, policy, consent), sin imports
Agno ni clientes físicos. Referencia/origen diferenciados; duración estricta,
tamaño acotado y resultados no vacíos/sin truncado; repr oculta contenido.
Facturación exacta con Decimal/Fraction, tarifa requerida, redondeo/mínimos y
cota derivada de 300 s. Parser vocal Sí/No separado del parser escrito existente.

Tests: `test_speech_policy.py` y `test_voice_consent_intent.py`, 94 casos nuevos.
Verificación local:

- Tests T2: **94 passed**, 0.65 s.
- Suite `pytest tests/unit/ -q`: **864 passed**, 17.09 s.
- Ruff global: **All checks passed**.
- `mypy src/`: **Success**, 131 source files.
- `git diff --check`: limpio.

V11–V13 y V22–V23 tienen tests de política. V03–V08 prueban límites/modelos y
reportes de inspección simulados, no decoding ni streaming real. Códigos seguros
de política/modelos no equivalen a respuestas UX o garantías de cero llamadas en
el processor todavía no conectado. V27/V30 sólo verifican clasificación de
procedencia; claims/efectos durables siguen pendientes de T5.

`inspection-design.md` documenta FFmpeg/ffprobe candidato tras revisar la
documentación oficial y entorno/Dockerfile; binarios no disponibles localmente,
sin instalación ni prueba física. Timeout y aprobación final de 10 MiB siguen
pendientes. Protocols no representan adaptadores implementados. No se han creado
VoiceConsentEvidence/claims, config runtime STT, migraciones ni proveedores.
No se han ejecutado integration/E2E ni inferencia; voz continúa sin habilitar.

## T3 — persistencia exclusiva (2026-10-06)

Implementados modelos/cipher de preparación, `VoicePreparationsRepository`,
migración 0011 y bootstrap equivalente. Parent-first locks serializan claims
Agent/preparación; PK interacción excluye duplicados; token de dueño y user_id
controlan transiciones. Intención/coste persistidos antes de STT; call_id vincula
resultado inmutable cifrado. No bytes de audio en DB ni descargas/clientes físicos.

Recovery explícito de un propietario conocido muerto y cutoff cierra preparing/
downloaded como controlado, transcribing/transcribed como ambiguo, sin requeue.
No es una detección automática de muerte ni está conectado al lifecycle aún.
El trigger bloquea Agent con preparación incompleta/cipher ausente o vencido,
limpia transcript en estados terminales ordinarios y acompaña purge del payload
ambiguo. Expiración inicial 24 h y techo ambiguo 7 días sin prolongar el inicial.

Validación: suite unit **868 passed** (18.90 s), Ruff global limpio, mypy limpio
(133 source files). Tests cifrado/rollback/parent ausente/equivalencia DDL pasan.
PostgreSQL/Docker no disponible: pruebas nuevas concurrency/recover/retention y
lifecycle migrations **omitidas**, no evidencia de SQL ejecutado. No aplicar la
migración a producción sin validar fresh/upgrade con datos/downgrade en PostgreSQL.
No tests E2E/inferencia ni activación; no hay temporales físicos que limpiar en T3.

### Validación PostgreSQL posterior (2026-10-06)

Docker disponible, PostgreSQL `pgvector/pgvector:pg16` healthy. Ejecutadas las
fixtures existentes en base dedicada `ancoramind_test` y bases de migración
temporales; no se aplicaron migraciones ni se modificaron datos de desarrollo
o producción. Esta evidencia sustituye la limitación de DB no disponible arriba.

- `pytest tests/integration/test_voice_preparations.py tests/integration/test_migrations.py -q`:
  **13 passed**, 13.02 s, sin skips. Incluye claims concurrentes, aislamiento de
  usuario/propietario, cifrado/limpieza terminal/expiración, recuperación en cuatro
  etapas sin requeue, bloqueo de preparación tras Agent y vinculación de call_id.
- Pruebas de migración: fresh head, downgrade/re-upgrade, adopción con datos y
  bootstrap idempotente compatible con Alembic head.
- Suite completa `pytest tests/integration/ -q`: **109 passed**, 68.98 s.
- Suite completa `pytest tests/unit/ -q`: **868 passed**, 21.26 s.
- Ruff global limpio; mypy limpio (133 source files); `git diff --check` limpio.

No hizo falta corregir código. T3 validado como persistencia aislada; todavía no
prueba STT/Agent E2E, muerte automática de propietarios, purge periódico ni
temporales reales. Integración processor/lifecycle permanece pendiente de T4.