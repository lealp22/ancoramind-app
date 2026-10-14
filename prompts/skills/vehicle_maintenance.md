# Skill — Vehicles

## When to Use

- User mentions their car, vehicle, or specific brand/model
- User wants to register a NEW vehicle ("Registra mi coche...", "Añade la furgoneta")
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
- `not_found` → tell user, suggest registering the vehicle (see Vehicle Registration below)

## Vehicle Registration

When the user wants to register a NEW vehicle (or a `not_found` result suggests it):

1. Required: make and model. Ask for them if missing.
2. Optional: year, license plate (matrícula), nickname, VIN.
   Only ask for what the user already offered — don't interrogate.
3. **You MUST call `propose_vehicle`.** NEVER write a proposal summary or
   confirmation request yourself — a proposal only exists if the tool created it.
   The tool shows the summary and the proposal ID to the user.
4. The Core presents the stored fields and confirmation buttons. Do not
   repeat its summary or ask for confirmation again in your answer.
5. The Core validates human consent and executes; the Agent has no executor.
6. Only claim success after a verified Core result, never from the proposal alone.

Duplicate plates are rejected at execution time (normalized comparison:
uppercase, alphanumeric only). If the Core reports a duplicate,
tell the user and do NOT retry with the same data.

## Maintenance Registration

Same proposal/execute flow as Vehicle Registration: **you MUST call
`propose_vehicle_maintenance`** — never simulate the proposal text yourself.
1. Gather required fields (vehicle, date, mileage if applicable)
2. Call `propose_vehicle_maintenance` — it creates the proposal and shows it
3. Wait for confirmation
4. The Core validates consent and executes, without an Agent executor call
5. Only claim success after a verified Core result

Link to source document when available.

## Data Integrity

- Maintenance records are canonical data
- Always link provenance (source document ID)
- Never invent maintenance events
- Kilometrage should be validated (don't allow decreasing values
  without asking)