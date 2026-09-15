# The Master Craftsman Layer

A vertically integrated trades services company that augments semi-skilled
workers with AI, AR, and remote licensed supervision to deliver master-level
plumbing, electrical, and HVAC work.

## Thesis

- **Workforce cliff.** The average U.S. electrician is ~55; roughly 40% of
  licensed capacity is projected gone by 2032 while demand climbs
  (electrification, data centers, aging housing stock).
- **Three unlocks converge (2027+).** Models reliable enough for code lookup /
  diagnosis / load calcs / permits; AR glasses wearable all day; cheap
  task-specific robotics.
- **Labor arbitrage.** Replace an $80–$120/hr fully-loaded journeyman with a
  ~$35/hr augmented worker + one remote licensed supervisor per 8–10 jobs.
- **Beachhead.** One metro, residential HVAC *service* (not install), a single
  high-margin service line first.
- **TAM.** ~$1.5T annual U.S. trades spend; 1% = $15B.

## Founding constraints

- Operator: ~15 years OSP/GIS + operations, Arkansas-based.
- Cash-constrained; must reach unit-economics proof in **< 9 months** from
  first hire.
- Regulatory blast radius: one gas leak or wrong-panel splice ends the company.
  **Safety > velocity, always.**

## Repository map

| Dir | Purpose |
|-----|---------|
| `entity/` | Corporate formation artifacts, cap table, founder docs |
| `market/` | Beachhead selection analysis, competitor watch |
| `hiring/` | Pipelines, job descriptions, screening logic |
| `ops/` | Operating cadence, incident log, safety review |
| `tech/` | Dispatch, diagnosis, code library, supervisor console, AR client, MCPs |
| `finance/` | Unit economics, chart of accounts, forecasts |
| `legal/` | Supervision-risk brief, regulatory diligence |
| `reports/` | Weekly ops reports + living decision log |

## Status: scaffolding only

This repository is a **planning and technical workspace**. It does not, and
must not, autonomously execute real-world actions that spend money, form legal
entities, employ people, or handle third-party personal data. Those are
founder-owned decisions requiring human sign-off and, where noted, licensed
professionals (attorney, insurance broker, state licensing board). See
`reports/decisions.md` for the open decisions and `EXECUTION_BOUNDARY.md` for
what is deliberately not automated and why.
