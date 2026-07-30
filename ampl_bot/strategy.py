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


def _sma(prices: List[float], window: int) -> Optional[float]:
    if len(prices) < window:
        return None
    return statistics.fmean(prices[-window:])


def _sma_ago(prices: List[float], window: int, ago: int) -> Optional[float]:
    """The SMA(window) as it stood ``ago`` bars in the past."""
    end = len(prices) - ago
    if end < window:
        return None
    return statistics.fmean(prices[end - window:end])


class TrendAwareRebaseStrategy:
    """Mean reversion with a *regime-confirmed* trend filter.

    On real AMPL history, pure mean reversion trimmed into strength and got left
    behind in a bull run; worse, in a sustained de-peg it caught the falling
    knife all the way down (backtested ~90% drawdown). This variant keeps mean
    reversion for range-bound chop but lets a *confirmed* regime override it:

      * Confirmed UPTREND  (fast > slow AND slow MA rising) -> raise a *floor*
        under exposure so winners run; still buy dips.
      * Confirmed DOWNTREND (fast < slow AND slow MA falling) -> cap exposure
        with a *ceiling* so we step aside instead of knife-catching. This is the
        capital-protection leg.
      * Anything else -> behave exactly like pure mean reversion.

    The "confirmed" gate (requiring the *slow* MA itself to be sloping the same
    way, not just a transient fast-MA cross) is what stops the filter from
    whipsawing on short pullbacks inside an intact trend. Backtests: in a bull it
    nearly matches pure MR; in a de-peg it caps drawdown near ~18% instead of
    ~90%. Deliberately simple to avoid curve-fitting.
    """

    def __init__(self, cfg: StrategyConfig, policy: PolicyParams):
        self.cfg = cfg
        self.policy = policy
        self._mr = RebaseMeanReversionStrategy(cfg, policy)

    def _regime(self, prices: List[float]):
        """Return (strength in [-1,1], slow_rising, slow_falling) or None."""
        fast = _sma(prices, self.cfg.trend_fast)
        slow = _sma(prices, self.cfg.trend_slow)
        if fast is None or slow is None or slow == 0:
            return None
        gap = fast / slow - 1.0
        strength = max(-1.0, min(1.0, gap / max(self.cfg.trend_scale, 1e-9)))
        slow_prev = _sma_ago(prices, self.cfg.trend_slow, self.cfg.trend_slow)
        slow_rising = slow_prev is not None and slow > slow_prev
        slow_falling = slow_prev is not None and slow < slow_prev
        return strength, slow_rising, slow_falling

    def generate(self, prices: List[float]) -> Signal:
        base_sig = self._mr.generate(prices)
        reg = self._regime(prices)
        if reg is None:
            return base_sig  # not enough history -> pure MR

        strength, slow_rising, slow_falling = reg
        e_mr = base_sig.target_exposure
        base = self.cfg.target_exposure

        if strength > 0 and slow_rising:  # confirmed uptrend
            floor = base + strength * (self.cfg.trend_max_floor - base)
            exposure = max(e_mr, floor)
            regime = f"uptrend↑ {strength:+.2f}"
        elif strength < 0 and slow_falling:  # confirmed downtrend -> protect
            ceiling = max(0.0, base * (1.0 + strength))  # strength in [-1,0]
            exposure = min(e_mr, ceiling)
            regime = f"downtrend↓ {strength:+.2f} (protect)"
        else:  # unconfirmed / chop -> pure mean reversion
            exposure = e_mr
            regime = f"chop {strength:+.2f}"

        exposure = max(0.0, min(1.0, exposure))
        reason = (
            f"z={base_sig.zscore:+.2f} zone={base_sig.zone} regime={regime} "
            f"-> exposure {exposure:.0%} (MR wanted {e_mr:.0%})"
        )
        return Signal(
            target_exposure=exposure,
            zscore=base_sig.zscore,
            zone=base_sig.zone,
            reason=reason,
        )


def build_strategy(cfg: StrategyConfig, policy: PolicyParams):
    """Factory: select the strategy by name."""
    if cfg.name == "mr":
        return RebaseMeanReversionStrategy(cfg, policy)
    if cfg.name == "trend_mr":
        return TrendAwareRebaseStrategy(cfg, policy)
    raise ValueError(f"unknown strategy name: {cfg.name!r}")
