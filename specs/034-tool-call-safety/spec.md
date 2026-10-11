# BL-16 — Protección compartida de tool calls

> **Status:** Implementado y validado localmente; retirada upstream pendiente — 2026-10-11

## Contexto y decisión

El repro sintético con Agno 2.9.0 conserva llamadas vacías tanto en
`OpenRouter` como en `OpenAILike`; el primero añade UUID en no-streaming y
ambos consolidan deltas incompletos en streaming. `SafeOpenRouter` evita el
fallo original de specs/006, pero el Gateway usa `OpenAILike` sin ese filtro.
No se presume que LiteLLM emita hoy esas respuestas: se protege su frontera
OpenAI-compatible si las recibe.

La revisión del código upstream v3.1.2 encontró los mismos cuerpos de
`Model._populate_assistant_message`,
`Model._populate_assistant_message_from_stream_data` y
`OpenAIChat.parse_tool_calls` que en 2.9.0. No se ejecutó 3.1.2 ni se
autoriza migrar a 3.x. BL-16 permanece abierta hasta demostrar que el
runtime nativo elimina las llamadas incompletas antes de ejecutar/persistir.

Fuentes primarias revisadas:
- <https://github.com/agno-agi/agno/blob/v3.1.2/libs/agno/agno/models/base.py>
- <https://github.com/agno-agi/agno/blob/v3.1.2/libs/agno/agno/models/openai/chat.py>

## Alcance aprobado

- Compartir el filtro en un mixin de infraestructura en `ancora_agent.py`.
- Conservar `SafeOpenRouter` y añadir `SafeOpenAILike`, seleccionado por
  `resolve_model_parts` para `openai-like`, incluido LiteLLM privado.
- No alterar el adaptador `openai`, rutas, secretos, snapshots, budgets,
  auditoría, política de consentimiento o retries (siempre cero gobernados).
- No añadir dependencias, prompts, migraciones ni llamadas remotas de inferencia.

## Contrato

1. Una entrada estructuralmente válida tiene `type='function'`, `function`
   diccionario y `name` string no vacío ni compuesto solo de espacios.
   Las demás entradas se descartan. No se validan JSON ni argumentos de
   negocio aquí: siguen siendo responsabilidad de Agno y del Core.
2. IDs ausentes en llamadas válidas siguen siendo completados por Agno;
   orden, nombre y argumentos de las llamadas válidas se conservan.
3. No-streaming: filtrar antes de poblar el mensaje. Admitir `[]` y `None`
   y normalizar la ausencia de llamadas a `None` para terminar el loop.
4. Streaming: nunca filtrar deltas individuales; consolidar primero con
   Agno y filtrar el mensaje antes de ejecutar/persistir. Un delta parcial
   que acaba en una llamada válida no se pierde.
5. Los warnings contienen solo recuento y metadata del adaptador/modelo,
   nunca contenido, nombres de tools ni argumentos de las llamadas.
6. `GovernedModelMixin` permanece primero en el MRO; la protección no
   habilita los caminos sync/streaming prohibidos ni omite reservas/auditoría.

## Criterios de aceptación

- Regresiones originales verdes en ambos adaptadores (sync y streaming).
- Pruebas adversariales de forma, ausencia de llamadas, IDs omitidos,
  preservación exacta de llamadas válidas y consolidación de deltas.
- Modelo real compuesto por `AgnoLLMAccess` probado con transporte simulado:
  solo llamadas vacías no ejecutan tool ni provocan otro turno; una válida
  junto a vacías se ejecuta una vez y el turno siguiente recibe historial limpio.
- Budget y usage mantienen un evento por llamada física simulada;
  fallo controlado antes del proveedor al agotar budget o faltar contexto.
- Suite unit completa, Ruff, mypy, evals deterministas y diff-check verdes.

## Limitaciones y retirada futura

Permanece el acoplamiento a dos métodos privados de Agno. La revisión de
compatibilidad se debe repetir al actualizarlo. No corrige sesiones ya
contaminadas ni sustituye autorización/consentimiento. No se ejecuta E2E
Telegram/Gateway real en este incremento. Retirar ambos adaptadores y el
mixin solo después de pasar estos repros con clases nativas; actualizar la
factory y conservar pruebas de contrato en la frontera gobernada.
