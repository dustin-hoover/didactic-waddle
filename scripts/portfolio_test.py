"""Honest test: diversified cross-sectional momentum vs. the incumbents.

Cross-sectional momentum — hold the few strongest-trending coins, rotate as
leadership changes, step to cash when the market rolls over — is one of the few
durable, well-documented edges in markets. This tests it on real aligned daily
data with a-priori (untuned) parameters, and compares it honestly to:
  * equal-weight buy & hold of the whole universe,
  * BTC buy & hold,
  * the incumbent single-asset BTC trend filter.

Reports full-period AND second-half-only (a cheap out-of-sample look) so we can
see whether any edge is real or a fluke of the window.
"""

import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tradebot import indicators as ind  # noqa: E402
from tradebot.backtest import run_backtest  # noqa: E402
from tradebot.config import BotConfig, StrategyConfig  # noqa: E402
from tradebot.ohlcv import ExchangeFeed  # noqa: E402

UNIVERSE = ["BTC", "ETH", "BNB", "XRP", "ADA", "LINK", "LTC", "SOL", "AVAX", "DOGE"]
# a-priori parameters — standard values, deliberately NOT tuned to this data
LOOKBACK = 90        # momentum window (days)
TREND_EMA = 50       # per-coin absolute trend filter
MARKET_EMA = 100     # BTC market regime filter (risk-off below)
TOPK = 3             # hold the strongest K
REBAL = 7            # rebalance every N days
FEE = 0.001
SLIP = 0.0007


def metrics(curve):
    rets = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve)) if curve[i - 1] > 0]
    sh = (statistics.fmean(rets) / statistics.pstdev(rets)) * math.sqrt(365) if len(rets) > 2 and statistics.pstdev(rets) else 0
    peak, mdd = -1e9, 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak) if peak > 0 else 0
    return curve[-1] / curve[0] - 1, sh, mdd


def xs_momentum(dates, closes):
    """closes: {sym: [aligned daily closes]}. Returns equity curve (start 1.0)."""
    n = len(dates)
    emas = {s: ind.ema(closes[s], TREND_EMA) for s in closes}
    btc_ema = ind.ema(closes["BTC"], MARKET_EMA)
    weights = {s: 0.0 for s in closes}
    equity = [1.0]
    eq = 1.0
    for i in range(1, n):
        # daily P&L from yesterday's weights
        r = sum(weights[s] * (closes[s][i] / closes[s][i - 1] - 1) for s in closes)
        eq *= (1 + r)
        # rebalance?
        if i % REBAL == 0 and i > LOOKBACK:
            market_on = btc_ema[i] is not None and closes["BTC"][i] > btc_ema[i]
            target = {s: 0.0 for s in closes}
            if market_on:
                scored = []
                for s in closes:
                    mom = closes[s][i] / closes[s][i - LOOKBACK] - 1
                    trend_ok = emas[s][i] is not None and closes[s][i] > emas[s][i]
                    if trend_ok and mom > 0:
                        scored.append((mom, s))
                scored.sort(reverse=True)
                picks = [s for _, s in scored[:TOPK]]
                for s in picks:
                    target[s] = 1.0 / TOPK   # equal weight among picks; rest cash
            turnover = sum(abs(target[s] - weights[s]) for s in closes)
            eq *= (1 - turnover * (FEE + SLIP))
            weights = target
        equity.append(eq)
    return equity


def ts_trend_basket(dates, closes):
    """Diversified time-series momentum: hold equal weight among the coins that are
    each individually above their own trend (and only when the market is on).
    Cash otherwise. More robust than cross-sectional picking.
    """
    n = len(dates)
    emas = {s: ind.ema(closes[s], TREND_EMA) for s in closes}
    btc_ema = ind.ema(closes["BTC"], MARKET_EMA)
    weights = {s: 0.0 for s in closes}
    eq = 1.0
    equity = [1.0]
    for i in range(1, n):
        eq *= (1 + sum(weights[s] * (closes[s][i] / closes[s][i - 1] - 1) for s in closes))
        if i % REBAL == 0 and i > TREND_EMA:
            market_on = btc_ema[i] is not None and closes["BTC"][i] > btc_ema[i]
            up = [s for s in closes if market_on and emas[s][i] is not None and closes[s][i] > emas[s][i]]
            target = {s: (1.0 / len(up) if s in up else 0.0) for s in closes} if up else {s: 0.0 for s in closes}
            turnover = sum(abs(target[s] - weights[s]) for s in closes)
            eq *= (1 - turnover * (FEE + SLIP))
            weights = target
        equity.append(eq)
    return equity


def equal_weight_hold(closes):
    syms = list(closes)
    n = len(closes[syms[0]])
    eq = [1.0]
    for i in range(1, n):
        r = statistics.fmean(closes[s][i] / closes[s][i - 1] - 1 for s in syms)
        eq.append(eq[-1] * (1 + r))
    return eq


def report(label, curve):
    r, sh, dd = metrics(curve)
    print(f"  {label:<26} return {r*100:>+7.0f}%   sharpe {sh:>5.2f}   maxDD {dd*100:>3.0f}%")


def main():
    feed = ExchangeFeed()
    bars = {s: feed.history(s, "1d", 1000) for s in UNIVERSE}
    common = sorted(set.intersection(*[{b.date[:10] for b in v} for v in bars.values()]))
    closes = {s: [next(b.close for b in bars[s] if b.date[:10] == d) for d in common] for s in UNIVERSE}
    # faster aligned build:
    idx = {s: {b.date[:10]: b.close for b in bars[s]} for s in UNIVERSE}
    closes = {s: [idx[s][d] for d in common] for s in UNIVERSE}
    print(f"Universe {len(UNIVERSE)} coins, {len(common)} aligned days {common[0]} -> {common[-1]}\n")

    def window(lo, hi):
        return {s: closes[s][lo:hi] for s in UNIVERSE}, common[lo:hi]

    for name, (lo, hi) in [("FULL PERIOD", (0, len(common))),
                           ("SECOND HALF (out-of-sample look)", (len(common)//2, len(common)))]:
        cw, dw = window(lo, hi)
        print(f"=== {name} ({dw[0]} -> {dw[-1]}) ===")
        report("TS-trend basket (diversified)", ts_trend_basket(dw, cw))
        report("XS-momentum portfolio", xs_momentum(dw, cw))
        report("Equal-weight buy&hold", equal_weight_hold(cw))
        report("BTC buy&hold", [cw["BTC"][i] / cw["BTC"][0] for i in range(len(cw["BTC"]))])
        btc_bars = [b for b in bars["BTC"] if b.date[:10] in set(dw)]
        r = run_backtest(btc_bars, BotConfig(symbol="BTC", interval="1d",
                                             strategy=StrategyConfig(kind="trend")))
        print(f"  {'BTC trend (incumbent)':<26} return {r.strategy_return*100:>+7.0f}%   "
              f"sharpe {r.sharpe:>5.2f}   maxDD {r.max_drawdown*100:>3.0f}%")
        print()


if __name__ == "__main__":
    main()
