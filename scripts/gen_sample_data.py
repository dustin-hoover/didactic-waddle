"""Generate a synthetic AMPL price series for demos/tests.

This is NOT real market data. It is a mean-reverting-around-target series used
so the backtester and dashboard run out of the box. Replace data/sample_ampl.csv
with real history (timestamp,price CSV) to backtest against actual AMPL data.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.data import SyntheticPriceProvider, write_csv  # noqa: E402

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_ampl.csv")
    bars = SyntheticPriceProvider(days=540, target=1.019, seed=7).history()
    write_csv(bars, out)
    print(f"Wrote {len(bars)} bars to {out}")
