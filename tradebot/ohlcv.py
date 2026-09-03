"""OHLCV market data for any crypto, from public exchange APIs (no key needed).

Day/swing signals need candles *with volume* and at intraday resolution, which
daily-close feeds can't provide. This module pulls real OHLCV from public
exchange endpoints, with fallback across venues, and paginates for deep history.

Primary: Binance.US (deep history, standard kline format, paginates cleanly).
Fallback: Coinbase Exchange, then OKX. Binance.com is geo-blocked (HTTP 451) in
many regions, so it is not used.

Everything is stdlib-only (urllib). Symbols are given as a base asset ("BTC",
"ETH", "SOL", ...); the venue-specific pair is resolved per exchange.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol

_UA = "Mozilla/5.0 tradebot/0.1"

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

        # Fallbacks (single page each).
        for fetch in (self._coinbase, self._okx):
            bars = fetch(base, interval, limit, None)
            if bars:
                return bars[-limit:]
        raise RuntimeError(f"no OHLCV available for {base} at {interval} on any venue")

    def latest(self, base: str, interval: str = "1h") -> Bar:
        return self.history(base, interval, limit=2)[-1]


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
