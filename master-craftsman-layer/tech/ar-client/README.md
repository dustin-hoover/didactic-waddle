# ar-client/ — RealWear / Vuzix headset client

Hands-free overlay for the field tech. Managed via the `ar-headset-fleet` MCP.

## Overlay elements
- Current step of the guided procedure.
- The governing code citation for the step (from `code-library` / `diagnosis`),
  with edition year + jurisdiction visible.
- Torque / measurement targets for the current fastener or reading.
- **"Flag supervisor"** button — always one interaction away; triggers the
  supervisor console live-view.

## Hard behavior
- On a hazard-classed step (gas, main panel, roof penetration) the client does
  **not** advance until a supervisor live-view is active. This mirrors the
  schema constraint and the diagnosis-service escalation — three layers, same
  rule, by design.
- Every code citation shown is the one logged to `diagnosis_audit`; the tech
  sees exactly what the audit trail records.

## Not built
Device SDK not wired (no fleet connector / hardware). Scaffold + overlay spec.
