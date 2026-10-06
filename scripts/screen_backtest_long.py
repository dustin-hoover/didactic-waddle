"""Phase 2b: isolate the SELECTION edge from the gate, over a bear-inclusive window.

The first backtest ran only in a bull, where the BTC gate's cash-sitting crushed
returns and muddied the question. This one answers two things cleanly over
2021→2026 (which INCLUDES the brutal 2022 bear), with daily data paginated straight
from Binance.US (no CoinGecko history cap):

  1. Does the fundamental SELECTION have edge, independent of the gate?
     -> compare Screened top-N (UN-gated) vs Equal-weight-all (UN-gated) vs BTC B&H.
  2. Does the gate earn its keep once a real bear is in-sample?
     -> compare the UN-gated vs GATED version of the same screened basket (maxDD).

Point-in-time throughout: chain TVL as-of-date (DefiLlama), trailing-30d dollar
volume and trend from the price bars, universe membership gated by "did this coin
trade yet." Monthly rebalance, 10 bps turnover cost.

Residual bias: still today's surviving L1s (a dead chain isn't here) — but far less
severe than the short test, and the 2022 bear is the real stress we were missing.
"""

from __future__ import annotations

import json
import math
import os
import ssl
import sys
import time
import urllib.request
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.fundamentals import _pct_ranks

# (price symbol, Binance.US pair, DefiLlama chain slug). BNB excluded (not on Binance.US).
UNIVERSE = [
    ("ETH", "ETHUSDT", "Ethereum"), ("SOL", "SOLUSDT", "Solana"),
    ("AVAX", "AVAXUSDT", "Avalanche"), ("MATIC", "MATICUSDT", "Polygon"),
    ("ADA", "ADAUSDT", "Cardano"), ("DOT", "DOTUSDT", "Polkadot"),
    ("ATOM", "ATOMUSDT", "Cosmos"), ("NEAR", "NEARUSDT", "Near"),
    ("TRX", "TRXUSDT", "Tron"),
]
START = "2021-01-01"
COST = 0.001
TOP_N = 4


def _http_json(url, tries=4, timeout=40):
    ca = "/root/.ccr/ca-bundle.crt"
    ctx = ssl.create_default_context(cafile=ca) if os.path.exists(ca) else None
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e; time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"failed: {url[:70]} :: {last}")


def binance_daily(pair, start_ms):
    """Paginated daily klines -> {YYYY-MM-DD: (close, dollar_volume)}."""
    out, cur, now = {}, start_ms, int(time.time() * 1000)
    while cur < now:
        rows = _http_json(f"https://api.binance.us/api/v3/klines?symbol={pair}&interval=1d&limit=1000&startTime={cur}")
        if not rows:
            break
        for r in rows:
            d = dt.datetime.utcfromtimestamp(r[0] / 1000).strftime("%Y-%m-%d")
            out[d] = (float(r[4]), float(r[4]) * float(r[5]))
        if len(rows) < 1000:
            break
        cur = rows[-1][0] + 86_400_000
    return out


def chain_tvl(slug):
    d = _http_json(f"https://api.llama.fi/v2/historicalChainTvl/{slug}")
    return {dt.datetime.utcfromtimestamp(p["date"]).strftime("%Y-%m-%d"): float(p["tvl"]) for p in d}


def sma(xs, i, n):
    lo = max(0, i - n + 1)
    return sum(xs[lo:i + 1]) / (i - lo + 1)


def stats(daily):
    eq = [1.0]
    for r in daily:
        eq.append(eq[-1] * (1 + r))
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v); mdd = max(mdd, (peak - v) / peak)
    mu = sum(daily) / len(daily)
    sd = math.sqrt(sum((x - mu) ** 2 for x in daily) / (len(daily) - 1)) if len(daily) > 2 else 0
    return eq[-1] - 1, mdd, (mu / sd * math.sqrt(365) if sd else 0.0)


def main():
    start_ms = int(dt.datetime.strptime(START, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    print("paginating Binance.US daily history + DefiLlama TVL from", START, "…")
    btc = binance_daily("BTCUSDT", start_ms)
    dates = sorted(btc.keys())
    bclose = [btc[d][0] for d in dates]
    coins = {}
    for sym, pair, slug in UNIVERSE:
        try:
            px = binance_daily(pair, start_ms)
            tv = chain_tvl(slug)
            coins[sym] = {"px": px, "tvl": tv}
            first = min(px) if px else "-"
            print(f"  {sym}: {len(px)} days (from {first}), TVL pts {len(tv)}")
        except Exception as e:  # noqa: BLE001
            print(f"  {sym}: skipped ({str(e)[:40]})")
    syms = list(coins.keys())
    print(f"window {dates[0]} → {dates[-1]} ({len(dates)} days)\n")

    def ff(m, d):
        if d in m:
            return m[d]
        best = None
        for k in m:
            if k <= d and (best is None or k > best):
                best = k
        return m[best] if best else None

    def ret(sym, i):
        a = ff(coins[sym]["px"], dates[i - 1]); b = ff(coins[sym]["px"], dates[i])
        return (b[0] / a[0] - 1) if (a and b and a[0]) else 0.0

    warmup = 210
    W = {k: {s: 0.0 for s in syms} for k in ("ew_u", "scr_u", "scr_g")}
    pos_btc_g = 0.0
    dr = {k: [] for k in ("bh", "btc_g", "ew_u", "scr_u", "scr_g")}
    bear = {k: [] for k in dr}   # 2022 sub-sample

    for i in range(warmup, len(dates)):
        d = dates[i]
        gate = (bclose[i] > sma(bclose, i, 200)) and (sma(bclose, i, 20) > sma(bclose, i, 200))
        if d[:7] != dates[i - 1][:7]:
            # rank coins that already trade at date d
            live = [s for s in syms if ff(coins[s]["px"], d)]
            tvl = [ff(coins[s]["tvl"], d) for s in live]
            liq = []
            for s in live:
                vs = [ff(coins[s]["px"], dates[j]) for j in range(max(0, i - 30), i)]
                vs = [v[1] for v in vs if v]
                liq.append(sum(vs) / len(vs) if vs else None)
            tr = []
            for s in live:
                cs = [ff(coins[s]["px"], dates[j]) for j in range(max(0, i - 60), i + 1)]
                cs = [c[0] for c in cs if c]
                tr.append(1.0 if (len(cs) > 5 and cs[-1] > sum(cs) / len(cs)) else 0.0)
            rtvl = _pct_ranks([math.log10(v) if v and v > 0 else None for v in tvl])
            rliq = _pct_ranks([math.log10(v) if v and v > 0 else None for v in liq])
            score = {live[k]: 0.45 * rtvl[k] + 0.30 * rliq[k] + 0.25 * tr[k] for k in range(len(live))}
            picks = sorted(live, key=lambda s: score[s], reverse=True)[:TOP_N]
            new = {k: {s: 0.0 for s in syms} for k in W}
            for s in picks:
                new["scr_u"][s] = 1.0 / len(picks)
                new["scr_g"][s] = (1.0 / len(picks)) if gate else 0.0
            for s in live:
                new["ew_u"][s] = 1.0 / len(live)
            btc_t = 1.0 if gate else 0.0
            cost = {k: sum(abs(new[k][s] - W[k][s]) for s in syms) * COST for k in W}
            cost["btc_g"] = abs(btc_t - pos_btc_g) * COST
            W, pos_btc_g = new, btc_t
        else:
            cost = {k: 0.0 for k in ("ew_u", "scr_u", "scr_g", "btc_g")}

        rb = btc[dates[i]][0] / btc[dates[i - 1]][0] - 1
        row = {
            "bh": rb, "btc_g": pos_btc_g * rb - cost["btc_g"],
            "ew_u": sum(W["ew_u"][s] * ret(s, i) for s in syms) - cost["ew_u"],
            "scr_u": sum(W["scr_u"][s] * ret(s, i) for s in syms) - cost["scr_u"],
            "scr_g": sum(W["scr_g"][s] * ret(s, i) for s in syms) - cost["scr_g"],
        }
        for k in dr:
            dr[k].append(row[k])
            if d.startswith("2022"):
                bear[k].append(row[k])

    labels = [("BTC buy & hold", "bh"), ("BTC, gated", "btc_g"),
              ("Equal-weight all, UN-gated", "ew_u"),
              ("Screened top-%d, UN-gated" % TOP_N, "scr_u"),
              ("Screened top-%d, gated" % TOP_N, "scr_g")]
    print(f"=== FULL window {dates[warmup]} → {dates[-1]} ===")
    print(f"{'strategy':<28}{'return':>9}{'maxDD':>8}{'Sharpe':>8}")
    for name, k in labels:
        t, m, s = stats(dr[k])
        print(f"{name:<28}{t*100:>8.0f}%{m*100:>7.0f}%{s:>8.2f}")
    print(f"\n=== 2022 BEAR only ({len(bear['bh'])} days) — did the gate protect? ===")
    print(f"{'strategy':<28}{'return':>9}{'maxDD':>8}")
    for name, k in labels:
        if bear[k]:
            t, m, _ = stats(bear[k])
            print(f"{name:<28}{t*100:>8.0f}%{m*100:>7.0f}%")
    print("\nSelection edge = Screened-UNgated vs Equal-weight-UNgated & BTC B&H.")
    print("Gate value   = Screened-gated vs Screened-UNgated (esp. 2022 maxDD).")


if __name__ == "__main__":
    main()
