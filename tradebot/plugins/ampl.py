"""AMPL (Ampleforth) plugin — the rebase mechanics as a tradebot specialization.

The generic framework treats every coin as OHLCV. AMPL is special: its supply
rebases daily toward a CPI target, so price mean-reverts to that target and a
holder's *units* grow/shrink with the rebase. This plugin overlays that onto the
robust trend filter:

  * Trade AMPL with the normal TrendFilterStrategy, BUT
  * trim exposure when price is deep in the "expansion" zone (far above target),
    where forthcoming negative rebases erode unit count and price tends to revert
    down — the AMPL-specific edge.

The FULL rebase-aware backtester (which applies daily rebases to holdings and
compares to buy-and-hold across AMPL's real history) still lives in the original
`ampl_bot/` package; this plugin is the bridge into the generic engine.
"""

from __future__ import annotations

from typing import List

from ampl_bot.mechanics import PolicyParams, deviation, market_zone

from ..ohlcv import Bar
from ..signals import Signal, TrendFilterStrategy


class AmplTrendStrategy(TrendFilterStrategy):
    def __init__(self, style: str = "swing", policy: PolicyParams | None = None,
                 trim_start: float = 0.10):
        super().__init__(style)
        self.policy = policy or PolicyParams()
        self.trim_start = trim_start  # begin trimming once deviation exceeds this

    def generate(self, bars: List[Bar]) -> Signal:
        sig = super().generate(bars)
        price = bars[-1].close
        dev = deviation(price, self.policy)
        zone = market_zone(price, self.policy)
        # In expansion (price >> target), scale exposure down as deviation grows.
        if sig.target_exposure > 0 and dev > self.trim_start:
            trim = min(1.0, (dev - self.trim_start) / 0.25)  # full trim by +35% dev
            sig.target_exposure *= (1.0 - 0.7 * trim)
        sig.reason += f" | AMPL dev={dev:+.0%} zone={zone}"
        return sig
