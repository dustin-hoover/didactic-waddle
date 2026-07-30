"""Backtester.

Walks a price series day by day: apply the protocol rebase to holdings, ask the
strategy for a desired exposure, clamp it through risk, and simulate the fill.
Reports performance vs. a buy-and-hold baseline so we can judge honestly whether
the strategy adds anything.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import List

from .config import BotConfig
from .data import PriceBar
from .executor import PaperExecutor, Portfolio
from .risk import RiskManager, RiskState
from .strategy import RebaseMeanReversionStrategy


@dataclass
class BacktestResult:
    equity_curve: List[float] = field(default_factory=list)
    timestamps: List[str] = field(default_factory=list)
    strategy_return: float = 0.0
    buyhold_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    num_trades: int = 0
    halted: bool = False

    def summary(self) -> str:
        return (
            f"Strategy return : {self.strategy_return:+.1%}\n"
            f"Buy & hold      : {self.buyhold_return:+.1%}\n"
            f"Sharpe (daily)  : {self.sharpe:.2f}\n"
            f"Max drawdown    : {self.max_drawdown:.1%}\n"
            f"Trades          : {self.num_trades}\n"
            f"Circuit breaker : {'TRIPPED' if self.halted else 'ok'}"
        )


def _sharpe(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mu = statistics.fmean(returns)
    sd = statistics.pstdev(returns)
    if sd == 0:
        return 0.0
    return (mu / sd) * math.sqrt(365)  # annualised from daily.


def _max_drawdown(curve: List[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def run_backtest(bars: List[PriceBar], cfg: BotConfig) -> BacktestResult:
    strategy = RebaseMeanReversionStrategy(cfg.strategy, cfg.policy)
    risk = RiskManager(cfg.risk)
    execu = PaperExecutor(cfg.costs)

    pf = Portfolio(cash=cfg.starting_cash)
    rstate = RiskState(peak_equity=cfg.starting_cash)

    prices: List[float] = []
    result = BacktestResult()
    baseline_ampl = None  # buy-and-hold units bought on day 0.

    for bar in bars:
        prices.append(bar.price)

        # Buy-and-hold baseline: buy on first bar, then just ride rebases.
        if baseline_ampl is None:
            baseline_ampl = cfg.starting_cash / bar.price
        else:
            from .mechanics import compute_rebase
            r = compute_rebase(bar.price, 1.0, cfg.policy)
            baseline_ampl *= (1.0 + r.rebase_pct)

        # 1) Protocol rebase hits our holdings.
        execu.apply_rebase(pf, bar.price, cfg.policy)

        equity = pf.equity(bar.price)
        rstate = risk.update_and_check(rstate, equity, bar.price, pf.exposure(bar.price))

        # 2) Decide + act (unless halted or too little history).
        if not rstate.halted and len(prices) >= 2:
            sig = strategy.generate(prices)
            target = risk.clamp_exposure(sig.target_exposure)
            # Respect per-trade size cap by not jumping more than allowed.
            current = pf.exposure(bar.price)
            capped_delta = risk.limit_trade_size(target - current)
            target = current + capped_delta

            if risk.stop_triggered(rstate, bar.price):
                target = 0.0  # hard exit.

            fill = execu.rebalance_to(pf, target, bar.price, bar.timestamp)
            if fill is not None and fill.side == "buy":
                rstate.entry_price = bar.price
            if pf.ampl <= 1e-9:
                rstate.entry_price = None

        result.equity_curve.append(pf.equity(bar.price))
        result.timestamps.append(bar.timestamp)

    daily_returns = [
        result.equity_curve[i] / result.equity_curve[i - 1] - 1.0
        for i in range(1, len(result.equity_curve))
        if result.equity_curve[i - 1] > 0
    ]
    final_equity = result.equity_curve[-1] if result.equity_curve else cfg.starting_cash
    baseline_equity = (baseline_ampl or 0.0) * bars[-1].price if bars else cfg.starting_cash

    result.strategy_return = final_equity / cfg.starting_cash - 1.0
    result.buyhold_return = baseline_equity / cfg.starting_cash - 1.0
    result.sharpe = _sharpe(daily_returns)
    result.max_drawdown = _max_drawdown(result.equity_curve)
    result.num_trades = len(pf.fills)
    result.halted = rstate.halted
    return result
