"""Phase 2: does the fundamentally-screened basket actually beat BTC-only?

The make-or-break test for tradebot.fundamentals. We rank a universe of major
L1/L2 tokens MONTHLY on POINT-IN-TIME signals (no lookahead):
  * usage     — that chain's TVL as of the rebalance date (DefiLlama historical)
  * liquidity — trailing-30d dollar volume from price bars
  * trend     — price above its 50d SMA, causally
…take the top-N equal-weight, but only while the BTC regime gate is ON (else cash).
Rebalanced monthly with a transaction cost. Compared against the honest benchmarks:

  * BTC buy & hold                    (the thing to beat)
  * BTC, gated                        (hold BTC when gate ON, cash when OFF)
  * Equal-weight ALL, gated           (alts in a bull, but NO selection skill)
  * Screened top-N, gated             (the thesis: selection adds value)

If "Screened top-N" doesn't beat BOTH "BTC gated" (is the basket worth it?) and
"EW-all gated" (does the RANKING add anything over just holding everything?), the
screen has no demonstrated edge — and we say so.

HONEST BIASES (stated loudly): the universe is TODAY's survivors with long history,
so membership carries survivorship bias (a coin that died isn't here) — this flatters
the result. TVL is point-in-time but universe membership is not. Crypto history is
short (one-ish regime). Treat the output as necessary-not-sufficient evidence.
"""

from __future__ import annotations

import json
import math
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.ohlcv import get_feed
from tradebot.fundamentals import _pct_ranks

# (price symbol, DefiLlama chain slug) — majors with long history + clean chain TVL.
UNIVERSE = [
    ("ETH", "Ethereum"), ("SOL", "Solana"), ("BNB", "BSC"), ("AVAX", "Avalanche"),
    ("MATIC", "Polygon"), ("NEAR", "Near"), ("ADA", "Cardano"), ("TRX", "Tron"),
    ("DOT", "Polkadot"), ("ATOM", "Cosmos"),
]
COST = 0.001        # 10 bps per unit of turnover, one side
TOP_N = 4


def _http_json(url):
    ca = "/root/.ccr/ca-bundle.crt"
    ctx = ssl.create_default_context(cafile=ca) if os.path.exists(ca) else None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return json.loads(r.read())


def chain_tvl_by_date(slug):
    """{YYYY-MM-DD: tvl} from DefiLlama historical chain TVL."""
    import datetime as dt
    d = _http_json(f"https://api.llama.fi/v2/historicalChainTvl/{slug}")
    return {dt.datetime.utcfromtimestamp(p["date"]).strftime("%Y-%m-%d"): float(p["tvl"]) for p in d}


def sma(xs, i, n):
    lo = max(0, i - n + 1)
    return sum(xs[lo:i + 1]) / (i - lo + 1)


def stats(daily):
    eq = [1.0]
    for r in daily:
        eq.append(eq[-1] * (1 + r))
    total = eq[-1] - 1
    peak = eq[0]; mdd = 0.0
    for v in eq:
        peak = max(peak, v); mdd = max(mdd, (peak - v) / peak)
    if len(daily) > 2:
        mu = sum(daily) / len(daily)
        sd = math.sqrt(sum((x - mu) ** 2 for x in daily) / (len(daily) - 1))
        sharpe = mu / sd * math.sqrt(365) if sd else 0.0
    else:
        sharpe = 0.0
    return total, mdd, sharpe


def main():
    feed = get_feed()
    print("fetching BTC + universe price history and chain TVL (point-in-time)…")
    btc = feed.history("BTC", "1d", 1000)
    dates = [b.date[:10] for b in btc]
    btc_close = [b.close for b in btc]
    idx = {d: i for i, d in enumerate(dates)}

    coins = {}
    for sym, slug in UNIVERSE:
        try:
            bars = feed.history(sym, "1d", 1000)
            close = {b.date[:10]: b.close for b in bars}
            dvol = {b.date[:10]: b.close * b.volume for b in bars}
            tvl = chain_tvl_by_date(slug)
            coins[sym] = {"close": close, "dvol": dvol, "tvl": tvl}
            print(f"  {sym}: {len(bars)} bars, TVL points {len(tvl)}")
        except Exception as e:  # noqa: BLE001
            print(f"  {sym}: skipped ({str(e)[:50]})")
    syms = list(coins.keys())

    def ff(m, d):  # latest value in map m at or before date d
        if d in m:
            return m[d]
        best = None
        for k in m:
            if k <= d and (best is None or k > best):
                best = k
        return m[best] if best else None

    # daily returns per coin (aligned to BTC dates)
    def ret(sym, i):
        c0 = ff(coins[sym]["close"], dates[i - 1]); c1 = ff(coins[sym]["close"], dates[i])
        return (c1 / c0 - 1) if (c0 and c1) else 0.0

    warmup = 210
    w_scr = {s: 0.0 for s in syms}
    w_ew = {s: 0.0 for s in syms}
    pos_btc = 0.0
    dr = {"bh": [], "btc_gate": [], "ew_gate": [], "screen": []}

    for i in range(warmup, len(dates)):
        d = dates[i]
        # BTC regime gate, causal
        gate = (btc_close[i] > sma(btc_close, i, 200)) and (sma(btc_close, i, 20) > sma(btc_close, i, 200))

        # monthly rebalance (first trading day of a new month)
        if d[:7] != dates[i - 1][:7]:
            new_scr = {s: 0.0 for s in syms}
            new_ew = {s: 0.0 for s in syms}
            btc_target = 1.0 if gate else 0.0
            if gate:
                tvl_v, liq_v, tr_v = [], [], []
                for s in syms:
                    tvl_v.append(ff(coins[s]["tvl"], d))
                    # trailing-30d mean dollar volume
                    vols = [ff(coins[s]["dvol"], dates[j]) for j in range(max(0, i - 30), i)]
                    vols = [v for v in vols if v]
                    liq_v.append(sum(vols) / len(vols) if vols else None)
                    # trend: price > 50d SMA (causal)
                    cs = [ff(coins[s]["close"], dates[j]) for j in range(max(0, i - 60), i + 1)]
                    cs = [c for c in cs if c]
                    tr_v.append(1.0 if (len(cs) > 5 and cs[-1] > sum(cs) / len(cs)) else 0.0)
                tr_tvl = _pct_ranks([math.log10(v) if v and v > 0 else None for v in tvl_v])
                tr_liq = _pct_ranks([math.log10(v) if v and v > 0 else None for v in liq_v])
                score = [0.45 * tr_tvl[k] + 0.30 * tr_liq[k] + 0.25 * tr_v[k] for k in range(len(syms))]
                ranked = sorted(range(len(syms)), key=lambda k: score[k], reverse=True)
                picks = [syms[k] for k in ranked[:TOP_N]]
                for s in picks:
                    new_scr[s] = 1.0 / len(picks)
                for s in syms:
                    new_ew[s] = 1.0 / len(syms)
            # apply turnover cost as a one-day drag
            cost_scr = sum(abs(new_scr[s] - w_scr[s]) for s in syms) * COST
            cost_ew = sum(abs(new_ew[s] - w_ew[s]) for s in syms) * COST
            cost_btc = abs(btc_target - pos_btc) * COST
            w_scr, w_ew = new_scr, new_ew
            pos_btc = btc_target
        else:
            cost_scr = cost_ew = cost_btc = 0.0

        rb = btc_close[i] / btc_close[i - 1] - 1
        dr["bh"].append(rb)
        dr["btc_gate"].append(pos_btc * rb - cost_btc)
        dr["ew_gate"].append(sum(w_ew[s] * ret(s, i) for s in syms) - cost_ew)
        dr["screen"].append(sum(w_scr[s] * ret(s, i) for s in syms) - cost_scr)

    span = f"{dates[warmup]} → {dates[-1]} ({len(dr['bh'])} days)"
    print(f"\n=== Phase 2 backtest — monthly rebalance, {TOP_N}-pick, 10bps cost ===\n{span}\n")
    print(f"{'strategy':<26}{'return':>9}{'maxDD':>8}{'Sharpe':>8}")
    labels = [("BTC buy & hold", "bh"), ("BTC, gated", "btc_gate"),
              ("Equal-weight all, gated", "ew_gate"), ("Screened top-%d, gated" % TOP_N, "screen")]
    for name, k in labels:
        t, m, s = stats(dr[k])
        print(f"{name:<26}{t*100:>8.1f}%{m*100:>7.0f}%{s:>8.2f}")
    print("\nVerdict rule: the screen earns its place only if 'Screened' beats BOTH "
          "'BTC, gated' and 'Equal-weight all, gated' on risk-adjusted terms.")
    print("Biases: universe = today's survivors (optimistic); TVL point-in-time but "
          "membership is not; short history.")


if __name__ == "__main__":
    main()
