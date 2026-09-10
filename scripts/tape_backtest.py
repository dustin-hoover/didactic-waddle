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
from tradebot.tape_journal import _pearson  # single canonical implementation

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


def daily_flow(symbol: str, days: int, max_swaps: int, sample_blocks: int = 900):
    """Return a list of per-day dicts: {imbalance, net_usd, close} oldest-first.

    We do NOT scan whole days — busy pools (e.g. ETH/USDC) emit tens of thousands
    of swaps a day and blow past RPC result caps, which is slow and flaky. Instead
    we sample a fixed ``sample_blocks`` slice ending at each day's boundary (~900
    blocks ≈ ~3h ≈ a few hundred prints). The slice is the SAME size and time-of-
    day offset every day, so the imbalance and the forward return are comparable
    across days — a consistent estimator, at a tiny fraction of the RPC cost.
    """
    pool = _TAPE_POOLS.get(symbol.upper())
    if not pool:
        raise SystemExit(f"no configured pool for {symbol}")
    meta = pool_meta(pool)
    if meta is None:
        raise SystemExit(f"could not resolve pool metadata for {symbol}")
    eth_price = (v3_price_usd("ETH") or 0.0) if meta.quote == "WETH" else 0.0
    tip = latest_block()
    blocks_per_day = int(_DAY / _SECS_PER_BLOCK)
    out = []
    for d in range(days, 0, -1):
        hi = tip - (d - 1) * blocks_per_day
        lo = hi - sample_blocks + 1
        prints = _fetch_range(pool, meta, eth_price, max(0, lo), hi, sample_blocks, max_swaps)
        if not prints:
            out.append(None)
            print(f"  day -{d}: no prints", flush=True)
            continue
        buy = sum(b.usd_size for b in prints if b.side == "BUY")
        sell = sum(b.usd_size for b in prints if b.side == "SELL")
        tot = buy + sell
        # "Strong hands" cohort: the largest prints of the slice (top decile, >=5),
        # a scale-free proxy so ETH and a thin alt are treated comparably. This is
        # the whale-specific test — does the BIGGEST money predict, even if
        # aggregate (retail-dominated) flow doesn't?
        by_size = sorted(prints, key=lambda b: b.usd_size, reverse=True)
        k = max(5, len(by_size) // 10)
        whales = by_size[:k]
        w_gross = sum(b.usd_size for b in whales)
        w_net = sum(b.signed_usd for b in whales)
        prints.sort(key=lambda b: b.block)
        out.append({"imbalance": (buy - sell) / tot if tot else 0.0,
                    "net_usd": buy - sell, "close": prints[-1].price, "n": len(prints),
                    "wimb": (w_net / w_gross) if w_gross else 0.0, "wn": len(whales)})
        print(f"  day -{d}: {len(prints)} prints  imb {out[-1]['imbalance']:+.3f}  "
              f"whale {out[-1]['wimb']:+.3f}  close ${out[-1]['close']:,.4f}", flush=True)
    return out




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


def _run_journal(path):
    from tradebot import tape_journal as tj
    j = tj.load(path)
    r = tj.analyze(j)
    print(f"=== accumulated flow journal: {path} ===")
    print(f"  days {r['n_days']}  symbols {r['n_symbols']}  usable pairs {r['n_pairs']}")
    if r.get("corr") is not None:
        print(f"  corr(imbalance_t, return_t+1) : {r['corr']:+.3f}")
        print(f"  directional hit-rate          : {r['hit_rate']:.0%}")
        if r.get("mean_fwd_accumulation") is not None:
            print(f"  mean fwd | accumulation       : {r['mean_fwd_accumulation']:+.2%}")
        if r.get("mean_fwd_distribution") is not None:
            print(f"  mean fwd | distribution       : {r['mean_fwd_distribution']:+.2%}")
        print(f"  flow-following / buy&hold     : {r['flow_following_return']:+.2%} / {r['buyhold_return']:+.2%}")
    w = r.get("whale")
    if w and w.get("corr") is not None:
        print(f"  -- WHALE-only (strong hands), {w['n_pairs']} pairs --")
        print(f"  corr(whale_t, return_t+1)     : {w['corr']:+.3f}")
        print(f"  directional hit-rate          : {w['hit_rate']:.0%}")
        if w.get("mean_fwd_accumulation") is not None:
            print(f"  mean fwd | whale accumulation : {w['mean_fwd_accumulation']:+.2%}")
        if w.get("mean_fwd_distribution") is not None:
            print(f"  mean fwd | whale distribution : {w['mean_fwd_distribution']:+.2%}")
        print(f"  whale-following / buy&hold    : {w['flow_following_return']:+.2%} / {w['buyhold_return']:+.2%}")
    print(f"  VERDICT: {r['verdict']}")


def _run_backfill(path, symbols, days, max_swaps, sample_blocks=900):
    """Pull ``days`` of history for each symbol and write it into the journal.

    Lets a keyed archive RPC (repo secret ETH_RPC_URL) populate weeks of real
    flow in one run — the key never leaves the repo. Dates are calendar days
    counted back from today (day 1 = most recent full window).
    """
    from tradebot import tape_journal as tj
    journal = tj.load(path)
    for sym in symbols:
        print(f"backfilling {sym} ({days}d)…", flush=True)
        series = daily_flow(sym, days, max_swaps, sample_blocks=sample_blocks)
        for j, entry in enumerate(series):
            if not entry:
                continue
            d = days - j                       # oldest-first -> day index
            date = tj.date_days_ago(d - 1)     # day 1 == today
            journal.setdefault("days", {}).setdefault(date, {})[sym.upper()] = {
                "imb": round(entry["imbalance"], 4), "net": round(entry["net_usd"]),
                "price": entry["close"], "wimb": round(entry.get("wimb", 0.0), 4),
                "wn": entry.get("wn", 0)}
        tj.save(path, journal)
    print(f"\nwrote {path}\n")
    _run_journal(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="ETH")
    ap.add_argument("--symbols", default="", help="comma-separated (backfill mode)")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--max-swaps", type=int, default=1500, dest="max_swaps")
    ap.add_argument("--sample-blocks", type=int, default=900, dest="sample_blocks",
                    help="block-slice sampled per day (consistent estimator; ~900≈3h)")
    ap.add_argument("--journal", default="", help="analyze an accumulated tape_journal.json instead of live pulls")
    ap.add_argument("--backfill", default="", help="path to write: pull history into a journal for many symbols")
    a = ap.parse_args()
    if a.journal:
        _run_journal(a.journal)
        return
    if a.backfill:
        syms = a.symbols.split(",") if a.symbols else [a.symbol]
        _run_backfill(a.backfill, syms, a.days, a.max_swaps, a.sample_blocks)
        return
    print(f"Pulling ~{a.days} days of on-chain flow for {a.symbol} "
          f"(≤{a.max_swaps} prints/day)…", flush=True)
    series = daily_flow(a.symbol, a.days, a.max_swaps, sample_blocks=a.sample_blocks)
    analyze(a.symbol.upper(), series)


if __name__ == "__main__":
    main()
