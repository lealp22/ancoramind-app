# ADR-005 — Acceso LLM gobernado, configuración runtime y LiteLLM

> **Status:** Accepted (diseño aprobado 2026-09-13; implementación pendiente —
> specs/013, BL-23)
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
| YAML/TOML como source of truth de producción | Hot reload y coordinación pobres en Railway |
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
