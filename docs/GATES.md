# GATES.md — Saatgut capital-at-risk gates

> Per `ACTION_PLAN_FOR_CLAUDE.md`. **No phase raises live capital at risk until its
> gate is passed AND Dustin signs this file in writing (name + date + the dollar cap).**
> Claude never edits a signature line; only Dustin does.

## Canary cap (the hard dollar limit for all live activity until Phase 1+)
- **Amount:** _[Dustin to write a fixed USD figure, ≤ 1–2% of investable net worth]_
- **Set by:** _[name + date]_

## Phase 0 — Stop the bleeding
Required before sign-off:
- [~] 0.1 Workflow hardening DONE (Action SHAs pinned, minimal `permissions`, `.github/CODEOWNERS`). STILL PENDING (breaking, needs Dustin): move signing off GitHub Pages into a local signer; make the Pages dashboard read-only; enable branch protection + "require Code Owners review" (repo admin setting, cannot be set from code).
- [~] 0.2 `scripts/approvals_audit.py` reports zero unlimited/excessive approvals (DONE); localStorage caps relabeled as advisory/non-binding in `wallet.html` (DONE). STILL PENDING (needs Dustin): on-chain hard caps via Safe + Zodiac Roles / Squads so caps are enforced outside the browser + exact-amount approvals.
- [x] 0.3 Global kill switch + portfolio drawdown breaker (code: `autopilot.py`, `scripts/kill.py`). _On-chain pause still pending (0.2)._
- [x] 0.4 Token universe tightened: UNKNOWN/CAUTION never live-eligible (code: `execution.py`, `solana_exec.py`, `universe.py`).
- [x] 0.5 Real-fill cost reconciliation (code: `fills.py` → `docs/fills.jsonl`, `scripts/cost_report.py` → `docs/cost_model.json`; `backtest.run_backtest(cost_report=…)` + `build_site.py` use the worse of modelled vs realized). _Awaiting real canary fills to populate the log._

**Phase 0 gate — SIGNED:** _[Dustin: name + date + canary cap]_ ☐ not yet

## Phase 1 — Validation infrastructure
- [x] 1.1 Point-in-time, survivorship-free datastore (code: `datastore.py`; tests cover delisted-coin-in-past-universe + the look-ahead canary). _Needs a real historical load (incl. dead coins) to be useful — infra only so far._
- [x] 1.2 Evaluation harness — walk-forward, CPCV (purge+embargo), Deflated Sharpe, PBO/CSCV, stationary block bootstrap, BTC buy&hold + 200d-SMA benchmarks, trial registry (code: `evaluate.py` → `docs/trials.jsonl`; known-answer tests: noise→PBO≥0.5 & DSR<0.5, planted edge detected).

_Note: 1.1/1.2 are the referee. No strategy's headline number stands until it is run through this harness. The regime gate re-evaluation (the open debt in FINDINGS.md) is the first job for it — not yet done._

**Phase 1 gate — SIGNED:** _[Dustin]_ ☐ not yet

## Phase 2 — Market-state model     **SIGNED:** ☐ not yet
## Phase 3 — Evolutionary strategy + selection     **SIGNED:** ☐ not yet
## Phase 4 — Scaling gates (G0–G3+)     **SIGNED:** ☐ not yet
## Phase 5 — Operator safeguards     **SIGNED:** ☐ not yet

---
*Check marks record code completion; a phase is only "passed" when Dustin signs its gate line.*
