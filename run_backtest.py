"""CLI: run the backtest and print a summary.

    python run_backtest.py                 # uses data/sample_ampl.csv
    python run_backtest.py --csv mydata.csv
"""

import argparse
import os

from ampl_bot.backtest import run_backtest
from ampl_bot.config import BotConfig
from ampl_bot.data import CsvPriceProvider, SyntheticPriceProvider

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sample_ampl.csv")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=SAMPLE, help="timestamp,price CSV of AMPL/USD")
    p.add_argument("--cash", type=float, default=10_000.0)
    p.add_argument("--strategy", choices=["mr", "trend_mr"], default=None,
                   help="override the strategy (default: config)")
    args = p.parse_args()

    if os.path.exists(args.csv):
        bars = CsvPriceProvider(args.csv).history()
        src = args.csv
    else:
        bars = SyntheticPriceProvider().history()
        src = "synthetic (sample CSV not found)"

    cfg = BotConfig(starting_cash=args.cash)
    if args.strategy:
        cfg.strategy.name = args.strategy
    res = run_backtest(bars, cfg)
    print(f"Source: {src}  ({len(bars)} bars)\n")
    print(res.summary())


if __name__ == "__main__":
    main()
