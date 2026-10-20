# Spike — Compatibilidad de Phoenix con AncoraMind

Un spike es una investigación corta y con tiempo limitado cuyo producto es una
respuesta (sí / no / con matices), no código de producción. El código que se
escriba aquí es desechable y no se integra en `src/`.

Límite de tiempo: una sesión de trabajo (~half day). Si no hay respuesta, se
documenta lo bloqueante y se decide.

## Preguntas a responder

| # | Pregunta | Criterio de "sí" |
|---|---|---|
| Q1 | ¿`openinference-instrumentation-agno` funciona con `agno>=2.9,<3` instalado? | Instala sin conflictos de dependencias y genera spans de un run |
| Q2 | ¿Captura bien una ejecución con `present_reply` y `tool_choice=required`? | El span del run muestra las llamadas a tools, incluida la terminal |
| Q3 | ¿Podemos usar un `TracerProvider` propio sin tocar el global ni el pipeline de Grafana? | El instrumentor acepta `tracer_provider=` y el Collector no recibe esos spans |
| Q4 | ¿Qué atributos emite realmente? | Lista completa para construir la allowlist |
| Q5 | ¿Se puede interponer un exporter envolvente que modifique/descarte spans? | Los spans enmascarados llegan a Phoenix; un error de máscara descarta el span |
| Q6 | ¿Phoenix calcula coste con los aliases `ancoramind-default-rN`? | Muestra coste o se puede aportar por atributo |
| Q7 | ¿Cómo se autentica el exporter contra Phoenix con auth activa? | Clave de sistema en cabecera, probada en local |
| Q8 | ¿Qué cuesta en latencia y memoria? | Sobrecarga medida con y sin tracing, dentro de lo aceptable |
| Q9 | ¿Cómo se borra por usuario en Phoenix? | Procedimiento reproducible por UI o API |

## Método

1. Entorno aislado: venv nuevo fuera del repo (o rama desechable), con
   `arize-phoenix` local en Docker o `phoenix serve`. **No** usar el Phoenix de
   producción ni datos reales: solo mensajes sintéticos.
2. Instalar instrumentor y exporter; reproducir un run mínimo con el Agent
   configurado como en producción (modelo simulado o llamada real acotada y
   autorizada por el propietario; sin gasto nuevo sin aprobación).
3. Volcar los spans a fichero (exporter de consola) y revisar atributos (Q4).
4. Implementar un exporter envolvente de 20–30 líneas con una máscara de juguete
   (Q5) y forzar una excepción.
5. Registrar un segundo provider y verificar que el Collector queda intacto (Q3).
6. Medir latencia/memoria con 50 runs sintéticos con y sin tracing (Q8).
7. Probar autenticación (Q7) y borrado (Q9) en el Phoenix local con auth activa.

## Resultado esperado

Un informe `spike-result.md` en esta carpeta con: respuesta a cada Q, versiones
exactas probadas, lista de atributos, decisión (instrumentor vs spans manuales) y
riesgos nuevos. Si Q1–Q3 o Q5 son "no", se propone la alternativa de spans
manuales en `LLMAccess` antes de seguir.

## Fuera del spike

Detectores de enmascarado reales, cambios en `src/`, despliegue y activación de
flags en Railway.
