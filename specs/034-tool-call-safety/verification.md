# Verificación — BL-16 / specs/034

Fecha de trabajo: 2026-10-11 (fecha local declarada del entorno).
Python 3.12.10, Agno 2.9.0, OpenAI SDK 3.3.1, Windows/PowerShell.

## Resultado

Incremento local completo; **BL-16 no se cierra**. La protección compartida
cubre OpenRouter directo y OpenAI-compatible/LiteLLM mediante la factory
existente. `GovernedModelMixin` sigue primero en el MRO, seguido de
`SafeOpenAILike`/`SafeOpenRouter` y `ToolCallSafetyMixin`. No hay cambios
en modelos físicos, dependencias, prompts, gobernanza, rutas o configuración.

## Repro y cobertura

En revisión previa, los adaptadores nativos 2.9.0 conservaron `{}` junto a
una llamada válida (Agno genera UUID), y streaming conservó una entrada
solo-ID con función vacía. `SafeOpenRouter` eliminó ambas formas.
La revisión estática de los tres métodos relevantes en upstream v3.1.2
encontró cuerpos iguales a los de 2.9.0; no se instaló/ejecutó esa versión.

`tests/unit/test_tool_call_safety.py`: **44 casos** nuevos; más **5 casos**
adicionales al parametrizar las regresiones originales para `SafeOpenAILike`:

- Ausencia `None`/`[]`, forma exacta del fallo original, nombres inválidos,
  orden, ID ausente completado por Agno, argumentos preservados sin parseo.
- Streaming sync/async legacy: consolidación previa de argumentos por delta,
  conservación de llamadas válidas y terminación tras solo llamadas vacías.
- Logs: sin texto, argumentos, nombres de tools ni IDs de llamada; se
  inspecciona también `LogRecord.getMessage()` para no depender del formatter
  metadata-only instalado por otros tests al importar la app.
- `AgnoLLMAccess` compuesto real, proveedor simulado: solo vacías → una
  inferencia simulada, cero tools; vacías + válida → una ejecución local y
  segundo turno con assistant/tool correlacionados sin llamada vacía.
- SDK OpenAI y parser reales con `httpx.MockTransport`, sin sockets:
  respuesta HTTP con `{}`; ejecución y replay; ruta `/v1/chat/completions`,
  alias y credencial sintética correctos. IDs del fixture respetan la forma
  de OpenRouter, que normaliza IDs al serializar el historial.
- Preservación de conteos de budget/usage, rechazo antes de proveedor si
  falta contexto/se agota budget, sync/streaming gobernados siguen prohibidos.

Las pruebas de loop son de infraestructura: la tool `echo` es sintética,
sin efectos externos ni mutaciones; no sustituyen pruebas de consentimiento.

## Comandos y resultados finales

Ejecutados con `.venv/Scripts/python.exe` desde la raíz del repositorio:

| Comando | Resultado |
|---|---|
| `-m pytest tests/unit/ -q --cov=src --cov-report=term --tb=short` | **1199 passed**, cobertura **78,58 %**, gate 70 % superado |
| `-m pytest tests/integration/ -q --tb=short` | **143 passed, 1 skipped** (smoke live opt-in) |
| `-m pytest tests/unit/test_tool_call_safety.py -q --tb=short` | **44 passed** |
| `-m ruff check src/ tests/ scripts/ migrations/` | Limpio |
| `-m mypy src/` | Limpio, 161 módulos |
| `scripts/run_evals.py` | Catálogo válido, 27 casos/6 categorías; sin inferencia |
| `git diff --check` | Limpio |

Las primeras ejecuciones globales detectaron un assert del nuevo test de
logs dependiente del formatter; se corrigió para inspeccionar el registro
original y la suite final pasa. Dos intentos de integración fallaron en
`test_stt_errors_after_send_are_ambiguous_and_never_replayed[timeout]`:
su plazo de 50 ms incluye escrituras PostgreSQL antes de entrar al mock STT,
que registró cero invocaciones. El caso aislado pasó (1), su módulo pasó
(16) y la suite final completa pasó (143). Una comprobación cargando la
factory original de HEAD solo en memoria también pasó; no se editó voz
ni se atribuye causalidad al cambio BL-16. Se conserva esta evidencia de
variabilidad temporal, sin ocultar los fallos iniciales.

Algunas ejecuciones iniciales de unit emitieron errores de exportación OTel
a `localhost:4318` (Collector local ausente), no fallos de test. La ejecución
final completó sin esos mensajes. No se cambiaron configuración/exportadores.

## Límites y retirada

- Sin llamadas reales a Telegram/OpenRouter/LiteLLM ni inferencia pagada;
  integración usa PostgreSQL de tests local, nunca Supabase/producción.
- Sin actualizar Agno, activar flags, desplegar, commit ni push.
- No repara historial ya contaminado, no valida argumentos de negocio y
  no añade autorización ni retries. La ruta `openai` permanece intacta.
- Se mantiene dependencia de dos métodos privados. Para retirar: repetir
  fixtures con clases nativas en un entorno aislado, comprobar streaming y
  loop async + replay limpio y actualizar factory/tests/docs juntos. Un
  cambio de modelo no demuestra por sí solo que el adaptador sea seguro.
