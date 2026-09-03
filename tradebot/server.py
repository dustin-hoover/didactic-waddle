"""Zero-dependency dashboard for tradebot (stdlib only).

    python -m tradebot.server            # http://127.0.0.1:8000

Endpoints (read-only; no endpoint can move real funds):
  GET /                 -> dashboard HTML
  GET /api/screen       -> screener across the default universe
  GET /api/coin         -> one coin's signal panel + backtest + price/equity
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .backtest import run_backtest
from .config import BotConfig, StrategyConfig
from .ohlcv import ExchangeFeed
from .screener import DEFAULT_UNIVERSE, screen
from .signals import CompositeStrategy, TrendFilterStrategy

STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "tradebot.html")
_FEED = ExchangeFeed()


def _screen_payload(q):
    interval = q.get("interval", ["4h"])[0]
    style = q.get("style", ["swing"])[0]
    rows = screen(DEFAULT_UNIVERSE, interval=interval, style=style, feed=_FEED)
    return {"interval": interval, "style": style, "rows": [
        {"symbol": r.symbol, "price": r.price, "trend_up": r.trend_up, "score": r.score,
         "rsi": r.rsi, "atr_pct": r.atr_pct, "reason": r.reason, "error": r.error} for r in rows]}


def _coin_payload(q):
    symbol = q.get("symbol", ["BTC"])[0].upper()
    interval = q.get("interval", ["4h"])[0]
    style = q.get("style", ["swing"])[0]
    kind = q.get("kind", ["trend"])[0]
    bars = _FEED.history(symbol, interval, 1000)
    comp = CompositeStrategy(style).generate(bars)
    trend = TrendFilterStrategy(style).generate(bars)
    cfg = BotConfig(symbol=symbol, interval=interval,
                    strategy=StrategyConfig(kind=kind, style=style))
    bt = run_backtest(bars, cfg)
    step = max(1, len(bars) // 300)
    return {
        "symbol": symbol, "interval": interval, "style": style, "kind": kind,
        "price": bars[-1].close,
        "trend_up": trend.target_exposure > 0,
        "score": comp.score,
        "votes": comp.votes,
        "reason": comp.reason,
        "backtest": {"strategy_return": bt.strategy_return, "buyhold_return": bt.buyhold_return,
                     "sharpe": bt.sharpe, "max_drawdown": bt.max_drawdown,
                     "num_trades": bt.num_trades, "exposure_avg": bt.exposure_avg},
        "times": [b.date[:10] for b in bars][::step],
        "prices": [b.close for b in bars][::step],
        "equity": bt.equity_curve[::step],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                with open(STATIC, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif u.path == "/api/screen":
                self._send(200, json.dumps(_screen_payload(q)).encode(), "application/json")
            elif u.path == "/api/coin":
                self._send(200, json.dumps(_coin_payload(q)).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:  # noqa: BLE001
            self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")

    def log_message(self, *a):
        pass


def serve(host="127.0.0.1", port=8000):
    print(f"tradebot dashboard on http://{host}:{port}  (paper/read-only)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    serve(a.host, a.port)
