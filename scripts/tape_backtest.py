"""Does the on-chain tape actually PREDICT? Validate before we trade it.

"Follow the tape, don't just predict" only earns a position if the tape has edge.
This harness pulls recent daily on-chain flow for a symbol, then tests whether a
day's net-flow imbalance (CVD) predicts the NEXT day's return:

  * Pearson correlation(imbalance_t, return_t+1)
  * directional hit-rate (does the sign of today's flow call tomorrow's move?)
  * mean forward return on accumulation days vs distribution days
  * a flow-following equity curve vs. buy & hold over the window

HONEST caveat up front: free public RPC can only serve a shallow, recent window,
and per-day flow here is estimated from up to ``max_swaps`` prints per day. This is
a SMALL-SAMPLE sniff test, not a multi-year proof. Treat a positive result as
"worth a real study on an archive node," and a negative/None result as "do not let
flow size a position yet." Set ETH_RPC_URL to your own node for a deeper window.

Usage:
  python scripts/tape_backtest.py --symbol ETH --days 10
  python scripts/tape_backtest.py --symbol LINK --days 7 --max-swaps 1500
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.onchain_feed import v3_price_usd
from tradebot.tape import (_SECS_PER_BLOCK, _TAPE_POOLS, decode_swap, latest_block,
                           pool_meta, _rpc, SWAP_TOPIC)

_DAY = 86_400


def _fetch_range(pool, meta, eth_price, lo, hi, span, max_swaps):
    prints = []
    cur = lo
    while cur <= hi and len(prints) < max_swaps:
        top = min(cur + span - 1, hi)
        try:
            logs = _rpc("eth_getLogs", [{"address": pool, "topics": [SWAP_TOPIC],
                                         "fromBlock": hex(cur), "toBlock": hex(top)}])
        except Exception:  # noqa: BLE001
            if span > 200:
                span //= 2
                continue
            cur = top + 1
            continue
        for log in logs or []:
            b = decode_swap(meta, log, eth_price=eth_price)
            if b:
                prints.append(b)
        cur = top + 1
    return prints


def daily_flow(symbol: str, days: int, max_swaps: int):
    """Return a list of per-day dicts: {imbalance, net_usd, close} oldest-first."""
    pool = _TAPE_POOLS.get(symbol.upper())
    if not pool:
        raise SystemExit(f"no configured pool for {symbol}")
    meta = pool_meta(pool)
    if meta is None:
        raise SystemExit(f"could not resolve pool metadata for {symbol}")
    eth_price = (v3_price_usd("ETH") or 0.0) if meta.quote == "WETH" else 0.0
    tip = latest_block()
    now = time.time()
    blocks_per_day = int(_DAY / _SECS_PER_BLOCK)
    out = []
    for d in range(days, 0, -1):
        hi = tip - (d - 1) * blocks_per_day
        lo = hi - blocks_per_day + 1
        prints = _fetch_range(pool, meta, eth_price, max(0, lo), hi, 800, max_swaps)
        if not prints:
            out.append(None)
            continue
        buy = sum(b.usd_size for b in prints if b.side == "BUY")
        sell = sum(b.usd_size for b in prints if b.side == "SELL")
        tot = buy + sell
        prints.sort(key=lambda b: b.block)
        out.append({"imbalance": (buy - sell) / tot if tot else 0.0,
                    "net_usd": buy - sell, "close": prints[-1].price, "n": len(prints)})
        print(f"  day -{d}: {len(prints)} prints  imb {out[-1]['imbalance']:+.3f}  "
              f"close ${out[-1]['close']:,.4f}", flush=True)
    return out


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (vx * vy) if vx and vy else None


def analyze(symbol, series):
    rows = [(i, s) for i, s in enumerate(series) if s]
    # pair imbalance_t with return_t+1, using consecutive available days
    imb, fwd = [], []
    acc_ret, dist_ret = [], []
    for k in range(len(series) - 1):
        a, b = series[k], series[k + 1]
        if not a or not b or not a["close"]:
            continue
        r = b["close"] / a["close"] - 1
        imb.append(a["imbalance"])
        fwd.append(r)
        (acc_ret if a["imbalance"] > 0 else dist_ret).append(r)
    print(f"\n=== {symbol}: tape edge over {len(series)} days ({len(imb)} usable pairs) ===")
    if len(imb) < 3:
        print("  too few usable days to judge — deepen the window (ETH_RPC_URL) and retry.")
        return
    corr = _pearson(imb, fwd)
    hits = sum(1 for i, r in zip(imb, fwd) if (i > 0) == (r > 0))
    print(f"  corr(imbalance_t, return_t+1) : {corr:+.3f}" if corr is not None else "  corr: n/a")
    print(f"  directional hit-rate          : {hits}/{len(imb)} = {hits/len(imb):.0%}")
    if acc_ret:
        print(f"  mean fwd return | accumulation : {sum(acc_ret)/len(acc_ret):+.2%} (n={len(acc_ret)})")
    if dist_ret:
        print(f"  mean fwd return | distribution : {sum(dist_ret)/len(dist_ret):+.2%} (n={len(dist_ret)})")
    # flow-following vs buy&hold (go long next day iff today's flow is positive)
    eq_flow, eq_hold = 1.0, 1.0
    for i, r in zip(imb, fwd):
        eq_hold *= (1 + r)
        if i > 0:
            eq_flow *= (1 + r)
    print(f"  flow-following return          : {eq_flow-1:+.2%}")
    print(f"  buy & hold return              : {eq_hold-1:+.2%}")
    print("\n  VERDICT: " + (
        "flow shows forward edge in this window — worth a deeper archive-node study."
        if (corr or 0) > 0.2 and hits / len(imb) > 0.5 else
        "no reliable forward edge in this small window — keep the tape as a RANKING/"
        "context tool; do not let it size positions yet."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--max-swaps", type=int, default=2000, dest="max_swaps")
    a = ap.parse_args()
    print(f"Pulling ~{a.days} days of on-chain flow for {a.symbol} "
          f"(≤{a.max_swaps} prints/day)…", flush=True)
    series = daily_flow(a.symbol, a.days, a.max_swaps)
    analyze(a.symbol.upper(), series)


if __name__ == "__main__":
    main()
