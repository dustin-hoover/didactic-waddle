"""Stress-test the strategies across market regimes.

The single year of free real data is a bull run, which flatters
buy-and-hold and pure mean reversion. This script adds a synthetic *de-peg*
(sustained downtrend) so the capital-protection behaviour is visible — the
regime pure mean reversion is dangerous in.

    python scripts/regime_test.py [--csv data/ampl_history.csv]

Findings it reproduces:
  * Bull: pure MR edges out the trend filter on return; both beat buy & hold
    on risk-adjusted terms.
  * De-peg: pure MR catches the falling knife (huge drawdown); the gated
    trend filter caps the drawdown dramatically. That is the whole point of it.
"""

import argparse
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.backtest import run_backtest  # noqa: E402
from ampl_bot.config import BotConfig  # noqa: E402
from ampl_bot.data import CsvPriceProvider, PriceBar  # noqa: E402
from ampl_bot.mechanics import compute_rebase  # noqa: E402


def synth_depeg(days: int = 365, start_price: float = 1.20, drift: float = -0.006, seed: int = 11):
    rng = random.Random(seed)
    price = start_price
    bars = []
    d0 = date(2024, 1, 1)
    for i in range(days):
        price *= 1 + drift + rng.gauss(0, 0.05)
        price = max(0.10, price)
        bars.append(PriceBar((d0 + timedelta(days=i)).isoformat(), round(price, 6)))
    return bars


def buyhold_return(bars):
    pol = BotConfig().policy
    units = 10_000 / bars[0].price
    peak = 10_000
    mdd = 0.0
    for i, b in enumerate(bars):
        if i > 0:
            units *= 1 + compute_rebase(b.price, 1.0, pol).rebase_pct
        eq = units * b.price
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    return units * bars[-1].price / 10_000 - 1, mdd


def report(label, bars):
    print(f"\n=== {label}  ({len(bars)} bars, {bars[0].price} -> {bars[-1].price}) ===")
    print(f"{'strategy':<12}{'return':>11}{'sharpe':>9}{'maxDD':>9}")
    print("-" * 41)
    for name in ("mr", "trend_mr"):
        cfg = BotConfig()
        cfg.strategy.name = name
        r = run_backtest(bars, cfg)
        print(f"{name:<12}{r.strategy_return:>+10.1%}{r.sharpe:>9.2f}{r.max_drawdown:>8.1%}")
    bh_ret, bh_dd = buyhold_return(bars)
    print(f"{'buy & hold':<12}{bh_ret:>+10.1%}{'—':>9}{bh_dd:>8.1%}")


def main():
    p = argparse.ArgumentParser()
    default = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ampl_history.csv")
    p.add_argument("--csv", default=default)
    args = p.parse_args()

    if os.path.exists(args.csv):
        report("BULL — real AMPL", CsvPriceProvider(args.csv).history())
    report("DE-PEG — synthetic downtrend", synth_depeg())
    print(
        "\nNote: the de-peg is synthetic; treat its magnitudes as illustrative, "
        "not a forecast. The robust takeaway is the DRAWDOWN gap: pure MR is "
        "dangerous in a sustained decline, the gated trend filter is not."
    )


if __name__ == "__main__":
    main()
