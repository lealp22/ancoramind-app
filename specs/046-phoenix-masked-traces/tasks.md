# Tareas — Spec 046

- [ ] T0 · Spike (`spike.md`): informe `spike-result.md` local disponible (2026-10-22),
      Q1–Q5/Q7/Q9 acotados, Q6/Q8 y seam de procedencia pendientes; no cierre pleno.
- [x] T1 · Decisión del propietario (2026-10-23): ADR-007 Accepted con la enmienda
      acotada del principio 11, captura manual, retención 30 días, todos los
      usuarios autorizados. Autoriza implementar con flag OFF; no la activación.
- [x] T2 (2026-10-25, local) · `src/observability/masking.py` (patrón con validación:
      Luhn, DNI/NIE, IBAN, matrícula, VIN, email, teléfono, tokens, red numérica) +
      nueva `src/observability/field_policy.py` (capa por esquema, por nombre de
      campo y forma del valor), usada por `MaskedSpanExporter` en los argumentos
      `propose_*`. Cuatro clases: identificador personal (marcador tipado siempre),
      texto libre (se conserva y se enmascara por patrón), id interno (se conserva
      sólo si es un UUID canónico) y estructurado (se conserva sólo con la forma
      estricta de su campo). Un valor que no valida en un id o campo estructurado
      sale como `[INVALIDO]`, no se exporta tras enmascararlo: el patrón no ve
      nombres y una fecha con prosa es una anomalía. Corrige dos defectos del
      prototipo: los UUID salían como `[TOKEN]` (se perdía la correlación con
      PostgreSQL) y los enteros pasaban por la red numérica. Un test de deriva
      falla si una `propose_*` añade un parámetro sin clasificar. **Límite
      aceptado, sin cambio:** el texto libre sólo se enmascara por formato; nombres,
      direcciones y salud no se detectan (ADR-007).
- [x] T3 · Corpus existente válido/inválido y 10 controles cotidianos en español;
      0 positivos en esos controles, no medida poblacional de falsos positivos.
- [x] T4 parcial (2026-10-25) · `src/observability/phoenix_export.py`:
      `MaskedSpanExporter` (allowlist, máscara por esquema+patrón, fail-closed por
      span, fail-open en I/O), procedencia `ancora.capture.source` ∈
      {user_text, final_reply, proposal_args, call_metadata}, tools sólo
      `propose_*`/`present_reply`, `build_phoenix_tracing`/`configure_`/`shutdown_`
      con provider propio no global, nunca lanza y sin dependencias nuevas
      (gRPC OTLP ya estaba). Tests en `tests/unit/test_phoenix_export.py`.
      Cableado con T6 (2026-10-25): `lifecycle.py` llama a `configure_phoenix_tracing`
      al crear el runner y a `shutdown_phoenix_tracing` en el apagado de
      observabilidad. Con flag OFF o config incompleta devuelve `None` y no crea nada.
      Pendiente de T4: máscara por esquema de campos de dominio concretos (T2) y
      prueba contra Phoenix real en Railway. El prototipo del spike sigue siendo
      sólo referencia.
- [x] T5 parcial (2026-10-23) · Settings `PHOENIX_*` en `src/config.py` y `.env.example`;
      `phoenix_tracing_active` exige flag + endpoint http(s) + API key + clave de
      seudónimo ≥32 + proyecto; configuración incompleta no impide arrancar
      (fail-open) y solo informa nombres, nunca valores. Pendiente: alta del
      provider (va con T4); aún sin efecto en producción.
- [x] T6 (2026-10-25, local, flag OFF) · Captura manual en
      `GovernedInteractionRunner.run` vía `src/observability/phoenix_capture.py`
      (política) + `phoenix_export.py` (exporter). Procedencia decidida por el
      llamador: el processor pasa `capture_user_text` (False para voz, adjunto sin
      texto sintetizado y cualquier otro llamador). Metadatos siempre (también en
      fallo, con sólo el nombre de la clase de error). Respuesta del modelo y
      argumentos `propose_*` sólo si el turno no tuvo adjuntos y todas sus tools
      están en `SAFE_READ_TOOLS`/`propose_*`/`present_reply`: una tool nueva queda
      excluida por defecto. Argumentos de tools de lectura nunca se capturan.
      Trazas nuevas (contexto vacío), una por turno, con `correlation_id`,
      `interaction_id` y seudónimo HMAC. Tests: `test_phoenix_capture.py` y
      procedencia en `test_interaction_processor.py`; 4 mutaciones de las reglas de
      privacidad rompen sus tests. **Desviación de la spec:** la spec capturaba la
      respuesta final siempre; aquí se omite tras leer/analizar documentos o con
      adjuntos, porque puede reproducir su contenido (ADR-007). Propietario
      confirma la excepción y `SAFE_READ_TOOLS` (2026-10-25); recogida en la spec,
      sección «Diseño de captura». `search_documents` queda dentro de la exclusión.
      **Visibilidad por tool (opción A, 2026-10-25):** span `tool_metadata` por
      llamada (nombre del registro, orden, ok/error, duración, tamaño del
      resultado). Cierra un fallo propio de la primera entrega: el nombre de tool
      lo escribe el modelo y un `propose_*` inventado desbloqueaba contenido y
      llegaba al span; ahora todo nombre fuera de `KNOWN_TOOLS` sale como
      `unknown_tool`. Test de deriva contra las `propose_*` definidas en
      `src/agent/tools` (detectó `propose_preference_forget`, no cableada).
      Opción B (resultados enmascarados de `SAFE_READ_TOOLS`) no se implementa.
      **Mensaje de error de tool (2026-10-25):** decisión del propietario de incluirlo
      cuando el resultado es `error`. Acotado: primera línea, cortado antes de
      `input_value=`, 300 caracteres, enmascarado, sólo para tools registradas y sólo
      con `outcome=error`. Límite residual documentado en la spec (nombres/hosts no
      se detectan). Vigilar tras activar si aparece contenido; revisar T7 (canarios).
- [x] T7 (2026-10-25, local) · `tests/unit/test_phoenix_pipeline_privacy.py`: un turno
      real (`GovernedInteractionRunner` + `GovernedAgentFactory` reales con su hook
      de presupuesto, modelo guionizado, tools sintéticas) con dos providers reales
      exportando a memoria (Grafana y Phoenix). Canarios (DNI, tarjeta, teléfono,
      IBAN, matrícula, mensaje de error) entran por entrada del usuario, argumentos
      de propuesta, resultado de lectura, documento y error de tool. Comprueba lo que
      cada exportador **recibe**, no los filtros por separado: Grafana sin ningún
      canario ni clave fuera de su allowlist; Phoenix sólo con marcadores; sin
      resultados de lectura, contenido de documentos, bytes/nombre de adjuntos ni
      texto de voz; el LLM y lo persistido son idénticos con y sin Phoenix
      (criterio 9). Un test de control falla si algún pipeline no exporta nada.
      **Hallazgo en producción, ajeno a Phoenix:** ver «Hallazgo T7» abajo.
- [x] T8 (2026-10-25, local) · Mismo fichero: Phoenix caído (export, flush y shutdown
      lanzan), exporter que devuelve FAILURE, masker que lanza, provider roto y
      provider ya cerrado no cambian la respuesta; un turno fallido produce el mismo
      error con y sin Phoenix; Grafana sigue exportando con Phoenix caído; sin
      reintentos acumulados; el `MaskedSpanExporter` es el único acceso al delegado.
      Con el masker roto sólo salen spans de metadatos de tool (sin texto libre).

      **Hallazgo T7 (pipeline Grafana, ya desplegado antes de Phoenix):** al fallar
      una tool, `MetadataTelemetry.span()` llamaba a `use_span()` con los valores por
      defecto del SDK (`record_exception=True`, `set_status_on_exception=True`), que
      copiaban a Grafana el mensaje de la excepción en `status.description` y en un
      evento `exception` con `exception.message` y `exception.stacktrace`,
      saltándose la allowlist de atributos. En el test, un DNI dentro del mensaje de
      una excepción de tool llegaba al exporter. Corregido en `telemetry.py`: ambos
      a `False` y el estado de error se marca con el nombre de la clase únicamente,
      para todos los spans de la app. Revertir el arreglo hace fallar los tests.
      **No se ha comprobado qué hay ya almacenado en Grafana Cloud** (trazas
      anteriores de tools con error); si la regla 11 importa retroactivamente,
      conviene revisar la retención de trazas allí. El log de consola de Railway
      sigue recibiendo el texto de la excepción por parte del propio Agno
      (`log_warning/log_error`), sin cambio.
- [x] T9 (2026-10-25) · Documentación al día, sin activar nada.
      `docs/production-security-privacy.md`: inventario de copias de contenido (con
      «verificado» frente a «declarado»), qué se captura y qué no, límites del
      enmascarado, retención y borrado por usuario, y los factores que dispararían
      una DPIA (no realizada, pendiente de revisión legal). `docs/pilot-terms.md`:
      sección de la copia en Phoenix (enmascarado incompleto, 30 días, seudónimo,
      qué no se guarda, derecho a pedir borrado) y plazos de conservación corregidos,
      con aviso al operador de **publicar el texto antes de activar el flag**.
      `docs/architecture.md` §14.2 nueva y fila de observabilidad. AGENTS.md: estado
      de BL-56 (el principio 11 ya estaba enmendado desde 2026-10-23). ADR-006: nota
      de corrección del hallazgo de Grafana. Hallazgos que salieron al documentar:
      la purga de payloads ambiguos a 7 días no la invoca ningún código de
      producción (los términos prometían un borrado que no ocurre; el texto ya no lo
      promete) y `agno_runtime` guarda sin enmascarar y sin retención (ya anotado
      por el propietario). **Pendiente de prueba real:** el borrado por usuario sólo
      se probó contra un backend local desechable, y la retención de 30 días es
      declarada, no comprobada.
- [ ] T10 · Runbook: variables en Railway, red privada, retirada del dominio público.
- [ ] T11 · Gates: pytest unit + integration, Ruff, mypy, `git diff --check`; SHA/CI.
- [ ] T12 · Activación controlada: flag ON solo para el propietario y verificación E2E.
