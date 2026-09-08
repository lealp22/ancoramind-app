# Verification: 008 — Railway Deployment Automation

> Estado: **PASS de preparación de repositorio** — no se ha creado proyecto ni
> deployment Railway todavía.

## Verificación local

| Check | Resultado |
|---|---|
| Server config development/production | ✅ defaults, precedencia `PORT` y validación |
| Webhook helpers sin exponer secretos | ✅ 9 tests de URL, API y sanitización |
| Unit tests completos | ✅ 123 passing (entorno limpio incluido) |
| Ruff | ✅ módulos de despliegue limpios; lint global pendiente BL-19 |
| Docker build limpio | ✅ Agno 2.9.0, contenedor production y `/health` 2xx |

## Evidencia local (2026-09-08)

- Entorno limpio equivalente a CI: `agno==2.9.0`, 123 tests passing y lint de
  `main`, server config, webhook y script en verde.
- Docker: construcción desde `.dockerignore`, sin `.env` en el contexto.
- Smoke test: `APP_ENV=production PORT=8080` → escucha `0.0.0.0:8080`,
  `reload=False`, `GET /health` devuelve `{"status":"ok"}`.
- Sin proyecto Railway, variables remotas, webhook ni despliegue creados en
  esta fase.

## Verificación Railway pendiente

- [ ] Proyecto Railway y servicio GitHub creados por el usuario.
- [ ] Rama de despliegue: `main`; Auto Deploy + Wait for CI habilitados.
- [ ] Variables de producción cargadas exclusivamente en Railway.
- [ ] Railway domain generado y `GET /health` devuelve 200.
- [ ] Webhook registrado mediante `scripts/telegram_webhook.py set`.
- [ ] Telegram E2E de documento y búsqueda de matrícula repetido.
- [ ] Rollback a deployment anterior probado o procedimiento confirmado.