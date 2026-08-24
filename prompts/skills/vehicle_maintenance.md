# Skill — Vehicle Maintenance

## Available Tools

- `find_vehicle` — resolve a vehicle reference ("mi coche", "el Ford", "el Mondeo")
- `get_vehicle_summary` — get overview of a vehicle
- `get_vehicle_maintenance_history` — get maintenance records
- `register_vehicle_maintenance` — record a maintenance event (requires confirmation)

## When to Use

- User mentions their car, vehicle, or specific brand/model
- User sends an invoice or document related to a vehicle
- User asks about maintenance history
- User wants to record a service, repair, or inspection

## Vehicle Resolution

Users refer to vehicles in various ways:
- "mi coche" → their primary vehicle
- "el Ford" → brand reference
- "el Mondeo" → model reference
- "la furgoneta" → vehicle type

Use `find_vehicle` to resolve these references.

Results:
- `found` → use the vehicle
- `ambiguous` → present candidates, ask user to pick
- `not_found` → tell user, suggest registering the vehicle

## Maintenance Registration

When registering maintenance:
1. Gather required fields (vehicle, date, mileage if applicable)
2. Propose the maintenance record to the user
3. Wait for confirmation
4. Only claim success after the tool returns it

Link to source document when available.

## Data Integrity

- Maintenance records are canonical data
- Always link provenance (source document ID)
- Never invent maintenance events
- Kilometrage should be validated (don't allow decreasing values
  without asking)