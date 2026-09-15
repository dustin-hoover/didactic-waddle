# Decision log

Living record of decisions, who owns them, and status. Append-only; newest at
top of each section. `[OPEN]` decisions block downstream phases.

## Open decisions (founder-owned)

| # | Decision | Blocks | Owner | Status |
|---|----------|--------|-------|--------|
| D1 | **Beachhead metro** — pick from ranked candidates | Entity state, hiring, all GTM | Founder | `[OPEN]` — needs real market data pull + founder pick |
| D2 | **Greenlight the remote-supervision model** after attorney review of the supervision-risk brief | Any hiring | Founder + attorney | `[OPEN]` — brief not yet substantiable without CourtListener/Descrybe pull for the chosen state |
| D3 | **Approve first cohort of candidates** before any offer | Offers | Founder | `[OPEN]` — no pipeline yet |
| D4 | **Authorize any spend** (ads, payroll, card program) | Phases 3/4/6 | Founder | `[OPEN]` — no financial rails connected |

## Log

### 2026-09-15 — Market + legal research + tech scaffolds (partial phases 1/2/5)
- **Market (real sources):** pulled AR + OK trade-licensing statutes/rules and
  BLS OEWS wages. Key finding: regulatory posture, not labor cost, is the
  deciding dimension. **Arkansas permissive** (registrant model, statute silent
  on physical-presence supervision); **Oklahoma likely incompatible** ("direct
  supervision" + 3:1 apprentice cap breaks 1:8-10 remote model). Kansas City =
  best wage arbitrage but regulatory read pending + dual-state (KS/MO).
  Recommended top-2 for D1: **NW Arkansas** and **Kansas City**.
- **Legal:** authored `legal/supervision-risk-brief.md` as attorney-prep (not
  advice), with the linchpin question, AR/OK primary-source findings, and the
  CourtListener/Descrybe case-pull query set to run once D1 fixes the state.
- **Tech:** scaffolded diagnosis service (Python, with a real bug caught + fixed
  in hazard detection — "compressor"/"cooling" no longer false-trigger the CO
  signal), plus dispatch / supervisor-console / ar-client / code-library specs.
  Safety invariants (sign-off, hazard live-view, audit) restated across all
  three enforcement layers. Authored 3 JD drafts (not posted).
- **Still gated / not done:** entity formation, any spend, any hire, PII
  prospecting list, sending any email. KS/MO/SC/ID/TN statutory read pending.
  Case-law pull deferred until D1 picks the finalist state.
- **Founder owns:** D1 (pick NWA or KC), then D2 (attorney greenlight for that
  state). Everything downstream waits on those.

### 2026-09-15 — Phase 0 executed (scaffold)
- Created working tree, README, execution boundary, decision log.
- Authored unit-economics model from operator-supplied assumptions.
- Authored `tech/schema.sql` with safety invariants (supervisor sign-off,
  auto-escalation, audit logging) enforced at the data layer.
- Scaffolded custom MCP directory with one complete reference stub and a
  manifest of the remaining nine.
- **Degraded:** none of the operational connectors (QuickBooks, Gusto, Stripe,
  Ramp, Ashby, Docusign, Close, Twilio, LegalZoom, Metricool, AdWhispr, Vibe
  Prospecting, TomTom, Badger, Xweather, ElevenLabs) are connected in this
  session. Available for real work: Bigdata.com, CourtListener, Descrybe,
  Gmail, Google Calendar/Drive, Felt Maps, Exa, Firecrawl, GitHub.
- **Founder now owns:** D1 (market pick). Nothing spends, forms, or hires until
  that and D2 clear.
