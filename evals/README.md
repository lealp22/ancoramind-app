# Evals — contratos de comportamiento del agente

Los ficheros de esta carpeta son datasets versionados para prevenir regresiones
al cambiar prompts, descripciones de tools o modelos. No contienen credenciales,
IDs reales, mensajes de usuarios ni documentos privados: todos los ejemplos son
sintéticos.

## Alcance de esta primera entrega

El comando `scripts/run_evals.py` es **determinista**: comprueba que todos los
catálogos cumplen el contrato y permite revisar los casos de forma reproducible.
No llama a un LLM, no ejecuta tools y no evalúa respuestas en lenguaje natural.

La spec 018 añade `src.agent.evals`, un harness asíncrono aislado para
materializar esos mismos casos, inyectar un executor sintético y comprobar por
código outcome, tool requerida/vetada y confirmación. El harness no crea Agent,
provider, `LLMAccess`, sesión de DB ni tools de producción; inputs, contextos y
respuestas quedan en memoria, y sus reportes excluyen esos contenidos.

El adaptador posterior contra un Agent gobernado sigue pendiente: deberá pasar
por `LLMAccess`/Gateway, usar `RuntimeConfigSnapshot` y budget propios de
evaluación, e inyectar únicamente tools simuladas sin I/O. No se habilitará en
CI ni con credenciales reales sin aprobación explícita.

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

En `response_style`, `expected.response_criteria` contiene criterios observables
para revisión humana de la respuesta (brevedad, estructura, incertidumbre y
confirmación). El runner comprueba que la lista existe y está bien formada,
**no** que el modelo cumpla esos criterios. La evaluación del estilo contra un
Agent gobernado queda pendiente; no confundir validación del catálogo con
validación de respuestas reales.

## Piloto propuesto: Jev como evaluador auxiliar (no implementado)

La propuesta para el siguiente incremento de BL-8 está en
[`specs/014-agentic-evals/jev-pilot-proposal.md`](../specs/014-agentic-evals/jev-pilot-proposal.md).
El flujo previsto usa **solo casos y contextos sintéticos**: tras el adaptador
gobernado aislado, comprobar por código tools y confirmaciones, puntuar criterios
semánticos de `response_style` con Jev de forma opcional y comparar sus juicios
con etiquetas humanas y un baseline versionado.

Jev no reemplazaría las aserciones sobre tools prohibidas, autorización o
confirmaciones; una puntuación alta no convierte un caso fallido en aprobado.
Antes de implementarlo hay que validar su API de decisiones a través de la
frontera gobernada `LLMAccess`/Gateway, sin bypass directo a OpenRouter. El
comando `python scripts/run_evals.py` **sigue validando solo el catálogo**: no
ejecuta este flujo, no llama a Jev y no evalúa respuestas del Agent.

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