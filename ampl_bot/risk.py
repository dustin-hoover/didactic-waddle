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
    halt_price: float | None = None  # Price at which the breaker tripped.


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
        """Evaluate the drawdown circuit breaker.

        When ``halted`` is True the caller must move to CASH (target exposure 0)
        — halting must *reduce risk*, not merely stop rebalancing a position that
        then rides the crash down. We re-enter only after price bounces
        ``reenter_bounce_frac`` off the halt price, i.e. once the decline that
        tripped the breaker has clearly reversed.
        """
        if equity > state.peak_equity:
            state.peak_equity = equity
        drawdown = 0.0 if state.peak_equity == 0 else 1.0 - equity / state.peak_equity

        if not state.halted:
            if drawdown >= self.cfg.max_drawdown_frac:
                state.halted = True
                state.halt_price = price
        else:
            # Re-enter once price has recovered off the halt level.
            if state.halt_price and price >= state.halt_price * (1.0 + self.cfg.reenter_bounce_frac):
                state.halted = False
                state.halt_price = None
                state.peak_equity = equity  # reset the high-water mark on re-entry
        return state

    def stop_triggered(self, state: RiskState, price: float) -> bool:
        """True if the open position has fallen past the stop-loss from entry."""
        if state.entry_price is None or state.entry_price <= 0:
            return False
        loss = 1.0 - price / state.entry_price
        return loss >= self.cfg.stop_loss_frac
