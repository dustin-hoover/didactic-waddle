"""tradebot CLI — backtest, screen, and paper-trade any crypto.

    python tb.py backtest --symbol BTC --interval 4h --style swing
    python tb.py backtest --symbol ETH --interval 1d --kind composite   # experimental
    python tb.py screen  --interval 4h --style swing
    python tb.py paper   --symbol BTC --interval 1h --once

Long/flat spot, paper only. Data comes from public exchange OHLCV (no key).
"""

import argparse
import time

from tradebot.backtest import run_backtest
from tradebot.config import BotConfig, StrategyConfig
from tradebot.engine import TradingEngine
from tradebot.ohlcv import ExchangeFeed
from tradebot.screener import DEFAULT_UNIVERSE, screen


def cmd_backtest(a):
    bars = ExchangeFeed().history(a.symbol, a.interval, a.limit)
    cfg = BotConfig(symbol=a.symbol, interval=a.interval,
                    strategy=StrategyConfig(kind=a.kind, style=a.style))
    r = run_backtest(bars, cfg)
    print(f"{a.symbol} {a.interval} [{a.kind}/{a.style}]  ({len(bars)} bars: "
          f"{bars[0].date[:10]} -> {bars[-1].date[:10]})\n")
    print(r.summary())


def cmd_screen(a):
    uni = a.symbols.split(",") if a.symbols else DEFAULT_UNIVERSE
    rows = screen(uni, interval=a.interval, style=a.style)
    print(f"Screen [{a.style} {a.interval}] — ranked by trend then conviction\n")
    print(f"{'sym':<6}{'price':>12}{'trend':>7}{'score':>8}{'rsi':>6}{'atr%':>7}")
    print("-" * 46)
    for r in rows:
        if r.error:
            print(f"{r.symbol:<6} ERROR {r.error[:40]}")
            continue
        print(f"{r.symbol:<6}{r.price:>12.4f}{('UP' if r.trend_up else 'down'):>7}"
              f"{r.score:>+8.2f}{(r.rsi or 0):>6.0f}{(r.atr_pct or 0) * 100:>6.1f}%")


def cmd_paper(a):
    cfg = BotConfig(mode="paper", symbol=a.symbol, interval=a.interval,
                    strategy=StrategyConfig(kind=a.kind, style=a.style))
    engine = TradingEngine(cfg)
    feed = ExchangeFeed()
    print(f"Live PAPER [{a.kind}/{a.style}] on {a.symbol} {a.interval}. Ctrl-C to stop.\n")
    while True:
        try:
            bars = feed.history(a.symbol, a.interval, 400)
            rep = engine.step(bars)
            print(f"{rep.ts}  ${rep.price:,.4f}  equity ${rep.equity:,.2f}  "
                  f"expo {rep.exposure:>4.0%}  {rep.action}  | {rep.reason}")
        except Exception as e:  # noqa: BLE001
            print(f"tick error: {e}")
        if a.once:
            break
        time.sleep(a.interval_seconds)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest")
    b.add_argument("--symbol", default="BTC")
    b.add_argument("--interval", default="4h")
    b.add_argument("--kind", choices=["trend", "composite"], default="trend")
    b.add_argument("--style", choices=["swing", "day"], default="swing")
    b.add_argument("--limit", type=int, default=1000)
    b.set_defaults(fn=cmd_backtest)

    s = sub.add_parser("screen")
    s.add_argument("--symbols", default="", help="comma-separated; default is a 10-coin universe")
    s.add_argument("--interval", default="4h")
    s.add_argument("--style", choices=["swing", "day"], default="swing")
    s.set_defaults(fn=cmd_screen)

    pa = sub.add_parser("paper")
    pa.add_argument("--symbol", default="BTC")
    pa.add_argument("--interval", default="1h")
    pa.add_argument("--kind", choices=["trend", "composite"], default="trend")
    pa.add_argument("--style", choices=["swing", "day"], default="swing")
    pa.add_argument("--once", action="store_true")
    pa.add_argument("--interval-seconds", type=int, default=3600, dest="interval_seconds")
    pa.set_defaults(fn=cmd_paper)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
