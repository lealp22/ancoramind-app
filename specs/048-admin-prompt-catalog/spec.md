# 048 — Catálogo de prompts de sólo lectura

## Alcance autorizado

Pestaña Prompts en el dashboard existente: inventario de `prompts/**/*.md`,
selección/contenido, SHA-256 normalizado como el loader, referencias literales
de uso (AST) y selector de contenido histórico real exportado de Git. No simular
aprobaciones, activaciones ni versiones inexistentes. No cambiar prompts ni su
carga, consentimiento, inferencia, schema DB o despliegue.

## Contrato

- API protegida con el bearer/flag/cabeceras existentes; listado sin contenido,
  detalle por nombre exacto de inventario y revisión exacta exportada.
- No rutas arbitrarias, symlinks, recursos externos, provider/Git/BD en runtime.
- Artefacto `src/agent/prompt_history.json` generado offline, validado con Pydantic
  y checksum, copiado por Docker con src/. `--check` en CI con checkout completo.
- Historial de archivos actuales por ruta/HEAD: no borrados/renombrados/ramas.
  Fuente SHA/fecha, no autor/email/mensaje; shallow/ausencia/corrupción explícitos.
- Mostrar contenido presente vs histórico sin afirmar prompt efectivo por run.
  Cargas principales pueden estar cacheadas desde arranque. Usos detectados no
  equivalen a activación ni cubren patrones dinámicos.
- UI `textContent`, sin Markdown activo. Limpieza al salir/timeout; IDs de petición
  descartan respuestas tardías al cambiar selección/cerrar sesión.

## Aceptación

Auth 401, flag OFF 404, mutaciones 405; cero DB/inferencia; contenido real y hashes
coincidentes; traversal/symlinks bloqueados; export/import sin .git; historial
inválido no inventa datos; cuatro pestañas accesibles; navegación de archivos y
versiones, vacío/error/carreras/logout y pantalla estrecha. Pruebas unitarias,
Ruff/mypy, check del export y navegador sintético local antes de entrega.

Futuro no implementado: revisores/aprobaciones/evals/diff, activación/rollback y
correlación inmutable por ejecución. Detalle operativo en runbook 027.

## Verificación local — 2026-10-22

- 16 assets y 64 entradas Git exportadas; `--check` coincide. Prueba de copia del
  paquete sin `.git`, lectura actual/histórica y equivalencia CRLF/LF superada.
- 129 focales passed/1 skip; suite 2260 passed/2 skips (permisos symlink Windows).
  WEB_SEARCH_ENABLED=false y OTLP vacío sólo en el subproceso de pruebas para no
  heredar el arranque operativo local; no edición de `.env`.
- Ruff global, mypy 187 fuentes y diff check correctos.
- Navegador con servidor FastAPI aislado loopback y bearer sintético: APIs de
  prompts reales, resto de datos simulado, cero DB/Agent/POST. Inventario de 16,
  contenido y selector Git, usos reales/no uso declarado, texto no ejecutable,
  carreras de selección/logout, error/recuperación y ancho móvil superados.
- Sin modificación de `prompts/`, carga de instrucciones ni configuración remota.
  No despliegue ni validación Railway; empaquetado deducido del Dockerfile y
  probado por copia local, no build fresh de la imagen.