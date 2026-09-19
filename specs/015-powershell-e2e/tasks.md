# Tasks: 015 — PowerShell E2E Script

## T1: Script nativo

- [x] Crear `scripts/run-e2e.ps1` compatible con Windows PowerShell 5.1.
- [x] Añadir `-Check`, `-Reset`, `-Port`, `-EnvFile` y `-PublicBaseUrl`.
- [x] Cargar `.env` como datos literales, sin ejecutar contenido.
- [x] Validar provider, Storage, DB y requisitos LiteLLM cuando está activo.
- [x] Implementar flujo local PostgreSQL/ngrok/webhook/app y flujo remoto HTTPS.

## T2: Tests y documentación

- [x] Añadir tests sin efectos externos para configuración válida, provider
      desconocido, literalidad de `.env` y URL pública inválida.
- [x] Actualizar `docs/deployment-e2e.md`, `docs/quick-start.md` y `AGENTS.md`.
- [x] Actualizar BACKLOG y conteos de tests.