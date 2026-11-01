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

    def worse_of(self, realized: dict) -> "CostModel":
        """Return a CostModel that takes the WORSE (higher) of modelled vs realized
        cost for each parameter (Phase 0.5). A backtest must never assume execution
        cheaper than reality; `realized` is a dict with fee_frac / slippage_frac
        (e.g. from tradebot.fills.realized_costs or docs/cost_model.json)."""
        rf = float(realized.get("fee_frac", 0.0) or 0.0)
        rs = float(realized.get("slippage_frac", 0.0) or 0.0)
        return CostModel(fee_frac=max(self.fee_frac, rf),
                         slippage_frac=max(self.slippage_frac, rs))

    @classmethod
    def from_report(cls, path: str = "docs/cost_model.json",
                    base: "Optional[CostModel]" = None) -> "CostModel":
        """Load effective (worse-of) costs from a cost report, falling back to the
        modelled defaults when the report is missing or unreadable. This is how the
        backtester reads its cost parameters from reconciled real fills."""
        import json as _json
        b = base or cls()
        try:
            with open(path) as fh:
                rep = _json.load(fh)
        except (FileNotFoundError, ValueError, OSError):
            return b
        realized = rep.get("realized", {}) if isinstance(rep, dict) else {}
        return b.worse_of(realized)


@dataclass
class StrategyConfig:
    kind: str = "trend"                 # "trend" (robust default) or "composite" (experimental)
    style: str = "swing"                # "swing" or "day"
    aggressiveness: float = 1.2         # score -> extra exposure above the floor
    entry_threshold: float = 0.03       # composite score above this = bullish regime -> hold
    min_long_exposure: float = 0.6      # exposure floor when bullish (keep beta, don't be timid)
    rebalance_band: float = 0.12        # skip rebalances smaller than this (cut fee churn)
    weights: Optional[Dict[str, float]] = None  # override preset weights
    # EXPERIMENTAL on-chain flow confirmation (paper only, OFF by default). On a
    # clean 60-day/one-regime sample the trend+accumulation overlay robustly lifted
    # Sharpe and ~halved max drawdown across EMA spans (scripts/trend_flow_test.py)
    # — a DE-RISKING filter, not a return booster (it gives up some upside and
    # trades less), and NOT out-of-sample validated across a down market. When on,
    # the live engine only holds a trend-long if the on-chain tape confirms.
    flow_confirm: bool = False
    flow_mode: str = "accum"            # "accum": require net buying; "distexit": flat only on strong distribution
    flow_dist_thr: float = 0.15         # distexit: stand aside when tape score < -this
    flow_blocks: int = 900             # tape lookback per decision (~3h)


@dataclass
class BotConfig:
    mode: str = "paper"
    symbol: str = "BTC"
    interval: str = "4h"                # candle size ("1h","4h","1d",...)
    starting_cash: float = 10_000.0
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostModel = field(default_factory=CostModel)
    protection: ProtectionConfig = field(default_factory=ProtectionConfig)
    state_path: str = "data/tradebot_state.json"
