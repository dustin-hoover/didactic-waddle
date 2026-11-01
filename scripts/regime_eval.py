#!/usr/bin/env python3
"""regime_eval.py — put the regime gate in front of the Phase 1 referee.

The regime gate is the ONE signal this project believes in. In-sample it reduced
drawdown and its params were chosen by a sweep — exactly the setup that manufactures
fake edges. This script runs it honestly through tradebot.evaluate:

  * Builds daily return series on real BTC history, acting on the PRIOR day's gate
    state (no look-ahead), net of costs (the worse-of cost model).
  * A 54-point parameter grid becomes 54 "strategies" so PBO/CSCV can measure whether
    the parameter CHOICE is overfit, and the grid's Sharpe spread feeds the Deflated
    Sharpe Ratio (so the trial count is honest). Every grid point is logged to the
    trial registry (docs/trials.jsonl), pinned to the git commit.
  * Walk-forward checks that the DEPLOYED config's edge persists out-of-sample.
  * A stationary block bootstrap gives drawdown / CAGR / ruin distributions.
  * Everything is compared to BTC buy&hold and a 200d-SMA rule.

It writes a plain-language verdict to docs/regime_eval.json and prints it. Honesty
first: whatever it says, that is the result.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import evaluate as ev                 # noqa: E402
from tradebot.config import CostModel               # noqa: E402
from tradebot.ohlcv import ExchangeFeed             # noqa: E402
from tradebot.regime import RegimeConfig, sweep     # noqa: E402

PPY = 365.0


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def gate_returns(closes, cfg: RegimeConfig, cost_per_flip: float):
    """Daily returns of the gate rule on `closes`, acting on the PRIOR day's state
    (no look-ahead), charging `cost_per_flip` on each on/off change."""
    states = sweep(closes, cfg)                      # causal: state[i] uses closes[:i+1]
    out, pos = [], 0
    for i in range(1, len(closes)):
        desired = 1 if states[i - 1] else 0          # act on YESTERDAY's confirmed state
        r = (closes[i] / closes[i - 1] - 1.0) * pos
        if desired != pos:
            r -= cost_per_flip
        out.append(r)
        pos = desired
    return out


def _stats(returns):
    return {"cagr": round(ev.cagr(returns, PPY), 4),
            "sharpe": round(ev.sharpe(returns, PPY), 3),
            "max_drawdown": round(ev.max_drawdown(returns), 4)}


def main(argv) -> int:
    sym = argv[1] if len(argv) > 1 else "BTC"
    try:
        feed = ExchangeFeed()
        bars = feed.history(sym, "1d", 2000)
    except Exception as e:  # noqa: BLE001
        print(f"regime_eval: could not fetch {sym} history ({str(e)[:100]})", file=sys.stderr)
        return 2
    closes = [b.close for b in bars]
    if len(closes) < 400:
        print(f"regime_eval: only {len(closes)} daily bars — need ~400+ for a 200d gate.",
              file=sys.stderr)
        return 2

    costs = CostModel.from_report("docs/cost_model.json")
    cost_per_flip = costs.fee_frac + costs.slippage_frac
    commit = _git_commit()
    reg = ev.TrialRegistry("docs/trials.jsonl")

    # Benchmarks (net of cost where they trade).
    bh = ev.buy_hold_returns(closes)
    sma = ev.sma_rule_returns(closes, window=200, fee_frac=cost_per_flip)

    # Deployed config + a 54-point grid (the parameters we might have overfit).
    deployed = RegimeConfig()                        # sma_short=20, confirm_days=3, buffer=.02, golden
    grid, labels = [], []
    for short in (10, 20, 50):
        for confirm in (1, 3, 5):
            for buf in (0.0, 0.02, 0.05):
                for golden in (True, False):
                    grid.append(RegimeConfig(sma_short=short, confirm_days=confirm,
                                             buffer=buf, require_golden_cross=golden))
                    labels.append(f"s{short}_c{confirm}_b{buf}_{'g' if golden else 'ng'}")

    series = [gate_returns(closes, c, cost_per_flip) for c in grid]
    for lab, s in zip(labels, series, strict=True):
        reg.record(config_hash=lab, git_commit=commit,
                   metrics=_stats(s), note=f"{sym} regime grid")
    dep = gate_returns(closes, deployed, cost_per_flip)

    # DSR with a trial count + Sharpe spread measured from the grid itself.
    import statistics
    grid_sp = [ev.sharpe_per_period(s) for s in series]
    trial_std = statistics.pstdev(grid_sp) if len(grid_sp) > 1 else None
    dsr_dep = ev.deflated_sharpe_ratio(dep, n_trials=len(grid), trial_sharpe_std=trial_std)
    dsr_bh = ev.deflated_sharpe_ratio(bh, n_trials=len(grid), trial_sharpe_std=trial_std)

    # PBO: is the parameter choice overfit? (CSCV over the grid)
    T = min(len(s) for s in series)
    pbo = ev.pbo_cscv([s[:T] for s in series], n_blocks=10)

    # Walk-forward: does the DEPLOYED config's edge persist OOS? Compare mean OOS daily
    # return of the gate vs buy&hold across expanding-train / fixed-test folds.
    wf = ev.walk_forward_splits(len(dep), train_min=max(250, len(dep)//2), test_size=90)
    wf_gate, wf_bh = [], []
    for _, test in wf:
        wf_gate.append(statistics.fmean(dep[i] for i in test))
        wf_bh.append(statistics.fmean(bh[i] for i in test))
    wf_folds = len(wf)
    wf_gate_wins = sum(1 for g, b in zip(wf_gate, wf_bh, strict=True) if g > b)

    boot = ev.bootstrap_distribution(dep, n_paths=1000, mean_block=20, periods_per_year=PPY,
                                     ruin_dd=0.5, seed=1)

    report = {
        "symbol": sym, "git_commit": commit, "n_days": len(closes),
        "cost_per_flip": round(cost_per_flip, 5), "n_trials": len(grid),
        "benchmarks": {"buy_hold": _stats(bh), "sma200": _stats(sma)},
        "deployed_gate": _stats(dep),
        "dsr_deployed": round(dsr_dep, 4), "dsr_buy_hold": round(dsr_bh, 4),
        "pbo": round(pbo.pbo, 4), "pbo_median_logit": round(pbo.median_logit, 3),
        "walk_forward": {"folds": wf_folds, "gate_beats_bh_folds": wf_gate_wins,
                         "mean_gate_daily": round(statistics.fmean(wf_gate), 6) if wf_gate else 0,
                         "mean_bh_daily": round(statistics.fmean(wf_bh), 6) if wf_bh else 0},
        "bootstrap_deployed": {"cagr": boot.cagr, "max_drawdown": boot.max_drawdown,
                               "ruin_prob_50dd": boot.ruin_prob},
    }
    os.makedirs("docs", exist_ok=True)
    with open("docs/regime_eval.json", "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    # ---- plain-language verdict ------------------------------------------------
    d, b, s = report["deployed_gate"], report["benchmarks"]["buy_hold"], report["benchmarks"]["sma200"]
    print(f"\n=== Regime gate vs the referee — {sym}, {len(closes)} daily bars, commit {commit} ===")
    print(f"cost/flip {cost_per_flip*1e4:.0f} bps · {len(grid)} parameter trials\n")
    print(f"{'book':<14}{'CAGR':>9}{'Sharpe':>9}{'maxDD':>9}")
    for name, st in (("buy&hold", b), ("200d-SMA", s), ("regime gate", d)):
        print(f"{name:<14}{st['cagr']*100:>8.1f}%{st['sharpe']:>9.2f}{st['max_drawdown']*100:>8.1f}%")
    print(f"\nDeflated Sharpe (deployed): {dsr_dep:.2f}   (buy&hold DSR {dsr_bh:.2f})")
    print(f"PBO (param overfit prob):   {pbo.pbo:.2f}   [>=0.5 = overfit, ~0 = robust]")
    print(f"Walk-forward: gate beat buy&hold in {wf_gate_wins}/{wf_folds} OOS folds")
    print(f"Bootstrap (deployed): median CAGR {boot.cagr['median']*100:.1f}%, "
          f"median maxDD {boot.max_drawdown['median']*100:.1f}%, "
          f"P(>=50% DD) {boot.ruin_prob*100:.0f}%")

    verdict = _verdict(report)
    print("\nVERDICT: " + verdict)
    report["verdict"] = verdict
    with open("docs/regime_eval.json", "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print("wrote docs/regime_eval.json  (+ grid logged to docs/trials.jsonl)")
    return 0


def _verdict(r: dict) -> str:
    d, b = r["deployed_gate"], r["benchmarks"]["buy_hold"]
    parts = []
    if r["dsr_deployed"] >= 0.95:
        parts.append("DSR says the gate's Sharpe survives deflation")
    elif r["dsr_deployed"] >= 0.5:
        parts.append(f"DSR is weak ({r['dsr_deployed']:.2f}) — Sharpe only marginally beats luck")
    else:
        parts.append(f"DSR FAILS ({r['dsr_deployed']:.2f}) — Sharpe is indistinguishable from the luckiest of {r['n_trials']} tries")
    if r["pbo"] >= 0.5:
        parts.append(f"PBO={r['pbo']:.2f} says the parameter choice is OVERFIT")
    elif r["pbo"] <= 0.2:
        parts.append(f"PBO={r['pbo']:.2f} says the parameters are robust OOS")
    else:
        parts.append(f"PBO={r['pbo']:.2f} (mixed)")
    better_dd = d["max_drawdown"] < b["max_drawdown"]
    parts.append(("the gate cut drawdown " if better_dd else "the gate did NOT cut drawdown ")
                 + f"({d['max_drawdown']*100:.0f}% vs buy&hold {b['max_drawdown']*100:.0f}%)")
    cmp = "beats" if d["cagr"] > b["cagr"] else "trails"
    parts.append(f"CAGR {cmp} buy&hold ({d['cagr']*100:.0f}% vs {b['cagr']*100:.0f}%)")
    return "; ".join(parts) + "."


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
