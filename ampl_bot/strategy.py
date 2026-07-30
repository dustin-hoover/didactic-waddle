"""Rebase-aware mean-reversion strategy.

Thesis (honest version): AMPL's price tends to mean-revert toward its CPI
target because the supply policy pushes it there over time. So we hold *more*
AMPL exposure when price is stretched below target (contraction zone, reversion
up expected) and *less* when stretched above (expansion zone, reversion down
expected). We measure "stretched" with a rolling z-score of the deviation from
target, not an absolute rule, so the strategy adapts to changing volatility.

This is not a guaranteed edge. Mean reversion fails during regime breaks (e.g.
a sustained de-peg). Risk controls (risk.py) exist precisely because the thesis
can be wrong.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Optional

from .config import StrategyConfig
from .mechanics import PolicyParams, deviation, market_zone


@dataclass
class Signal:
    target_exposure: float  # Desired fraction of equity in AMPL, in [0, 1].
    zscore: float
    zone: str
    reason: str


class RebaseMeanReversionStrategy:
    def __init__(self, cfg: StrategyConfig, policy: PolicyParams):
        self.cfg = cfg
        self.policy = policy

    def _zscore(self, deviations: List[float]) -> float:
        if len(deviations) < 2:
            return 0.0
        window = deviations[-self.cfg.lookback:]
        if len(window) < 2:
            return 0.0
        mu = statistics.fmean(window)
        sd = statistics.pstdev(window)
        if sd == 0:
            return 0.0
        return (window[-1] - mu) / sd

    def generate(self, prices: List[float]) -> Signal:
        """Given the price history up to now, return a desired exposure."""
        price = prices[-1]
        devs = [deviation(p, self.policy) for p in prices]
        z = self._zscore(devs)
        zone = market_zone(price, self.policy)

        base = self.cfg.target_exposure
        # Negative z (below-target/contraction) => lean long. Positive => lean out.
        # Scale linearly with z beyond entry threshold, clamp to [0,1].
        tilt = 0.0
        if abs(z) >= self.cfg.exit_z:
            span = max(self.cfg.entry_z - self.cfg.exit_z, 1e-9)
            magnitude = min(1.0, (abs(z) - self.cfg.exit_z) / span)
            tilt = magnitude * 0.5  # up to +/-50% exposure swing
            tilt = -tilt if z > 0 else tilt

        target = max(0.0, min(1.0, base + tilt))
        reason = (
            f"z={z:+.2f} zone={zone} -> exposure {target:.0%} "
            f"(base {base:.0%}, tilt {tilt:+.0%})"
        )
        return Signal(target_exposure=target, zscore=z, zone=zone, reason=reason)
