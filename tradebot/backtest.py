"""OHLCV-driven backtester for the composite-signal strategy.

Walks candles: compute the composite signal from history-to-date, apply risk
(ATR stop, per-trade cap, drawdown circuit breaker), simulate the fill. Reports
performance vs. buy-and-hold. Intrabar stop/liquidation is modelled at the bar's
low (conservative) rather than assuming a clean close-to-close exit.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import List

from .config import BotConfig
from .ohlcv import Bar
from .portfolio import PaperExecutor, Portfolio
from .protection import ProfitProtector
from .risk import RiskManager, RiskState
from .signals import build_strategy


@dataclass
class BacktestResult:
    equity_curve: List[float] = field(default_factory=list)
    timestamps: List[int] = field(default_factory=list)
    strategy_return: float = 0.0
    buyhold_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    num_trades: int = 0
    win_rate: float = 0.0
    exposure_avg: float = 0.0
    bars_per_year: float = 365.0
    reserve_final: float = 0.0        # stable value banked (protected)
    reserve_frac: float = 0.0         # reserve as fraction of final total equity
    reserve_yield: float = 0.0        # yield earned on the reserve
    num_skims: int = 0
    num_reinvests: int = 0            # flywheel firings (reserve -> trading)
    total_reinvested: float = 0.0     # cumulative reinvested back into trading
    trading_base_final: float = 0.0   # seed + everything the flywheel injected

    def summary(self) -> str:
        s = (
            f"Strategy return : {self.strategy_return:+.1%}\n"
            f"Buy & hold      : {self.buyhold_return:+.1%}\n"
            f"Sharpe (annual) : {self.sharpe:.2f}\n"
            f"Max drawdown    : {self.max_drawdown:.1%}\n"
            f"Trades          : {self.num_trades}\n"
            f"Avg exposure    : {self.exposure_avg:.0%}"
        )
        if self.reserve_final > 0:
            s += (f"\nBanked reserve  : ${self.reserve_final:,.0f} "
                  f"({self.reserve_frac:.0%} of equity, +${self.reserve_yield:,.0f} yield, "
                  f"{self.num_skims} skims)")
        if self.num_reinvests > 0:
            s += (f"\nFlywheel        : {self.num_reinvests} reinvestments, "
                  f"${self.total_reinvested:,.0f} recycled into trading "
                  f"(base ${self.trading_base_final:,.0f})")
        return s


_BARS_PER_YEAR = {
    "1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520, "1h": 8760,
    "2h": 4380, "4h": 2190, "6h": 1460, "12h": 730, "1d": 365,
}


def _sharpe(returns: List[float], periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0
    mu = statistics.fmean(returns)
    sd = statistics.pstdev(returns)
    return 0.0 if sd == 0 else (mu / sd) * math.sqrt(periods_per_year)


def _max_dd(curve: List[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def run_backtest(bars: List[Bar], cfg: BotConfig) -> BacktestResult:
    strat = build_strategy(cfg.strategy)
    risk = RiskManager(cfg.risk)
    execu = PaperExecutor(cfg.costs)
    pf = Portfolio(cash=cfg.starting_cash)
    rstate = RiskState(peak_equity=cfg.starting_cash)

    result = BacktestResult()
    result.bars_per_year = _BARS_PER_YEAR.get(cfg.interval, 365.0)
    exposures: List[float] = []

    protector = ProfitProtector(cfg.protection, execu, result.bars_per_year, seed=cfg.starting_cash)

    for i, bar in enumerate(bars):
        price = bar.close
        rstate = risk.update_and_check(rstate, pf.equity(price), price)

        if rstate.halted:
            execu.rebalance_to(pf, 0.0, price, bar.ts)
            rstate.entry_price = rstate.stop_price = None
        else:
            sig = strat.generate(bars[: i + 1])
            target = risk.clamp_exposure(sig.target_exposure)

            # Intrabar ATR stop: if this bar's low pierced the stop, exit first.
            if risk.stop_triggered(rstate, bar.low) and pf.units > 0:
                execu.rebalance_to(pf, 0.0, min(price, rstate.stop_price or price), bar.ts)
                rstate.entry_price = rstate.stop_price = None
                target = 0.0

            current = pf.exposure(price)
            # Deadband: skip tiny rebalances (fee churn), but always allow a full exit.
            in_band = target > 0 and abs(target - current) < cfg.strategy.rebalance_band
            if not in_band:
                target = current + risk.limit_trade_size(target - current)
                fill = execu.rebalance_to(pf, target, price, bar.ts)
                if fill is not None and fill.side == "buy" and rstate.entry_price is None:
                    risk.set_stop(rstate, price, sig.atr_pct)
                if pf.units <= 1e-12:
                    rstate.entry_price = rstate.stop_price = None

        # Capital-preservation layer: skim profits into the protected reserve.
        protector.step(pf, price, bar.ts)

        result.equity_curve.append(protector.total_equity(pf, price))
        result.timestamps.append(bar.ts)
        exposures.append(pf.exposure(price))

    daily = [result.equity_curve[i] / result.equity_curve[i - 1] - 1.0
             for i in range(1, len(result.equity_curve)) if result.equity_curve[i - 1] > 0]
    final = result.equity_curve[-1] if result.equity_curve else cfg.starting_cash
    result.strategy_return = final / cfg.starting_cash - 1.0
    result.buyhold_return = bars[-1].close / bars[0].close - 1.0 if bars else 0.0
    result.sharpe = _sharpe(daily, result.bars_per_year)
    result.max_drawdown = _max_dd(result.equity_curve)
    result.num_trades = len(pf.fills)
    result.exposure_avg = statistics.fmean(exposures) if exposures else 0.0
    result.reserve_final = protector.state.reserve
    result.reserve_frac = protector.state.reserve / final if final > 0 else 0.0
    result.reserve_yield = protector.state.yield_earned
    result.num_skims = protector.state.skims
    result.num_reinvests = protector.state.reinvests
    result.total_reinvested = protector.state.total_reinvested
    result.trading_base_final = protector.state.trading_base
    return result
