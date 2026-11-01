"""Point-in-time, survivorship-free datastore (Phase 1.1).

The single most common way a crypto backtest lies to you:
  1. SURVIVORSHIP — you test on the coins that exist *today*, silently dropping the
     ones that died. Winners-only history inflates every result.
  2. LOOK-AHEAD — you use a datum (a fundamental, a revision, a close) at a bar before
     it was actually knowable. Tiny leaks produce spectacular fake edges.

This store refuses both by construction, using only the Python stdlib (CSV on disk,
append-only), so it runs anywhere this project runs:

  * Every symbol carries a LISTING and optional DELISTING date. `universe_asof(d)`
    reconstructs membership *as of d* — a coin delisted in 2023 is still in the 2021
    universe. Dead coins are first-class.
  * Every feature value is stored with the timestamp it would ACTUALLY have been known
    (`known_ts`), which may lag the period it describes. `features_asof(..., asof)`
    returns only values known by `asof`. Nothing is forward-filled past its known time.

The leakage canary (`aligned_feature`, with a `lag_bars` shift) exists so a test can
prove that shifting features by even one bar changes results — if it ever doesn't, the
pipeline has baked in look-ahead and the number is not to be trusted.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


def _d(x: str) -> str:
    """Normalize a date-ish string to YYYY-MM-DD (lexicographically sortable)."""
    return (x or "")[:10]


@dataclass
class Listing:
    symbol: str
    listing_date: str                    # YYYY-MM-DD, first day the asset traded
    delisting_date: Optional[str] = None  # YYYY-MM-DD, last day (None = still live)

    def alive_on(self, date: str) -> bool:
        d = _d(date)
        if d < _d(self.listing_date):
            return False
        return self.delisting_date is None or d <= _d(self.delisting_date)


@dataclass
class BarRow:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class DataStore:
    """CSV-backed, append-only. Layout under `root`:
        listings.csv                         symbol,listing_date,delisting_date
        bars/<SYMBOL>__<interval>.csv        date,open,high,low,close,volume
        features/<SYMBOL>__<name>.csv        value_date,known_ts,value
    """

    def __init__(self, root: str):
        self.root = root
        os.makedirs(os.path.join(root, "bars"), exist_ok=True)
        os.makedirs(os.path.join(root, "features"), exist_ok=True)

    # ---- listings / universe --------------------------------------------------
    @property
    def _listings_path(self) -> str:
        return os.path.join(self.root, "listings.csv")

    def record_listing(self, symbol: str, listing_date: str,
                       delisting_date: Optional[str] = None) -> None:
        """Upsert a listing (latest write for a symbol wins on read)."""
        new = not os.path.exists(self._listings_path)
        with open(self._listings_path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["symbol", "listing_date", "delisting_date"])
            w.writerow([symbol.upper(), _d(listing_date), _d(delisting_date) if delisting_date else ""])

    def listings(self) -> Dict[str, Listing]:
        out: Dict[str, Listing] = {}
        try:
            with open(self._listings_path, newline="") as fh:
                for r in csv.DictReader(fh):
                    sym = (r.get("symbol") or "").upper()
                    if not sym:
                        continue
                    out[sym] = Listing(sym, _d(r.get("listing_date", "")),
                                       _d(r["delisting_date"]) if r.get("delisting_date") else None)
        except FileNotFoundError:
            pass
        return out

    def universe_asof(self, date: str) -> List[str]:
        """Symbols that were tradeable ON `date` — including coins since delisted.
        Survivorship-free: membership is reconstructed as of the date, not today."""
        return sorted(s for s, lst in self.listings().items() if lst.alive_on(date))

    # ---- bars -----------------------------------------------------------------
    def _bars_path(self, symbol: str, interval: str) -> str:
        return os.path.join(self.root, "bars", f"{symbol.upper()}__{interval}.csv")

    def append_bars(self, symbol: str, interval: str, bars: Sequence) -> None:
        """Append bars. Each item is a BarRow or a (date,o,h,l,c,v) sequence/dict."""
        path = self._bars_path(symbol, interval)
        new = not os.path.exists(path)
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "open", "high", "low", "close", "volume"])
            for b in bars:
                if isinstance(b, BarRow):
                    row = [b.date, b.open, b.high, b.low, b.close, b.volume]
                elif isinstance(b, dict):
                    row = [_d(b["date"]), b["open"], b["high"], b["low"], b["close"], b.get("volume", 0)]
                else:
                    row = [_d(b[0]), b[1], b[2], b[3], b[4], b[5] if len(b) > 5 else 0]
                w.writerow(row)

    def bars(self, symbol: str, interval: str) -> List[BarRow]:
        path = self._bars_path(symbol, interval)
        out: List[BarRow] = []
        try:
            with open(path, newline="") as fh:
                for r in csv.DictReader(fh):
                    out.append(BarRow(_d(r["date"]), float(r["open"]), float(r["high"]),
                                      float(r["low"]), float(r["close"]), float(r["volume"])))
        except FileNotFoundError:
            return []
        out.sort(key=lambda b: b.date)
        return out

    # ---- features (point-in-time) ---------------------------------------------
    def _feat_path(self, symbol: str, name: str) -> str:
        return os.path.join(self.root, "features", f"{symbol.upper()}__{name}.csv")

    def append_feature(self, symbol: str, name: str, value: float,
                       value_date: str, known_ts: Optional[str] = None) -> None:
        """Record a feature value for `value_date`, KNOWN at `known_ts` (defaults to the
        value_date itself — i.e. same-day knowable, like a price). A lagged fundamental
        passes a later known_ts so it never leaks into earlier bars."""
        kt = _d(known_ts) if known_ts else _d(value_date)
        if kt < _d(value_date):
            raise ValueError("known_ts cannot precede value_date (that would be look-ahead)")
        path = self._feat_path(symbol, name)
        new = not os.path.exists(path)
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["value_date", "known_ts", "value"])
            w.writerow([_d(value_date), kt, value])

    def features_asof(self, symbol: str, name: str, asof: str) -> List[tuple]:
        """All (value_date, value) for this feature that were KNOWN by `asof`, sorted by
        value_date. Values whose known_ts is after `asof` are withheld — no look-ahead."""
        path = self._feat_path(symbol, name)
        asof_d = _d(asof)
        rows: List[tuple] = []
        try:
            with open(path, newline="") as fh:
                for r in csv.DictReader(fh):
                    if _d(r["known_ts"]) <= asof_d:
                        rows.append((_d(r["value_date"]), float(r["value"])))
        except FileNotFoundError:
            return []
        rows.sort(key=lambda t: t[0])
        return rows

    def latest_feature(self, symbol: str, name: str, asof: str) -> Optional[float]:
        """The most recent feature value KNOWN by `asof` (point-in-time read)."""
        rows = self.features_asof(symbol, name, asof)
        return rows[-1][1] if rows else None

    def aligned_feature(self, symbol: str, name: str, interval: str,
                        lag_bars: int = 0) -> List[Optional[float]]:
        """Feature aligned to each bar date, as known at that bar (point-in-time),
        optionally shifted by `lag_bars` bars.

        `lag_bars=0` uses the value knowable at each bar. A POSITIVE lag uses an EARLIER
        bar's value at each date (a legitimate extra delay). A NEGATIVE lag would pull a
        FUTURE value into the present — that is look-ahead, and the leakage-canary test
        asserts that any nonzero shift changes the series (so a leak can't hide)."""
        bars = self.bars(symbol, interval)
        base = [self.latest_feature(symbol, name, b.date) for b in bars]
        if lag_bars == 0:
            return base
        out: List[Optional[float]] = []
        for i in range(len(base)):
            j = i - lag_bars
            out.append(base[j] if 0 <= j < len(base) else None)
        return out
