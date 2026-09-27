# Verification: 015 — PowerShell E2E Script

> **Fecha:** 2026-09-27 · **Entorno:** Windows 11 + Windows PowerShell 5.1
> **Estado:** ✅ verificado localmente

| Check | Resultado |
|---|---|
| Parser Windows PowerShell | ✅ sintaxis válida |
| `run-e2e.ps1 -Check -PublicBaseUrl … -EnvFile .env` | ✅ provider OpenRouter, Supabase y endpoint HTTPS validados sin efectos |
| `pytest tests/unit/test_run_e2e_powershell.py -q` | ✅ 4 passed |
| `pytest tests/unit/ -q` | ✅ 493 passed |
| `pytest tests/integration/ -q` | ✅ 71 passed |
| `ruff check src/ tests/ scripts/ migrations/` | ✅ limpio |

No se ejecutó el flujo destructivo/local completo en esta verificación: iniciar
ngrok, registrar webhook o arrancar la app no es apropiado como test automático.
Esos pasos quedan disponibles para ejecución manual mediante el script.

La comprobación de errores normaliza únicamente whitespace de `stderr` antes de
buscar las frases de contrato. Windows PowerShell puede partir visualmente esos
mensajes si la ruta del workspace contiene espacios; se siguen comprobando tanto
el mensaje semántico como el código de salida no exitoso.