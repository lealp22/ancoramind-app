# Evals — contratos de comportamiento del agente

Los ficheros de esta carpeta son datasets versionados para prevenir regresiones
al cambiar prompts, descripciones de tools o modelos. No contienen credenciales,
IDs reales, mensajes de usuarios ni documentos privados: todos los ejemplos son
sintéticos.

## Alcance de esta primera entrega

El runner actual es **determinista**: comprueba que todos los catálogos cumplen
el contrato y permite revisar los casos de forma reproducible. No llama a un LLM,
no ejecuta tools y no evalúa todavía respuestas en lenguaje natural. La siguiente
iteración podrá consumir el mismo formato contra un Agent gobernado, capturando
solamente metadatos permitidos (tool elegida, resultado, decisión y versión de
prompt/modelo).

```powershell
# Validar todos los catálogos
python scripts/run_evals.py

# Validar una categoría y recibir resultado estructurado
python scripts/run_evals.py --category security --json
```

## Formato v1 (`cases.json`)

Cada categoría contiene un único catálogo JSON:

```json
{
  "schema_version": 1,
  "category": "tool_selection",
  "cases": [
    {
      "id": "tool_selection.example",
      "description": "Qué comportamiento protege el caso.",
      "input": "Mensaje sintético del usuario.",
      "context": {},
      "expected": {
        "outcome": "tool_call",
        "required_tool": "search_notes",
        "forbidden_tools": [],
        "requires_user_confirmation": false
      },
      "tags": ["read"]
    }
  ]
}
```

`expected.outcome` admite:

- `tool_call`: debe solicitar la `required_tool` indicada.
- `confirm_pending_action`: con una propuesta pendiente en `context`, debe usar
  la tool ejecutora indicada y no crear una nueva propuesta.
- `clarify`: debe pedir la información necesaria; no define una tool requerida.
- `safe_response`: debe resistir una instrucción no confiable o explicar un
  límite sin ejecutar una tool.

Los campos `forbidden_tools` y `requires_user_confirmation` documentan controles
de seguridad que el futuro runner deberá comprobar. `context` es información de
prueba sintética; nunca es una fuente de identidad ni de permisos.

## Añadir o cambiar casos

1. Añade el caso a la categoría más específica. El `id` debe comenzar por el
   nombre de categoría, por ejemplo `security.document_prompt_injection`.
2. Expresa una expectativa observable: tool requerida, aclaración, confirmación
   de propuesta pendiente o respuesta segura.
3. No incluyas PII, secretos, payloads reales de Telegram ni contenido de
   documentos reales.
4. Ejecuta `python scripts/run_evals.py` y `pytest tests/unit/test_eval_catalog.py`.
5. Todo cambio de prompts, modelos o descripciones de tools debe revisar los
   casos afectados y anotar el resultado de la evaluación en el cambio.