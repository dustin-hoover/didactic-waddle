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
    max_position_frac: float = 0.60  # Max fraction of equity held in AMPL.
    per_trade_frac: float = 0.20  # Max fraction of equity moved in one trade.
    stop_loss_frac: float = 0.25  # Exit if position down this much from entry.
    max_drawdown_frac: float = 0.35  # Circuit breaker: halt trading past this DD.


@dataclass
class CostModel:
    fee_frac: float = 0.001  # 10 bps taker fee, typical CEX/DEX.
    slippage_frac: float = 0.001  # Modelled slippage per trade.


@dataclass
class StrategyConfig:
    lookback: int = 30  # Days for the mean/vol estimate.
    entry_z: float = 1.0  # Enter when |z-score of deviation| exceeds this.
    exit_z: float = 0.25  # Scale out as price returns toward target.
    target_exposure: float = 0.5  # Baseline AMPL exposure at neutrality.


@dataclass
class BotConfig:
    mode: str = "paper"  # "paper" only until real adapters are deliberately enabled.
    starting_cash: float = 10_000.0
    policy: PolicyParams = field(default_factory=PolicyParams)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostModel = field(default_factory=CostModel)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    state_path: str = "data/portfolio_state.json"
