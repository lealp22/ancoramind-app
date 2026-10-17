# Tasks — Spec 018: Isolated Agentic Evals Execution Harness

> **Backlog:** BL-8 · abierto 2026-09-27

- [x] T1 · Definir el aislamiento: no reutilizar el runner Telegram/ledger ni
      tools de producción; contextos sintéticos son DATA, nunca autoridad.
- [x] T2 · Materializar catálogos v1 validados en casos tipados y crear un
      puerto executor asíncrono inyectable.
- [x] T3 · Implementar checks deterministas de outcome, tool requerida/vetada y
      confirmación, con proyección metadata-only.
- [x] T4 · Añadir unit tests con executor fake que demuestren la ausencia de
      inputs/contextos/respuestas en el reporte.
- [x] T5 · Actualizar documentación y BACKLOG.
- [x] T6 · Adaptador físico implementado (2026-10-03):
      `src/agent/eval_physical_executor.py::GovernedPhysicalEvalExecutor` +
      catálogo de tools simuladas en `src/agent/eval_tools.py`. Agent
      gobernado por `LLMAccess` inyectado, `RuntimeConfigSnapshot`/budget de
      evaluación separados (bootstrap, sin PostgreSQL), sin reutilizar
      `GovernedAgentFactory` (acoplado a history/db de producción). Probado
      con un `Model` scripted en memoria (sin red/coste) —
      `tests/unit/test_eval_tools.py` + `tests/unit/test_eval_physical_executor.py`.
      **Decisión documentada:** `outcome` sólo deriva de las tools realmente
      invocadas; un sentinel `no_tool_call` sustituye a `clarify`/
      `safe_response` cuando no se invoca ninguna tool, porque distinguir
      esos dos requiere juzgar el texto de respuesta semánticamente — eso es
      T8, no T6. Detalle en `verification.md`.
- [ ] T7 · Con credenciales y presupuesto aprobados, ejecutar la modalidad LLM
      fuera de CI por defecto y capturar evidencia metadata-only.
      Preparación autorizada 2026-10-16: snapshot explícito, plan limitado,
      Gateway-only y preflight sin inferencia implementados y probados;
      `t7-preparation.md`. Reserva de 0,10 USD estimados aceptada posteriormente;
      sin aprobación de ejecución, credenciales/acceso ni inferencia real.
      BL-48 permanece abierto. Secuencia acordada en `incremental-roadmap.md`.
- [x] T7a · Lanzador explícito serial y revisión humana en terminal (2026-10-17):
      reserva local exclusiva/no replay, aprobación SHA+fuentes+casos+plan,
      SDK sin retry, scope Gateway, checkpoints/reporte metadata-only y parada
      ante fallo/cancelación/no evaluado. Pruebas sin inferencia pagada.
- [ ] T7b · Aprobar plan/presupuesto/snapshot, acceso privado y clave exclusiva;
      lanzar una campaña real con revisor presente y registrar los resultados.
- [x] T7c-local · Preparar operación puntual en servicio temporal privado Railway,
      separado del bot: no ejecutar al arrancar/reiniciar, shell con TTY probado
      sin modelo, assets/procedencia verificables y conservación de reporte y
      reserva sobre mount persistente entre contenedores. Motor único; p/f/x,
      repregunta ante errata y `--check-console` implementados. Imagen sin Git ni
      secretos con sello/huella contrastados con Git/CI externo; no firma.
      Runbook `railway-console-runbook.md`. Sin aprovisionamiento/ejecución real.
- [ ] T7c-remoto · CI/commit aprobados, coste/ventana Railway acordados, desplegar
      servicio temporal sin dominio, mount exclusivo `/eval-state`, clave eval
      restringida/expirable, scope/budget y TTY real del operador verificados.
      **Parcial 2026-10-17:** coste/creación inicial autorizados; CI db0c59b verde,
      servicio/volumen 100 MB creados sin dominio ni secretos. Selección real de
      Dockerfile contradice configuración: último deployment CRASHED, proceso
      falla cerrado sin inferencia. No listo para shell/campaña. Ver
      `railway-provisioning.md`; clave/TTY/scope y corrección pendientes.
      **Recuperación posterior:** contexto privado con Dockerfile eval en raíz,
      mismos fuentes/huella db0c59b CI-verde; deployment `54892e8d…` SUCCESS,
      idle_manual_only y 1 running/0 crashed. Defecto de ruta GitHub no corregido;
      empaquetado reproducible local `prepare_eval_build.py`. Sin keys/inferencia;
      **Verificación posterior por propietario:** shell accesible, mount_valid y
      writable true, preflight_valid db0c59b/huella esperada y console_ready;
      inference_started/approval_granted false. Subgates mount/preflight/TTY
      superados, no T7c completo. Siguen clave exclusiva/expirable, scope/budget
      externo, gateway_access not_checked y aprobación/ejecución de campaña.
      Autorizada después preparación de clave/acceso sin modelo; helpers locales
      de operador y `gateway-access-runbook.md` listos, no ejecutados remotamente.
      Clave prevista sólo lectura r4/2 h/0,10 USD sin reset; no inferencia. No
      marcar clave/scope/budget live verificados hasta reportes reales.
      **Reporte real posterior del propietario:** eval_key_read_only_ready,
      clave exclusiva sólo lectura r4, expiración 2026-10-18T01:37:40.773Z,
      presupuesto nominal 0,10 USD sin reset/gasto cero, concurrencia 1. Creación
      y restricciones releídas en Gateway confirmadas; acceso desde evals,
      pricing/enforcement de coste y aprobación/campaña siguen pendientes.
      Intento desde evals bloqueado sin inferencia; causa no confirmada. Helper
      local mejorado con diagnóstico metadata-only por etapas, sin relajar scope
      ni regenerar clave/redeploy. Pendiente salida de diagnóstico del operador.
- [x] T7d · Registrar decisión del propietario (2026-10-17): primero motor
      compartido/operación por consola y campaña humana de cinco casos; web,
      golden set humano, piloto/calibración Jev, segunda opinión y automatización
      quedan diferidos en `incremental-roadmap.md`, sin gasto/CI nuevos.
- [ ] T8 · Definir/calibrar scoring semántico opcional (Jev u otro juez) con
      etiquetas humanas sintéticas y baseline por ruta/configuración.
      **Preparación local sin inferencia (2026-10-14):**
      `src/agent/eval_semantic_scoring.py` define el puerto `SemanticJudge`,
      juicio por criterio, estados `pass`/`fail`/`not_evaluated`, calibración y
      comparación de baseline únicamente si coinciden ruta lógica, revisión de
      configuración, rúbrica y versión de juez. Sus reportes son metadata-only.
      `evals/response_style/provisional_labels.json` aporta nueve ejemplos
      sintéticos buenos/malos/ambiguos, marcados explícitamente
      `provisional_synthetic`; se validan por `scripts/run_evals.py`, pero el
      código rechaza calibrar cualquier juez hasta que un revisor humano cree un
      fixture `human_reviewed`. No existe adaptador Jev/LLM, `LLMAccess`, CLI de
      ejecución ni llamada de red en este incremento.
- [x] T6b · Tras el cierre legacy (BL-39/40, 2026-10-11), trasladar los casos
      de confirmación a `CoreConsentEvalExecutor` aislado y actualizar
      expectativas a las mutaciones canónicas (`register_vehicle`,
      `create_reminder`), nunca a `execute_*`. El harness modela las
      transiciones elegibilidad/presentación/principal/expiración/descarte y
      WRITE_TRIVIAL con estado sintético por caso y reporte metadata-only; no
      toca repositorios, sesiones, Telegram ni ejecutores productivos. El
      adaptador Agent sigue rechazando confirmaciones antes de inferencia y ese
      rechazo no cuenta como éxito de consentimiento. Evidencia en
      `verification.md`.
