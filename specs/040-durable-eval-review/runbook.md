# Operación reutilizable — preparada localmente, no desplegada

## Preparación única por el propietario

No ejecutar los comandos nuevos sobre la imagen histórica db0c59b: no los contiene.
Commit/CI y despliegue aislado del nuevo candidato pendientes. Usar paquete eval
explícito, no rebuild GitHub con selector conocido incorrecto. No redesplegar bot.
Guardar sólo en eval service los secretos, con política aprobada del propietario:

- `ANCORA_EVAL_GATEWAY_URL`: URL privada terminada `/v1`.
- `ANCORA_EVAL_GATEWAY_KEY`: clave **reutilizable exclusiva de eval**, modelo r4,
  caducidad propuesta7 días, concur1, sólo chat completions/models/info, sin reset
  automático de presupuesto. Helper acepta max_budget finito <=1 USD, pero esto
  **no autoriza 1 USD**: fijar el importe expresamente acordado, suficiente para
  campaña0,10 además del gasto acumulado. Si se agota, para; no resetea/crea otra.
  RPM/TPM acotados en Gateway; no copiar clave bot/upstream ni master al evaluador.
- `ANCORA_EVAL_EVIDENCE_KEY`: Fernet distinta del bot, almacenada como secreto;
  no dentro del volumen de evidencia ni Git. Perderla impide descifrar artefactos.
- `ANCORA_EVAL_STATE_DIR=/eval-state`, volumen exclusivo persistente real,
  `ANCORA_EVAL_REQUIRE_VOLUME=1`. Un mount no garantiza backups ni alta disponibilidad.
- `ANCORA_EVAL_APPROVAL_FILE=/eval-state/approval.json`: decisión no secreta del
  propietario para **SHA/huellas/casos/plan nuevos**, sintético, riesgos/snapshot
  aceptados. Clave existente no concede aprobación. No reutilizar firma/sello viejos.

No se han generado estas claves ni configurado variables remotas por este cambio.
La nueva clave/budget/7d se acuerdan antes del setup; no revocar/create cada ensayo.
Una misma campaña/candidato no se repite por cambiar token: se conserva anti-replay.

Approval file: objeto con `evidence_synthetic_approved: true` y `gates` con **sólo**
los ocho campos ya usados por `validate_live_approval`: APPROVED_PLAN/SHA/SOURCE/
CASES, SYNTHETIC_APPROVED, EXTERNAL_BUDGET_VERIFIED, SNAPSHOT_PROVENANCE_ACCEPTED,
HUMAN_REVIEW_APPROVED (todos prefijados `ANCORA_EVAL_`). No secretos en ese archivo;
valores exactos aprobados del nuevo preflight, no placeholders convertidos en permisos.
Mantener este archivo por candidato elimina exports manuales en cada terminal.

## Uso habitual (shell Linux del evaluador ya configurado)

```sh
python /app/scripts/eval_console.py run
```

Genera ID y muestra reporte metadata `worker_launched`, arranca un worker
desacoplado de SSH (mismo contenedor, sin servicio/cron/puerto adicional) y abre
revisión. El worker consulta clave dedicada/scope/saldo existente sin mutarlo,
reserva antes de red/modelo y usa el motor/LLMAccess existente. Antes de pedir
valoración se guarda la evidencia cifrada. Cada criterio se guarda al marcarlo.

- `p`: criterio cumple; sólo todos pass permiten siguiente caso.
- `f`: no cumple; detiene inferencias siguientes.
- `x` o línea vacía: no evaluado; detiene inferencias siguientes.
- **EOF/corte de revisión**: no se inventa etiqueta. Respuesta/criterios anteriores
  quedan guardados; worker espera como máximo2h una decisión recuperable, sin
  inferencia nueva mientras espera. Tras timeout se detiene; nunca auto-restart.

Revisar la **misma respuesta** sin pagar otra inferencia:

```sh
python /app/scripts/eval_console.py list
python /app/scripts/eval_console.py review --run ID --reviewer owner
python /app/scripts/eval_console.py status --run ID
```

`ID` es el run_id obtenido. Abrir/cerrar/revisar/listar no ejecuta modelo. Dentro
de la misma ejecución aprobada, si el worker sigue vivo y todos los criterios se
guardan como pass, puede continuar al siguiente caso autorizado. No reanuda una
inferencia interrumpida. Si muere worker/contenedor: sólo revisar evidencia existente,
estado incierto/sin replay. PID/probe no es identificación infalible de procesos;
no borrar .lock por fallo sin inspeccionar que no existe escritor activo. No hay
lease distribuido ni recovery automático de lock huérfano.

Corregir una etiqueta conservando la anterior y un motivo:

```sh
python /app/scripts/eval_console.py label --run ID --case response_style.single_proposal --criterion 0 --label fail --reviewer owner --comment 'Falta evidencia del campo solicitado'
```

Usar `--comment` sólo para notas sintéticas, nunca secretos/datos personales;
puede quedar en shell history del operador aunque artefacto esté cifrado.
Las correcciones **no restauran permiso de inferencia** tras un fail/x, ni cambian
el resultado técnico histórico. No genera consentimientos del bot.

## Qué ve el revisor

Español Unicode legible, pero controles de terminal/bidi/format escapados; datos
siguen entre comillas, sin interpretar como instrucciones/controles de consola.
Se muestra petición, contexto, answer/proposal_text, trace de tools sintéticas,
propuestas creadas/seeded con sus payloads reales, y presentación Core simulada.
Se reutiliza renderer puro `render_proposal_block`, no se invoca Telegram ni se
promete TTL real de esos botones en eval. Para TODO se valida estructura mediante
modelo domain antes de crear; se comprueba existencia reviewable real del store.
Título/semántica/fecha **solicitada** siguen requiriendo juicio humano: no parser
de lenguaje natural escondido ni campos rellenados desde el input.

Lo que guardó store muestra lo que pidió el modelo, no lo que debería haber
pedido; un nombre `propose_*` por sí solo ya no certifica propuesta. La cobertura
completa de entrega Telegram/consentimiento/BD se prueba aparte. El primer caso
histórico no tenía esos hechos; no reconstruirlo ni declarar pass retrospectivo.

## Golden set: dos destinos distintos

Archivo de runs y revisiones NO es golden automáticamente. Completar cada criterio
con pass/fail y aceptar manualmente sintético/sanitizado antes de promover:

```sh
python /app/scripts/eval_console.py promote --run ID --case response_style.single_proposal --dataset agent --split development --reviewer owner --sanitized-approved
python /app/scripts/eval_console.py promote --run ID --case response_style.single_proposal --dataset judge --split validation --reviewer owner --sanitized-approved
```

Son destinos distintos: Agent guarda caso/input/contexto/expectativas, no imita una
respuesta literal; juez guarda respuesta observada, criterios/labels y hechos de
presentación. Negative fail también sirve para calibrar juez. `not_evaluated` o
review parcial no puede promoverse. Corrección etiqueta genera otra versión por
contenido, mantiene run/revisiones y evita duplicar el mismo ejemplo entre
development/validation del mismo destino. No es detección semántica universal de
fugas por paráfrasis. Golden curado se conserva explícitamente fuera de la retención
7d de evidencia bruta; no selección automática, juez pagado o entrenamiento.

Export explícito a fichero nuevo absoluto, nunca stdout:

```sh
python /app/scripts/eval_console.py export --version HASH --output /eval-state/selected-example.json --sanitized-approved
```

Salida contiene `fixture` compatible con catálogo Agent o calibración
human_reviewed del juez existente, más provenance. Seleccionar sólo `fixture` al
añadir al catálogo y mantener provenance junto a ella; revisar antes de Git.
Compatibilidad de formato **no** equivale a cobertura del juez: su puerto actual
recibe sólo reply/criterio, no propuesta/trace/Core. El export juez advierte
`current_reply_only_judge_port_sufficient=false`; para criterios que dependen de
esos hechos se debe extender el contrato del juez o seleccionar criterios sólo
textuales en un incremento aparte. No calibrar automáticamente con el fixture
sin esa decisión ni perder el contenido enriquecido del artefacto curado.
No exportar en ruta pública/logs ni secretos. Export no admite overwrite.

## Archivo y retención

`/eval-state/private-evidence/`: manifest/casos/snapshot, eventos de evidencia,
review por criterio, checkpoints, correcciones y promociones; todo cifrado Fernet.
Head cifrado enlaza secuencia/hashes; detecta truncado/corrupción normal. No firma
externa: alguien con clave y control del volumen puede reescribir historia; un
rollback conjunto de eventos/head no se detecta con anclaje externo inexistente.
Archivos eventos exclusivos, publish atómico/link+fsync, locks por operación.
No reutilizar secreto Fernet en otro servicio; permisos POSIX600/700 y protección
del volumen; ACL Windows las gestiona el operador (chmod no es ACL Windows).

Tras7d deja de permitir revisión/promoción del material bruto. Purga explícita:

```sh
python /app/scripts/eval_console.py purge --run ID
```

Elimina ciphertext bruto conservando tombstone/reserva anti-replay. No se instala
cron ni se promete borrado automático: operador debe ejecutar purga en mantenimiento
si quiere liberar bytes. Golden curado/export aprobado se conserva por decisión
explícita y requiere gestión de retención independiente. No datos personales de
usuarios Telegram/documents. Detector de secretos bloquea patrones conocidos,
**no sustituye** revisión de privacidad y fixtures sintéticas aprobadas.

## Antes de usar de verdad

- Corregir/esclarecer campaña interrumpida: conservar marker/report, etiquetas no
  dadas siguen no evaluadas; revocación anterior no confirmada no equivale a pasada.
- Cambia fingerprint de fuentes/modelado de tools de eval: commit/CI nuevos,
  aprobación de identidad nueva y despliegue exclusivo eval con coste/ventana
  acordados. Motor acepta nueva fuente aprobada sin borrar marca histórica del
  candidato previo, no permite replay de la misma fuente.
- Revisor actual es identificador operativo (por defecto owner), **no** login/
  autenticación multiusuario; autorización la proporciona la shell privada.
- No nueva inferencia ni credenciales generadas en la validación local de specs/040.