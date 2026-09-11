"""What is the most effective *attainable* day/swing strategy for this app?

This app can only do one kind of thing: LONG/FLAT SPOT, low turnover, on a handful
of liquid majors, net of fees+slippage on CoW. So the honest search is not "the best
strategy in all of crypto" (leverage, shorting, funding-carry, market-making and HFT
are all off the table here) — it is: among what we can actually execute, what beats
just holding BTC, net of costs, out-of-sample?

We test, on real daily history fetched fresh from the repo feed:

  A. Benchmarks — buy & hold BTC, buy & hold ETH, equal-weight basket.
  B. Cross-sectional / dual MOMENTUM ROTATION — each rebalance, hold the top-K of a
     majors basket by trailing-L return, WITH an absolute-momentum cash filter (only
     hold names whose trailing return > 0; else cash). A no-filter control too.
  C. Single-asset TREND filter (the repo's validated TrendFilterStrategy) and the
     COMPOSITE strategy on BTC/ETH, via the real cost-aware backtester.

No lookahead: a decision at day t uses only closes through t and earns t -> t+1.
Everything is net of a per-turnover cost (B) or the repo cost model (C). Split into
first/second half for a crude out-of-sample check.

FINDINGS (run 2026-09, a ~1yr crypto bear: majors -19% to -77%) — reproduce by
re-running; results are regime-dependent and this is ONE regime, ONE year:
  * Rotation LOST to buy&hold BTC in-sample and out-of-sample. In a correlated
    crash, "rotate into the strongest alts" picks volatile losers; BTC fell least.
    The absolute-momentum cash filter helped vs the no-filter control (~-53% ->
    ~-15%) but still did not beat simply holding BTC.
  * The single-asset TREND/swing filter won cleanly: it sat in cash through the
    downtrend, beating buy&hold by ~26-45 pts and roughly halving drawdown (ETH
    trend/swing was +1.5% in a year ETH fell 43%). Faster variants (day-style,
    composite over-trading) did WORSE — the edge is lower frequency, not higher.
  * Conclusion: the effective, attainable strategy here is trend-timed BTC/ETH that
    goes to cash below regime — which is already this app's default (kind="trend",
    style="swing"). Trend-following gives up some upside in strong bull rips; it is
    a drawdown-reducer, not a magic return booster. Not a bull-market-validated claim.

Usage:  python scripts/momentum_experiment.py [--days 366]
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.backtest import run_backtest
from tradebot.config import BotConfig, CostModel, RiskConfig, StrategyConfig
from tradebot.ohlcv import Bar, ExchangeFeed
from tradebot.protection import ProtectionConfig

BASKET = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "DOGE", "DOT", "LTC"]
COST_ONEWAY = 0.0025          # 25 bps per unit turnover (fee+slippage), conservative
ANN = math.sqrt(365)


def _metrics(curve: List[float]):
    rets = [curve[i] / curve[i-1] - 1 for i in range(1, len(curve)) if curve[i-1] > 0]
    if not rets:
        return 0.0, 0.0, 0.0
    mu, sd = statistics.fmean(rets), statistics.pstdev(rets)
    sharpe = 0.0 if sd == 0 else (mu / sd) * ANN
    peak, mdd = -1e9, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1 - v / peak)
    return curve[-1] / curve[0] - 1, sharpe, mdd


def _show(name: str, curve: List[float]):
    tr, sh, dd = _metrics(curve)
    print(f"  {name:38} ret {tr*100:+7.1f}%   Sharpe {sh:+5.2f}   maxDD {dd*100:4.0f}%")


def _buyhold(closes: Dict[str, List[float]], sym: str, start: int, end: int):
    c = closes[sym][start:end]
    return [x / c[0] for x in c]


def _equalweight(closes: Dict[str, List[float]], syms: List[str], start: int, end: int):
    curve = [1.0]
    for d in range(start + 1, end):
        r = statistics.fmean(closes[s][d] / closes[s][d-1] - 1 for s in syms)
        curve.append(curve[-1] * (1 + r))
    return curve


def _momentum(closes, syms, start, end, L, top_k, step, abs_filter=True):
    curve, w, eq, d = [1.0], {s: 0.0 for s in syms}, 1.0, start
    while d < end - 1:
        mom = {s: closes[s][d] / closes[s][d-L] - 1 for s in syms}
        ranked = sorted(syms, key=lambda s: mom[s], reverse=True)
        picks = [s for s in ranked if (mom[s] > 0 or not abs_filter)][:top_k]
        neww = ({s: (1.0/len(picks) if s in picks else 0.0) for s in syms}
                if picks else {s: 0.0 for s in syms})
        eq *= (1 - COST_ONEWAY * sum(abs(neww[s] - w[s]) for s in syms))
        w = neww
        for _ in range(step):
            if d + 1 >= end:
                break
            eq *= (1 + sum(w[s] * (closes[s][d+1] / closes[s][d] - 1) for s in syms))
            curve.append(eq)
            d += 1
    return curve


def _bars_from(closes_hl, sym) -> List[Bar]:
    return closes_hl[sym]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=366)
    args = ap.parse_args()

    feed = ExchangeFeed()
    bars: Dict[str, List[Bar]] = {}
    for s in BASKET:
        try:
            bars[s] = feed.history(s, "1d", limit=args.days)
        except Exception as e:  # noqa: BLE001
            print(f"skip {s}: {e}")
    syms = [s for s in BASKET if s in bars]
    N = min(len(bars[s]) for s in syms)
    closes = {s: [b.close for b in bars[s][-N:]] for s in syms}
    print(f"universe: {syms}\nbars: {N} daily  cost/turnover: {COST_ONEWAY*1e4:.0f}bps\n")
    for s in syms:
        c = closes[s]
        print(f"  {s:5} {c[0]:.4g} -> {c[-1]:.4g}  ({100*(c[-1]/c[0]-1):+.0f}%)")

    maxL = 90

    def window(label, a, b):
        print(f"\n### {label}  (days {a}..{b}) ###")
        print("  -- benchmarks --")
        _show("buy&hold BTC", _buyhold(closes, "BTC", a, b))
        _show("buy&hold ETH", _buyhold(closes, "ETH", a, b))
        _show("equal-weight basket (daily reb)", _equalweight(closes, syms, a, b))
        print("  -- momentum rotation (abs-momentum cash filter) --")
        for L in (20, 40, 60, 90):
            for k in (1, 2, 3):
                _show(f"L={L:>2} top{k} reb/wk", _momentum(closes, syms, a, b, L, k, 7))

    window("FULL", maxL, N)
    half = maxL + (N - maxL) // 2
    window("1st half (in-sample)", maxL, half)
    window("2nd half (OUT-OF-SAMPLE)", half, N)

    print("\n### CONTROL: rotation with NO cash filter (always invested) ###")
    _show("L=40 top2 reb/wk NO-filter", _momentum(closes, syms, maxL, N, 40, 2, 7, abs_filter=False))

    print("\n### Single-asset TREND / COMPOSITE via the repo cost-aware backtester ###")
    print(f"  {'asset/strategy':26} {'strat':>8} {'buy&hold':>9} {'Sharpe':>7} {'maxDD':>6} {'trades':>6} {'exp':>5}")
    for sym in ("BTC", "ETH"):
        for kind, style in (("trend", "swing"), ("trend", "day"), ("composite", "swing")):
            cfg = BotConfig(symbol=sym, interval="1d", starting_cash=10_000.0,
                            strategy=StrategyConfig(kind=kind, style=style),
                            risk=RiskConfig(), costs=CostModel(), protection=ProtectionConfig())
            r = run_backtest(bars[sym], cfg)
            print(f"  {sym+' '+kind+'/'+style:26} {r.strategy_return*100:+7.1f}% "
                  f"{r.buyhold_return*100:+8.1f}% {r.sharpe:+7.2f} {r.max_drawdown*100:5.0f}% "
                  f"{r.num_trades:6d} {r.exposure_avg*100:4.0f}%")


if __name__ == "__main__":
    main()
