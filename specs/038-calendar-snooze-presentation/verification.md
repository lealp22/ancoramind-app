# Verificación 038 — BL-49

2026-10-17. Implementación y validación locales; producción sin cambios.

## Evidencia

- Regresiones del renderer reproducen la omisión antes del parche: frecuencia,
  intervalo, límite y aviso no aparecían; snooze no tenía nombre legible,
  duración ni contexto canónico. Tras el parche, 29 casos unitarios nuevos
  cubren renderer y composición Core en los dos módulos afectados.
- Recurrencias diaria/semanal/mensual/anual, intervalos unitarios/múltiples,
  límite inclusivo con offset intacto/sin límite, evento único, aviso OFF y
  antelación cero/positiva. Los defaults son los de ejecución, no del LLM.
- Snooze en minutos/horas/combinaciones; título canónico, target ausente o
  ID inválido; título de payload ignorado; límites por campo, una sola línea
  y escape HTML. Una lectura SQL fallida se propaga y cierra la sesión: no
  inventa target ni usa una inferencia/retry de reemplazo.
- Cuatro integraciones nuevas en `test_calendar_snooze_presentation.py`:
  objetivo propio/ajeno/inexistente y evento recurrente con aviso al inicio.
  Repositorios y PostgreSQL reales, sin Agno/Telegram/proveedores reales.
  La composición usa la identidad de la interacción y no filtra título ajeno;
  mantiene payload/hash y estado `pending_confirmation`, IDs de botones y
  respuesta independiente. No crea eventos ni recordatorios al presentar.

## Gates ejecutados

- `pytest tests/unit/ -q --tb=short`: **1582 passed**.
- `pytest tests/integration/ -q --tb=short`: **207 passed, 1 skipped**.
  Destino forzado: Docker PostgreSQL `127.0.0.1:5432`, base dedicada
  `ancoramind_test`; URL custom ignorada y `ANCORA_TEST_REQUIRE_DB=1`.
  `ANCORA_STT_SMOKE_APPROVED=0` fuerza exclusión de la inferencia live.
- Ruff global (`src/ tests/ scripts/ migrations/`): limpio.
- `mypy src/`: limpio, 175 módulos. `git diff --check`: limpio.
- Aviso de exportación OTLP a localhost:4318 sin Collector local en la suite
  unitaria; no es fallo funcional ni evidencia del Collector remoto.

## Límites y siguiente validación

Sin cambios de payload/hash, permisos, consentimiento, ejecutor, tools/prompts,
recurrencia, zonas horarias, notificaciones, migraciones ni configuración.
El título es contexto de lectura al presentar, no un nuevo campo del payload
ni una promesa de disponibilidad futura. Los textos largos conservan el
truncado existente de 120 caracteres por campo. «No disponible» no concede
acceso: la validación de propiedad en ejecución permanece intacta.

No despliegue ni SQL remoto, inferencia real, cambios de flags o E2E Telegram.
Para cierre operativo: autorizar SHA y ventana, comprobar CI del mismo SHA,
validar visualmente evento recurrente con límite/aviso y snooze con objetivo
y duración; registrar entrega/botones y resultado. No usar SQL como sustituto
de la revisión humana del bloque. BL-48 mantiene su alcance independiente.