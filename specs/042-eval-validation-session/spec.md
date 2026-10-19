# 042 — Sesión de validación con presupuesto acumulado

## Decisión del propietario

Continuar el trabajo y avisar sólo cuando haya una acción real del propietario.
Autorización acotada a los cinco casos sintéticos de BL-48/r4/revisión humana y
evidencia cifrada7d, límite **0,10 USD acumulado**, incluyendo el run histórico
52759a15ad454050aef8b5c1a9b3f122. No es0,10 por intento. No otra clave/rotación,
reset presupuestario, provider alternativo ni nuevas inferencias por implementar.
Se sustituye para este modo la aprobación manual por SHA por una autorización de
sesión; cada SHA/huella/run sí se registra, la trazabilidad no se elimina.

## Contrato

- Opt-in `eval_console.py session-init --accept-session`; requiere imagen sellada
  limpia y volumen real. No ejecuta modelo; sólo GET de key/info/models existentes.
  Modo legacy approval.json y one-shot siguen disponibles sin sesión creada.
- Una sesión fija por volumen y clave de evidencia, ledger Fernet atómico/fsync
  bajo private-evidence/validation-session. Se liga al hash de la misma clave de
  Gateway (nunca el secreto) y caduca a7d; reinicializar no renueva saldo/plazo.
- Ámbito: mismo modelo/plan/snapshot/casos/rúbrica/presupuesto/prompts/tools/runtime.
  Fingerprint excluye sólo archivos allowlist de operación/diagnóstico del harness;
  no es firma, sandbox ni prueba de equivalencia de código Python. Esos cambios
  siguen requiriendo revisión y CI/despliegue manual specs/041 del SHA exacto.
  Un cambio de producto/prompts/modelo/catálogo o de clave se bloquea y necesita
  decisión distinta, no edición silenciosa del ledger.
- Importa reportes metadata anteriores del plan; no borra/rescribe/resume runs.
  Reporte ausente/incompleto/en curso, symlink o evidencia sin reporte bloquean.
  El candidato PRE_SESSION_SHA=db0c59b se separa explícitamente ANTES del check de
  terminalidad: su checkpoint interrumpido puede conservar reserved/running. Esto
  no lo declara terminado ni lo reanuda; mantiene fuera de sesión sus claves2h
  históricas. Controles de fichero/JSON permanecen; SHA actual/desconocido no
  terminal sigue bloqueando. Fix de orden tras reporte real2026-10-19.
  Cada caso histórico iniciado reserva el techo antiguo0,02, aunque actualnull:
  primer passed+segundo detenido consumen conservadoramente0,04, no0,003563 total.
  Segundo sólo permite diagnóstico nuevo si todos los eventos de uso completaron
  y error era InvalidPresentationOutputError; timeout/error red quedan inciertos.
- Obtiene saldo de la misma clave; max_budget debe seguir0,10, sin reset/rotación,
  único r4, concurrencia1, rutas mínimas, expiración y permisos verificados. Spend
  finito, no negativo y no decreciente; lectura fallida/clave distinta bloquean.
- Reserva **por caso**, antes de inferencia, nunca toda otra campaña0,10. El saldo
  disponible es0,10 menos máximo entre spend Gateway y baseline conservadora más
  reservas de esta sesión. No libera automáticamente reservas al final: metadata
  actual/estimada o Gateway con retraso no certifica factura final. Cada reserva
  queda consumida aunque el caso falle; exceso conocido bloquea y se conserva.
- `run` omite casos ya passed de la misma sesión para no pagarlos otra vez, pero
  no declara ese pass del candidato nuevo. Reduce el techo por caso al repartir
  saldo entre pendientes, redondeo hacia abajo, nunca superior0,02. También permite
  selección explícita de casos existentes con `--cases`. No se altera el catálogo.
- Un lanzamiento manual por source fingerprint, incluso cambiando subset/techo,
  claim exclusivo. Worker sin restart; lease exclusivo de sesión evita paralelos.
  Muerte dura deja lease; inspección explícita, no PID ni borrado automático.
  Caso reservado/incierto no se repite aunque cambie SHA; candidato nuevo puede
  diagnosticar fallo terminal acreditado dentro del mismo scope/saldo. No replay
  automático, reparación de etiquetas ni merge de resultados como campaña única.
- GET de scope/saldo antes de cada caso y justo antes/después de cada POST físico
  de chat vía event hooks del cliente ya gobernado. No providers/rutas de inferencia
  nuevas ni llamadas fuera de LLMAccess. Cualquier otra ruta POST se rechaza.
  Mantiene ejecución/time/model/tool budgets, sin retries del SDK/Agent/Gateway.
- Checkpoint/status guarda `session_reason` fijo y clase allowlist junto con uso/
  diagnóstico anterior; no contenido adicional. Review/list/status no infieren.
  Session status muestra saldo observado vs reserva, no saldo exacto facturable.

## Límites explícitos

0,10 es techo nominal/aproximado: las estimaciones de tokens/precios y spend de
Gateway pueden retrasarse; no se promete tope duro de factura ni reserva atómica
upstream. No habilitar BYOK/rutas/fallback ni mutar límite upstream compartido.
Un caso próximo al límite puede pararse conservadoramente antes de completarse;
si saldo insuficiente no se intenta y se habla con propietario antes de ampliar.

Un operador con clave y control de archivos puede reescribir ledger/historia; no
protección ante rollback conjunto o uso externo de la clave. Scope allowlist no
detecta cambios maliciosos dentro del harness excluido: confianza en Git/CI/revisión.
Un único volumen/operador, sin scheduler/DB/lease distribuido. Ledger/markers metadata
conservados para no renovar saldo al purgar evidencia bruta; retención contenido7d
sigue specs/040. No certifica E2E Telegram ni corrige causa histórica de present_reply.

## Prueba y parada

Import/redondeo/clave/scope/expiry/spend decreciente/saldo insuficiente, dos workers,
dos reservas concurrentes, sin filtrar secretos, read-only init/idempotencia,
histórico no recuperable/replay, cliente SDK/GovernedModel con HTTP sintético:
checks pre/post por POST, no retries, gasto agotado bloquea antes transporte y fallo
GET post-respuesta consume reserva sin seguir. Probar gates globales, catálogo y
paquete sellado offline. Stop sin commit/push/deploy/inferencia reales por agente.