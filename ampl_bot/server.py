"""Zero-dependency dashboard server (Python stdlib only).

Serves a small single-page dashboard and JSON APIs so it runs out of the box
with `python -m ampl_bot.server` — no pip install required. Endpoints:

  GET /                -> dashboard HTML (static/index.html)
  GET /api/state       -> current market zone, signal, and portfolio snapshot
  GET /api/backtest    -> backtest metrics + equity curve on the sample series

Everything is read-only from the browser's perspective; there is no endpoint
that can move real funds.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .backtest import run_backtest
from .config import BotConfig
from .data import CsvPriceProvider, SyntheticPriceProvider
from .mechanics import deviation, market_zone
from .strategy import RebaseMeanReversionStrategy

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
SAMPLE_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sample_ampl.csv")


def _load_bars():
    if os.path.exists(SAMPLE_CSV):
        return CsvPriceProvider(SAMPLE_CSV).history()
    return SyntheticPriceProvider().history()


def _state_payload(cfg: BotConfig) -> dict:
    bars = _load_bars()
    prices = [b.price for b in bars]
    strat = RebaseMeanReversionStrategy(cfg.strategy, cfg.policy)
    sig = strat.generate(prices)
    latest = bars[-1]
    return {
        "timestamp": latest.timestamp,
        "price": latest.price,
        "target": cfg.policy.target_price,
        "deviation": deviation(latest.price, cfg.policy),
        "zone": market_zone(latest.price, cfg.policy),
        "signal": {
            "target_exposure": sig.target_exposure,
            "zscore": sig.zscore,
            "reason": sig.reason,
        },
        "mode": cfg.mode,
    }


def _backtest_payload(cfg: BotConfig) -> dict:
    bars = _load_bars()
    res = run_backtest(bars, cfg)
    # Downsample the curve for the browser if long.
    step = max(1, len(res.equity_curve) // 300)
    return {
        "summary": res.summary(),
        "strategy_return": res.strategy_return,
        "buyhold_return": res.buyhold_return,
        "sharpe": res.sharpe,
        "max_drawdown": res.max_drawdown,
        "num_trades": res.num_trades,
        "halted": res.halted,
        "timestamps": res.timestamps[::step],
        "equity_curve": res.equity_curve[::step],
        "prices": [b.price for b in bars][::step],
    }


def _live_payload(cfg: BotConfig) -> dict:
    """Best-effort live on-chain spot. Never raises to the browser."""
    from .feeds import OnChainFeed
    from .mechanics import deviation, market_zone

    try:
        bar = OnChainFeed().latest()
        return {
            "ok": True,
            "source": "uniswap-v2 + chainlink (ethereum mainnet)",
            "timestamp": bar.timestamp,
            "price": bar.price,
            "deviation": deviation(bar.price, cfg.policy),
            "zone": market_zone(bar.price, cfg.policy),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    cfg = BotConfig()

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict) -> None:
        self._send(200, json.dumps(obj).encode(), "application/json")

    def do_GET(self):  # noqa: N802 (stdlib naming)
        path = urlparse(self.path).path
        try:
            if path == "/" or path == "/index.html":
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(_state_payload(self.cfg))
            elif path == "/api/backtest":
                self._json(_backtest_payload(self.cfg))
            elif path == "/api/live":
                self._json(_live_payload(self.cfg))
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:  # keep the dev server alive, report the error
            self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")

    def log_message(self, *args):  # quieter console
        pass


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AMPL bot dashboard on http://{host}:{port}  (paper/read-only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    serve(args.host, args.port)
