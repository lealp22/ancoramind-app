# Spec: 027 — Pantalla de administración centralizada

> **Backlog:** BL-43
> **Status:** implementado localmente (2026-10-05)
> **Target:** un punto de entrada web para las labores de operador diarias
> (invitaciones, runtime-config, salud, enlaces externos) que convive con los
> CLIs existentes sin reemplazarlos.

---

## Contexto

AncoraMind depende hoy de varias piezas externas (Railway, Supabase,
OpenRouter, LiteLLM Gateway, Grafana) además de dos superficies HTTP de
administración propias:

- `/admin/runtime-config/*` (BL-23/specs/013), operada con
  `scripts/runtime_config.py`.
- `/admin/telegram-pairing/*` (BL-24/specs/017), operada con
  `scripts/telegram_pairing.py`.

Ambas son JSON protegido por un único `RUNTIME_CONFIG_ADMIN_TOKEN` compartido,
pensado para uso desde terminal. No existe ningún frontend en el repo.

## Requirement

### Must Have

1. `GET /admin/dashboard` — página HTML autocontenida (CSS/JS inline, sin
   build ni dependencias nuevas), servida sólo cuando `ADMIN_DASHBOARD_ENABLED=true`.
2. Autenticación propia: `ADMIN_DASHBOARD_TOKEN`, un secreto **distinto** de
   `RUNTIME_CONFIG_ADMIN_TOKEN`. El dashboard vive en un navegador — más
   expuesto que una terminal — así que ese token nunca debe viajar al
   navegador; el backend del dashboard llama directamente a la lógica de
   dominio compartida (`TelegramPairingService`, el mismo `RuntimeConfigManager`
   que ya crea `main.py`) en vez de reenviar peticiones a los admin API
   existentes.
3. Panel de invitaciones: crear (`issue_invitation`) y listar
   (`list_invitations`, nuevo método de repositorio/servicio) invitaciones de
   pairing (BL-24). El código generado se muestra una sola vez.
4. Panel de runtime-config: paridad completa con `scripts/runtime_config.py` —
   status, validar, crear revisión, activar, rollback — operando sobre la
   misma instancia de `RuntimeConfigManager` que usa el admin API HTTP (un
   cambio hecho desde cualquiera de los dos se refleja en el otro).
5. Panel de salud: consume `GET /health/readiness` tal cual (sin cambios,
   sigue público y metadata-only).
6. Panel de enlaces: URLs configurables (`ADMIN_LINK_*_URL`) a Grafana,
   Railway, Supabase, OpenRouter y LiteLLM Gateway. Supabase y LiteLLM Gateway
   adjuntan el estado ya calculado por `HealthRegistry` (`database` y
   `gateway`); el resto son enlaces estáticos.
7. Los CLIs existentes (`scripts/runtime_config.py`,
   `scripts/telegram_pairing.py`) siguen funcionando sin ningún cambio de
   comportamiento — el dashboard es una fachada adicional, no un reemplazo.
8. **Sólo se despliega detrás de HTTPS.** `ADMIN_DASHBOARD_TOKEN` viaja como
   cabecera `Authorization: Bearer` igual que `RUNTIME_CONFIG_ADMIN_TOKEN` —
   no hay cifrado adicional a nivel de aplicación. La confidencialidad en
   tránsito depende por completo de que el dominio sea HTTPS (como ya es el
   caso en Railway). **Nunca** se expone este dashboard en un túnel o puerto
   HTTP sin TLS fuera de `APP_ENV=development` en `localhost`.
9. **Mitigaciones de defensa en profundidad para el token en `sessionStorage`**
   (no sustituyen a HTTPS, reducen el daño si el navegador o la pestaña se
   ven comprometidos):
   - Expiración por inactividad: el JS borra el token de `sessionStorage` y
     exige volver a introducirlo tras 30 minutos sin ninguna interacción
     (ratón, teclado, scroll o touch). El valor es holgado a propósito — no
     busca interrumpir una sesión de trabajo activa, sólo acotar cuánto
     tiempo seguiría siendo utilizable el token si se roba, sin depender de
     detectar el robo para que caduque.
   - Cabeceras de seguridad en toda respuesta bajo `/admin/dashboard*`:
     `Content-Security-Policy` (sin scripts/estilos de origen remoto, sin
     framing, sin `form-action`), `X-Frame-Options: DENY`,
     `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` y
     `Cache-Control: no-store` (para que el navegador no cachee páginas con
     códigos de invitación u otro contenido sensible).
   - `sessionStorage` ya es por pestaña y se borra sola al cerrarla; no se
     usa `localStorage` para que no sobreviva entre sesiones del navegador.

### Won't Have (este incremento)

- **Interruptor manual de parada de emergencia para el Agent/LLM** (circuit
  breaker accionado a mano). Hoy sólo existe el hard-stop automático al 90%
  del gasto. Construirlo toca la ruta crítica de `LLMAccess`/`GovernedModel`
  (matriz de aceptación A–Y de specs/013) y queda registrado como **BL-44**,
  pendiente de diseño propio.
- Un formulario con un campo por cada clave anidada del esquema de
  `RuntimeConfiguration` (rutas, budgets, concurrency…): el panel de
  runtime-config usa un `<textarea>` con el JSON completo, igual que
  `--config archivo.json` en el CLI.
- Roles o múltiples administradores: un único token compartido, igual que
  hoy con `RUNTIME_CONFIG_ADMIN_TOKEN`.
- Estado en vivo de Grafana/Railway/OpenRouter: sin credenciales baratas hoy
  para una consulta en vivo; quedan como enlaces estáticos.

## Design

```
GET  /admin/dashboard                               → HTML estático (shell + login + JS), público

# Invitaciones (BL-24) — TelegramPairingService directamente
GET  /admin/dashboard/api/invitations
POST /admin/dashboard/api/invitations

# Runtime config (BL-23) — RuntimeConfigManager compartido directamente
GET  /admin/dashboard/api/runtime-config/status
POST /admin/dashboard/api/runtime-config/validate
POST /admin/dashboard/api/runtime-config/revisions
POST /admin/dashboard/api/runtime-config/revisions/{revision}/activate
POST /admin/dashboard/api/runtime-config/rollback

# Enlaces + salud
GET  /admin/dashboard/api/links                      → URLs configuradas + health_status (db/gateway)
GET  /health/readiness                               → ya existe, público, sin cambios
```

Implementación: `src/agent/admin_dashboard.py` (instalación condicionada por
`ADMIN_DASHBOARD_ENABLED`, siguiendo el mismo patrón fail-closed de
`runtime_config_admin.py`/`telegram_pairing_admin.py`) +
`src/agent/admin_dashboard_static/dashboard.html` (página única).
`src/repositories/pairing.py`/`src/domain/interactions/pairing_service.py`
ganan `list_invitations`.

## Verification

Ver `verification.md` en este directorio.

## Operación

Ver `docs/runbooks-027-admin-dashboard.md` para flags, cómo arrancar/acceder,
qué hace cada panel y triage.
