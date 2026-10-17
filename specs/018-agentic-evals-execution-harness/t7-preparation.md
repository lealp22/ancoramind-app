# T7 — Preparación del harness real aislado (2026-10-16)

**Autorizado:** preparar wiring/ruta/presupuesto/acceso seguro. **No autorizado
todavía:** ejecutar inferencia pagada con el candidato, crear claves o túneles,
exponer Gateway, mutar configuración/revisiones o desplegar. BL-48 permanece
abierto hasta resultados reales; no se sustituye por la matriz manual Telegram.

**Decisión posterior (2026-10-17):** reserva estimada de 0,10 USD aceptada;
ejecución elegida dentro de Railway mediante servicio temporal separado y
revisión humana puntual por shell, sin túneles. No autoriza aprovisionamiento,
claves, despliegue ni inferencia; siguen pendientes los gates concretos.
Alcance inmediato y continuación futura en [camino incremental](incremental-roadmap.md).

**Incremento local posterior:** servicio temporal idle e imagen dedicada,
procedencia sellada sin copiar Git, mount persistente obligatorio, p/f/x y
prueba de consola sin modelo. Ver [runbook Railway](railway-console-runbook.md).
Preparación local no equivale a despliegue ni campaña revisada.

**Aprovisionamiento posterior autorizado:** servicio separado y volumen 100 MB
creados con CI db0c59b verde; arranque todavía bloqueado (Dockerfile real distinto
del configurado). Sin clave/TTY/inferencia. No se migra bot/Gateway ni se admite
campaña por esta autorización. Estado preciso: [evidencia Railway](railway-provisioning.md).

## Incremento implementado

- `src/agent/eval_campaign.py`: candidato validado, aprobación ligada al checksum
  del plan, únicamente `LLMAccess` con Gateway, configuración separada sin .env,
  credenciales ambiente ni DB. `EvalUsageRecorder` solo guarda metadata en memoria.
- Executor físico acepta snapshot/budget explícitos, revisa identidad de revisión,
  rechaza expansión de límites y arma deadline. Se envía max_tokens al SDK.
- `scripts/eval_preflight.py`: carga/valida snapshot y plan sin modelos/red. La
  opción explícita `--check-gateway` realiza solo GET `/v1/models`, sin seguir
  redirects, y exige que la clave vea exactamente el alias previsto.
- El constructor de executor no ejecuta nada. Incremento posterior: lanzador
  explícito y revisión humana en consola, descritos debajo. No se añade a CI
  inferencia pagada ni un juez automático.

## Candidato — no aprobación

Assets bajo `evals/response_style/`:

- `runtime-rev8-snapshot.json`: exportación tipada de lectura, referencia histórica
  revisión 8/checksum `e2663c6a…db25`. No se publica una revisión nueva.
- `bl48-campaign-plan.json`: `single_proposal`, `mixed_read_proposal`,
  `tasks_after_discard`, `explicit_reproposal`, `pending_proposals_read`.
- Ruta lógica `ancoramind-default`, alias `ancoramind-default-r4`. Cada caso:
  120 s, 6 model calls/requests, 12 tools, 1024 output tokens, un intento de
  Gateway por llamada, sin retry/fallback cruzado. Son límites de eval, no cambios
  del runtime ni permiso para repetir una llamada incierta.
- Reserva **0,02 USD estimados por caso, 0,10 USD total**. No es un techo de
  facturación: verificar pricing y límite externo con una clave de evaluación
  exclusiva antes de aprobar el plan. No reutilizar la clave del bot.
- Fingerprint contenido `a41f255f1b4022bc5ac1c7efb35a02d82fb4ec2396d71f4991fea1db15f7cccc`.
- Checksum plan `8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139`.

## Preflight reproducible (sin inferencia)

Desde PowerShell, rutas absolutas:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
python "$root\scripts\eval_preflight.py" `
  --snapshot "$root\evals\response_style\runtime-rev8-snapshot.json" `
  --plan "$root\evals\response_style\bl48-campaign-plan.json"
```

Resultado obtenido: exit 0, `status=valid`, `inference_started=false`,
`gateway_access=not_checked`, `approval_status=pending_separate_approval`,
`semantic_status=not_evaluated`. Esto valida el candidato, **no** conectividad,
permisos/costes reales ni comportamiento del LLM.

## Acceso seguro pendiente

1. Aprobar plan/ruta/coste/privacidad sintética y SHA concreto a evaluar; revisar
   candidatos y permitir como máximo esos cinco casos, una vez cada uno.
2. Preparar, tras autorización específica, ejecución dentro de la red privada
   Railway en servicio temporal separado del bot. Sin túneles ni dominio público
   para esta fase. Comprobar terminal interactiva y conservar estado anti-replay;
   no instalar CLI ni aprovisionar acceso automáticamente. Ver camino incremental.
3. Configurar solo en el entorno seguro `ANCORA_EVAL_GATEWAY_URL` y
   `ANCORA_EVAL_GATEWAY_KEY` (no pegarlas en chat, argv, Git o reportes). La clave
   debe estar restringida al alias r4 y presupuesto externo verificado; no master
   key ni clave productiva compartida. URL solo loopback o Railway interno, `/v1`.
4. Ejecutar preflight con `--check-gateway` únicamente tras autorizar ese acceso.
   Ante 401, scope amplio u otro error: parar, sin fallback ni inferencia.
5. Tras aprobación explícita, el wiring exige `ANCORA_EVAL_APPROVED_PLAN` igual
   al checksum exacto del plan, `ANCORA_EVAL_SYNTHETIC_APPROVED=1` y
   `ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED=1`. Son señales de una decisión humana,
   **no establecerlas sin esa decisión ni confundirlas con verificación técnica
   del presupuesto**. El lanzador ahora para ante fallo, no relanza casos,
   conserva uso metadata-only y reserva el total antes de comenzar. Faltan acceso,
   aprobación y ejecución/revisión reales.

## Hallazgo de checksum — no reescribir historia

El checksum canónico recalculado para rev. 8 cambia entre procesos porque
`capabilities` es frozenset y `canonical_config_json` no ordena sus elementos.
La investigación inicial no reprodujo el hash almacenado. **Actualización local
2026-10-17:** enumeradas las 72 combinaciones de orden de capacidades sobre la
representación canónica del archivo preparado, una reproduce exactamente
`e2663c6ab9e2666f41ba3d5399d05feb8a0d4141de0d2d74fdcfca19b3afdb25`.
La configuración tipada de esa combinación es igual a la del snapshot; no se
cambian valores, solo el orden serializado. Se aplica la omisión canónica ya
existente de bloques/campos opcionales nulos; hashear el JSON exportado bruto no
es el mismo algoritmo. El orden explica la discrepancia **del artefacto local**.
Esto no verifica vigencia/igualdad con producción, que no se consultó, ni prueba
qué proceso histórico generó la huella. Prueba ejecutada sin red ni inferencia.
No se cambia el algoritmo productivo, una revisión existente ni se atribuye
el fingerprint de eval al control plane. El fingerprint de eval ordena capacidades
y liga toda la estructura tipada (incluidos revisión y checksum histórico) al plan
aprobado, por lo que un cambio de contenido requiere otra aprobación.
Queda remediar la inestabilidad con compatibilidad histórica en BL-23/specs/013;
no aceptar silenciosamente el snapshot ni reescribir checksums existentes.

## Evidencia local

- 36 tests focales campaña/executor: HTTP SDK mockeado con LLMAccess real, sin
  repositorios/tools productivos; gates de aprobación/scope/URL/budget/checksum,
  no heredar secretos de ambiente, dos procesos con hash seeds distintos,
  reporte sin texto, provider IDs ni credenciales.
- Suite global **1465 passed**, cobertura **80,19 %**; integración PostgreSQL
  local **173 passed, 1 STT live skipped**. Ruff global y mypy src (173 archivos)
  verdes. Catálogo estático válido 36 casos/9 ejemplos provisionales.
- Solo preflight puro ejecutado; sin nuevas inferencias aparte del E2E Telegram
  autorizado en specs/036 §13. Sin commit/push/despliegue.

## Lanzador y revisión humana implementados — 2026-10-17

Autorizado completar código y avisar de lo necesario por parte del propietario;
**no se interpreta como aprobación automática del candidato ni del gasto**.

### Qué hace y qué no garantiza

- `scripts/execute_eval_campaign.py` es preflight puro por defecto. La opción
  `--execute` exige aprobaciones ligadas a plan, SHA limpio, huella de fuentes y
  huella de casos/rúbrica, además de aceptación del snapshot/privacidad/presupuesto
  externo y revisión humana. No hay valores por defecto que activen esos permisos.
- Compara SHA/árbol/huella antes de cada caso; no se atribuye un resultado a un
  checkout distinto. Las huellas se obtienen otra vez tras el commit final.
- Reserva local exclusiva por checksum del plan antes de red/inferencia en
  `tmp/eval-campaigns/<plan_checksum>.reserved.json`. Cinco casos seriales, un
  uso del runner. Marcador retenido ante fallo/interrupción, sin resume ni borrar
  automáticamente. **Solo protege ese directorio/equipo**: no es un lock distribuido
  ni impide que un operador borre/copíe archivos. No borrar/evadir el marcador para
  repetir una operación incierta; requiere reconciliación y nueva autorización.
- Reserva completa 0,10 USD **estimados**, límites por caso enforced por el budget
  gobernado, max_tokens en SDK, SDK `max_retries=0`, HTTP sin redirects/proxy env.
  No es un techo de facturación del proveedor ni verificación del límite externo.
- GET `/models` verifica exactamente alias r4 antes del modelo. No crea claves,
  túneles ni dominios; no usa master key ni provider directo. Conexión fallida
  consume la reserva local por diseño conservador, sin permitir replay automático.
- Parada ante error, cancelación, checks deterministas fallidos, uso ausente o
  incorrecto, cambios de fuentes, revisión fail/not_evaluated o I/O de checkpoint
  fallido. No se continúa a otro caso tras esos resultados.
- La salida/reporte solo contiene metadata permitida: IDs, rutas/versiones,
  herramientas conocidas, tokens/costes, labels por índice y clase de error;
  `actual_cost=null` sigue desconocido, no cero. Logs/stdout/stderr de bibliotecas
  suprimidos durante la ejecución; no se imprime contenido de excepción.

### Revisión de la misma ejecución, sin repetir inferencia

`TerminalCampaignReviewer` abre explícitamente `CONIN$/CONOUT$` en Windows o
`/dev/tty` en POSIX. Exige consola interactiva; no acepta stdin desde pipe ni
guarda respuestas para revisión posterior. Muestra datos sintéticos, `answer`,
`proposal_text`, tools observadas y criterios, escapando secuencias de control.
El humano escribe `pass`, `fail` o `not_evaluated` por criterio; vacío/EOF para.
Ahora también admite `p/f/x`, mayúsculas y espacios; una entrada desconocida
repregunta sin inferencia adicional. `--check-console` permite verificar TTY
con texto fijo sin key, red, reserva ni concesión de aprobación.
Reporte guarda solo índice/label, método `human_console_v1` y checks técnicos.

No es un juez LLM calibrado ni baseline T8; no reemplaza los checks técnicos por
opinión. El criterio sobre bloque final del Core no se certifica con este harness:
la revisión debe limitarse a la partición del Agent y cruzar la evidencia E2E
de specs/036; no afirmar que el harness aislado entrega botones reales.
No grabar la terminal (transcript, screen recorder o logging externo): la app
no puede impedir capturas externas. Si no hay revisor presente, **no ejecutar**.

### Pasos del operador: solo después de aprobar el ensayo

1. Revisar y comitear el incremento; volver a ejecutar gates/checks para ese SHA.
   No hace falta redeploy del bot. El lanzador rechaza árbol sucio.
   En imagen eval, contrastar SHA/huella sellados con checkout limpio y CI externo;
   `identity_source=sealed_image` no demuestra por sí mismo procedencia Git.
2. Ejecutar **sin `--execute`** usando rutas absolutas:

   ```powershell
   $root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
   python "$root\scripts\execute_eval_campaign.py" `
     --snapshot "$root\evals\response_style\runtime-rev8-snapshot.json" `
     --plan "$root\evals\response_style\bl48-campaign-plan.json"
   ```

3. Revisar su metadata y aprobar **esos** plan/SHA/source/cases fingerprints.
   Los valores previos al commit no son aprobación reutilizable. Plan y snapshot
   candidatos sin cambios respecto a los hashes indicados arriba.
4. Disponer de acceso privado autorizado y clave r4 exclusiva. El script existente
   `scripts/litellm_create_virtual_key.py` **no sirve sin cambios para esta clave**:
   incluye aliases base adicionales y escribe la clave a stdout. No ejecutarlo
   para esta campaña ni reutilizar la clave del bot.
5. Configurar secretos fuera del chat/Git/argv: `ANCORA_EVAL_GATEWAY_URL` y
   `ANCORA_EVAL_GATEWAY_KEY`. Primero `eval_preflight.py ... --check-gateway` sin
   inferencia, una vez autorizado ese acceso. Este ensayo tampoco crea la clave.
6. Tras autorización y comprobación externa configurar en la misma terminal:
   `ANCORA_EVAL_APPROVED_PLAN`, `ANCORA_EVAL_APPROVED_SHA`,
   `ANCORA_EVAL_APPROVED_SOURCE`, `ANCORA_EVAL_APPROVED_CASES` con los valores del
   preflight y los cuatro flags siguientes a `1` **solo si son ciertos**:
   `ANCORA_EVAL_SYNTHETIC_APPROVED`, `ANCORA_EVAL_EXTERNAL_BUDGET_VERIFIED`,
   `ANCORA_EVAL_SNAPSHOT_PROVENANCE_ACCEPTED`, `ANCORA_EVAL_HUMAN_REVIEW_APPROVED`.
   Los flags no sustituyen verificación del proveedor, aprobación humana ni CI.
7. Con revisor presente ejecutar el mismo comando añadiendo `--execute`; revisar
   los cinco casos sin otras operaciones en la ventana. Ante parada no relanzar.
   Después inspeccionar el reporte metadata-only y registrar resultado, incluido
   parcial/not_evaluated; BL-48 solo cierra si cumple todos sus gates.

Reserva estimada aceptada y propietario dispuesto a revisar. Pendientes:
procedencia del snapshot, plan/ruta/cinco casos ligados al SHA y huellas vigentes,
autorización de recursos/acceso privado/clave exclusiva, límites externos
verificados y sesión interactiva acordada. No se pide pegar secretos. Hasta
entonces: `gateway_access=not_checked`, sin inferencia. La aceptación del enfoque
incremental no sustituye estas aprobaciones.