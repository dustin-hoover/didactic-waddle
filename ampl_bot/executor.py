"""Portfolio + paper-trading executor.

The Portfolio holds USD (stable) and AMPL *units*. AMPL units are rebased daily
per the protocol. The PaperExecutor turns a desired target exposure into a
simulated fill with fees and slippage, and persists state to disk.

There is deliberately no live-order path here. A real executor would implement
`submit_order` against a specific venue; that is an explicit, audited addition,
not something that ships enabled.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import List

from .config import BotConfig, CostModel
from .mechanics import PolicyParams, RebaseResult, compute_rebase


@dataclass
class Fill:
    timestamp: str
    side: str  # "buy" or "sell"
    ampl: float  # AMPL units transacted.
    price: float  # Effective price after slippage.
    fee: float  # USD fee paid.


@dataclass
class Portfolio:
    cash: float  # USD / stablecoin.
    ampl: float = 0.0  # AMPL units.
    fills: List[Fill] = field(default_factory=list)

    def equity(self, price: float) -> float:
        return self.cash + self.ampl * price

    def exposure(self, price: float) -> float:
        eq = self.equity(price)
        return 0.0 if eq == 0 else (self.ampl * price) / eq


class PaperExecutor:
    def __init__(self, costs: CostModel):
        self.costs = costs

    def apply_rebase(self, pf: Portfolio, price: float, policy: PolicyParams) -> RebaseResult:
        # total_supply is irrelevant to a single holder's *fraction*; we only
        # need the rebase percentage, so pass a nominal supply of 1.0.
        result = compute_rebase(price, total_supply=1.0, params=policy)
        pf.ampl *= (1.0 + result.rebase_pct)
        return result

    def rebalance_to(self, pf: Portfolio, target_exposure: float, price: float, timestamp: str) -> Fill | None:
        """Move toward the target exposure with one simulated fill."""
        eq = pf.equity(price)
        if eq <= 0:
            return None
        current = pf.exposure(price)
        delta_frac = target_exposure - current
        if abs(delta_frac) < 1e-4:
            return None

        usd_to_move = delta_frac * eq
        if usd_to_move > 0:  # buy AMPL
            eff_price = price * (1.0 + self.costs.slippage_frac)
            usd_to_move = min(usd_to_move, pf.cash)
            if usd_to_move <= 0:
                return None
            fee = usd_to_move * self.costs.fee_frac
            ampl_bought = (usd_to_move - fee) / eff_price
            pf.cash -= usd_to_move
            pf.ampl += ampl_bought
            fill = Fill(timestamp, "buy", ampl_bought, eff_price, fee)
        else:  # sell AMPL
            eff_price = price * (1.0 - self.costs.slippage_frac)
            ampl_to_sell = min(-usd_to_move / price, pf.ampl)
            if ampl_to_sell <= 0:
                return None
            proceeds = ampl_to_sell * eff_price
            fee = proceeds * self.costs.fee_frac
            pf.cash += proceeds - fee
            pf.ampl -= ampl_to_sell
            fill = Fill(timestamp, "sell", ampl_to_sell, eff_price, fee)

        pf.fills.append(fill)
        return fill


def save_portfolio(pf: Portfolio, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({"cash": pf.cash, "ampl": pf.ampl, "fills": [asdict(x) for x in pf.fills]}, f, indent=2)


def load_portfolio(path: str) -> Portfolio:
    with open(path) as f:
        d = json.load(f)
    pf = Portfolio(cash=d["cash"], ampl=d.get("ampl", 0.0))
    pf.fills = [Fill(**x) for x in d.get("fills", [])]
    return pf
