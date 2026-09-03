"""Portfolio + paper-trading executor (asset-agnostic, long/flat spot).

Holds USD (stable) and units of one base asset. No live-order path here; a real
executor against a venue is a deliberate, audited addition.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .config import CostModel


@dataclass
class Fill:
    ts: int
    side: str
    units: float
    price: float
    fee: float


@dataclass
class Portfolio:
    cash: float
    units: float = 0.0
    fills: List[Fill] = field(default_factory=list)

    def equity(self, price: float) -> float:
        return self.cash + self.units * price

    def exposure(self, price: float) -> float:
        eq = self.equity(price)
        return 0.0 if eq == 0 else (self.units * price) / eq


class PaperExecutor:
    def __init__(self, costs: CostModel):
        self.costs = costs

    def rebalance_to(self, pf: Portfolio, target_exposure: float, price: float, ts: int) -> Optional[Fill]:
        eq = pf.equity(price)
        if eq <= 0:
            return None
        delta_frac = target_exposure - pf.exposure(price)
        if abs(delta_frac) < 1e-4:
            return None
        usd = delta_frac * eq
        if usd > 0:  # buy
            eff = price * (1.0 + self.costs.slippage_frac)
            usd = min(usd, pf.cash)
            if usd <= 0:
                return None
            fee = usd * self.costs.fee_frac
            units = (usd - fee) / eff
            pf.cash -= usd
            pf.units += units
            fill = Fill(ts, "buy", units, eff, fee)
        else:  # sell
            eff = price * (1.0 - self.costs.slippage_frac)
            units = min(-usd / price, pf.units)
            if units <= 0:
                return None
            proceeds = units * eff
            fee = proceeds * self.costs.fee_frac
            pf.cash += proceeds - fee
            pf.units -= units
            fill = Fill(ts, "sell", units, eff, fee)
        pf.fills.append(fill)
        return fill


def save_portfolio(pf: Portfolio, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({"cash": pf.cash, "units": pf.units, "fills": [asdict(x) for x in pf.fills]}, f, indent=2)


def load_portfolio(path: str) -> Portfolio:
    with open(path) as f:
        d = json.load(f)
    pf = Portfolio(cash=d["cash"], units=d.get("units", 0.0))
    pf.fills = [Fill(**x) for x in d.get("fills", [])]
    return pf
