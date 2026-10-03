# ADR-005 — Acceso LLM gobernado, configuración runtime y LiteLLM

> **Status:** Accepted — implementado localmente (T2–T14, diseño aprobado
> 2026-09-13); rollout Railway completo y Collector/Grafana pendientes —
> specs/013/verification.md, BL-23. **Enmendado 2026-09-18** (ver §Enmienda):
> fuente de verdad de las definiciones de modelo y publicación aditiva de aliases.
> **Contexto:** provider/model físicos están acoplados hoy al Agent y a variables
> de startup; un cambio de modelo en Railway requiere deployment.

---

## Contexto

AncoraMind crea un modelo físico de Agno al arrancar y lo asigna a un Agent
singleton. La extracción documental crea otro Agent directamente. No existe una
capability transversal que aplique configuración versionada, budget, coste,
correlación, retries o circuit breaker a todas las inferencias.

El diseño debe mantener Agno como infraestructura reemplazable y permitir
cambiar rutas/modelos sin redeploy, sin consultar PostgreSQL o disco en cada
model turn y sin almacenar secrets en configuración editable.

## Decisión

1. **Frontera `LLMAccess`** — toda inferencia pasa por una abstracción propia que
   exige `ExecutionContext`, aplica budget y emite telemetry.
2. **Agent por run** — cada ejecución captura un `RuntimeConfigSnapshot`
   inmutable y crea un Agent con ruta versionada; no se muta un singleton a
   mitad de run.
3. **Rutas lógicas** — AncoraMind solicita aliases como
   `ancoramind-default-r<N>`, `ancoramind-fast-r<N>` y
   `ancoramind-vision-r<N>`; provider/model físicos se resuelven en el Gateway.
4. **LiteLLM Proxy** — target de Gateway como servicio privado Railway, con DB
   PostgreSQL dedicada e imagen fijada.
5. **OpenRouter** — upstream de LiteLLM; conserva su fallback interno entre
   providers.
6. **Fail closed** — cuando LiteLLM sea obligatorio, su caída no activa bypass
   directo a OpenRouter.
7. **Config neutral** — PostgreSQL de AncoraMind conserva revisiones tipadas y
   portables; la DB de LiteLLM contiene estado operacional sustituible.
8. **Cache en memoria** — `RuntimeConfigManager.snapshot()` no hace I/O.
9. **Activación atómica** — draft, validación, publicación del alias Gateway,
   healthcheck y compare-and-swap del active pointer. Last-known-good permanece
   ante error.
10. **Invalidación** — swap directo con una réplica; evolución a
    `LISTEN/NOTIFY` más reconciliación lenta.
11. **Control plane** — API administrativa protegida, scripts HTTP iniciales y
    CLI posterior. Nunca se expone como tool del LLM.
12. **Secrets** — API keys, master/virtual keys y credenciales permanecen en
    Railway environment.
13. **Reliability inicial** — retries de Agent, Model y LiteLLM a 0; fallback
    cross-model LiteLLM a 0; cooldown del Gateway y fallback interno OpenRouter.
14. **Budget inicial** — 120 s, 6 model calls, 12 tools hard ceiling, 8 requests
    Gateway y 2 attempts por model call.

## Enmienda (2026-09-18) — definiciones de modelo y publicación aditiva

### Motivo

El punto 9 de la decisión ("publicación del alias Gateway") y §11 de
`design.md` describen una publicación en dos fases que **no se llegó a
implementar**: `RuntimeConfigManager.activate()` sólo realiza el CAS en
PostgreSQL y nunca publica nada en el Gateway. Como consecuencia, el cambio de
modelo físico seguía exigiendo editar `gateway/litellm-config.yaml` y redesplegar
LiteLLM, lo que contradice el criterio de cierre de BL-23 ("el modelo cambia sin
redeploy").

Además, el 2026-09-18 el pilot cambió `gpt-5.4-mini` → `gpt-5.6-luna` editando
en sitio el alias `ancoramind-default-r1`. Eso viola el punto 3 (`design.md`
§11: "los aliases versionados no se mutan mientras puedan estar en uso") y rompe
la trazabilidad: filas de `llm_usage_events` con
`effective_gateway_route = ancoramind-default-r1` pueden corresponder a dos
modelos físicos distintos según la fecha. Queda registrado como desviación del
pilot, tolerada sólo por su carácter no productivo.

### Decisiones

15. **Fuente de verdad aditiva de definiciones de modelo.**
    `gateway/litellm-config.yaml` declara los aliases **base** (`*-r1`) y es la
    referencia revisable en Git. Con `store_model_in_db: true` la base de datos
    del Gateway puede **únicamente añadir** aliases versionados nuevos (`r2`,
    `r3`, …). Nunca se edita ni se borra un alias base o en uso: un cambio de
    modelo físico se expresa publicando un alias nuevo y activando una revisión
    de runtime config que apunte a él.
16. **Publicación por script de operador.**
    La publicación la ejecuta `scripts/litellm_gateway_alias.py` con
    `LITELLM_MASTER_KEY`. AncoraMind **nunca** posee la master key del Gateway:
    sólo la virtual key restringida a los aliases vigentes. La publicación no se
    expone como tool, endpoint público ni capability del LLM.
17. **Uso restringido a `/model/*`.**
    Queda prohibido escribir settings (`general_settings`, `router_settings`,
    `litellm_settings`) por API o Admin UI: LiteLLM los persiste en
    `LiteLLM_Config` y **sobrescriben** el `config.yaml` en el siguiente
    arranque, anulando en silencio la política aprobada de circuit breaker,
    retries y fallbacks.
18. **Precedencia del yaml para settings, de la DB sólo para modelos.**
    Los settings de infraestructura y política siguen viviendo exclusivamente en
    `gateway/litellm-config.yaml`. La DB del Gateway no es fuente de verdad del
    producto (ver §Portabilidad): se puede reconstruir publicando de nuevo los
    aliases desde cero.

### Consecuencias

- Un cambio de modelo deja de requerir redeploy: publicar alias → `grant` a la
  virtual key → activar revisión CAS → verificar inferencia.
- El `grant` es **aditivo** (mantiene los aliases previos) para que el rollback a
  un alias anterior no dependa de volver a tocar la key.
- Sigue existiendo una única fuente de verdad por ámbito: yaml para settings y
  aliases base; DB sólo para aliases incrementales.
- Coste: un flag más en el Gateway, un script de operador y la política de
  limpieza de aliases antiguos.

## Portabilidad de la DB LiteLLM

La DB dedicada puede almacenar virtual keys, spend logs, deployments y estado
de cooldown/circuit, pero no es fuente de verdad del producto. Si LiteLLM se
sustituye:

- rutas, policies y budgets se regeneran desde la config neutral de AncoraMind;
- las nuevas credenciales se crean en el Gateway sustituto;
- spend logs se exportan o conservan read-only durante su retención;
- circuit/cooldown se descarta como estado efímero;
- no se migra ninguna tabla del schema `ancora`.

## Consecuencias

### Positivas

- El Agent deja de depender de provider/model físicos.
- Cambios de ruta afectan a nuevas ejecuciones sin redeploy.
- Todo acceso LLM comparte budget, coste, correlación y políticas.
- La configuración de AncoraMind permanece portable si cambia el Gateway.
- LiteLLM centraliza virtual keys, rate limits, spend y circuit/cooldown.

### Negativas

- Nuevo servicio, DB y hop de red.
- No existe una transacción distribuida entre ambos control planes.
- Se necesita un proceso de publicación en dos fases y limpieza de aliases
  antiguos.
- La latencia y superficie de seguridad de LiteLLM deben medirse/revisarse.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Modelo físico dentro del Agent | Acoplamiento y redeploy por cambio |
| YAML/TOML como única source of truth de producción | Sin vía runtime el cambio de modelo exige redeploy; el pilot lo demostró (BL-23 pendiente) |
| PostgreSQL consultado por request/model turn | Latencia e I/O innecesarios |
| LiteLLM SDK in-process | No crea una frontera central ni aislamiento operativo |
| Config solo en la DB de LiteLLM | Lock-in y mezcla de policies de producto/infraestructura |
| Alias mutable | Un run podría cambiar de modelo a mitad |
| Bypass directo al caer el Gateway | Evita budgets, rate limits y auditoría |
| Retries simultáneos en Agno/LiteLLM/OpenRouter | Amplificación multiplicativa |

## Re-evaluación

Reabrir si el benchmark muestra overhead inaceptable, LiteLLM bloquea un
requisito confirmado, sus capacidades necesarias dejan de estar disponibles en
la edición elegida o un Gateway alternativo ofrece una ventaja demostrable con
menor riesgo operacional.
