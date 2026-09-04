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
from tradebot.ohlcv import ExchangeFeed  # noqa: E402
from tradebot.onchain import fetch as fetch_onchain  # noqa: E402
from tradebot.screener import DEFAULT_UNIVERSE  # noqa: E402
from tradebot.signals import CompositeStrategy, TrendFilterStrategy, _last  # noqa: E402
from tradebot import indicators as ind  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
INTERVAL = os.environ.get("TB_INTERVAL", "4h")
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
    feed = ExchangeFeed()
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

    data = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "interval": INTERVAL, "style": STYLE, "onchain": onchain,
            "rows": rows, "featured": featured}
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
