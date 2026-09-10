"""Build the static dashboard site for GitHub Pages, and fire phone alerts.

Runs on a schedule inside GitHub Actions (the "computer" in a phone-only setup):
  1. pulls live signals across a coin universe + on-chain market context,
  2. backtests each coin and a featured chart,
  3. pushes BUY/EXIT alerts to your phone via ntfy.sh (topic from NTFY_TOPIC),
  4. writes docs/ (index.html explainer, app.html dashboard, data.json) which
     GitHub Pages serves.

State (last long/flat per coin) persists in docs/alert_state.json, committed by
the workflow, so alerts fire only on genuine changes.
"""

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tradebot.alerts import push_ntfy  # noqa: E402
from tradebot.backtest import run_backtest  # noqa: E402
from tradebot.config import BotConfig, StrategyConfig  # noqa: E402
from tradebot.ohlcv import get_feed  # noqa: E402
from tradebot.onchain import fetch as fetch_onchain  # noqa: E402
from tradebot.screener import DEFAULT_UNIVERSE  # noqa: E402
from tradebot.signals import CompositeStrategy, TrendFilterStrategy, _last  # noqa: E402
from tradebot import indicators as ind  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
# On-chain data is daily-only, so force a 1d screener interval in on-chain mode.
ONCHAIN = os.environ.get("TB_DATA_SOURCE", "auto").lower() == "onchain"
INTERVAL = "1d" if ONCHAIN else os.environ.get("TB_INTERVAL", "4h")
STYLE = os.environ.get("TB_STYLE", "swing")
NTFY = os.environ.get("NTFY_TOPIC", "").strip()


def load_state():
    p = os.path.join(DOCS, "alert_state.json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def build():
    os.makedirs(DOCS, exist_ok=True)
    feed = get_feed()
    state = load_state()
    rows = []
    alerts = []

    for sym in DEFAULT_UNIVERSE:
        try:
            bars = feed.history(sym, INTERVAL, 1000)
            trend = TrendFilterStrategy(STYLE).generate(bars)
            comp = CompositeStrategy(STYLE).generate(bars)
            bt = run_backtest(bars, BotConfig(symbol=sym, interval=INTERVAL,
                                              strategy=StrategyConfig(kind="trend", style=STYLE)))
            now_long = trend.target_exposure > 0
            rows.append({
                "symbol": sym, "price": bars[-1].close, "trend_up": now_long,
                "score": round(comp.score, 3), "rsi": _last(ind.rsi([b.close for b in bars], 14)),
                "atr_pct": comp.atr_pct, "reason": comp.reason,
                "ret": bt.strategy_return, "bh": bt.buyhold_return, "dd": bt.max_drawdown,
                "reserve": bt.reserve_final, "reserve_frac": bt.reserve_frac,
            })
            was = state.get(sym)
            if was is not None and was != now_long:
                action = "BUY" if now_long else "EXIT"
                msg = (f"{sym} {INTERVAL}: trend flipped {'UP → BUY' if now_long else 'DOWN → EXIT to cash'} "
                       f"@ ${bars[-1].close:,.2f}")
                alerts.append((action, sym, msg))
            state[sym] = now_long
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": sym, "error": str(e)[:80]})

    rows.sort(key=lambda r: (r.get("trend_up", False), r.get("score", -9)), reverse=True)

    # on-chain context
    try:
        m = fetch_onchain()
        onchain = {"fear_greed": m.fear_greed, "fear_greed_label": m.fear_greed_label,
                   "defi_tvl_usd": m.defi_tvl_usd, "stablecoin_mcap_usd": m.stablecoin_mcap_usd,
                   "eth_gas_gwei": m.eth_gas_gwei, "risk_regime": m.risk_regime,
                   "exposure_scale": m.exposure_scale()}
    except Exception as e:  # noqa: BLE001
        onchain = {"error": str(e)[:80]}

    # featured chart: BTC daily
    featured = {}
    try:
        fb = feed.history("BTC", "1d", 1000)
        fr = run_backtest(fb, BotConfig(symbol="BTC", interval="1d",
                                        strategy=StrategyConfig(kind="trend")))
        start = fb[0].close
        bh = [10000 * (b.close / start) for b in fb]
        step = max(1, len(fb) // 160)
        featured = {"symbol": "BTC", "interval": "1d",
                    "dates": [b.date[:10] for b in fb][::step],
                    "strategy": [round(x, 1) for x in fr.equity_curve][::step],
                    "buyhold": [round(x, 1) for x in bh][::step],
                    "stats": {"strat_ret": fr.strategy_return, "bh_ret": fr.buyhold_return,
                              "strat_dd": fr.max_drawdown, "sharpe": fr.sharpe,
                              "reserve": fr.reserve_final, "reserve_frac": fr.reserve_frac,
                              "skims": fr.num_skims}}
    except Exception as e:  # noqa: BLE001
        featured = {"error": str(e)[:80]}

    # LIVE PAPER PORTFOLIO — advance the real machine (trade + skim + flywheel).
    # State persists in docs/paper_state.json (committed) across scheduled runs.
    paper = {}
    try:
        from tradebot.engine import TradingEngine
        pcfg = BotConfig(mode="paper", symbol="BTC", interval="1d", starting_cash=1000.0,
                         strategy=StrategyConfig(kind="trend", style="swing"),
                         state_path=os.path.join(DOCS, "paper_state.json"))
        eng = TradingEngine(pcfg)
        pbars = feed.history("BTC", "1d", 400)
        reps = eng.advance(pbars)
        paper = eng.snapshot(pbars[-1].close)
        paper["new_steps"] = len(reps)
        paper["last_action"] = reps[-1].action if reps else "no new candle"
    except Exception as e:  # noqa: BLE001
        paper = {"error": str(e)[:80]}

    # ON-CHAIN TAPE — strongest block-order flow of the day. Gated behind TB_TAPE=1
    # because reading a day of Uniswap V3 swaps across the universe is heavy on
    # public RPC; keep it off for fast/reliable default runs. Set your own
    # ETH_RPC_URL and TB_TAPE=1 to enable. It ranks/reads flow; it does NOT trade.
    tape = {}
    if os.environ.get("TB_TAPE", "").strip() in ("1", "true", "on"):
        try:
            from tradebot.tape import rank_universe
            blk = int(os.environ.get("TB_TAPE_BLOCKS", "3600"))  # ~12h default
            tape = {"blocks": blk, "rows": [
                {"symbol": t.symbol, "score": round(t.score, 3), "bias": t.bias,
                 "net_usd": round(t.net_usd), "buy_usd": round(t.buy_usd),
                 "sell_usd": round(t.sell_usd), "whale_share": round(t.whale_share, 3),
                 "n_prints": t.n_prints, "price": t.price,
                 "largest": ({"side": t.largest.side, "usd": round(t.largest.usd_size),
                              "price": t.largest.price} if t.largest else None),
                 "error": t.error}
                for t in rank_universe(blocks=blk, top=10)]}
        except Exception as e:  # noqa: BLE001
            tape = {"error": str(e)[:80]}
        # Accumulate the forward-validation sample: log today's flow, then measure
        # whether past flow predicted realized returns. Grows over weeks.
        if tape.get("rows"):
            try:
                from tradebot import tape_journal as tj
                jpath = os.path.join(DOCS, "tape_journal.json")
                journal = tj.record(tj.load(jpath), tape["rows"])
                tj.save(jpath, journal)
                tape["edge"] = tj.analyze(journal)
            except Exception as e:  # noqa: BLE001
                tape["edge"] = {"error": str(e)[:80]}

    data = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "interval": INTERVAL, "style": STYLE, "onchain": onchain,
            "rows": rows, "featured": featured, "paper": paper, "tape": tape}
    json.dump(data, open(os.path.join(DOCS, "data.json"), "w"), indent=1)
    json.dump(state, open(os.path.join(DOCS, "alert_state.json"), "w"))

    # copy explainer -> docs/index.html (rewrite the in-app app link to a relative one)
    landing = open(os.path.join(ROOT, "static", "landing.html")).read().replace('href="/app"', 'href="app.html"')
    open(os.path.join(DOCS, "index.html"), "w").write(landing)
    # copy the static dashboard template -> docs/app.html
    app = open(os.path.join(ROOT, "static", "app_static.html")).read()
    open(os.path.join(DOCS, "app.html"), "w").write(app)
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")

    # push phone alerts
    pushed = 0
    if NTFY:
        for action, sym, msg in alerts:
            if push_ntfy(NTFY, f"{action} {sym}", msg, priority="high"):
                pushed += 1

    print(f"built docs/ · {len([r for r in rows if 'error' not in r])} coins · "
          f"{len(alerts)} flips · {pushed} pushed · regime {onchain.get('risk_regime')}")


if __name__ == "__main__":
    build()
