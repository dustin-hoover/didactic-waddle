"""Stress-test the strategies across REAL AMPL market regimes.

Uses the bundled full-history CSV (data/ampl_full.csv, sourced from DefiLlama:
2019 -> present, including the 2020 peak and the 2021-22 de-peg) and slices out
three regimes so the behaviour is grounded in real data, not a synthetic proxy.

    python scripts/fetch_ampl_history.py --source defillama --out data/ampl_full.csv
    python scripts/regime_test.py

Findings it reproduces (see README for the full discussion):
  * Bull:  buy & hold has the highest raw return but the deepest drawdown; pure
           mean reversion wins on risk-adjusted terms.
  * Crash: pure mean reversion beats buy & hold OUTRIGHT and by drawdown.
  * The "trend_mr" filter underperforms pure "mr" on real data everywhere — it
    was tuned on a synthetic downtrend and does not survive contact with real,
    choppy AMPL. Kept only for study.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.backtest import run_backtest  # noqa: E402
from ampl_bot.config import BotConfig  # noqa: E402
from ampl_bot.data import CsvPriceProvider, PriceBar  # noqa: E402
from ampl_bot.mechanics import compute_rebase  # noqa: E402

FULL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ampl_full.csv")


def buyhold(bars):
    pol = BotConfig().policy
    units = 10_000 / bars[0].price
    peak = 10_000.0
    mdd = 0.0
    for i, b in enumerate(bars):
        if i > 0:
            units *= 1 + compute_rebase(b.price, 1.0, pol).rebase_pct
        eq = units * b.price
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    return units * bars[-1].price / 10_000 - 1, mdd


def window(bars, lo, hi):
    return [b for b in bars if lo <= b.timestamp <= hi]


def report(label, bars):
    print(f"\n=== {label}  ({len(bars)} bars, {bars[0].timestamp} -> {bars[-1].timestamp}) ===")
    print(f"{'strategy':<12}{'return':>13}{'sharpe':>9}{'maxDD':>9}")
    print("-" * 43)
    for name in ("mr", "trend_mr"):
        cfg = BotConfig()
        cfg.strategy.name = name
        r = run_backtest(bars, cfg)
        print(f"{name:<12}{r.strategy_return:>+12.1%}{r.sharpe:>9.2f}{r.max_drawdown:>8.1%}")
    bh_ret, bh_dd = buyhold(bars)
    print(f"{'buy & hold':<12}{bh_ret:>+12.1%}{'—':>9}{bh_dd:>8.1%}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=FULL)
    args = p.parse_args()
    if not os.path.exists(args.csv):
        sys.exit("Run: python scripts/fetch_ampl_history.py --source defillama --out data/ampl_full.csv")

    bars = CsvPriceProvider(args.csv).history()
    report("BULL — recent ~1yr", bars[-365:])
    report("CRASH — real de-peg 2020-07 to 2022-12", window(bars, "2020-07-01", "2022-12-31"))
    report("FULL CYCLE — 2019 to present", bars)
    print(
        "\nCaveat: full-cycle ABSOLUTE returns are unreliable — the model uses a "
        "fixed CPI target, but AMPL's real target drifted over 7 years, and "
        "rebase compounding dominates long spans. Trust the RELATIVE comparisons "
        "and drawdowns, especially in the crash window."
    )


if __name__ == "__main__":
    main()
