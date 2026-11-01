# GATES.md — Saatgut capital-at-risk gates

> Per `ACTION_PLAN_FOR_CLAUDE.md`. **No phase raises live capital at risk until its
> gate is passed AND Dustin signs this file in writing (name + date + the dollar cap).**
> Claude never edits a signature line; only Dustin does.

## Canary cap (the hard dollar limit for all live activity until Phase 1+)
- **Amount:** _[Dustin to write a fixed USD figure, ≤ 1–2% of investable net worth]_
- **Set by:** _[name + date]_

## Phase 0 — Stop the bleeding
Required before sign-off:
- [ ] 0.1 Signing moved off GitHub Pages (local signer); Pages dashboard read-only; workflow hardened (pinned SHAs, minimal permissions, branch protection, CODEOWNERS).
- [ ] 0.2 Hard caps enforced on-chain (Safe + Roles / Squads), not in localStorage; exact-amount approvals; `approvals_audit.py` reports zero unlimited approvals.
- [x] 0.3 Global kill switch + portfolio drawdown breaker (code: `autopilot.py`, `scripts/kill.py`). _On-chain pause still pending (0.2)._
- [x] 0.4 Token universe tightened: UNKNOWN/CAUTION never live-eligible (code: `execution.py`, `solana_exec.py`, `universe.py`).
- [x] 0.5 Real-fill cost reconciliation (code: `fills.py` → `docs/fills.jsonl`, `scripts/cost_report.py` → `docs/cost_model.json`; `backtest.run_backtest(cost_report=…)` + `build_site.py` use the worse of modelled vs realized). _Awaiting real canary fills to populate the log._

**Phase 0 gate — SIGNED:** _[Dustin: name + date + canary cap]_ ☐ not yet

## Phase 1 — Validation infrastructure
- [ ] 1.1 Point-in-time, survivorship-free datastore.
- [ ] 1.2 Evaluation harness (walk-forward, CPCV, DSR, PBO, block bootstrap) + trial registry.

**Phase 1 gate — SIGNED:** _[Dustin]_ ☐ not yet

## Phase 2 — Market-state model     **SIGNED:** ☐ not yet
## Phase 3 — Evolutionary strategy + selection     **SIGNED:** ☐ not yet
## Phase 4 — Scaling gates (G0–G3+)     **SIGNED:** ☐ not yet
## Phase 5 — Operator safeguards     **SIGNED:** ☐ not yet

---
*Check marks record code completion; a phase is only "passed" when Dustin signs its gate line.*
