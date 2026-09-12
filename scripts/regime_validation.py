"""Bull-period validation of the regime gate — does it cost us in confirmed bulls?

The open question after the strategy work: gating beats buy&hold over a full cycle by
sitting out bears, but does it 'give up upside in bull rips'? This isolates the BULL
(gate-ON) days and measures how much of buy&hold's gain the gated engine captures.

Four books, multi-year daily, net of cost, no lookahead (act on prior-day state):
  BH            buy & hold
  TREND         trend filter only (no regime gate) — the asset's OWN trend
  GATE          regime gate only (long when BTC bull confirmed, else cash)
  GATED-TREND   trend AND gate (the wired system): long only when trend up AND bull on
Every day is bucketed BULL (gate ON) vs BEAR (gate OFF); BH and GATED-TREND are
compounded within each bucket so bull-period capture reads directly.

FINDINGS (run 2026-09 over ~3.5y of BTC/ETH daily):
  * BTC: 95% bull-period capture (BH +123% vs gated +117% on bull days) while cutting
    full-cycle drawdown 53%->27%. The gate does NOT cost upside in bulls; the
    full-cycle gap to buy&hold is from sitting out OFF-periods that later bounced.
  * ETH: gating an ALT by BTC's regime is too blunt — ETH's OWN trend made +108% but
    ETH-gated-by-BTC made only +8%, because the BTC gate was OFF during some of ETH's
    best runs. Lesson: BTC is the right MACRO switch, but a tradeable alt should be
    gated by its own trend (BTC as an overlay), not hard-gated on BTC alone.
Regime-dependent; one window. Re-run to refresh.

Usage:  python scripts/regime_validation.py [SYM ...]   (default: BTC ETH)
"""

from __future__ import annotations

import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.ohlcv import ExchangeFeed          # noqa: E402
from tradebot.regime import sweep                 # noqa: E402
from tradebot.signals import TrendFilterStrategy  # noqa: E402

ANN, COST = math.sqrt(365), 0.002


def _metrics(curve):
    r = [curve[i]/curve[i-1]-1 for i in range(1, len(curve)) if curve[i-1] > 0]
    if not r:
        return 0.0, 0.0, 0.0
    mu, sd = statistics.fmean(r), statistics.pstdev(r)
    sh = 0.0 if sd == 0 else mu/sd*ANN
    pk, mdd = -1e9, 0.0
    for v in curve:
        pk = max(pk, v); mdd = max(mdd, 1-v/pk) if pk > 0 else mdd
    return curve[-1]/curve[0]-1, sh, mdd


def run(sym, feed):
    bars = feed.history(sym, "1d", 1300)
    closes = [b.close for b in bars]
    gate = sweep(closes)
    tf = TrendFilterStrategy("swing")
    tgt = [tf.generate(bars[:i+1]).target_exposure for i in range(len(bars))]
    start = 200
    books = {"BH": [], "TREND": [], "GATE": [], "GATED-TREND": []}
    eq = {k: 1.0 for k in books}; pos = {k: 0.0 for k in books}
    bull = {"BH": 1.0, "GATED-TREND": 1.0}; bear = {"BH": 1.0, "GATED-TREND": 1.0}
    bull_days = bear_days = 0
    for i in range(start+1, len(closes)):
        r = closes[i]/closes[i-1]-1
        g, t = gate[i-1], tgt[i-1]
        want = {"BH": 1.0, "TREND": t, "GATE": 1.0 if g else 0.0,
                "GATED-TREND": t if g else 0.0}
        for k in books:
            if want[k] != pos[k]:
                eq[k] *= (1 - COST*abs(want[k]-pos[k])); pos[k] = want[k]
            eq[k] *= (1 + pos[k]*r); books[k].append(eq[k])
        tgt_gt = want["GATED-TREND"]
        if g:
            bull_days += 1; bull["BH"] *= (1+r); bull["GATED-TREND"] *= (1+tgt_gt*r)
        else:
            bear_days += 1; bear["BH"] *= (1+r); bear["GATED-TREND"] *= (1+tgt_gt*r)

    tot = bull_days + bear_days
    print(f"\n=== {sym} — {len(closes)} days, {bull_days} bull / {bear_days} bear "
          f"(gate ON {100*bull_days/tot:.0f}%) ===")
    for k in books:
        tr, sh, dd = _metrics([1.0]+books[k])
        print(f"  {k:12} ret {tr*100:+8.1f}%   Sharpe {sh:+5.2f}   maxDD {dd*100:4.0f}%")
    bh_b, gt_b = (bull["BH"]-1), (bull["GATED-TREND"]-1)
    cap = f"{100*gt_b/bh_b:.0f}% capture" if bh_b > 0 else "(buy&hold was NET NEGATIVE on bull days)"
    print("  -- conditional --")
    print(f"  BULL days: buy&hold {bh_b*100:+7.1f}%   gated-trend {gt_b*100:+7.1f}%   {cap}")
    print(f"  BEAR days: buy&hold {(bear['BH']-1)*100:+7.1f}%   gated-trend "
          f"{(bear['GATED-TREND']-1)*100:+7.1f}%  (gate sat these out)")


def main():
    syms = sys.argv[1:] or ["BTC", "ETH"]
    feed = ExchangeFeed()
    for s in syms:
        try:
            run(s, feed)
        except Exception as e:  # noqa: BLE001
            print(f"{s}: ERROR {e}")


if __name__ == "__main__":
    main()
