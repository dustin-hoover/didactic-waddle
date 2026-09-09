"""OHLCV market data for any crypto, from public exchange APIs (no key needed).

Day/swing signals need candles *with volume* and at intraday resolution, which
daily-close feeds can't provide. This module pulls real OHLCV from public
exchange endpoints, with fallback across venues, and paginates for deep history.

Primary: Binance.US (deep history, standard kline format, paginates cleanly).
Fallback: Coinbase Exchange, then OKX, then CoinGecko. Binance.com is geo-blocked
(HTTP 451) in many regions, so it is not used. CoinGecko widens coverage to
thousands of coins (including ones not on the exchanges above) and is a safety
net if an exchange is down; set COINGECKO_API_KEY for higher limits / more
history (a free demo key works).

Everything is stdlib-only (urllib). Symbols are given as a base asset ("BTC",
"ETH", "SOL", ...); the venue-specific pair is resolved per exchange.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol

_UA = "Mozilla/5.0 tradebot/0.1"

# CoinGecko symbol -> coin id (curated for the common universe; others resolved
# live via /search). Kept small and explicit to avoid ambiguous symbol matches.
_CG_BASE = "https://api.coingecko.com/api/v3"
_CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "XRP": "ripple",
    "ADA": "cardano", "LINK": "chainlink", "LTC": "litecoin", "SOL": "solana",
    "AVAX": "avalanche-2", "DOGE": "dogecoin", "AMPL": "ampleforth", "SPOT": "spot",
    "DOT": "polkadot", "MATIC": "matic-network", "UNI": "uniswap", "ATOM": "cosmos",
    "TRX": "tron", "BCH": "bitcoin-cash", "NEAR": "near", "APT": "aptos",
    "ARB": "arbitrum", "OP": "optimism", "SUI": "sui", "TIA": "celestia",
}
_cg_id_cache: Dict[str, Optional[str]] = {}


def _cg_get(path: str, params: dict):
    q = dict(params)
    key = os.environ.get("COINGECKO_API_KEY", "").strip()
    if key:
        q["x_cg_demo_api_key"] = key
    url = _CG_BASE + path + "?" + "&".join(f"{k}={v}" for k, v in q.items())
    return _http_json(url)


def cg_resolve_id(base: str) -> Optional[str]:
    """Symbol -> CoinGecko coin id (curated map, then a live /search fallback)."""
    b = base.upper()
    if b in _CG_IDS:
        return _CG_IDS[b]
    if b in _cg_id_cache:
        return _cg_id_cache[b]
    cid = None
    try:
        for c in _cg_get("/search", {"query": base}).get("coins", []):
            if c.get("symbol", "").upper() == b:
                cid = c["id"]
                break
    except Exception:  # noqa: BLE001
        cid = None
    _cg_id_cache[b] = cid
    return cid


def coingecko_markets(symbols: List[str]) -> Dict[str, dict]:
    """Rich market context for a set of symbols in ONE call: price, market cap,
    rank, 24h volume and change. Useful for the screener/dashboard. {} on failure.
    """
    ids = [cg_resolve_id(s) for s in symbols]
    idmap = {cg_resolve_id(s): s.upper() for s in symbols if cg_resolve_id(s)}
    ids = [i for i in ids if i]
    if not ids:
        return {}
    try:
        rows = _cg_get("/coins/markets", {"vs_currency": "usd", "ids": ",".join(ids), "per_page": len(ids)})
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, dict] = {}
    for r in rows:
        sym = idmap.get(r.get("id"), (r.get("symbol") or "").upper())
        out[sym] = {"price": r.get("current_price"), "market_cap": r.get("market_cap"),
                    "rank": r.get("market_cap_rank"), "volume_24h": r.get("total_volume"),
                    "change_24h": r.get("price_change_percentage_24h")}
    return out

# Interval -> milliseconds, and the label each venue uses.
_INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "12h": 43_200_000, "1d": 86_400_000,
}


@dataclass(frozen=True)
class Bar:
    ts: int          # epoch ms (open time)
    open: float
    high: float
    low: float
    close: float
    volume: float    # base-asset volume

    @property
    def date(self) -> str:
        return datetime.fromtimestamp(self.ts / 1000, tz=timezone.utc).isoformat()


class OHLCVProvider(Protocol):
    def history(self, base: str, interval: str, limit: int) -> List[Bar]: ...


def _http_json(url: str, tries: int = 4, timeout: int = 30):
    last: Optional[Exception] = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"request failed after {tries} tries: {url} :: {last}")


class ExchangeFeed:
    """Real OHLCV with multi-venue fallback and pagination for deep history."""

    def __init__(self, quote: str = "USDT"):
        self.quote = quote

    # -- per-venue fetchers (one page) ------------------------------------
    def _binance_us(self, base: str, interval: str, limit: int, start_ms: Optional[int]) -> List[Bar]:
        for pair in (f"{base}{self.quote}", f"{base}USD"):
            url = f"https://api.binance.us/api/v3/klines?symbol={pair}&interval={interval}&limit={min(limit,1000)}"
            if start_ms is not None:
                url += f"&startTime={start_ms}"
            try:
                rows = _http_json(url)
            except Exception:
                continue
            if isinstance(rows, list) and rows:
                return [Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]
        return []

    def _coinbase(self, base: str, interval: str, limit: int, start_ms: Optional[int]) -> List[Bar]:
        gran = _INTERVAL_MS.get(interval, 3_600_000) // 1000
        url = f"https://api.exchange.coinbase.com/products/{base}-USD/candles?granularity={gran}"
        try:
            rows = _http_json(url)
        except Exception:
            return []
        # Coinbase: [time, low, high, open, close, volume], newest first.
        bars = [Bar(int(r[0]) * 1000, float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])) for r in rows]
        return sorted(bars, key=lambda b: b.ts)

    def _okx(self, base: str, interval: str, limit: int, start_ms: Optional[int]) -> List[Bar]:
        bar = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1H",
               "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H", "1d": "1D"}.get(interval, "1H")
        url = f"https://www.okx.com/api/v5/market/candles?instId={base}-{self.quote}&bar={bar}&limit={min(limit,300)}"
        try:
            data = _http_json(url).get("data", [])
        except Exception:
            return []
        bars = [Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in data]
        return sorted(bars, key=lambda b: b.ts)

    def _coingecko(self, base: str, interval: str, limit: int, start_ms: Optional[int]) -> List[Bar]:
        """CoinGecko fallback — widens coverage to thousands of coins. Daily uses
        market_chart (close + real volume, high=low=close); intraday uses the OHLC
        endpoint (true OHLC, volume 0). Honors COINGECKO_API_KEY if set.
        """
        cid = cg_resolve_id(base)
        if not cid:
            return []
        if interval == "1d":
            try:
                mc = _cg_get(f"/coins/{cid}/market_chart", {"vs_currency": "usd", "days": 365})
            except Exception:  # noqa: BLE001
                return []
            day_ms = 86_400_000
            vols = {int(t // day_ms): float(v) for t, v in mc.get("total_volumes", [])}
            by_day = {}
            for t, p in mc.get("prices", []):
                by_day[int(t // day_ms)] = float(p)  # keep last obs per day
            bars = [Bar(d * day_ms, p, p, p, p, vols.get(d, 0.0)) for d, p in sorted(by_day.items())]
            return bars[-limit:]
        # intraday: OHLC endpoint (keyless supports up to ~30 days at 4h/30m)
        days = min(30, max(1, (limit * _INTERVAL_MS[interval]) // 86_400_000 + 1))
        try:
            rows = _cg_get(f"/coins/{cid}/ohlc", {"vs_currency": "usd", "days": days})
        except Exception:  # noqa: BLE001
            return []
        bars = [Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), 0.0) for r in rows]
        return bars[-limit:]

    # -- public API -------------------------------------------------------
    def history(self, base: str, interval: str = "4h", limit: int = 1000) -> List[Bar]:
        """Return up to ``limit`` most-recent bars, paginating Binance.US as needed."""
        base = base.upper()
        if interval not in _INTERVAL_MS:
            raise ValueError(f"unsupported interval {interval!r}; pick from {list(_INTERVAL_MS)}")

        # Try Binance.US with pagination for deep history.
        step = _INTERVAL_MS[interval]
        merged: Dict[int, Bar] = {}
        need = limit
        # Walk backwards from now in 1000-bar pages.
        end = int(time.time() * 1000)
        start = end - need * step
        cursor = start
        pages = 0
        while len(merged) < need and pages < 60:
            page = self._binance_us(base, interval, 1000, cursor)
            if not page:
                break
            for b in page:
                merged[b.ts] = b
            last = page[-1].ts
            if last <= cursor:
                break
            cursor = last + step
            pages += 1
            if cursor > end:
                break
            time.sleep(0.15)

        bars = sorted(merged.values(), key=lambda b: b.ts)
        if bars:
            return bars[-limit:]

        # Fallbacks (single page each). CoinGecko last: widest coverage, tightest limits.
        for fetch in (self._coinbase, self._okx, self._coingecko):
            bars = fetch(base, interval, limit, None)
            if bars:
                return bars[-limit:]
        raise RuntimeError(f"no OHLCV available for {base} at {interval} on any venue")

    def latest(self, base: str, interval: str = "1h") -> Bar:
        return self.history(base, interval, limit=2)[-1]


def get_feed(source: Optional[str] = None):
    """Return the data feed. source (or TB_DATA_SOURCE env):
      * "onchain" -> OnChainFeed: Chainlink oracles + DefiLlama, no CEX (daily only).
      * "cex" / "auto" / None -> ExchangeFeed: Binance.US/Coinbase/OKX + CoinGecko.
    """
    src = (source or os.environ.get("TB_DATA_SOURCE", "auto")).lower()
    if src == "onchain":
        from .onchain_feed import OnChainFeed
        return OnChainFeed()
    return ExchangeFeed()


# ---- CSV + synthetic providers (offline) ------------------------------------
def write_csv(bars: List[Bar], path: str) -> None:
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.ts, b.open, b.high, b.low, b.close, b.volume])


def read_csv(path: str) -> List[Bar]:
    import csv
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append(Bar(int(row["ts"]), float(row["open"]), float(row["high"]),
                           float(row["low"]), float(row["close"]), float(row["volume"])))
    return out
