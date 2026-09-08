# Tasks: 008 — Railway Deployment Automation

## T1: Runtime production-ready

- [x] Resolver host, `PORT` y `reload` por entorno.
- [x] Producción escucha `0.0.0.0` y desactiva autoreload.
- [x] Test unitario de defaults, precedencia de puertos y validación.

## T2: Build and platform configuration

- [x] Corregir `Dockerfile`: copiar metadata + fuente antes de instalar.
- [x] Añadir `.dockerignore` para no enviar secretos, venv ni datos runtime.
- [x] Añadir `railway.json`: Dockerfile, start command, `/health`, timeout y
      restart policy.

## T3: CI/CD

- [x] Añadir workflow GitHub Actions para `pull_request` y `push` a `main`.
- [x] Ejecutar lint de los módulos productivos de despliegue y
      `pytest tests/unit/ -q`.
- [ ] En Railway: conectar GitHub, seleccionar `main`, activar Auto Deploy y
      **Wait for CI** (requiere cuenta/proyecto del usuario).
- [ ] En GitHub: proteger `main` requiriendo el check `CI / quality`
      (decisión del propietario).

## T4: Telegram webhook estable

- [x] Script Python para registrar, inspeccionar y borrar webhook.
- [x] Usa `TELEGRAM_WEBHOOK_SECRET_TOKEN`; no imprime secretos.
- [x] Tests unitarios del cliente y sanitización.
- [ ] Registrar webhook contra dominio Railway tras primer deployment.

## T5: Documentation and verification

- [x] Crear guía `docs/deployment-railway.md`.
- [x] Actualizar `.env.example`, README, development, AGENTS y BACKLOG.
- [x] Build Docker local limpio: Agno 2.9.0 resuelto y `/health` validado con
      `APP_ENV=production`, `PORT=8080`, `0.0.0.0`, sin autoreload.
- [ ] Primer deployment Railway (requiere acción del usuario/cuenta Railway).
- [ ] Verificar `/health`, webhook y E2E Telegram; desbloquea BL-1/T7.