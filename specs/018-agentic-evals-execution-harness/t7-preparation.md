# T7 — Preparación del harness real aislado (2026-10-16)

**Autorizado:** preparar wiring/ruta/presupuesto/acceso seguro. **No autorizado
todavía:** ejecutar inferencia pagada con el candidato, crear claves o túneles,
exponer Gateway, mutar configuración/revisiones o desplegar. BL-48 permanece
abierto hasta resultados reales; no se sustituye por la matriz manual Telegram.

## Incremento implementado

- `src/agent/eval_campaign.py`: candidato validado, aprobación ligada al checksum
  del plan, únicamente `LLMAccess` con Gateway, configuración separada sin .env,
  credenciales ambiente ni DB. `EvalUsageRecorder` solo guarda metadata en memoria.
- Executor físico acepta snapshot/budget explícitos, revisa identidad de revisión,
  rechaza expansión de límites y arma deadline. Se envía max_tokens al SDK.
- `scripts/eval_preflight.py`: carga/valida snapshot y plan sin modelos/red. La
  opción explícita `--check-gateway` realiza solo GET `/v1/models`, sin seguir
  redirects, y exige que la clave vea exactamente el alias previsto.
- No hay aún CLI de ejecución pagada ni juez semántico/calibración humana; el
  constructor de executor no ejecuta nada. No añadir esto indirectamente a CI.

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
2. Escoger ejecución en entorno privado autorizado o túnel loopback administrado
   por el operador hacia el Gateway existente. No dominio público ni provider
   directo. La CLI Railway no está instalada en este entorno; no se instala ni
   aprovisiona acceso automáticamente.
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
   del presupuesto**. La implementación de ejecución deberá parar ante fallo,
   no relanzar casos, conservar uso metadata-only y reservar el total antes de
   comenzar. Faltan ejecución/criterios semánticos y revisión humana/juez.

## Hallazgo de checksum — no reescribir historia

El checksum canónico recalculado para rev. 8 cambia entre procesos porque
`capabilities` es frozenset y `canonical_config_json` no ordena sus elementos.
Además, el hash almacenado no se reprodujo con el contenido/código actuales.
**No está probado que el orden de sets explique la discrepancia histórica**.
No se cambia el algoritmo productivo, una revisión existente ni se atribuye
el fingerprint de eval al control plane. El fingerprint de eval ordena capacidades
y liga toda la estructura tipada (incluidos revisión y checksum histórico) al plan
aprobado, por lo que un cambio de contenido requiere otra aprobación.
Queda investigación de compatibilidad/esquema histórico en BL-23/specs/013.

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