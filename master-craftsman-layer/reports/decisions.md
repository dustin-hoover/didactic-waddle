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
