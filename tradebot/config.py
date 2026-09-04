"""Configuration for the generic crypto day/swing bot.

Paper trading only by default; a live executor is a deliberate, audited add-on
(same stance as the original project). Long/flat spot only — no shorting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .protection import ProtectionConfig


@dataclass
class RiskConfig:
    max_position_frac: float = 1.0      # max fraction of equity in the asset (spot long)
    per_trade_frac: float = 0.50        # max fraction of equity moved per rebalance
    atr_stop_mult: float = 3.0          # hard stop at entry - mult*ATR
    max_drawdown_frac: float = 0.30     # circuit breaker: liquidate past this DD
    reenter_bounce_frac: float = 0.12   # re-enter after price bounces this off halt price


@dataclass
class CostModel:
    fee_frac: float = 0.001             # 10 bps taker
    slippage_frac: float = 0.0007       # modelled slippage per trade


@dataclass
class StrategyConfig:
    kind: str = "trend"                 # "trend" (robust default) or "composite" (experimental)
    style: str = "swing"                # "swing" or "day"
    aggressiveness: float = 1.2         # score -> extra exposure above the floor
    entry_threshold: float = 0.03       # composite score above this = bullish regime -> hold
    min_long_exposure: float = 0.6      # exposure floor when bullish (keep beta, don't be timid)
    rebalance_band: float = 0.12        # skip rebalances smaller than this (cut fee churn)
    weights: Optional[Dict[str, float]] = None  # override preset weights


@dataclass
class BotConfig:
    mode: str = "paper"
    symbol: str = "BTC"
    interval: str = "4h"                # candle size ("1h","4h","1d",...)
    onchain_gate: bool = False          # scale exposure by the live on-chain risk regime
    starting_cash: float = 10_000.0
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostModel = field(default_factory=CostModel)
    protection: ProtectionConfig = field(default_factory=ProtectionConfig)
    state_path: str = "data/tradebot_state.json"
