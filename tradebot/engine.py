"""Live paper-trading engine: one candle at a time, real signals, simulated fills.

Paper-only by default (mirrors the original project's stance). State persists so
the process can restart. Scheduling (poll each candle close) is left to a caller.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from .config import BotConfig
from .ohlcv import Bar
from .portfolio import PaperExecutor, Portfolio, load_portfolio, save_portfolio
from .risk import RiskManager, RiskState
from .signals import build_strategy


@dataclass
class TickReport:
    ts: int
    price: float
    equity: float
    exposure: float
    action: str
    halted: bool
    reason: str


class TradingEngine:
    def __init__(self, cfg: BotConfig):
        if cfg.mode != "paper":
            raise ValueError(f"mode={cfg.mode!r} unsupported; only 'paper' ships enabled.")
        self.cfg = cfg
        self.strategy = build_strategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk)
        self.execu = PaperExecutor(cfg.costs)
        if os.path.exists(cfg.state_path):
            self.pf = load_portfolio(cfg.state_path)
        else:
            self.pf = Portfolio(cash=cfg.starting_cash)
        self.rstate = RiskState(peak_equity=max(self.pf.cash, cfg.starting_cash))

    def step(self, bars: List[Bar]) -> TickReport:
        bar = bars[-1]
        price = bar.close
        self.rstate = self.risk.update_and_check(self.rstate, self.pf.equity(price), price)

        action = "hold"
        sig = self.strategy.generate(bars)
        if self.rstate.halted:
            self.execu.rebalance_to(self.pf, 0.0, price, bar.ts)
            self.rstate.entry_price = self.rstate.stop_price = None
            action = "HALT -> cash (drawdown breaker)"
        else:
            target = self.risk.clamp_exposure(sig.target_exposure)
            # Optional on-chain regime gate: trim exposure when the market is
            # frothy/risk-off (extreme greed, gas spikes). Context, not a signal.
            if self.cfg.onchain_gate and target > 0:
                try:
                    from .onchain import fetch as _fetch_oc
                    target *= _fetch_oc().exposure_scale()
                except Exception:  # noqa: BLE001 — never let context break trading
                    pass
            if self.risk.stop_triggered(self.rstate, bar.low) and self.pf.units > 0:
                self.execu.rebalance_to(self.pf, 0.0, price, bar.ts)
                self.rstate.entry_price = self.rstate.stop_price = None
                action = "stop-loss -> cash"
                target = 0.0
            current = self.pf.exposure(price)
            if not (target > 0 and abs(target - current) < self.cfg.strategy.rebalance_band):
                target = current + self.risk.limit_trade_size(target - current)
                fill = self.execu.rebalance_to(self.pf, target, price, bar.ts)
                if fill is not None:
                    action = f"{fill.side} {fill.units:.4f} @ {fill.price:.4f}"
                    if fill.side == "buy" and self.rstate.entry_price is None:
                        self.risk.set_stop(self.rstate, price, sig.atr_pct)
            if self.pf.units <= 1e-12:
                self.rstate.entry_price = self.rstate.stop_price = None

        save_portfolio(self.pf, self.cfg.state_path)
        return TickReport(bar.ts, price, self.pf.equity(price), self.pf.exposure(price),
                          action, self.rstate.halted, sig.reason)
