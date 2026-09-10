"""tradebot CLI — backtest, screen, and paper-trade any crypto.

    python tb.py backtest --symbol BTC --interval 4h --style swing
    python tb.py backtest --symbol ETH --interval 1d --kind composite   # experimental
    python tb.py screen  --interval 4h --style swing
    python tb.py paper   --symbol BTC --interval 1h --once
    python tb.py safety  --symbol PEPE                 # rug-screen a token
    python tb.py safety  --gas                          # Ethereum gas oracle
    python tb.py tape                                   # rank on-chain block-order flow
    python tb.py tape    --symbol LINK                  # one symbol, detailed flow

Long/flat spot, paper only. Data comes from public exchange OHLCV (no key).
The safety screen reads free-tier Etherscan contract facts (ETHERSCAN_API_KEY).
"""

import argparse
import time

from tradebot.backtest import run_backtest
from tradebot.config import BotConfig, StrategyConfig
from tradebot.engine import TradingEngine
from tradebot.ohlcv import get_feed
from tradebot.onchain import fetch as fetch_onchain
from tradebot.onchain import wallet_balances
from tradebot.screener import DEFAULT_UNIVERSE, screen


def cmd_backtest(a):
    bars = get_feed().history(a.symbol, a.interval, a.limit)
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
                    strategy=StrategyConfig(kind=a.kind, style=a.style,
                                            flow_confirm=a.flow_confirm, flow_mode=a.flow_mode))
    engine = TradingEngine(cfg)
    feed = get_feed()
    print(f"Live PAPER [{a.kind}/{a.style}] on {a.symbol} {a.interval}. Ctrl-C to stop.\n")
    while True:
        try:
            bars = feed.history(a.symbol, a.interval, 400)
            rep = engine.step(bars)
            print(f"{rep.ts}  ${rep.price:,.4f}  trading ${rep.equity:,.2f}  "
                  f"reserve ${rep.reserve:,.2f}  total ${rep.total:,.2f}  "
                  f"expo {rep.exposure:>4.0%}  {rep.action}")
        except Exception as e:  # noqa: BLE001
            print(f"tick error: {e}")
        if a.once:
            break
        time.sleep(a.interval_seconds)


def cmd_alert(a):
    from tradebot.alerts import check_many
    syms = a.symbols.split(",") if a.symbols else DEFAULT_UNIVERSE
    alerts = check_many(syms, a.interval, a.style, ntfy_topic=a.ntfy)
    print(f"Alerts [{a.style} {a.interval}]" + (f" · pushing BUY/EXIT to ntfy.sh/{a.ntfy}" if a.ntfy else "") + "\n")
    for al in alerts:
        mark = {"BUY": "🟢", "EXIT": "🔴", "HOLD": "  ", "ERROR": "⚠️"}.get(al.action, "  ")
        print(f"{mark} {al.action:<5} {al.message}")


def cmd_onchain(a):
    m = fetch_onchain()
    b = lambda x: f"${x/1e9:,.1f}B" if x else "n/a"
    print("On-chain / market-structure context (live):\n")
    print(f"  Fear & Greed : {m.fear_greed} ({m.fear_greed_label})")
    print(f"  DeFi TVL     : {b(m.defi_tvl_usd)}")
    print(f"  Stablecoins  : {b(m.stablecoin_mcap_usd)}  (sideline dry powder)")
    print(f"  ETH gas      : {m.eth_gas_gwei:.1f} gwei" if m.eth_gas_gwei else "  ETH gas      : n/a")
    print(f"\n  RISK REGIME  : {m.risk_regime}  (suggested exposure ×{m.exposure_scale():.2f})")
    if m.notes:
        print("  notes:", m.notes)


def cmd_tape(a):
    from tradebot.tape import DEFAULT_WHALE_USD, rank_universe, read_tape
    whale = a.whale if a.whale else DEFAULT_WHALE_USD
    if a.symbol:
        s = read_tape(a.symbol, blocks=a.blocks, whale_usd=whale)
        if s.error:
            print(f"{s.symbol}: {s.error}")
            return
        print(f"On-chain tape — {s.symbol}  (~{a.blocks} blocks, whale ≥ ${whale:,.0f})\n")
        print(f"  prints        : {s.n_prints}")
        print(f"  buy / sell    : ${s.buy_usd:,.0f} / ${s.sell_usd:,.0f}")
        print(f"  net (CVD)     : ${s.net_usd:,.0f}")
        print(f"  whale share   : {s.whale_share:.0%}  (${s.whale_usd:,.0f})")
        print(f"  tape score    : {s.score:+.3f}  -> {s.bias}")
        if s.largest:
            print(f"  largest print : {s.largest.side} ${s.largest.usd_size:,.0f} @ ${s.largest.price:,.4f}")
        return
    syms = a.symbols.split(",") if a.symbols else None
    print(f"Strongest on-chain opportunities (~{a.blocks} blocks) — ranked by flow conviction\n")
    print(f"{'sym':<6}{'score':>8}{'bias':>15}{'net USD':>16}{'whale%':>8}{'prints':>8}")
    print("-" * 61)
    for r in rank_universe(syms, blocks=a.blocks, whale_usd=whale, top=a.top):
        if r.error:
            print(f"{r.symbol:<6} ERROR {r.error[:40]}")
            continue
        print(f"{r.symbol:<6}{r.score:>+8.3f}{r.bias:>15}{r.net_usd:>16,.0f}"
              f"{r.whale_share:>7.0%}{r.n_prints:>8}")


def cmd_safety(a):
    from tradebot.safety import check, gas_oracle, resolve
    if a.gas:
        g = gas_oracle()
        gw = lambda x: f"{x:.2f} gwei" if x is not None else "n/a"
        print("Ethereum gas (Etherscan gas oracle, RPC fallback):\n")
        print(f"  safe {gw(g['safe'])}   propose {gw(g['propose'])}   "
              f"fast {gw(g['fast'])}   base {gw(g['base'])}")
        return
    syms = a.symbols.split(",") if a.symbols else [a.symbol]
    print("Token safety / rug-screen (Etherscan free-tier contract facts):\n")
    for i, s in enumerate(syms):
        try:
            print(check(resolve(s)).summary())
        except Exception as e:  # noqa: BLE001
            print(f"{s}: error — {str(e)[:80]}")
        if i < len(syms) - 1:
            print()


def cmd_wallet(a):
    print(f"Read-only balances for {a.address} (no keys, public chain state):\n")
    for sym, amt in wallet_balances(a.address).items():
        if amt > 0:
            print(f"  {sym:<5} {amt:,.6f}")


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
    pa.add_argument("--flow-confirm", action="store_true", dest="flow_confirm",
                    help="EXPERIMENTAL: only hold trend-longs the on-chain tape confirms")
    pa.add_argument("--flow-mode", default="accum", choices=["accum", "distexit"], dest="flow_mode")
    pa.set_defaults(fn=cmd_paper)

    al = sub.add_parser("alert")
    al.add_argument("--symbols", default="", help="comma-separated; default is the 10-coin universe")
    al.add_argument("--interval", default="4h")
    al.add_argument("--style", choices=["swing", "day"], default="swing")
    al.add_argument("--ntfy", default="", help="ntfy.sh topic to push BUY/EXIT alerts to your phone")
    al.set_defaults(fn=cmd_alert)

    oc = sub.add_parser("onchain")
    oc.set_defaults(fn=cmd_onchain)

    tp = sub.add_parser("tape")
    tp.add_argument("--symbol", default="", help="one symbol for detail; omit to rank the universe")
    tp.add_argument("--symbols", default="", help="comma-separated universe to rank")
    tp.add_argument("--blocks", type=int, default=7200, help="lookback in blocks (~7200 = 1 day)")
    tp.add_argument("--whale", type=float, default=0.0, help="whale-size print threshold in USD")
    tp.add_argument("--top", type=int, default=10)
    tp.set_defaults(fn=cmd_tape)

    sf = sub.add_parser("safety")
    sf.add_argument("--symbol", default="PEPE", help="token symbol or 0x… address")
    sf.add_argument("--symbols", default="", help="comma-separated symbols/addresses")
    sf.add_argument("--gas", action="store_true", help="show the gas oracle instead")
    sf.set_defaults(fn=cmd_safety)

    wa = sub.add_parser("wallet")
    wa.add_argument("address")
    wa.set_defaults(fn=cmd_wallet)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
