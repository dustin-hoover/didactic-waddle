"""Fetch REAL AMPL/USD daily history into a CSV.

    # Full multi-year history (2019->now), free, no key -- the good one:
    python scripts/fetch_ampl_history.py --source defillama --out data/ampl_full.csv

    # CoinGecko (public tier caps at ~365 days without a key):
    python scripts/fetch_ampl_history.py --source coingecko --days 365

Requires network access. Output is a timestamp,price CSV the backtester and
dashboard consume directly.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.data import write_csv  # noqa: E402
from ampl_bot.feeds import CoinGeckoFeed, DefiLlamaFeed  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["defillama", "coingecko"], default="defillama",
                   help="defillama = full multi-year history (recommended)")
    p.add_argument(
        "--days",
        default="365",
        help="CoinGecko only: 'max' or an integer. The public tier caps free "
        "history at ~365 days; pass --api-key for more.",
    )
    p.add_argument("--out", default="data/ampl_full.csv")
    p.add_argument("--api-key", default=os.environ.get("COINGECKO_API_KEY"))
    args = p.parse_args()

    if args.source == "defillama":
        bars = DefiLlamaFeed().history()
    else:
        days = args.days if args.days == "max" else int(args.days)
        bars = CoinGeckoFeed(api_key=args.api_key).history(days=days)

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_csv(bars, out)
    print(f"Wrote {len(bars)} real daily bars to {out}  (source: {args.source})")
    print(f"Range: {bars[0].timestamp} -> {bars[-1].timestamp}")
    peak = max(bars, key=lambda b: b.price)
    trough = min(bars, key=lambda b: b.price)
    print(f"Peak:   {peak.timestamp} ${peak.price:.3f}")
    print(f"Trough: {trough.timestamp} ${trough.price:.3f}")
    print(f"Latest: ${bars[-1].price:.4f}")


if __name__ == "__main__":
    main()
