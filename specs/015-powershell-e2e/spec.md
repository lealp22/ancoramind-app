# Spec: 015 — PowerShell E2E Script

> **Backlog:** BL-25
> **Status:** implemented (2026-09-19)
> **Target:** ejecutar la preparación E2E local desde Windows PowerShell sin
> depender de Bash, con una vía explícita para registrar el webhook de Railway.

---

## Requirement

El repositorio ofrece `scripts/run-e2e.sh`, pero el entorno principal de desarrollo
es Windows PowerShell. El script equivalente debe validar configuración sin ejecutar
`.env`, preparar PostgreSQL local solo cuando corresponda y registrar el webhook
sin exponer secretos.

## Design

`scripts/run-e2e.ps1` implementa:

- `-Check`: valida requisitos sin iniciar Docker, ngrok, Telegram ni la app.
- Flujo local: detecta PostgreSQL local, inicia/espera Docker, aplica
  `migrations/init.sql` solo si falta el schema, detecta/inicia ngrok, registra
  el webhook y ejecuta `python -m src.main`.
- `-Reset`: borra el webhook antes de volver a registrarlo.
- `-PublicBaseUrl https://<service>.up.railway.app`: valida una URL HTTPS limpia
  y registra el webhook contra un servicio ya desplegado; no inicia recursos locales.

El parser `.env` acepta únicamente asignaciones literales `KEY=VALUE` (incluido
`export KEY=VALUE`), elimina comillas externas simples/dobles y escribe variables
en el entorno del proceso. Nunca hace dot-source, `Invoke-Expression` ni expande
comandos del fichero.

## Success Criteria

1. Funciona en Windows PowerShell 5.1 y no requiere Git Bash/WSL.
2. `-Check` valida provider, Storage, DB y Gateway sin efectos externos.
3. Un contenido como `$(New-Item ...)` en `.env` no se ejecuta.
4. URL pública con path/query/fragmento se rechaza antes de registrar webhook.
5. Unit/integration suites y Ruff permanecen verdes.