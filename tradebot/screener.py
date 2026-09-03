"""Signal screener: rank a universe of coins by their current signals.

This is where the full "critical signals" panel earns its keep even though the
robust trading default is the simple trend filter: it surfaces, for many coins
at once, the trend regime, the composite conviction score, and the key
indicator readings — so you can spot what is setting up. It ranks, it does not
auto-trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import indicators as ind
from .ohlcv import ExchangeFeed
from .signals import CompositeStrategy, TrendFilterStrategy, _last

DEFAULT_UNIVERSE = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "DOGE", "LTC"]


@dataclass
class ScreenRow:
    symbol: str
    price: float
    trend_up: bool
    score: float          # composite conviction, [-1,1]
    rsi: Optional[float]
    atr_pct: Optional[float]
    reason: str
    error: Optional[str] = None


def screen(universe: List[str], interval: str = "4h", style: str = "swing",
           limit: int = 400, feed: Optional[ExchangeFeed] = None) -> List[ScreenRow]:
    feed = feed or ExchangeFeed()
    comp = CompositeStrategy(style)
    trend = TrendFilterStrategy(style)
    rows: List[ScreenRow] = []
    for sym in universe:
        try:
            bars = feed.history(sym, interval, limit)
            csig = comp.generate(bars)
            tsig = trend.generate(bars)
            close = [b.close for b in bars]
            rows.append(ScreenRow(
                symbol=sym,
                price=bars[-1].close,
                trend_up=tsig.target_exposure > 0,
                score=csig.score,
                rsi=_last(ind.rsi(close, 14)),
                atr_pct=csig.atr_pct,
                reason=csig.reason,
            ))
        except Exception as e:  # noqa: BLE001 — one bad symbol shouldn't kill the screen
            rows.append(ScreenRow(sym, 0.0, False, 0.0, None, None, "", error=str(e)[:80]))
    # Rank: trend-up first, then by composite conviction.
    rows.sort(key=lambda r: (r.trend_up, r.score), reverse=True)
    return rows
