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

## Strategy findings to date (all in-sample / paper)
| Idea | Finding | Score (reviewer) |
|---|---|---|
| BTC regime gate | Drawdown reducer, **in-sample** (2022 −64%→~0%, one bear; sweep on same data) | 6/10 |
| Funding carry | Real but modest, ~3–6% net APR, monitor only | 5/10 |
| Fundamental screen | No edge vs BTC over a full cycle | 1/10 |
| Momentum rotation | No edge net of cost | 1/10 |
| Whale following | ≈ coin-flip | 1/10 |
| Scalping | No edge | 1/10 |
| AI price prediction | OOS R² ≈ 0 | 1/10 |

**Headline caveat:** the regime gate's benefit is likely smaller out-of-sample than
the in-sample headline; it must be re-evaluated in the Phase 1 harness (walk-forward +
CPCV + DSR/PBO) before any claim stands. Result will be recorded here, whatever it is.

## Open validation debts (Phase 1 will close these)
- No walk-forward with frozen params; no deflated Sharpe / PBO (needed given many
  variants tried); no survivorship-free universe; no Monte-Carlo drawdown ranges; no
  real-fill cost reconciliation yet.

*Updated as evaluations run.*
