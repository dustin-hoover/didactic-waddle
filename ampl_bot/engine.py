"""Live-ish paper trading engine: one tick at a time.

`step()` is called with the latest price. It applies the rebase, asks the
strategy for exposure, runs risk, and simulates a fill — persisting state so the
process can restart without losing the portfolio. The scheduling (once a day,
around the rebase window, etc.) is left to a caller/cron so this stays testable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from .config import BotConfig
from .executor import PaperExecutor, Portfolio, load_portfolio, save_portfolio
from .mechanics import market_zone
from .risk import RiskManager, RiskState
from .strategy import RebaseMeanReversionStrategy


@dataclass
class TickReport:
    timestamp: str
    price: float
    zone: str
    equity: float
    exposure: float
    action: str
    halted: bool


class TradingEngine:
    def __init__(self, cfg: BotConfig):
        if cfg.mode != "paper":
            raise ValueError(
                f"mode={cfg.mode!r} is not supported. Only 'paper' ships enabled; "
                "a live executor must be added deliberately and audited."
            )
        self.cfg = cfg
        self.strategy = RebaseMeanReversionStrategy(cfg.strategy, cfg.policy)
        self.risk = RiskManager(cfg.risk)
        self.execu = PaperExecutor(cfg.costs)
        self.prices: List[float] = []

        if os.path.exists(cfg.state_path):
            self.pf = load_portfolio(cfg.state_path)
        else:
            self.pf = Portfolio(cash=cfg.starting_cash)
        self.rstate = RiskState(peak_equity=max(self.pf.cash, cfg.starting_cash))

    def step(self, timestamp: str, price: float) -> TickReport:
        self.prices.append(price)
        self.execu.apply_rebase(self.pf, price, self.cfg.policy)

        equity = self.pf.equity(price)
        self.rstate = self.risk.update_and_check(self.rstate, equity, price, self.pf.exposure(price))

        action = "hold"
        if not self.rstate.halted and len(self.prices) >= 2:
            sig = self.strategy.generate(self.prices)
            target = self.risk.clamp_exposure(sig.target_exposure)
            current = self.pf.exposure(price)
            target = current + self.risk.limit_trade_size(target - current)
            if self.risk.stop_triggered(self.rstate, price):
                target = 0.0
                action = "stop-loss exit"
            fill = self.execu.rebalance_to(self.pf, target, price, timestamp)
            if fill is not None:
                action = f"{fill.side} {fill.ampl:.2f} AMPL @ {fill.price:.4f}"
                if fill.side == "buy":
                    self.rstate.entry_price = price
            if self.pf.ampl <= 1e-9:
                self.rstate.entry_price = None
        elif self.rstate.halted:
            action = "halted (drawdown circuit breaker)"

        save_portfolio(self.pf, self.cfg.state_path)
        return TickReport(
            timestamp=timestamp,
            price=price,
            zone=market_zone(price, self.cfg.policy),
            equity=self.pf.equity(price),
            exposure=self.pf.exposure(price),
            action=action,
            halted=self.rstate.halted,
        )
