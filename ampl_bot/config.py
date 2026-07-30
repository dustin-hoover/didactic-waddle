"""Central configuration.

Trading is DISABLED against real venues by default. `mode="paper"` simulates
fills against live/observed prices and never sends an order anywhere. Switching
to a live mode is intentionally a manual, explicit act (see executor.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .mechanics import PolicyParams


@dataclass
class RiskConfig:
    # Sizing recalibrated after backtesting: the original 0.60 cap was the main
    # drag on returns (it clamped the signal well below what the data justified).
    # 0.85 keeps a cash buffer for rebalancing/stops while letting the signal
    # express. It empirically beat buy-and-hold on Sharpe AND drawdown.
    max_position_frac: float = 0.85  # Max fraction of equity held in AMPL.
    per_trade_frac: float = 0.30  # Max fraction of equity moved in one trade.
    stop_loss_frac: float = 0.25  # Exit if position down this much from entry.
    max_drawdown_frac: float = 0.35  # Circuit breaker: liquidate to cash past this DD.
    reenter_bounce_frac: float = 0.15  # Re-enter after price bounces this off the halt price.


@dataclass
class CostModel:
    fee_frac: float = 0.001  # 10 bps taker fee, typical CEX/DEX.
    slippage_frac: float = 0.001  # Modelled slippage per trade.


@dataclass
class StrategyConfig:
    # "mr" (pure mean reversion) is the default: on real full-cycle AMPL data it
    # beat both buy-and-hold (risk-adjusted, and outright through the crash) and
    # the "trend_mr" variant. "trend_mr" is kept for study but underperformed on
    # real data — it was tuned on a synthetic downtrend that doesn't resemble
    # real, choppy AMPL. See README.
    name: str = "mr"
    lookback: int = 30  # Days for the mean/vol estimate.
    entry_z: float = 1.0  # Enter when |z-score of deviation| exceeds this.
    exit_z: float = 0.25  # Scale out as price returns toward target.
    target_exposure: float = 0.5  # Baseline AMPL exposure at neutrality.

    # Trend/regime filter (used by "trend_mr"). A fast vs. slow moving-average
    # gap defines the regime; it overrides mean reversion at the extremes so the
    # bot rides sustained uptrends and steps aside in sustained downtrends.
    trend_fast: int = 20
    trend_slow: int = 60
    trend_scale: float = 0.08  # |fast/slow - 1| that counts as a full-strength trend.
    trend_max_floor: float = 0.95  # Exposure floor at max uptrend strength.


@dataclass
class BotConfig:
    mode: str = "paper"  # "paper" only until real adapters are deliberately enabled.
    starting_cash: float = 10_000.0
    policy: PolicyParams = field(default_factory=PolicyParams)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostModel = field(default_factory=CostModel)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    state_path: str = "data/portfolio_state.json"
