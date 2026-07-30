"""Live paper-trading loop driven by REAL market data.

Pulls the latest AMPL/USD price on an interval and steps the paper engine —
real signals on live data, simulated fills, no real orders. State persists to
data/portfolio_state.json so you can stop/restart.

    python run_paper.py --source onchain   --interval 3600   # on-chain spot hourly
    python run_paper.py --source coingecko --interval 3600   # CoinGecko latest
    python run_paper.py --source onchain --once              # single tick, then exit

The default interval is hourly because the rebase-timing thesis is a daily/
multi-day signal; polling faster just pays more fees for noise. For real cadence
you'd typically step once per day around the rebase window.
"""

import argparse
import time

from ampl_bot.config import BotConfig
from ampl_bot.engine import TradingEngine
from ampl_bot.feeds import CoinGeckoFeed, OnChainFeed


def make_feed(source: str):
    return OnChainFeed() if source == "onchain" else CoinGeckoFeed()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["onchain", "coingecko"], default="onchain")
    p.add_argument("--interval", type=int, default=3600, help="seconds between ticks")
    p.add_argument("--cash", type=float, default=10_000.0)
    p.add_argument("--once", action="store_true", help="run a single tick and exit")
    args = p.parse_args()

    cfg = BotConfig(mode="paper", starting_cash=args.cash)
    engine = TradingEngine(cfg)
    feed = make_feed(args.source)

    print(f"Live PAPER trading on {args.source} data. Ctrl-C to stop.\n")
    while True:
        try:
            bar = feed.latest()
            rep = engine.step(bar.timestamp, bar.price)
            print(
                f"{rep.timestamp}  ${rep.price:.4f}  {rep.zone:<12} "
                f"equity ${rep.equity:,.2f}  expo {rep.exposure:>4.0%}  {rep.action}"
            )
        except Exception as e:  # keep the loop alive across transient feed errors
            print(f"tick error: {e}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
