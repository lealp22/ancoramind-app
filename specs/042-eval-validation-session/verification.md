# Verificación local — sesión acumulada de evals

## Estado

Base3f2e8b89/CI39219285248 verde era sólo diagnóstico. Este incremento nuevo es local:
sin commit/push, CLI Railway local, credenciales leídas, mutaciones remotas, nuevas
claves ni inferencias por el agente. Autorización de gasto vigente0,10 acumulado,
no renovar por intento. No reabre run52759a15 ni inventa su salida faltante.

## Pruebas

- Ledger cifrado/atomic replace/fsync/lock y lease exclusivo. Scope excluye sólo
  diagnóstico/operativa allowlist; cambiar prompts/tools/casos/modelo bloquea.
  No es attestation de equivalencia semántica ni sandbox; código de publicación
  y candidato siguen Git/CI/revisión exacta.
- Importación reportes completos plan/cases, primerpassed/segundo presentación
  inválida con cinco eventos completados → reserva conservadora0,04. Otro error/
  uso incompleto queda uncertain y no replay. Falta/malformed/running/orphan bloquea.
- Reabrir/inicializar no renueva plazo ni límite y no crea clave. Cambio key hash,
  spend negativo/no finito/decreciente, scope/budget/reset/expiry/permisos rechazan.
- Reservas individuales y redondeo a la baja, sin liberación por metadata de coste
  menor/ausente. Baseline del Gateway evita que el gasto preexistente desaparezca.
  Concurrencia dos reservas no sobregira; lease existente no se limpia a ciegas.
- CLI init con acceptanceflag sólo GET/models/keyinfo; prepare no resuelve provider.
  Mismo source claim bloquea aunque cambie subset. Gates internos se ligan a SHA/
  huella/casos reales, no approval.json viejo. Legacy no cambia si no hay sesión.
- Recorrido real SDK/GovernedModel/SafeOpenAILike, HTTP MockTransport: checks pre y
  post en cada POST; agotamiento observado antes segundo GET de keyinfo bloquea
  antes transporte pagado; 503postcheck tras una respuesta consume reserva/error,
  no retry ni siguiente llamada. Otro recorrido de2casos+review cifrada completa
  con0,06 gasto inicial pasa donde la reserva de toda campaña fallaba.
- No cambio prompts/modelo/terminal guard, retries, calendarios/DB productiva.
  Nuevas fuentes implican huella/SHA nuevos para publicación, no nueva autorización
  económica dentro de mismo scope. Causa histórica exacta sigue desconocida.

## Resultado de verificación

- `pytest tests/unit/ -q --cov=src`: **1969 passed, 1 skipped**, **81,22 %**.
  Skip symlink Windows conocido; **44 pruebas nuevas** de sesión, recorrido real
  SDK/HTTP sintético incluido. Harness/presentación focal anterior198passed/1skip;
  últimas4 variantes incluidas en suite global final.
- `ruff check src/ tests/ scripts/ migrations/`, `mypy src/` (**180 fuentes**),
  `scripts/run_evals.py` (**36casos/6categorías/9provisionales**) y diff limpios.
- Paquete allowlist creado desde fuentes locales sin commit (no candidato aprobado),
  sello temporal validado, sin .git/.env/DB, consola empaquetada `--help` muestra
  session-init/session-status. Temporales eliminados. No build Docker ni publicación.
- Integraciones focales processor/presentation intentadas en DB dedicada local
  ancoramind_test/127.0.0.1:5432: **14 errores de setup**, ninguna prueba ejecutada.
  Docker daemon no disponible (named pipe dockerDesktopLinuxEngine ausente),
  PostgreSQL inaccesible. Bloqueo ambiental, no dar por passed ni usar DB remota.
  Última evidencia anterior:14focales pasaron para diagnóstico3f2e8b89, no esta fuente.
- Warning OTel localhost4318 ausente conocido; no fallo unitario ni cambio telemetry.
  SHA/CI exacta de este incremento siguen pendientes. No inferencia real, claves
  leídas, presupuesto externo alterado, campaña anterior relanzada ni CLI local.

### Atención antes de publicar

El import separa explícitamente el candidato histórico db0c59b (claves2h previas a
la nueva sesión) de la campaña7ea0cf06 con clave reutilizable. No borra ni reanuda
ese reporte/evidencia ni lo carga de nuevo al límite vigente. Cualquier otro
histórico no verificable bloquea; no se considera coste cero por estar incompleto.
La clave Gateway actual sigue aportando su gasto acumulado real observado aunque
un reporte provenga de otra clave. Esta separación de procedencia está probada
con ambos reportes coexistiendo; no requiere limpieza manual del volumen.