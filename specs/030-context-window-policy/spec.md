# specs/030 — Política de contexto por tokens y compactación gobernada (BL-34)

> **Status:** diseño + implementación de la política pura (sin generación
> real de compactación todavía — ver §7 alcance).

## 1. Problema

`GovernedAgentFactory.create_for_run()` (`src/agent/governed_agent_factory.py`)
fija `num_history_runs=10` como constante, igual que el agente legado
(`create_ancora_agent()` en `src/agent/ancora_agent.py`). Ese número acota
**turnos**, no **tamaño real**: diez respuestas largas pueden agotar la
ventana de un modelo pequeño (p. ej. una ruta `ancoramind-fast` barata) y,
simétricamente, desperdician ventana disponible en un modelo grande. No existe
hoy ninguna señal de cuántos tokens ocupa el historial que Agno va a inyectar
en el próximo turno antes de llamarlo.

## 2. Alcance de este incremento

Diseño y política **pura** (sin I/O, testeable con historiales sintéticos),
más su wiring en `GovernedAgentFactory` para sustituir el `num_history_runs`
fijo por un valor derivado de la ventana efectiva de la ruta y el budget del
run. La **generación real de un resumen compactado vía LLM** queda fuera de
este incremento (§7) — se decide la señal/estructura para activarla después,
pero no se activa aquí.

### No-objetivos (explícitos)

- No se sustituye ni se compite con BL-13/Dream (specs/029): Dream aprende
  preferencias duraderas con su propio pipeline; esta política sólo mantiene
  la conversación dentro de la ventana del modelo turno a turno.
- No se añade ningún tokenizer físico por proveedor (`tiktoken` u otro): se
  usa una heurística determinista y documentada como aproximación.
- No se activa compactación real por LLM en este incremento — solo se deja
  preparado el contrato (interfaz) para una ruta lógica futura.
- No se toca `agno_runtime`/retención de sesiones (mencionado en el backlog
  como pendiente, pero es un ítem operativo separado, no de este spec).

## 3. Estimación de tokens (heurística, sin I/O)

Reutiliza el mismo criterio ya usado en producción en
`src/agent/governed_model.py::_messages_char_count` /
`_APPROX_CHARS_PER_TOKEN = 4`: aproximar tokens como
`len(texto) // 4`. No es exacta por proveedor/modelo, pero es la misma
aproximación que ya gobierna la estimación de coste (`_estimate_call_cost`),
así que no introduce una segunda heurística incoherente con la existente.

`src/domain/context_policy/models.py` expone:

```python
def estimate_tokens(text: str) -> int:
    """Deterministic, provider-agnostic approximation: len(text) // 4."""
```

Documentado explícitamente como límite conocido en §8.

## 4. Ventana efectiva por ruta

`RoutingConfig`/`LogicalRoute` (`src/domain/runtime_config/models.py`) no
declara hoy ninguna ventana de contexto. Se añade un campo opcional:

```python
class LogicalRoute(RuntimeConfigModel):
    effective_gateway_route: str
    capabilities: frozenset[...]
    context_window_tokens: int | None = Field(default=None, ge=1024, le=2_000_000)
```

- `None` → la política cae a un valor conservador por defecto (§5) en vez de
  fallar: una ruta existente sin este campo no debe romper runtime-config ya
  persistido (compatibilidad aditiva, mismo criterio que `speech` opcional).
- `bootstrap_runtime_configuration()` fija valores explícitos para las rutas
  conocidas (`ancoramind-default`, `ancoramind-fast`, `ancoramind-vision`,
  `ancoramind-dream`); `ancoramind-embeddings` no lo necesita (no es una ruta
  de chat) y se deja en `None`.
- Es un campo aditivo en un modelo `frozen`/`extra="forbid"`: no rompe el
  checksum de revisiones ya persistidas con el campo ausente (mismo patrón de
  compatibilidad ya usado por `speech`, ver `canonical_config_json`).

## 5. Política (`src/domain/context_policy/`)

### 5.1 `ContextBudgetConfig` — reservas explícitas

```python
class ContextBudgetConfig(RuntimeConfigModel):
    """Reserved slices of the effective window, as absolute token counts."""
    reserved_for_instructions_tokens: int = Field(ge=0)
    reserved_for_current_message_tokens: int = Field(ge=0)
    reserved_for_tools_schema_tokens: int = Field(ge=0)
    safety_margin_tokens: int = Field(ge=0)
```

Presupuesto disponible para historial:

```
available_for_history = max(
    0,
    context_window_tokens
    - reserved_for_instructions_tokens
    - reserved_for_current_message_tokens
    - reserved_for_tools_schema_tokens
    - max_output_tokens  # ya existe en ExecutionBudgetConfig
    - safety_margin_tokens,
)
```

Valor por defecto cuando `context_window_tokens` es `None`: una ventana
conservadora fija (p. ej. 8192 tokens) documentada como "modelo desconocido,
asumir ventana pequeña" — nunca asumir una ventana grande por defecto (fail
closed hacia el lado seguro: truncar de más, no desbordar al proveedor).

### 5.2 Selección de historial — `select_history_window(...)`

Entrada: lista ordenada (más reciente al final) de turnos pasados, cada uno
con un tamaño ya estimado (`estimate_tokens` aplicado por el caller al texto
real del turno — la política no conoce el contenido, solo tamaños y un
identificador opaco de turno, para no mezclar PII en el dominio puro).

Salida (`ContextWindowDecision`):

```python
@dataclass(frozen=True)
class ContextWindowDecision:
    kept_turn_ids: tuple[str, ...]       # most recent turns that fit, oldest→newest
    turns_to_compact: tuple[str, ...]    # older turns that don't fit (may be empty)
    outcome: Literal["fits_entirely", "truncated", "needs_compaction"]
    available_for_history_tokens: int
    kept_tokens: int
```

Algoritmo: recorrer el historial desde el más reciente hacia atrás,
acumulando tamaño; cuando el siguiente turno (más antiguo) no cabe:
- si `turns_to_compact` queda vacío → `outcome="fits_entirely"`.
- si no vacío y existe una política de compactación configurada (§7, aún no
  activada) → `outcome="needs_compaction"`.
- si no hay compactación activada → `outcome="truncated"` (los turnos que no
  caben se descartan sin más: degradación determinista, sin reintentos).

### 5.3 Traducción a `num_history_runs`

`GovernedAgentFactory` sigue pasando un entero a Agno (no hay forma de pasarle
"estos turnos exactos" sin reemplazar su gestión de historial — fuera de
alcance). Se traduce la decisión a un entero acotado:

```python
def resolve_num_history_runs(decision, *, floor: int = 1, ceiling: int = 10) -> int:
    """len(kept_turn_ids) clamped to [floor, ceiling]; never below floor."""
```

`ceiling=10` preserva el límite actual como techo (nunca se agranda la
ventana de golpe más allá de lo ya aprobado); `floor=1` garantiza que el turno
inmediatamente anterior nunca se pierde salvo que ni siquiera él quepa (caso
degenerado: mensaje actual ya consume casi todo el presupuesto).


## 6. Wiring en `GovernedAgentFactory`

`create_for_run()` hoy no sabe cuántos turnos previos existen ni su tamaño:
Agno gestiona `AgentSession`/`db` internamente. Dos opciones evaluadas:

1. **Consultar el tamaño del historial antes de crear el `Agent`** (leer la
   sesión desde `db` para contar/estimar los últimos N turnos) y pasar el
   `num_history_runs` ya resuelto.
2. Dejar que Agno siga gestionando el historial, y solo variar el **techo**
   (`ceiling`) pasado a `resolve_num_history_runs` según la ventana de la
   ruta — sin leer la sesión real.

**Decisión:** opción 2 para este incremento. Leer la sesión completa de Agno
antes de construir el `Agent` añade una consulta a `db` en el camino crítico
de cada run y acopla `GovernedAgentFactory` a la estructura interna de la
tabla de sesiones de Agno (lo que el principio §2.1 de AGENTS.md ya reserva
exclusivamente a infraestructura reemplazable, con cuidado de no convertirlo
en una dependencia del dominio). Variar el techo según
`available_for_history_tokens / assumed_tokens_per_turn` (una estimación
conservadora de tamaño medio de turno, documentada como aproximación) ya
captura el caso que motiva BL-34 — modelos pequeños obtienen un techo menor,
modelos grandes uno mayor — sin leer el historial real. Leer la sesión real
para una poda turno-a-turno exacta queda como extensión futura explícita si
la aproximación por techo resulta insuficiente en el E2E.

```python
# GovernedAgentFactory.create_for_run()
ceiling = resolve_history_ceiling(
    context_window_tokens=route.context_window_tokens,
    execution_budget=snapshot.config.execution_budget,
    context_budget=snapshot.config.context_budget,  # nuevo bloque opcional
)
return Agent(..., num_history_runs=ceiling, ...)
```

`context_budget` es un nuevo bloque opcional en `RuntimeConfiguration`
(`context_budget: ContextBudgetConfig | None = None`), con default seguro
cuando es `None` (mismos valores que el bootstrap, ver tasks.md T2).

## 7. Compactación real — diferida explícitamente

Cuando `outcome="needs_compaction"`, este incremento **no** genera un resumen
real. Se deja preparado el contrato (`CompactionPort`, Protocol en
`src/domain/context_policy/compaction.py`) análogo a `DocumentExtractionPort`,
para una implementación futura que:

- Pase por `LLMAccess`, con una ruta lógica propia (candidata:
  `ancoramind-context-compaction`, o reutilizar `ancoramind-fast` — a decidir
  en el incremento que la active).
- Produzca un checkpoint versionado, reemplazable y acotado, ligado al rango
  de turnos que resume (`compacted_from_turn_id`, `compacted_to_turn_id`).
- Nunca sea tratado como memoria personal ni canónica (no persiste en
  `ancora.*`; vive sólo mientras dure la sesión conversacional, igual que el
  propio historial de Agno).
- Si falla o excede budget → degradar a `outcome="truncated"` sin reintentos
  (mismo principio de `retries=0` ya aplicado en todo el repo).

En este incremento, cuando `outcome="needs_compaction"` y no hay
`CompactionPort` configurado (el caso por defecto), la política degrada
automáticamente a `outcome="truncated"` — el contrato queda definido pero sin
implementación física conectada.

## 8. Limitaciones conocidas

- **Estimación de tokens por heurística de caracteres**, no por tokenizer
  real del proveedor — puede sub/sobre-estimar según idioma y modelo. Se
  acepta porque ya es el mismo criterio usado para estimar coste
  (`governed_model.py`); una mejora futura exigiría tokenizers por proveedor,
  fuera de alcance.
- **El techo de turnos no lee el historial real** (§6): es una aproximación
  por tamaño medio de turno, no una poda exacta turno a turno. Si el E2E
  revela que modelos pequeños siguen desbordando con el techo aproximado, se
  reconsiderará leer la sesión real como extensión.
- **Compactación real no implementada** (§7): el contrato existe, la
  generación no. `needs_compaction` siempre degrada a `truncated` hasta que
  se active un `CompactionPort` concreto.
- **Retención/purga de `agno_runtime`**: mencionada en el backlog original de
  BL-34 pero es un ítem operativo (housekeeping de la tabla de sesiones de
  Agno), no parte de la política de contexto en sí; se registra como
  pendiente separado en BACKLOG.md al cerrar este spec.

## 9. Observabilidad

Nuevo atributo metadata-only en el allowlist de
`src/observability/telemetry.py` (`SPAN_ATTRIBUTE_ALLOWLIST` +
`METRIC_ATTRIBUTE_ALLOWLIST`): `ancora.context.outcome` ∈
`{fits_entirely, truncated, needs_compaction}`. Sin contenido, sin tamaños
exactos de texto (solo el enum de resultado) — mismo criterio que
`ancora.document.extraction_route` (specs/021 T7).

## 10. Criterios de cierre

1. `select_history_window`/`resolve_num_history_runs`/`estimate_tokens` con
   cobertura unitaria: historial que cabe entero, historial que requiere
   truncado, mensaje actual que ya consume casi todo el presupuesto, cambio
   de ruta/modelo (ventana distinta) entre runs, turno individual más grande
   que todo el presupuesto disponible.
2. `GovernedAgentFactory.create_for_run()` usa el techo calculado en vez de
   `10` fijo; test de regresión que verifica que una ruta con ventana grande
   obtiene un techo mayor que una con ventana pequeña, dentro de `[1, 10]`.
3. `context_window_tokens`/`context_budget` aditivos: una
   `RuntimeConfiguration` persistida sin esos campos sigue validando y su
   checksum histórico no cambia (test de regresión de compatibilidad).
4. Ausencia de contenido personal en el nuevo atributo de telemetría (test de
   privacidad, mismo patrón que `test_observability_privacy.py`).
5. `pytest tests/unit/`, `ruff check src/ tests/ scripts/ migrations/` y
   `mypy src/` en verde. Sin necesidad de PostgreSQL/Docker — todo el
   incremento es dominio puro + wiring testeado con mocks.
6. BACKLOG.md BL-34 actualizado referenciando este spec; housekeeping de
   `agno_runtime` (§8) registrado como pendiente separado si no se aborda
   aquí.

