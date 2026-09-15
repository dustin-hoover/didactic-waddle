# MCP: state-license-board

Reference stub for the custom MCP servers this company needs. All ten follow
this shape: `SKILL.md`, `src/index.ts`, `package.json`, one placeholder tool
returning `{status: "not-implemented", contract_needed: true}`.

## Why this one is the reference

License verification is on the critical safety path: a job's supervising master
must hold an active, correctly-classed license in the job's jurisdiction
(enforced in `tech/schema.sql`). This MCP is how the platform checks that
against the state board of record.

## Intended tools (once a data contract exists)

- `verify_license(license_number, state)` → `{active, class, expires_on,
  disciplinary_flags}`
- `list_reciprocity(from_state, to_state)` → reciprocity rules / friction
- `watch_license(license_number)` → alert on status change or expiry

## Contract needed

State boards expose license data inconsistently (web lookup, bulk file, paid
API, or none). Before implementing: identify the beachhead state's board, its
access method, and terms of use. Until then the tool returns
`not-implemented` and the platform must treat license status as **unverified**
(fail-closed: no sign-off allowed against an unverified supervisor).
