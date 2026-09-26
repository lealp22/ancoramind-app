# Propuesta BL-8 — Piloto de Jev como evaluador auxiliar

> Estado: propuesta de siguiente incremento, **no implementada** (2026-09-26).
> La spec 014 existente describe únicamente la entrega inicial de catálogos
> sintéticos y validación determinista. No modificar `tasks.md` histórico para
> presentar este piloto como realizado.

## Objetivo y límites

Investigar si Jev aporta una señal útil y económica para detectar regresiones
**semánticas** en respuestas del Agent. Empezar por `response_style`: respuesta
directa, brevedad, estructura, expresión de incertidumbre y ausencia de
afirmaciones de acciones no realizadas. Jev es un candidato, no una dependencia
ni una decisión de usarlo en producción. No se propone para elegir o ejecutar
tools del bot, autorizar operaciones, sustituir al Agent principal, extraer
documentos ni decidir si una interacción es segura.

## Secuencia propuesta

1. **Runner de ejecuciones (necesario con o sin Jev):** materializar casos y
   contextos sintéticos en un entorno aislado; ejecutar el Agent gobernado con
   rutas y configuración versionadas; capturar resultado observable, tools
   solicitadas y respuesta para la evaluación en memoria. No usar usuarios,
   documentos ni credenciales de terceros reales, ni permitir escrituras o
   acciones externas reales. Especificar aislamiento y dobles de servicios
   antes de ejecutarlo. La validación estática actual permanece intacta.
2. **Checks deterministas primero:** comparar tool requerida/vetada, resultado,
   propuestas y confirmaciones contra las expectativas del catálogo. Un fallo
   de seguridad o gobernanza no puede convertirse en éxito por una puntuación
   semántica. No inferir permisos ni identidad desde `context`.
3. **Juicio semántico opcional:** para cada criterio concreto de
   `expected.response_criteria`, elaborar una pregunta de decisión acotada
   con el input, contexto sintético y respuesta; definir y versionar preguntas,
   opciones, escalas y modelo. Registrar puntuación y estado de error por
   criterio; si la evaluación falla, marcarla como no evaluada, nunca como
   aprobada. Evitar un único score opaco para toda la respuesta.
4. **Calibración humana:** crear una muestra sintética con respuestas buenas,
   malas y ambiguas, etiquetada por personas; comparar discrepancias y falsos
   aprobados, especialmente en incertidumbre y afirmaciones de acciones no
   ejecutadas. Definir umbrales y reglas para revisión humana solo tras medir
   esa concordancia. Conservar baseline por ruta/configuración, versión del
   Agent y del juez para comparaciones antes/después.
5. **Informe y decisión:** distinguir checks deterministas, juicios semánticos,
   no evaluados y coste/latencia por caso y por suite. La evaluación semántica
   será informativa al principio; no habilitar gate CI ni llamadas pagadas en
   CI por defecto. Adoptarla solo si detecta regresiones valiosas con un nivel
   aceptable de falsos aprobados y coste/latencia frente a revisión humana.

## Bloqueos y gobernanza

- **Compatibilidad:** comprobar la API de decisiones de Jev con el Gateway
  privado. Que el modelo esté disponible en OpenRouter no demuestra que la
  interfaz actual de `LLMAccess`/LiteLLM, diseñada para chat, admita esa API.
  Si no es compatible, documentar el resultado y diseñar una frontera
  gobernada equivalente antes de cualquier integración. Nunca llamar
  directamente a OpenRouter para eludir el Gateway obligatorio.
- **Presupuesto y trazabilidad:** toda inferencia del juez debe tener ruta
  versionada, contexto de ejecución, límites de tiempo/llamadas/coste, registro
  de uso y correlación conforme a specs/013; definir presupuesto separado de
  la ejecución bajo prueba para no alterar su resultado. No asumir que Jev
  puede reutilizar sin cambios el presupuesto del Agent ni su interfaz Agno.
- **Privacidad:** usar solo fixtures sintéticas; no incluir contenido personal
  en datasets, logs, telemetría ni informes persistidos. Las respuestas
  sintéticas pueden mantenerse en memoria para juzgarlas, pero exportar solo
  metadatos permitidos y puntuaciones. Revisar explícitamente qué datos
  atraviesan el Gateway antes de las pruebas.

## Criterio para iniciar la implementación

Detallar en un nuevo incremento SDD el aislamiento de herramientas, contrato
de puntuaciones y reportes, y pruebas de compatibilidad de Gateway; entonces
implementar runner y checks antes del adaptador Jev. Si el juez no supera la
calibración humana o la gobernanza no admite la API, mantener BL-8 operativo
con checks deterministas y revisión humana de respuestas.