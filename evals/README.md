# Evals — contratos de comportamiento del agente

Los ficheros de esta carpeta son datasets versionados para prevenir regresiones
al cambiar prompts, descripciones de tools o modelos. No contienen credenciales,
IDs reales, mensajes de usuarios ni documentos privados: todos los ejemplos son
sintéticos.

**Actualizar candidato desde navegador:** workflow manual
[Actualizar evaluador — specs/041](../specs/041-manual-eval-deploy/runbook.md),
SHA/CI explícitos y despliegue sólo evals desde runner GitHub. Sin Railway CLI
en equipo local ni inferencia automática; setup de secreto inicial necesario.

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
El catálogo tiene 42 casos, de los cuales 9 son de `response_style`. El
adaptador físico usa el contrato `AgentReply(answer, proposal_text)` como
producción, ahora mediante la tool terminal `present_reply`, sin JSON mode ni
`output_schema` en el bucle principal. La presentación no cuenta como tool de
dominio para el veredicto, aunque consume presupuesto igual que en producción.
No simula la entrega/outbox del Core: revisar un texto de
Agent no valida por sí solo la presentación final con botones en Telegram.
Los casos TODO/pendientes usan tools en memoria, sin repositorios productivos.

BL-30/specs/025 añade seis casos `security` de contenido web no confiable (cinco
ataques y un control benigno, tag `web`): instrucción en snippet, orden en título,
confirmación falsificada, cierre falso de delimitador y petición de leer datos
privados para enviarlos a una URL. El harness simula `search_web` sin I/O con las
claves de contexto `untrusted_web_snippet` y `untrusted_web_title`. Son contratos
estáticos: no se ejecutó inferencia real ni se mide resistencia del modelo.
No se ejecutó inferencia real ni evaluación semántica en este incremento.

BL-53/BL-55 (2026-10-22): política evaluable de presentación documental y fechas.
Tres casos `response_style.document_*` cubren nombre/procedencia sin UUID en uso
normal, ID solicitado y homónimos. Fixtures simuladas conservan IDs y procedencia;
no campaña ejecutada ni baseline humano nuevo. Catálogos: 45 casos/6 categorías.
Evidencia y límites en `specs/047-readable-presentation/verification.md`.

## Preparación local de scoring semántico (T8, sin juez conectado)

**Preparación T7 posterior (2026-10-16):** el candidato
`response_style/bl48-campaign-plan.json` y el snapshot secret-free exportado
`response_style/runtime-rev8-snapshot.json` permiten preflight sin inferencia
mediante `scripts/eval_preflight.py`. Wiring Gateway-only en
`src/agent/eval_campaign.py`, presupuesto restringido y aprobación separada
ligada al checksum; en ese incremento no había lanzador pagado ni juez conectado. Acceso privado,
clave exclusiva y reserva candidata de 0,10 USD estimados aún no aprobados.
Detalles/limitaciones: `specs/018-agentic-evals-execution-harness/t7-preparation.md`.
Esto no altera el carácter estático de `scripts/run_evals.py` ni cierra BL-48.

**Lanzador T7 posterior (2026-10-17):** `scripts/execute_eval_campaign.py` ya
ejecuta casos serialmente **solo** con `--execute`, aprobación explícita de plan,
SHA limpio/fuentes/rúbrica, clave Gateway exclusiva y revisor en terminal.
Sin esa opción es preflight puro. Reserva total local/no replay, parada ante
fallo/no evaluado, SDK sin retry/redirect/proxy env, respuesta particionada en
memoria para revisión humana; reporte solo metadata. No es un juez automático
calibrado, ni una evaluación realizada, ni garantía distribuida de at-most-once.
No hay acceso/Gateway ni presupuesto nuevo aprobado: consultar el runbook citado
antes de ejecutar. Nunca automatizar labels pass ni grabar respuestas en logs.

`src/agent/eval_semantic_scoring.py` prepara un contrato opcional para juzgar
cada `response_criteria` por separado. No es un modelo ni un cliente: define el
puerto `SemanticJudge`, los estados `pass`, `fail` y `not_evaluated`, calibración
y comparación con baseline versionado por ruta lógica, revisión de configuración,
rúbrica y versión de juez. `not_evaluated` no se interpreta como aprobado.

`evals/response_style/provisional_labels.json` contiene nueve respuestas
**sintéticas** buenas, malas y ambiguas. Está marcado
`label_source: "provisional_synthetic"`: el comando estático valida su formato,
pero el código impide usarlo para calibrar un juez. Para ello hace falta añadir
un fixture nuevo con `label_source: "human_reviewed"` tras revisión humana. No
convertir ejemplos provisionales en baseline ni umbrales de CI.

La calibración etiqueta únicamente criterios de texto. Las condiciones de que
una tool se haya invocado, una propuesta exista o el Core haya confirmado una
acción se mantienen en los checks deterministas y nunca las certifica el juez.
Los objetos de informe exponen IDs/versiones/estados por criterio; no exponen
respuestas, criterios, inputs ni contextos.

## Piloto futuro: Jev como evaluador auxiliar (no implementado)

La propuesta para el siguiente incremento de BL-8 está en
[`specs/014-agentic-evals/jev-pilot-proposal.md`](../specs/014-agentic-evals/jev-pilot-proposal.md).
El flujo previsto usa **solo casos y contextos sintéticos**: tras el adaptador
gobernado aislado, comprobar por código tools y confirmaciones, puntuar criterios
semánticos de `response_style` con Jev de forma opcional y comparar sus juicios
con etiquetas humanas y un baseline versionado.

Jev no reemplazaría las aserciones sobre tools prohibidas, autorización o
confirmaciones; una puntuación alta no convierte un caso fallido en aprobado.
Antes de conectarlo hay que validar su API de decisiones a través de la
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