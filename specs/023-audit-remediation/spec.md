# Spec 023 — Remediación de auditoría técnica (2026-10-02)

> **Backlog:** BL-40 (nuevo)
> **Status:** draft
> **Target:** cerrar los hallazgos de la auditoría de coherencia
> especificación/implementación del 2026-10-02, priorizados por riesgo.
> **Jerarquía:** AGENTS.md y docs/architecture.md mandan sobre este spec.

---

## 1. Contexto

Una auditoría de coherencia (especificaciones vs. implementación) detectó 8
hallazgos accionables, agrupados aquí en 6 fases ejecutables de forma
independiente pero con dependencias explícitas entre sí (fase 4 depende de
fase 3 completada; el resto son independientes). No se ha confirmado contra
Railway real ninguno de los hallazgos — fase 1 empieza por esa verificación
antes de cualquier cambio de código.

## 2. Hallazgos y fases

| Fase | Hallazgo original | Severidad |
|---|---|---|
| 1 | API REST de AgentOS expuesta sin autenticación | 🔴 Crítico |
| 2 | `UserContext` con fallback silencioso + `APP_ENV` inseguro por defecto | 🟠 Alto |
| 3 | Fuga de sesiones DB + UUIDs sin validar en tools | 🟠 Alto |
| 4 | Consentimiento de mutaciones mediado por el LLM (BL-39 T6b) | 🔴 Crítico |
| 5 | Zona horaria naive en recordatorios/calendario | 🟠 Alto |
| 6 | Sincronización documental (AGENTS/README/BACKLOG/specs/prompts) | 🟡 Medio |

## 3. Principios no negociables aplicables

- No se cierra ningún hallazgo sin test que lo demuestre (regresión).
- Fase 4 sigue el contrato ya diseñado en
  `specs/022-llm-input-trust/consent-design.md`; no se re-diseña aquí.
- Ningún cambio de esta spec afloja gobernanza existente (AGENTS.md §2.4).
- Cambios de superficie HTTP (fase 1) requieren verificación en un entorno
  real antes de considerarse cerrados — no basta con la inspección local.

## 4. Fuera de alcance

- Nueva infraestructura (Collector/Grafana rollout, BL-23/BL-33 pendientes).
- Cualquier cambio de modelo/proveedor LLM.
- Diseño nuevo de UX de consentimiento (ya existe en specs/022).

Ver `tasks.md` para el desglose ejecutable por fase.
