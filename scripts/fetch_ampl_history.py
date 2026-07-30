"""Fetch REAL AMPL/USD daily history from CoinGecko into a CSV.

    python scripts/fetch_ampl_history.py                 # max history -> data/ampl_history.csv
    python scripts/fetch_ampl_history.py --days 365 --out data/ampl_1y.csv

Requires network access. The output is a timestamp,price CSV the backtester and
dashboard can consume directly.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.data import write_csv  # noqa: E402
from ampl_bot.feeds import CoinGeckoFeed  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--days",
        default="365",
        help="'max' or an integer. Without a CoinGecko API key the public API "
        "caps free history at ~365 days; pass --api-key for more.",
    )
    p.add_argument("--out", default="data/ampl_history.csv")
    p.add_argument("--api-key", default=os.environ.get("COINGECKO_API_KEY"))
    args = p.parse_args()

    days = args.days if args.days == "max" else int(args.days)
    feed = CoinGeckoFeed(api_key=args.api_key)
    bars = feed.history(days=days)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_csv(bars, out)
    print(f"Wrote {len(bars)} real daily bars to {out}")
    print(f"Range: {bars[0].timestamp} -> {bars[-1].timestamp}")
    print(f"Latest AMPL/USD: ${bars[-1].price:.4f}")


if __name__ == "__main__":
    main()
