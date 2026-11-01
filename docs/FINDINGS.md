# FINDINGS.md — honest results, including failures

> Per `ACTION_PLAN_FOR_CLAUDE.md`: record the honest result of every evaluation,
> whatever it is. Nothing here is expected future performance; all figures are
> in-sample / paper unless a forward test is explicitly named.

## Independent risk review (31 Oct 2026)
An external reviewer assessed the codebase (from `CODEBASE_OVERVIEW.md`). Verdict:
**honest, well-structured research tool — not yet a validated money-maker; keep real
money at canary size only.** Scorecard lowlights: demonstrated edge 2/10 (loses to
BTC buy-and-hold in-sample), validation rigour 4/10 (params swept in-sample), web/
wallet attack surface 4/10 (signing on GitHub Pages), token-universe safety 4/10
(UNKNOWN kept). Full text archived by the owner. **These conclusions are accepted and
drive the action plan.**

## Regime gate — OUT-OF-SAMPLE verdict (1 Nov 2026, via the Phase 1 harness)
Ran the deployed gate + a 54-point parameter grid on 2000 BTC daily bars through
`tradebot.evaluate` (commit f0cf9ad), net of ~17 bps/flip, acting on prior-day state
(no look-ahead). Full output: `docs/regime_eval.json`; grid logged to `docs/trials.jsonl`.

| book | CAGR | Sharpe | max DD |
|---|---|---|---|
| buy & hold | 8.5% | 0.42 | **76.6%** |
| 200-day SMA (fixed) | **12.7%** | **0.53** | 35.7% |
| regime gate (deployed, tuned) | 11.3% | 0.50 | **33.7%** |

- **Drawdown reduction is REAL and survives OOS:** 34% vs buy&hold's 77%. That is the
  gate's genuine job and it does it.
- **The tuned parameters are OVERFIT: PBO = 0.71** (≥0.5 = overfit). The swept choice
  (sma_short=20, confirm_days=3) lands in the OOS bottom half 71% of the time. A plain,
  un-tuned **200-day SMA actually does slightly better** (12.7% / 0.53 vs 11.3% / 0.50).
- **No commanding alpha: Deflated Sharpe = 0.80** for the gate (buy&hold 0.74) — both
  "weak," i.e. neither Sharpe is statistically distinguishable from luck once you deflate
  for the trials run. On raw return the gate beat buy&hold in only 4/11 walk-forward folds
  (expected — it's a risk reducer, not a return booster; its OOS win is on drawdown).
- Bootstrap (deployed): median max DD 44.5%, **P(≥50% DD) = 33%** — real tail risk remains.

**Consequence (recorded, not yet actioned):** prefer the simplest trend rule (plain 200d
SMA) over the swept gate; claim **risk reduction, not return outperformance**; do not
present the tuned params as validated. This contradicts the old docstring claim that the
sweep was "not overfit" — that claim has been corrected in `regime.py`.

## Strategy findings to date (all in-sample / paper unless marked OOS)
| Idea | Finding | Score (reviewer) |
|---|---|---|
| BTC regime gate | **Drawdown reducer, confirmed OOS** (34% vs 77% maxDD); but tuned params overfit (PBO 0.71) and no alpha (DSR 0.80 ≈ buy&hold); plain 200d-SMA ≥ it. See OOS section above. | 6/10 |
| Funding carry | Real but modest, ~3–6% net APR, monitor only | 5/10 |
| Fundamental screen | No edge vs BTC over a full cycle | 1/10 |
| Momentum rotation | No edge net of cost | 1/10 |
| Whale following | ≈ coin-flip | 1/10 |
| Scalping | No edge | 1/10 |
| AI price prediction | OOS R² ≈ 0 | 1/10 |

**Headline caveat:** the regime gate's benefit is likely smaller out-of-sample than
the in-sample headline; it must be re-evaluated in the Phase 1 harness (walk-forward +
CPCV + DSR/PBO) before any claim stands. Result will be recorded here, whatever it is.

## Open validation debts
- [x] Walk-forward + Deflated Sharpe + PBO for the regime gate — DONE (see OOS section).
- [x] Monte-Carlo (block-bootstrap) drawdown ranges — DONE for the gate.
- [x] Real-fill cost reconciliation plumbing — DONE (`fills.py`/`cost_report.py`), awaiting real fills.
- [ ] Survivorship-free universe actually LOADED with history incl. dead coins
  (`datastore.py` exists; no real multi-coin load yet).
- [ ] Re-run the same harness on any NEW candidate signal before it is ever claimed.

*Updated as evaluations run.*
