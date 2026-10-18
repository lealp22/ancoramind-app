# T7/BL-48 — Campaña humana aprobada, ejecución pendiente

## Decisión explícita del propietario

Después de recibir smoke real (1POST, gasto0,0000353 USD reconciliado y clave
revocada), el propietario **autoriza UNA campaña** y su clave temporal, acepta
limitaciones/snapshot histórico y confirma revisión humana presente. No más
smokes/investigaciones previas. Esto no es prueba de campaña ejecutada/superada.

- Candidato sellado: SHA `db0c59be0b2eeb807d4222aeb5a62b622d90b200`, fuentes
  `108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82`.
- Plan `8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139`;
  casos `abddf11d06c5233ca97ddf016938ae759f698b740588167c5a9079dc5d137474`.
- Snapshot histórico rev8/checksum e2663c6a…, fingerprint a41f255f…; propietario
  acepta límite histórico20 distinto de upstream5 compartido observado y riesgo
  residual de coste/petición en curso. No mutar snapshot/routing/r4/pricing ni BD.
- Cinco casos seriales single_proposal, mixed_read_proposal, tasks_after_discard,
  explicit_reproposal, pending_proposals_read. Una ejecución por caso máximo,
  no repetir fallo/no evaluado/ambiguo; parada al primer error o criterio no pass.
- Por caso:120s,6model calls/requests,12tools simuladas,1024output tokens, sin
  reintentos del SDK/Agent ni replay; política snapshot inmutable. El harness no
  acredita todos los intentos internos upstream. No tools de negocio/DB del bot.
- Estimación0,02 USD/caso,0,10 total **adicionales**; coste nominal conjunto con
  smoke observado0,1000353 USD, no garantía de factura exacta. Clave nueva exclusiva
  r4/0,10 nominal sin reset/2h/concur1/RPM30/TPM250000, sólo GET models/key-info y
  chat-completions. No master en evals, no clave proveedor/bot modificada.
- Creación y revocación por shell LiteLLM del propietario; conservar marca/reporte
  en volumen eval existente, no reconstruir imagen. No commit/push/deploy agente.

## Operación única: dos shells

Se amplía el **mismo helper** `scripts/eval_accounting_smoke.py` con políticas de
clave inmutables smoke/campaign y roles campaign-admin/campaign; reutiliza gestión
loopback/TTY/revoke, no un motor nuevo. Es tooling local por stdin, no se añade
al contenedor ni al fingerprint aprobado. No ejecutar roles admin/smoke anteriores.

1. Abrir/mantener shells privadas **LiteLLM** y **ancoramind-evals**. Sin grabación,
   redirección de TTY o logs de contenido. No hace falta instalar herramientas.
2. PowerShell local: copiar admin de campaña:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
$source = Get-Content -Raw -Encoding UTF8 "$root\scripts\eval_accounting_smoke.py"
("python - --role campaign-admin <<'PY'`n" + $source + "`nPY`n") | Set-Clipboard
```

3. Pegar en shell **LiteLLM**, esperar `campaign_key_ready`. Muestra la clave
   únicamente en terminal privada, comprueba límites persistidos y queda esperando.
   **No pulsar Enter ni cerrar todavía**; si error, no crear otra.
4. PowerShell local: copiar el lanzador de campaña:

```powershell
$root = 'c:\Users\0020572\Documents\Formación\TheBridge\ancoramind-core'
$source = Get-Content -Raw -Encoding UTF8 "$root\scripts\eval_accounting_smoke.py"
("python - --role campaign <<'PY'`n" + $source + "`nPY`n") | Set-Clipboard
```

5. En shell **evals** (misma shell que lanzará el bloque), establecer sólo gate
   de la decisión ya recibida y URL no secreta:

```sh
export ANCORA_EVAL_GATEWAY_URL='http://litellm.railway.internal:4000/v1'
export ANCORA_EVAL_CAMPAIGN_OPERATOR_APPROVED='five-cases-0.10-usd-once'
```

6. Pegar bloque campaign, copiar después clave **CAMPAIGN nueva**, no alias/master/
   clave smoke, desde LiteLLM y pegarla en prompt oculto. No secreto en argv/env/Git.
   Revisa cada criterio con p/f/x. Mayúsculas aceptadas; errata repregunta sin LLM;
   vacío/EOF es no evaluado y detiene. Nunca automatizar respuestas humanas reales.
7. Tanto si pasa como si falla/cancela, volver a **LiteLLM y pulsar Enter**.
   Esperado `campaign_key_revoked_verified`. Fallo de cleanup exige revisar ese
   alias, no crear otra clave/repetir campaña. Expiración es backstop, no garantía
   de revocación inmediata si muere sesión/proceso admin.
8. Compartir sólo JSON final campaña+gasto y JSON de revocación, nunca clave,
   respuesta/contexto/rúbrica completa por logs. Los textos se ven sólo en TTY.
   Conservar archivos y reserva; no repetir comando si se interrumpe o falla.

## Qué ejecuta exactamente

Wrapper valida identidad/snapshot/plan/casos/mount y ausencia previa de reserva,
lee restricciones/gasto inicial0 de nueva clave campaña y llama **una vez al
`scripts.execute_eval_campaign.execute_approved` del contenedor sellado**.
El propio launcher mantiene reserva exclusiva/fsync, valida de nuevo la aprobación,
abre TTY, consulta scope, usa LLMAccess y tools sintéticas y revisa identidad antes
de cada caso. No modifica factories, prompts, descriptions ni conducta de candidato.

Flags internos de aprobación reflejan la decisión explícita registrada, incluido
aceptar procedencia histórica y verificación externa acotada mediante smoke y
relectura del límite nominal. No significan garantía universal0,10 ni una decisión
del LLM. Están sólo en mapa del proceso, no variables persistentes Railway.

Al terminar, wrapper relee hasta6 veces (2s) spend propio sin inferencias; añade
`gateway_spend` a copia de metadata. No compara sin matiz coste derivado del snapshot
con factura Gateway. Si falla reconciliación, informa read_failed/not_observed y
no repite inferencia ni cambia veredicto humano a pass por gasto.

Archivos bajo `/eval-state` para el plan exacto:

- `<checksum>.reserved.json`: consumida para siempre, no borrar/reutilizar.
- `<checksum>.report.json`: reporte original del harness, checkpoints.
- `<checksum>.gateway-report.json`: copia suplementaria con gasto propio/cleanup.

Marca del smoke `accounting-smoke-v1.reserved.json` es independiente y se conserva.
Otra key no permite repetir plan/volumen. Otro volumen o plan cambiado no comparte
garantía: no usarlos como atajo. Si falla wrapper después de inferencia, leer
reporte original sin relanzar. Resultado passed sólo si criterios humanos y checks
deterministas de los cinco casos pasan. Si stopped, conservar lo no evaluado como
tal; no cerrar BL-48 automáticamente por tener reporte.

## Validación local, no etiquetas reales

- 7 tests nuevos: runner/launcher/TTY/reporte/reserva reales con executor sintético,
  cinco casos ante p, parada1 ante f/x, rechazo de clave smoke, gate ausente y marker
  existente; metadata sin texto/secreto. Admin campaña: política0,10/2h y cleanup.
  20 focales junto a los13 smoke previos, todos sin coste/modelo real.
- Imagen sellada db0c59b, `--network none --tmpfs /eval-state`: wrapper por stdin,
  cinco ejecuciones sintéticas con revisión simulada **sólo para test**, motor
  sellado real, aprobación exacta/marca/reporte y replay bloqueado. No cambio en
  archivos /app ni manifests. Sin TTY se detiene antes de red/modelo.
- Suite global **1721 unitarias**, cobertura **80,58 %**, Ruff global y mypy src
  limpios; sin nuevas integraciones DB, claves reales, inferencias ni despliegues.
  Falta ejecución única del propietario y resultados reales/revocación.