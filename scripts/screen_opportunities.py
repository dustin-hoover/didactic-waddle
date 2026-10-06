"""Live opportunity screener — rank the top-100–150 by real quality, right now.

Pulls CoinGecko markets + DefiLlama TVL/fees, layers the validated trend read onto
the fundamental+liquidity shortlist, and prints the ranked board. Read-only research;
places no orders.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import fundamentals as fnd


def _fmt_usd(x):
    if not x:
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if x >= div:
            return f"${x/div:.1f}{unit}"
    return f"${x:.0f}"


def main(top_n: int = 20, trend_n: int = 30):
    print("pulling universe (CoinGecko markets + DefiLlama TVL/fees)…")
    coins = fnd.fetch_universe()
    print(f"  {len(coins)} coins; "
          f"{sum(1 for c in coins if c.tvl_usd)} with TVL, "
          f"{sum(1 for c in coins if c.fees24_usd)} with fees")

    # First pass: rank on usage + liquidity (no trend yet) to get a shortlist.
    shortlist = fnd.rank(coins, weights=fnd.ScoreWeights(usage=0.6, liquidity=0.4, trend=0.0),
                         top_n=trend_n)
    short_syms = {r["symbol"] for r in shortlist}

    # Layer the validated trend read onto just the shortlist (keeps price pulls small).
    try:
        from tradebot.ohlcv import get_feed
        from tradebot.signals import TrendFilterStrategy
        feed = get_feed()
        tf = TrendFilterStrategy("swing")
        trend_by_sym = {}
        for c in coins:
            if c.symbol in short_syms:
                try:
                    bars = feed.history(c.symbol, "1d", 260)
                    sig = tf.generate(bars)
                    trend_by_sym[c.symbol] = sig.target_exposure * 2 - 1  # [0,1]->[-1,1]
                except Exception:  # noqa: BLE001
                    pass
        for c in coins:
            if c.symbol in trend_by_sym:
                c.trend_strength = trend_by_sym[c.symbol]
        print(f"  trend measured for {len(trend_by_sym)}/{len(short_syms)} shortlisted names")
    except Exception as e:  # noqa: BLE001
        print(f"  (trend layer skipped: {e})")

    # Final composite ranking (usage + liquidity + trend).
    board = fnd.rank(coins, top_n=top_n)
    print(f"\n{'#':>2}  {'sym':<8}{'rank':>5}{'mcap':>9}{'vol24':>9}{'TVL':>9}{'fees24':>9}"
          f"{'use':>6}{'liq':>6}{'trend':>7}{'SCORE':>8}")
    for i, r in enumerate(board, 1):
        print(f"{i:>2}  {r['symbol']:<8}{(r['mcap_rank'] or '?'):>5}{_fmt_usd(r['mcap_usd']):>9}"
              f"{_fmt_usd(r['vol24_usd']):>9}{_fmt_usd(r['tvl_usd']):>9}{_fmt_usd(r['fees24_usd']):>9}"
              f"{r['usage_score']:>6.2f}{r['liquidity_score']:>6.2f}{r['trend_score']:>7.2f}"
              f"{r['score']:>8.3f}")
    print("\nUsage=TVL+fees · Liq=24h volume · Trend=validated filter. Read-only; "
          "the BTC gate still governs whether we'd open new longs.")


if __name__ == "__main__":
    main()
