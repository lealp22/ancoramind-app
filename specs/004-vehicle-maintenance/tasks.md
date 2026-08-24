# Tasks: 004 — Vehicle Maintenance

## Task Breakdown

### T1: Domain models
- [x] VehicleCreate, Vehicle, VehicleMaintenanceCreate, VehicleMaintenance
- [x] VehicleResolution (found/not_found/ambiguous)
- [x] VehicleSummary (vehicle + last maintenance + count)
- [x] display_name property

### T2: Database
- [x] `ancora.vehicles` table with indexes
- [x] `ancora.vehicle_maintenance` table with FK to vehicles + documents
- [x] `ancora.action_proposals` table (governance layer)

### T3: Repositories
- [x] VehiclesRepository — create, get_by_id, list_by_user, find_by_reference (ILIKE)
- [x] MaintenanceRepository — create, get_history, get_last
- [x] ActionProposalsRepository — create, get_pending, confirm, mark_executed

### T4: Domain service
- [x] VehicleService — find_vehicle, get_summary, get_maintenance_history
- [x] VehicleService — register_maintenance (WRITE)
- [x] Resolution logic: single → found, multiple → ambiguous, none → not_found

### T5: Tools (thin adapters)
- [x] find_vehicle — resolve reference + list all
- [x] get_vehicle_summary — full summary with last maintenance
- [x] get_vehicle_maintenance_history — chronological history
- [x] propose_vehicle_maintenance — creates ActionProposal
- [x] execute_vehicle_maintenance — confirms + registers + audits

### T6: App wiring
- [x] Vehicle tools registered in `_init_domain_tools()`
- [x] Total: 11 tools when ANCORA_DATABASE_URL is set

### T7: Tests
- [x] 59 unit tests (13 new: vehicle_models, vehicle_service)
- [x] find_vehicle resolution: found, not_found, ambiguous, list_all
- [x] register_maintenance: user context enforcement, repo call verification