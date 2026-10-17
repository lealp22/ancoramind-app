# Verification: 004 — Vehicle Maintenance

## E2E manual autorizado — 2026-10-17

**PASS acotado:** Playwright/Telegram, mismo baseline revisión 8/r4:
alta de un vehículo ficticio → confirmación Core → mantenimiento ficticio
→ confirmación Core → consulta posterior de vehículo e historial.

- El mantenimiento no existe antes de confirmar; propuesta presentada en
  `pending_confirmation`, target verificado por FK y usuario.
- Tras el Sí, propuesta `executed` y una fila de mantenimiento enlazada al
  vehículo esperado y a su `source_action_id`.
- Fecha/kilometraje/descripción/taller/trabajos recuperados en Telegram
  coinciden con el registro canónico. Sin importe, divisa ni documento.
- Consulta READ final `completed`, sin nuevas propuestas ni escrituras.
- Confirmaciones deterministas sin LLM; sin retries/fallback ni configuración
  modificada. 41 unitarias focales de vehículos superadas.

IDs, timestamps UTC, mensajes de prueba y consumo en
`specs/008-railway-deployment/mvp-release-campaign.md`, entrega 2.

No se acredita todavía la vertical completa factura → extracción → mantenimiento,
la procedencia documental, los importes, la ordenación con múltiples registros
ni la ambigüedad entre vehículos. No confundir este PASS manual con el cierre
de todos los criterios de la spec.