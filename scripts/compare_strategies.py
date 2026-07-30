"""A/B the strategies on the same price series.

    python scripts/compare_strategies.py --csv data/ampl_history.csv

Prints a side-by-side table so the trend filter's effect is honest and visible,
including how each compares to simply buying and holding.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.backtest import run_backtest  # noqa: E402
from ampl_bot.config import BotConfig  # noqa: E402
from ampl_bot.data import CsvPriceProvider, SyntheticPriceProvider  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    default = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ampl_history.csv")
    p.add_argument("--csv", default=default)
    p.add_argument("--cash", type=float, default=10_000.0)
    args = p.parse_args()

    if os.path.exists(args.csv):
        bars = CsvPriceProvider(args.csv).history()
        src = args.csv
    else:
        bars = SyntheticPriceProvider().history()
        src = "synthetic"

    print(f"Source: {src}  ({len(bars)} bars)\n")
    header = f"{'strategy':<12}{'return':>10}{'sharpe':>9}{'maxDD':>9}{'trades':>8}{'vs B&H':>10}"
    print(header)
    print("-" * len(header))

    bh = None
    for name in ("mr", "trend_mr"):
        cfg = BotConfig(starting_cash=args.cash)
        cfg.strategy.name = name
        res = run_backtest(bars, cfg)
        bh = res.buyhold_return
        edge = res.strategy_return - res.buyhold_return
        print(
            f"{name:<12}{res.strategy_return:>+9.1%}{res.sharpe:>9.2f}"
            f"{res.max_drawdown:>8.1%}{res.num_trades:>8}{edge:>+10.1%}"
        )
    print("-" * len(header))
    print(f"{'buy & hold':<12}{bh:>+9.1%}")


if __name__ == "__main__":
    main()
