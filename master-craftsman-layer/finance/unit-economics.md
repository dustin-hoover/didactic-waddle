# Unit economics — residential HVAC service beachhead

All figures below are **operator-supplied target assumptions**, not measured
results. They are the hypothesis to prove in < 9 months, not a claim about the
world. Every line needs to be replaced with actuals as jobs close.

## Per-job model (target)

| Metric | Target | Notes |
|--------|--------|-------|
| Avg ticket | $520 | Residential HVAC service call |
| Loaded labor cost / job | $95 | vs. industry ~$180 — the whole thesis rides on this |
| Parts margin | 42% | target |
| First-time fix rate | 88% | callbacks destroy CM and NPS |
| Callback rate ceiling | 4% | |
| Contribution margin / job | $215 | target |
| Jobs / tech / day | 4.5 | routing + diagnosis efficiency dependent |

## Loaded labor build (how $95 is supposed to work)

The arbitrage is: one remote supervising master amortized across 8–10 jobs, on
top of a $35/hr augmented tech, instead of a $65–$120/hr journeyman per job.

```
Tech time/job  ~1.6 hr @ $35/hr             = $56.0
Supervisor allocation (1 master / 9 jobs):
  master $65/hr, ~0.35 hr supervised/job    = $22.8
Dispatch + tooling + telematics allocation  = $16.2  (plug — refine with actuals)
------------------------------------------------------
Loaded labor / job (target)                 ~ $95
```
This build is **illustrative** — the $16.2 overhead allocation is a plug to
reconcile to the $95 target and must be replaced with real dispatch/tooling/
telematics cost per job once operating.

## Break-even staffing

- 6 techs + 1 remote supervising master + 1 dispatcher.
- At 4.5 jobs/tech/day × 6 techs ≈ 27 jobs/day.
- Supervisor load at 27 jobs/day tests the 1:8–1:10 ratio directly — watch for
  over-signing without live-view (see safety invariants).

## Sensitivities to watch (the model breaks if…)

- **Supervisor ratio slips below ~1:6** → labor arbitrage evaporates; CM/job
  falls under the $180 expansion gate.
- **Callback rate > 4%** → each callback is ~2× the CM of the original job in
  lost margin + trust.
- **Jobs/tech/day < 3.5** → fixed overhead per job spikes; likely a routing or
  diagnosis-latency problem, not a labor-rate problem.

## What must replace this file

Pull actuals from the (not-yet-connected) financial stack — QuickBooks cost
centers per service line and market, Stripe settled tickets, Gusto labor,
Ramp parts/fuel — and recompute weekly per the Phase 7 cadence. Until those are
connected, this file is a hypothesis, and every downstream number that cites it
inherits that caveat.
