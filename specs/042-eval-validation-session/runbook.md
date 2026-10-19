# Sesión acotada de evals — código local, todavía no publicado

No ejecutar estos comandos en el candidato7ea0cf06/3f2e8b89: falta este incremento.
No cambia claves/variables ya preparadas ni añade servicios. Propietario ya autorizó
el límite acumulado0,10USD; no repetir permiso por cada paso dentro de ese ámbito.

## Una publicación cuando esté todo en verde

1. Commit/push del incremento completo y CI del mismo SHA. Publicarlo como candidato
   con **Actualizar evaluador**, confirm_idle y check_only desmarcado. Procedimiento
   [specs/041](../041-manual-eval-deploy/runbook.md), sin CLI local. Nunca Re-run
   antiguo, ni pin GitHub/rebuild bot. Esperar deployed_idle_verified del nuevo SHA.
2. Nueva terminal privada de **ancoramind-evals**. Inicializar una sola vez:

   ```sh
   python /app/scripts/eval_console.py session-init --accept-session
   ```

   Importa reportes conservando marcadores y consulta metadata Gateway, sin modelo.
   `session_ready` incluye limit_usd, charged_or_reserved_usd, available_usd y
   gateway_spend_usd. No copiar claves, reescribir approval.json ni regenerar Fernet.
   Límite0,10 es de toda sesión, no nuevo gasto por lanzar este comando. Repetir
   inicialización válida sólo verifica sesión original; no extiende plazo/saldo.
3. Si `session_ready` tiene saldo, lanzar UNA vez:

   ```sh
   python /app/scripts/eval_console.py run
   ```

   Ya usa la sesión: registra identidad exacta y genera gates internos, sin otro
   bloque de aprobación por SHA. Omite passed anteriores, manteniendo su candidato
   original, y reparte saldo entre casos restantes; no promete campaña completa de
   una única versión. Techo por caso puede bajar; si no basta, para sin ampliarlo.
   Revisor p/f/x igual que specs/040; fail/x/cierre inválido detiene siguientes.

## Uso posterior sin nuevas aprobaciones repetitivas

```sh
python /app/scripts/eval_console.py session-status
python /app/scripts/eval_console.py status --run ID
python /app/scripts/eval_console.py review --run ID
```

Los comandos anteriores no infieren. Guardar run_id; nunca `run` para reconectar.
Para un diagnóstico pagado deliberado de UN caso, sólo en otro candidato revisado
del mismo scope y con saldo, lanzamiento manual:

```sh
python /app/scripts/eval_console.py run --cases response_style.mixed_read_proposal
```

Es una nueva ejecución separada, no reanudar/repetir el run52759a15. No se lanza
automáticamente tras fallo. Mismo source no puede volver a lanzar aunque cambie
subset/budget. Si quiere completar el resto en esa fuente, incluirlos en su primer
lanzamiento; no fabricar cambios SHA para eludir un bloqueo de replay.

## Paradas claras

- `session_budget_insufficient`: no subir límite ni nueva clave. Informar saldo/
  reserva y decidir con propietario. Reservas conservadoras no se liberan por
  borrar una respuesta ni porque Gateway todavía indique gasto bajo.
- `session_budget_unverifiable`/`session_gateway_unverified`/spend decreciente:
  no tratar como saldo cero consumido; revisar metadata/acceso sin inferencia.
- `session_case_consumed_or_uncertain`/lease existente: no borrar marcadores,
  relanzar/restart ni “arreglar” labels. Inspeccionar ejecución previa; incertidumbre
  no concede retry. Caso terminal fallido con usage completo puede probarse sólo
  como nueva ejecución de otro candidato revisado dentro del scope autorizado.
- `session_scope_or_key_changed`/expiración: la sesión no se extiende por publicar.
  No aceptar nuevo modelo/fixtures/prompts/clave automáticamente. Hablar si cambia
  el alcance, presupuesto o incertidumbre, no para repetir el mismo permiso.
- `session_history_unverifiable`: no empezar otra sesión vacía ni borrar reportes;
  falta evidencia de gasto/estado anterior. Guardar y resolver sin modelo.
  El reporte conocido db0c59b de claves2h anteriores se conserva separado de esta
  sesión; no se exige borrarlo para importar7ea0cf06.

## Contabilidad y retención

Run histórico conocido: dos casos empezados con techo0,02 cada uno →0,04 reservado
conservadoramente; quedan como máximo0,06 si Gateway no reporta más. Para4 pendientes,
techo inicial≤0,015. Esto NO factura0,04, sólo evita gastar reservas no acreditadas.
No declara coste total real del histórico por tener actual_cost=null.

Misma evidencia cifrada7d/purga manual de specs/040. Ledger/claims metadata quedan
para impedir resets/replays; no guardar en Git ni exportar ledger con material
privado. Golden sigue promoción manual/versionada. No copia automática de pasados
entre candidatos para declarar nuevo pass, ni inferencia al arrancar contenedor.