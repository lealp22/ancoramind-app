# Verificación — specs/028

## Incremento de diseño (2026-10-06)

Se han creado alcance, contratos propuestos, tareas y matriz de aceptación;
BL-26 apunta a specs/028. No hay cambios en runtime, proveedores, configuración
remota, migraciones ni prompts. No se ha activado voz ni gastado inferencia.

Verificación local ejecutada con `.venv/Scripts/python.exe`:

- `-m pytest tests/unit/ -q`: **770 passed**, 48.94 s.
- `-m ruff check src/ tests/ scripts/ migrations/`: **All checks passed**.
- `-m mypy src/`: **Success**, 126 source files; exit 0.
- `git diff --check`: exit 0.
- Telegram Bot API oficial Voice/getFile revisada para los contratos de metadata
  y descarga; proveedor/tarifas/endpoint STT no seleccionados ni validados aún.

Estos resultados son regresión de código existente, NO pruebas ejecutables de
voz. V01–V36 siguen pendientes. T2 convierte contratos/políticas en código y
tests; U/I/E se implementan en sus incrementos respectivos. No se han ejecutado
integration PostgreSQL ni E2E/inferencia real en este incremento documental.

Hallazgo de dependencia: `_execute_claimed()` del processor devuelve actualmente
una respuesta de confirmación y no conecta ejecución automática; el parser
escrito sólo acepta Sí y el consentimiento está condicionado por flag. Ningún
resultado de este incremento prueba que botones estén habilitados en producción.