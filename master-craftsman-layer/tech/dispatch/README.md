# dispatch/ — routing + customer ETA (Next.js)

Talks to TomTom Maps + Badger Maps (routing) and Twilio (customer ETA SMS).
None of those connectors are live in this session, so this is a scaffold with
adapter interfaces, not a running app.

## Responsibilities
- Assign each `jobs` row a technician + supervising master, respecting the
  supervisor's live ratio (see schema `supervising_master_id`).
- Auto-route the day's jobs (TomTom/Badger adapter).
- Push customer ETA + on-my-way SMS (Twilio adapter).
- Surface supervisor load so a master is never assigned past the ratio the
  chosen state's law allows (dimension b — hard-gated, not advisory).

## Adapter seams (stub now, wire later)
- `adapters/routing.ts` → TomTom / Badger
- `adapters/messaging.ts` → Twilio
- `adapters/fsm.ts` → `fsm-servicetitan` MCP

## Do-not-cross
- Dispatch may not assign a hazard-classed job without confirming a supervisor
  is available for synchronous live-view at the scheduled time.
