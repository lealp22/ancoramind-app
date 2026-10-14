# Evals — contratos de comportamiento del agente

Los ficheros de esta carpeta son datasets versionados para prevenir regresiones
al cambiar prompts, descripciones de tools o modelos. No contienen credenciales,
IDs reales, mensajes de usuarios ni documentos privados: todos los ejemplos son
sintéticos.

## Alcance de esta primera entrega

El comando `scripts/run_evals.py` es **determinista**: comprueba que todos los
catálogos cumplen el contrato y permite revisar los casos de forma reproducible.
No llama a un LLM, no ejecuta tools y no evalúa respuestas en lenguaje natural.
El catálogo `security` contiene ataques sintéticos y controles benignos de
lecturas; incluye una **descripción textual** de un ataque visual, no una prueba
de imagen/multimodal. Ni la validación estática ni esta descripción miden
resistencia real a prompt injection o tasa de falsos positivos.

La spec 018 añade `src.agent.evals`, un harness asíncrono aislado para
materializar esos mismos casos, inyectar un executor sintético y comprobar por
código outcome, tool requerida/vetada y confirmación. El harness no crea Agent,
provider, `LLMAccess`, sesión de DB ni tools de producción; inputs, contextos y
respuestas quedan en memoria, y sus reportes excluyen esos contenidos.

El adaptador contra un Agent gobernado existe para lecturas y propuestas:
`GovernedPhysicalEvalExecutor` pasa por `LLMAccess`, usa
`RuntimeConfigSnapshot`/budget propios e inyecta únicamente tools simuladas sin
I/O. No se habilita con credenciales reales ni en CI sin aprobación explícita.
La confirmación revisable no se evalúa ahí: el Agent no expone `execute_*` y el
Core decide el claim/ejecución antes de inferencia. `CoreConsentEvalExecutor`
verifica ese protocolo con un store sintético aislado; tampoco usa DB ni ejecuta
mutaciones reales.

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
- `confirm_pending_action`: el harness Core observa la mutación canónica de
  una propuesta presentada y válida en `context`, sin crear otra propuesta.
  No representa una tool `execute_*` invocable por el Agent.
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

BL-48/specs/036 añade cinco casos de presentación: propuesta única, consulta
mixta, tareas tras descarte, nueva petición explícita y lectura de pendientes.
El catálogo tiene 36 casos, de los cuales 9 son de `response_style`. El
adaptador físico usa el contrato `AgentReply(answer, proposal_text)` como
producción, pero no simula la entrega/outbox del Core: revisar un texto de
Agent no valida por sí solo la presentación final con botones en Telegram.
Los casos TODO/pendientes usan tools en memoria, sin repositorios productivos.
No se ejecutó inferencia real ni evaluación semántica en este incremento.

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