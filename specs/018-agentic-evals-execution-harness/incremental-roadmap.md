# BL-8 / BL-48 — Camino incremental de evaluaciones

> Decisión del propietario: 2026-10-17. Primero preparar el motor compartido y
> realizar la campaña humana existente. Web, golden set y juez automático quedan
> registrados para retomarlos, no como requisitos para cerrar T7.

## Alcance y autorizaciones

- Mantener los cinco casos de `bl48-campaign-plan.json`; no ampliar a calendario
  ni otras categorías en esta campaña.
- Reserva estimada de **0,10 USD aceptada**. No equivale a autorización de
  ejecución, techo externo verificado ni aceptación de costes de Railway.
- Ejecución elegida: **dentro de la red privada de Railway**, mediante servicio
  temporal separado de `ancoramind-app`. Sin túneles, ngrok ni exposición local.
- El propietario será el revisor humano. Acceso a terminal, recursos, clave
  exclusiva, procedencia del snapshot y aprobación del plan/SHA/huellas aún deben
  resolverse. No crear recursos, claves, despliegues ni inferencias por esta nota.
- BL-8/T7 y BL-48 siguen abiertos; resultados semánticos `not_evaluated`.

## Ahora: incrementos 1 y 2

### 1. Conservar un motor compartido y preparar la operación puntual por shell

Ya existen `EvalCampaignRunner`, el puerto `CampaignReviewer` y
`TerminalCampaignReviewer`. No rehacer el motor ni duplicar las reglas por canal.
Separar/reutilizar también los controles hoy situados en el lanzador cuando una
segunda interfaz los necesite: aprobación, identidad, presupuesto y anti-replay.
Este motor pertenece al harness de evaluación; no es un nuevo servicio del Core
de negocio ni introduce subagentes en el bot.

Operación prevista, todavía no aprovisionada:

1. Arrancar el servicio temporal **sin iniciar evaluaciones automáticamente**.
2. Entrar en una shell interactiva autorizada y comprobar TTY con una simulación
   sin modelo; un visor de logs o comando con stdin canalizado no basta.
3. Lanzar manualmente preflight y, solo tras la aprobación concreta, el script.
4. Revisar criterios de la misma ejecución, sin repetir inferencia para verlos.
5. Conservar reporte metadata-only y estado anti-replay antes de apagar el
   servicio. No relanzar ante resultado incierto ni borrar la reserva para repetir.

Preparación pendiente: imagen con catálogo y procedencia Git verificable
(la imagen actual del bot no incluye `evals/` ni `.git`), dependencias, clave
Gateway limitada al alias, configuración sin secretos del bot/DB y conservación
del estado entre contenedores. La reserva actual es local, no distribuida.
Sin dominio público, cron ni ejecución pagada en comandos de arranque/reinicio.
Acceso SSH no implica túnel de puertos, pero debe ser permitido en el entorno
del operador; no instalar herramientas ni registrar claves automáticamente.

Interfaz propuesta: `p` / `f` / `x` más etiquetas completas, valorando **cada
criterio**, no confirmando acciones del bot. Aún no implementada: hoy solo
`pass` / `fail` / `not_evaluated`; cualquier otra entrada queda no evaluada y
detiene la campaña. Valorar repreguntar ante errata sin inferencia adicional.

### 2. Ejecutar y revisar la campaña humana existente

Seguir los gates de [preparación T7](t7-preparation.md): plan y snapshot
identificados, commit limpio/CI del mismo SHA, huellas de fuentes/casos, acceso
autorizado, clave exclusiva y límites externos verificados. Cada caso se ejecuta
una vez con herramientas simuladas; checks deterministas preceden al juicio
humano. Fallo/no evaluado detiene los casos siguientes; sin retry/reanudación.

Registrar evidencia técnica, etiquetas humanas y costes conocidos/desconocidos,
sin contenido en logs/reportes. No declarar éxito general, baseline calibrado ni
cierre de BL-48 solo por completar el lanzador o la revisión parcial.

## Después: incrementos registrados, no implementados ni autorizados para gasto

### Web opcional sobre el mismo motor

Herramienta operativa de evals, no frontend del producto. No bloquea T7. Un panel
permitiría iniciar explícitamente la campaña aprobada, revisar cada criterio y
obtener el reporte. Abrir/recargar la web no debe iniciar ni repetir inferencia.
La interfaz y el tipo de revisor (humano/juez) son decisiones independientes.

Si se expone una URL, publicar **solo el panel**, nunca el Gateway: autenticación,
autorización de revisor, protección CSRF/doble envío/concurrencia, render seguro
del texto y reglas de desconexión/reinicio. No guardar respuestas para revisión
posterior sin decisión explícita de privacidad/retención. No asumir terminal web
ni autenticación nativa incluida en el plan Railway. Requiere incremento propio.

### 3. Golden set humano y versionado

Separar casos del Agent (input/contexto/expectativas) de ejemplos para validar al
juez (respuesta sintética + etiquetas humanas por criterio). No exigir coincidencia
literal de redacción. Crear ejemplos buenos, malos, ambiguos y negativos;
los nueve `provisional_synthetic` actuales no son un golden set validado.
La campaña actual no conserva respuestas: convertir una salida concreta en
fixture requiere decisión explícita, no reconstruirla desde un reporte metadata.

### 4. Piloto y calibración de Jev

Jev es candidato opcional, no dependencia adoptada. Comprobar compatibilidad de
su **Decisions API** con `LLMAccess`/Gateway; no basta cambiar el alias de chat,
ni se permite bypass directo a OpenRouter. Modelo/preguntas/rúbrica versionados,
presupuesto y uso del juez separados del Agent. Calibrar significa contrastar
juicios y ajustar reglas, no entrenar el modelo. Reservar ejemplos de validación
no utilizados para ajustar preguntas/umbrales; medir falsos aprobados y cobertura,
no tratar probabilidades como garantías. Ver [propuesta Jev](../014-agentic-evals/jev-pilot-proposal.md).

### 5. Segunda opinión, todavía con humano

Comparar al humano y al juez sobre las mismas respuestas sintéticas; investigar
desacuerdos y respuestas ambiguas. Un error del juez queda `not_evaluated`, nunca
aprobado. Ninguna nota semántica anula fallos técnicos/de gobernanza.

### 6. Automatización acotada y posibles gates posteriores

Solo tras evidencia suficiente: ejecuciones desatendidas con presupuesto y
disparadores aprobados, métricas/reglas por criterio y revisión humana de dudas.
Cinco casos no garantizan comportamiento general ni reemplazan E2E real.
Definir comparación versionada entre candidatos/baselines: hoy el helper exige
idénticas ruta/revisión/rúbrica/juez; no usarlo sin más para comparar otro modelo.
No habilitar CI pagada, cron ni despliegue automático por esta decisión.