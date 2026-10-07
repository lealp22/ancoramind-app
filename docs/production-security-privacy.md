# Seguridad y privacidad para producción y apertura pública

Estado: checklist de diseño y evidencia pendiente — 2026-10-07. No certifica
cumplimiento ni sustituye evaluación legal especializada. Complementa
`docs/llm-security-hardening.md` (prompt injection), `docs/governance.md`
(autorización) y ADR-005/006 (inferencias y observabilidad).

## Marco europeo explícito: RGPD/GDPR

RGPD (GDPR en inglés) es el Reglamento (UE) 2016/679. El MVP no es por sí
mismo una exención. Debe evaluarse la aplicabilidad territorial/material y los
roles reales; la aceptación de riesgos por el propietario no sustituye una
base jurídica, contratos de encargado ni los derechos de otras personas.
El EU AI Act es otro marco, complementario: no reemplaza el RGPD.
La excepción de actividad exclusivamente personal/doméstica tampoco debe
extrapolarse automáticamente al servicio ofrecido a terceros.

Fuente oficial: https://eur-lex.europa.eu/eli/reg/2016/679/oj

### Alcance de la decisión MVP

El propietario acepta OpenRouter para audio personal/Telegram/producción MVP,
incluida ausencia de garantía de proveedor fijo/ZDR extremo a extremo. Ver
`specs/028-telegram-voice-stt/preflight-smoke.md`. No autoriza tratamiento en
nombre de terceros ni elimina obligaciones legales. No es evidencia de que
todos los controles técnicos estén activos. Voz sigue gated hasta validación.

## Gates verificables antes de ofrecer el servicio a terceros

| Área | Evidencia requerida | Estado |
|---|---|---|
| Inventario | Flujos audio/texto/documentos, Telegram, Gateway, OpenRouter, subproveedores, DB, storage, backups, historial Agent y telemetría | Pendiente consolidar |
| GDPR: roles y bases | Determinar responsable/encargados, finalidades y base jurídica por tratamiento; condiciones art. 9 para categorías especiales, si aplica | Revisión legal pendiente |
| Minimización/retención | Plazos por categoría; audio temporal no documental, texto cifrado temporal ≠ historial Agent; eliminación/backups y ejercicio de derechos probado | Parcial, evidencia end-to-end pendiente |
| Proveedores | DPA, subencargados, ubicaciones, acceso, entrenamiento, logs y retención por endpoint; transfers internacionales y garantías aplicables | Pendiente |
| ZDR | Condición contractual y configuración verificadas en TODA la cadena cuando se exige, no solo marketing/flag. Metadata/billing y excepciones diferenciadas | No demostrado STT OpenRouter |
| Derechos/transparencia | Información clara, acceso/rectificación/supresión/exportación y procedimiento verificable | Pendiente |
| Riesgo | Evaluar necesidad de DPIA (art. 35), realizarla cuando corresponda; justificar resultado, revisión periódica | Pendiente |
| Seguridad | Aislamiento usuario/chat/bot, secretos rotables, mínimo privilegio, cifrado, sandbox/recursos decoder, tmpfs, admission, idempotencia y consentimiento determinista | Parcial; validación efectiva producción pendiente |
| Incidentes | Detección, runbook, responsables, evidencia y evaluación de notificación conforme a plazos aplicables | Pendiente |
| AI Act | Roles proveedor/deployer y clasificación por uso; transparencia de interacción IA (art. 50), alfabetización IA (art. 4), usos prohibidos/alto riesgo si aplican | Evaluación pendiente |
| Evals | Negaciones/silencio/ruido, confirmación vocal, prompt injection, regresión y fallo sin replay | Parcial; benchmark real pendiente |

ZDR es un control útil, NO requisito universal autónomo del GDPR ni garantía
de cumplimiento. El GDPR exige protección por diseño/default, minimización,
seguridad y accountability entre otras obligaciones. DPIA depende del riesgo;
«datos sensibles» coloquialmente no equivale siempre a categorías del art. 9.
Una grabación de voz no es automáticamente biometría especial: analizar si se
trata para identificar unívocamente a una persona y qué contiene el audio.

El AI Act no convierte automáticamente un asistente en sistema de alto riesgo
por usar STT o tratar datos personales. Clasificación, obligaciones y fechas
deben revisarse por uso real y normativa vigente antes del lanzamiento. No
suponer que todas las obligaciones de modelos GPAI corresponden a AncoraMind.

## Política operativa de voz

- Ambigüedad STT: «No he podido entender el audio. Por favor, envía tus
  indicaciones de nuevo.» Nuevo mensaje = nueva interacción; nunca retry del
  original ni autorización implícita para ejecutar acciones.
- Ambigüedad de ejecución de acciones NO se comunica como fallo de comprensión
  del audio; mantener auditoría/reconciliación sin duplicar efectos.
- No contenido en logs/OTel; errores de proveedor no se reenvían al usuario.
- Valorar proveedor fijo detrás del Gateway o STT propio si no se pueden
  verificar condiciones requeridas; no bypass de LLMAccess/gobernanza.

## Fuentes oficiales revisadas (2026-10-07)

- EDPB, protección por diseño/default:
  https://www.edpb.europa.eu/topics/ai-and-technology/privacy-by-design-and-by-default_en
- EDPB, DPIA:
  https://www.edpb.europa.eu/topics/accountability-and-compliance-tools/data-protection-impact-assessment_en
- Comisión, AI Act artículo 50:
  https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50
- OpenRouter, condiciones técnicas STT:
  https://openrouter.ai/blog/tutorials/transcription-on-openrouter/