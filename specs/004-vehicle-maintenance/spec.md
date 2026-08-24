# Spec: 004 — Vehicle Maintenance Vertical Slice

> **Milestone:** M4 — Primera vertical slice de producto
> **Status:** implemented
> **Target:** Invoice → extraction → proposal → confirmation → maintenance → later query

---

## Requirement

Primer dominio estructurado completo: vehículos y mantenimiento.
Full vertical slice: factura → extracción → vehículo → propuesta → confirmación → 
registro canónico → consulta posterior.

### Must Have

- Vehicle domain: `vehicles` + `vehicle_maintenance` tables in PostgreSQL
- Vehicle resolution: "mi coche" / "el Ford" / "el Mondeo" / "1234ABC"
- CRUD: find_vehicle, get_vehicle_summary, get_vehicle_maintenance_history
- WRITE with governance: propose → confirm → execute via action_proposals
- Source provenance: maintenance records linked to source documents
- All queries user-scoped and parameterized

### Should Have

- ActionProposal lifecycle: pending_confirmation → confirmed → executed
- Display names: nickname + make + model
- Ambiguity resolution (multiple vehicles matching)

### Won't Have

- Calendar / Reminder integration (M5)
- Bulk import
- Vehicle image storage

---

## Success Criteria

1. User says "mi coche" → `find_vehicle` resolves correctly
2. Vehicle summary shows last maintenance + total count
3. Maintenance history ordered by date DESC
4. `propose_vehicle_maintenance` creates action proposal, does NOT write
5. `execute_vehicle_maintenance` writes canonical record after confirmation
6. Maintenance record links to source document when from invoice