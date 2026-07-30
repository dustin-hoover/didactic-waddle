"""Risk management: caps, stop-loss, and a drawdown circuit breaker.

The strategy proposes a desired exposure; risk decides how much of that is
actually allowed. This layer is what protects accrued capital when the
mean-reversion thesis breaks.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import RiskConfig


@dataclass
class RiskState:
    peak_equity: float
    entry_price: float | None = None  # Volume-weighted entry of current position.
    halted: bool = False


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def clamp_exposure(self, desired: float) -> float:
        """Never exceed the maximum position fraction."""
        return max(0.0, min(self.cfg.max_position_frac, desired))

    def limit_trade_size(self, delta_frac: float) -> float:
        """Cap the size of a single rebalancing trade (as a fraction of equity)."""
        sign = 1.0 if delta_frac >= 0 else -1.0
        return sign * min(abs(delta_frac), self.cfg.per_trade_frac)

    def update_and_check(self, state: RiskState, equity: float, price: float, exposure: float) -> RiskState:
        """Update peak equity and evaluate the drawdown circuit breaker."""
        if equity > state.peak_equity:
            state.peak_equity = equity
        drawdown = 0.0 if state.peak_equity == 0 else 1.0 - equity / state.peak_equity
        if drawdown >= self.cfg.max_drawdown_frac:
            state.halted = True
        return state

    def stop_triggered(self, state: RiskState, price: float) -> bool:
        """True if the open position has fallen past the stop-loss from entry."""
        if state.entry_price is None or state.entry_price <= 0:
            return False
        loss = 1.0 - price / state.entry_price
        return loss >= self.cfg.stop_loss_frac
