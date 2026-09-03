"""Risk management: ATR stop-loss, position caps, drawdown circuit breaker.

The circuit breaker LIQUIDATES to cash on a drawdown breach (it does not merely
stop trading — a lesson learned the hard way in the original project) and
re-enters only after price recovers off the halt level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import RiskConfig


@dataclass
class RiskState:
    peak_equity: float
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    halted: bool = False
    halt_price: Optional[float] = None


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def clamp_exposure(self, desired: float) -> float:
        return max(0.0, min(self.cfg.max_position_frac, desired))

    def limit_trade_size(self, delta_frac: float) -> float:
        sign = 1.0 if delta_frac >= 0 else -1.0
        return sign * min(abs(delta_frac), self.cfg.per_trade_frac)

    def set_stop(self, state: RiskState, entry_price: float, atr_pct: Optional[float]) -> None:
        state.entry_price = entry_price
        if atr_pct and atr_pct > 0:
            state.stop_price = entry_price * (1.0 - self.cfg.atr_stop_mult * atr_pct)
        else:
            state.stop_price = None

    def stop_triggered(self, state: RiskState, price: float) -> bool:
        return state.stop_price is not None and price <= state.stop_price

    def update_and_check(self, state: RiskState, equity: float, price: float) -> RiskState:
        if equity > state.peak_equity:
            state.peak_equity = equity
        dd = 0.0 if state.peak_equity == 0 else 1.0 - equity / state.peak_equity
        if not state.halted:
            if dd >= self.cfg.max_drawdown_frac:
                state.halted = True
                state.halt_price = price
        else:
            if state.halt_price and price >= state.halt_price * (1.0 + self.cfg.reenter_bounce_frac):
                state.halted = False
                state.halt_price = None
                state.peak_equity = equity
        return state
